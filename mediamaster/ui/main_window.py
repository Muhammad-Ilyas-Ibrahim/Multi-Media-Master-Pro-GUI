"""The main window: navigation sidebar, pages, status bar and drag-and-drop.

Layout
    sidebar    grouped navigation; collapses to an icon rail on narrow windows
    header     page title and a one-line description
    pages      one QScrollArea per page, so short windows scroll instead of
               squashing controls; form pages keep a comfortable max width
    log        optional FFmpeg output, toggled from the status bar
    status     current task, progress, and a shortcut to the output folder

Files can be dropped anywhere. A drop on a page's source field goes there;
a drop elsewhere goes to the current page if it can use it, otherwise to the
page that best fits the file (a video opens Compress Video, and so on).
"""

import html
import os
import subprocess
import tempfile
import time
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QStackedWidget, QComboBox, QButtonGroup, QProgressBar, QCheckBox,
    QPlainTextEdit, QMessageBox, QScrollArea, QApplication, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon

from ..core import config
from ..core import media
from ..core.worker import Worker
from . import dnd
from . import icons
from .theme import THEMES, build_qss
from .widgets import (
    SourceField, LevelSelector, panel, form, form_label,
    button, tool_button, hint, label, hbox, repolish, ElidedLabel
)
from .trim_studio import TrimStudio


VIDEO_FILTER = config.file_filter("Video files", config.VIDEO_EXTS)
IMAGE_FILTER = config.file_filter("Image files", config.IMAGE_EXTS)
AUDIO_FILTER = config.file_filter("Audio files", config.AUDIO_EXTS)
AUDIO_OR_VIDEO_FILTER = config.file_filter(
    "Audio and video files", config.AUDIO_EXTS + config.VIDEO_EXTS)

SIDEBAR_WIDE = 212
SIDEBAR_RAIL = 52
COLLAPSE_BELOW = 940          # window width (logical px) that collapses the sidebar
CONTENT_MAX_W = 760           # form pages don't stretch past this


class Page:
    """Book-keeping for one page: how it shows up and what drops it takes."""

    def __init__(self, key, section, title, icon_name, desc, widget,
                 source=None, batch=None, start=None, take=None, accepts=None):
        self.key = key
        self.section = section
        self.title = title
        self.icon = icon_name
        self.desc = desc
        self.widget = widget
        self.source = source            # SourceField, if the page has one
        self.batch = batch              # "whole folder" QCheckBox, if the page has one
        self.start = start              # slot that launches the page's task
        self._take = take
        self._accepts = accepts

    def accepts(self, paths):
        if self._accepts:
            return self._accepts(paths)
        if self.source is None:
            return False
        if self.source.usable_drop(paths):
            return True
        # Pages with a batch checkbox take a file or a folder and flip the box.
        if self.batch is not None:
            return any(dnd.kind_of(p) == 'dir' or dnd.kind_of(p) in self.source.kinds
                       or dnd.is_unknown_file(p) for p in paths)
        return False

    def take(self, paths):
        if self._take:
            return self._take(paths)
        if self.source is None:
            return False
        target = self.source.usable_drop(paths)
        if target is None and self.batch is not None:
            self.batch.setChecked(any(dnd.kind_of(p) == 'dir' for p in paths))
            target = self.source.usable_drop(paths)
        if target:
            self.source.setText(target)
            return True
        return False


class MainWindow(dnd.DropTarget, QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.theme = config.load_saved_theme()
        self.worker = None
        self.rec_process = None
        self._run_buttons = []
        self._last_output = ""
        self._collapsed = None
        self.setWindowTitle(f"{config.APP_NAME}")
        icon_path = os.path.join(config.resource_base(), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        icons.set_palette(THEMES[self.theme])
        self._build_ui()
        self._apply_theme()
        self._size_to_screen()
        self.init_drops()
        self._select(0)

    # ------------------------------------------------------- host interface #
    def register_run_button(self, btn):
        self._run_buttons.append(btn)

    def launch(self, task, params):
        self._launch(task, params)

    def is_busy(self):
        return self.worker is not None and self.worker.isRunning()

    # --------------------------------------------------------- construction #
    def _size_to_screen(self):
        """Open at a size that suits the screen and its scale factor."""
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        self.setMinimumSize(640, 480)
        if avail is None:
            self.resize(1200, 800)
            return
        w = min(1320, int(avail.width() * 0.86))
        h = min(880, int(avail.height() * 0.88))
        self.resize(max(640, w), max(480, h))
        self.move(avail.x() + (avail.width() - self.width()) // 2,
                  avail.y() + (avail.height() - self.height()) // 2)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.trim = TrimStudio(self)
        self.pages = self._build_pages()
        outer.addWidget(self._build_sidebar())

        column = QWidget()
        column.setObjectName("mainColumn")
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._build_header())
        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page.widget)
        col.addWidget(self.stack, 1)
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(4000)
        self.console.setFixedHeight(170)
        self.console.hide()
        col.addWidget(self.console)
        col.addWidget(self._build_status())
        outer.addWidget(column, 1)

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("sidebar")
        self.sidebar = bar
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(8, 14, 8, 10)
        lay.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 4, 0)
        brand.setSpacing(9)
        self.brand_icon = QLabel()
        icon_path = os.path.join(config.resource_base(), 'icon.ico')
        if os.path.exists(icon_path):
            self.brand_icon.setPixmap(QIcon(icon_path).pixmap(QSize(20, 20)))
        self.brand_icon.setFixedSize(20, 20)
        self.brand_text = QWidget()
        bt = QVBoxLayout(self.brand_text)
        bt.setContentsMargins(0, 0, 0, 0)
        bt.setSpacing(0)
        bt.addWidget(label("MultiMedia Master", "brand"))
        bt.addWidget(label(f"Pro {config.APP_VERSION}", "brandVersion"))
        brand.addWidget(self.brand_icon)
        brand.addWidget(self.brand_text, 1)
        lay.addLayout(brand)
        lay.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        self.section_labels = []
        current = None
        for i, page in enumerate(self.pages):
            if page.section != current:
                current = page.section
                if i:
                    lay.addSpacing(10)
                sec = label(current.upper(), "navSection")
                sec.setProperty('full', current.upper())
                sec.setFixedHeight(20)
                self.section_labels.append(sec)
                lay.addWidget(sec)
            b = QPushButton(page.title.replace('&', '&&'))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(17, 17))
            b.clicked.connect(lambda _c, idx=i: self._select(idx))
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            lay.addWidget(b)
        lay.addStretch(1)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("sideTool")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setIconSize(QSize(16, 16))
        self.theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self.theme_btn)
        ok = config.ffmpeg_available()
        self.engine_state = label("FFmpeg ready" if ok else "FFmpeg not found", "engineState")
        self.engine_state.setToolTip(config.FFMPEG)
        lay.addSpacing(4)
        lay.addWidget(self.engine_state)
        return bar

    def _build_header(self):
        head = QFrame()
        head.setObjectName("pageHeader")
        lay = QVBoxLayout(head)
        lay.setContentsMargins(24, 14, 24, 13)
        lay.setSpacing(2)
        self.page_title = label("", "pageTitle")
        self.page_desc = ElidedLabel("", Qt.ElideRight)
        self.page_desc.setObjectName("pageDesc")
        lay.addWidget(self.page_title)
        lay.addWidget(self.page_desc)
        return head

    def _build_status(self):
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(32)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(10)
        self.status_label = ElidedLabel("Ready", Qt.ElideRight)
        self.status_label.setObjectName("status")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(180)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.reveal_btn = QPushButton("Show in folder")
        self.reveal_btn.setObjectName("statusBtn")
        self.reveal_btn.setCursor(Qt.PointingHandCursor)
        self.reveal_btn.clicked.connect(lambda: config.open_in_explorer(self._last_output))
        self.reveal_btn.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("statusBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_task)
        self.cancel_btn.hide()
        self.log_btn = QPushButton("Log")
        self.log_btn.setObjectName("statusBtn")
        self.log_btn.setCheckable(True)
        self.log_btn.setCursor(Qt.PointingHandCursor)
        self.log_btn.setToolTip("Show FFmpeg output")
        self.log_btn.toggled.connect(self.console.setVisible)
        lay.addWidget(self.status_label, 1)
        lay.addWidget(self.progress)
        lay.addWidget(self.reveal_btn)
        lay.addWidget(self.cancel_btn)
        lay.addWidget(self.log_btn)
        return bar

    # ---------------------------------------------------------------- pages #
    def _form_page(self, body_widgets):
        """Wrap page content in a scroll area, centred at a readable width."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        holder.setObjectName("pageBody")
        outer = QHBoxLayout(holder)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.addStretch(0)
        column = QWidget()
        column.setMaximumWidth(CONTENT_MAX_W)
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        for w in body_widgets:
            if w is None:
                col.addStretch(1)
            elif isinstance(w, QWidget):
                col.addWidget(w)
            else:
                col.addLayout(w)
        col.addStretch(1)
        outer.addWidget(column, 100)
        outer.addStretch(0)
        scroll.setWidget(holder)
        return scroll

    def _format_combo(self, options):
        combo = QComboBox()
        combo.addItem("Same as source", None)
        for ext in options:
            combo.addItem(ext.upper(), ext)
        combo.setMinimumWidth(170)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return combo

    def _level_rows(self, frm, kind):
        level = LevelSelector(kind)
        desc = ElidedLabel(level.description(), Qt.ElideRight)
        desc.setObjectName("hint")
        desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        level.changed.connect(lambda _v: desc.setText(level.description()))
        frm.addRow(form_label("Compression"), level)
        frm.addRow(QLabel(""), desc)
        return level

    def _io_page(self, key, section, title, icon_name, desc, kinds, file_filter,
                 batch_text, settings, single, batch, folder_kinds=None):
        """A page that works on one file, or on a whole folder when its batch
        checkbox is ticked. `single` / `batch` are (button text, note)."""
        folder_kinds = folder_kinds or kinds
        src = SourceField('file', kinds, file_filter)
        check = QCheckBox(batch_text)
        check.setCursor(Qt.PointingHandCursor)
        btn = button(single[0], "primary", 'ph.play-fill')
        self._run_buttons.append(btn)
        note = hint(single[1])
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(note, 1)
        row.addWidget(btn, 0, Qt.AlignRight | Qt.AlignTop)

        def on_batch(on):
            src.set_mode('dir' if on else 'file', folder_kinds if on else kinds)
            btn.setText((batch if on else single)[0])
            note.setText((batch if on else single)[1])
        check.toggled.connect(on_batch)

        page = Page(key, section, title, icon_name, desc,
                    self._form_page([check, src, settings, row]),
                    source=src, batch=check)
        btn.clicked.connect(lambda: self._start(page))
        return page

    def _build_pages(self):
        pages = []

        # --- Video: compress (one file, or every video in a folder)
        pn, body = panel("Settings")
        f = form()
        self.cv_level = self._level_rows(f, 'video')
        self.cv_fmt = self._format_combo(['mp4', 'mkv', 'mov'])
        f.addRow(form_label("Output format"), self.cv_fmt)
        body.addLayout(f)
        pages.append(self._io_page(
            'cv', "Video", "Compress video", 'ph.film-strip',
            "Re-encode videos with H.264 to make them smaller.",
            ('video',), VIDEO_FILTER, "Batch: compress every video in a folder", pn,
            ("Compress", "Saved next to the original with a “_compressed” suffix."),
            ("Compress folder", "Results go to a new “<folder>_compressed” folder "
                                "with a CSV report.")))

        # --- Video: trim
        trim_scroll = QScrollArea()
        trim_scroll.setWidgetResizable(True)
        trim_scroll.setFrameShape(QFrame.NoFrame)
        self.trim.setObjectName("pageBody")
        trim_scroll.setWidget(self.trim)
        pages.append(Page('trim', "Video", "Trim & preview", 'ph.scissors',
                          "Play a video or audio file, mark the part you want and export it.",
                          trim_scroll, accepts=self.trim.accepts, take=self.trim.take))

        # --- Audio: extract
        pn, body = panel("Settings")
        f = form()
        # Single line: wrapped labels inside a QFormLayout get clipped.
        out_note = ElidedLabel("MP3 · variable bit rate, highest quality (V0)", Qt.ElideRight)
        out_note.setObjectName("hint")
        out_note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        f.addRow(form_label("Output"), out_note)
        body.addLayout(f)
        pages.append(self._io_page(
            'ea', "Audio", "Extract audio", 'ph.music-notes',
            "Save the soundtrack of a video as an MP3.",
            ('video',), VIDEO_FILTER, "Batch: extract from every video in a folder", pn,
            ("Extract", "Saved next to the source video."),
            ("Extract folder", "Results go to a new “<folder>_audio” folder.")))

        # --- Audio: convert (audio files, or the sound of a video)
        self.ca_ext = QComboBox()
        self.ca_ext.addItems(['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'opus', 'wma'])
        self.ca_ext.setMinimumWidth(170)
        self.ca_ext.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pn, body = panel("Settings")
        f = form()
        f.addRow(form_label("Convert to"), self.ca_ext)
        body.addLayout(f)
        pages.append(self._io_page(
            'ca', "Audio", "Convert audio", 'ph.arrows-left-right',
            "Change the format of an audio file, or save a video's sound in another format.",
            ('audio', 'video'), AUDIO_OR_VIDEO_FILTER,
            "Batch: convert every audio file in a folder", pn,
            ("Convert", "Saved next to the source."),
            ("Convert folder", "Results go to a new “<folder>_<format>” folder."),
            folder_kinds=('audio',)))

        # --- Image: compress (one image, or every image in a folder)
        pn, body = panel("Settings")
        f = form()
        self.ci_level = self._level_rows(f, 'image')
        self.ci_fmt = self._format_combo(['jpg', 'png', 'webp'])
        f.addRow(form_label("Output format"), self.ci_fmt)
        body.addLayout(f)
        pages.append(self._io_page(
            'ci', "Image", "Compress image", 'ph.image',
            "Reduce the file size of photos and pictures.",
            ('image',), IMAGE_FILTER, "Batch: compress every image in a folder", pn,
            ("Compress", "Saved next to the original with a “_compressed” suffix."),
            ("Compress folder", "Results go to a new “<folder>_compressed” folder "
                                "with a CSV report.")))

        # --- Image: convert
        self.cim_ext = QComboBox()
        self.cim_ext.addItems(['png', 'jpg', 'webp', 'avif', 'jxl', 'bmp', 'tiff', 'gif', 'tga',
                               'ico'])
        self.cim_ext.setMinimumWidth(170)
        self.cim_ext.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pn, body = panel("Settings")
        f = form()
        f.addRow(form_label("Convert to"), self.cim_ext)
        body.addLayout(f)
        pages.append(self._io_page(
            'cim', "Image", "Convert image", 'ph.arrows-clockwise',
            "Change the format of an image or a whole folder of images.",
            ('image',), IMAGE_FILTER, "Batch: convert every image in a folder", pn,
            ("Convert", "Saved next to the source."),
            ("Convert folder", "Results go to a new “<folder>_<format>” folder.")))

        # --- Capture: screen recorder
        pages.append(self._record_page())
        return pages

    def _record_page(self):
        self.rec_src = SourceField('dir', ('video',),
                                   empty_hint="or click to browse  ·  remembered for next time",
                                   count_files=False)
        saved = config.load_saved_output_dir()
        default = os.path.join(os.path.expanduser('~'), 'Videos')
        if saved and os.path.isdir(saved):
            self.rec_src.setText(saved)
        elif os.path.isdir(default):
            self.rec_src.setText(default)
        self.rec_src.pathChanged.connect(self._remember_rec_dir)

        # Audio: off by default; when on, pick which microphone to record.
        apn, abody = panel("Audio")
        self.rec_audio = QCheckBox("Record audio from a microphone")
        self.rec_audio.setCursor(Qt.PointingHandCursor)
        self.rec_mic = QComboBox()
        self.rec_mic.setMinimumWidth(260)
        self.rec_mic.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.rec_mic.addItem("Looking for microphones…", None)
        self.rec_mic.setEnabled(False)
        self.rec_mic_refresh = tool_button('ph.arrows-clockwise', "Look for microphones again")
        self.rec_mic_refresh.clicked.connect(self._load_microphones)
        mic_row = QHBoxLayout()
        mic_row.setSpacing(6)
        mic_row.addWidget(self.rec_mic, 1)
        mic_row.addWidget(self.rec_mic_refresh)
        f = form()
        f.addRow(form_label("Microphone"), mic_row)
        abody.addWidget(self.rec_audio)
        abody.addLayout(f)
        self.rec_audio_note = hint("")
        abody.addWidget(self.rec_audio_note)
        self.rec_audio.setChecked(bool(config.load_setting('record_audio', False)))
        self.rec_audio.toggled.connect(self._on_rec_audio_toggled)
        self.rec_mic.currentIndexChanged.connect(self._on_mic_chosen)
        self._mic_thread = None
        self._on_rec_audio_toggled(self.rec_audio.isChecked())
        QTimer.singleShot(0, self._load_microphones)

        pn, body = panel()
        body.setSpacing(10)
        self.rec_state = label("Ready to record", "hint")
        self.rec_state.setAlignment(Qt.AlignCenter)
        self.rec_timer_label = label("00:00:00", "recTimer")
        self.rec_timer_label.setAlignment(Qt.AlignCenter)
        self.rec_btn = button("Start recording", "record", 'ph.record-fill', '#ffffff')
        self.rec_btn.setMinimumWidth(200)
        self.rec_btn.clicked.connect(self._toggle_recording)
        body.addSpacing(6)
        body.addWidget(self.rec_timer_label)
        body.addWidget(self.rec_state)
        body.addSpacing(4)
        body.addLayout(hbox(None, self.rec_btn, None))
        body.addSpacing(6)
        note = hint("Captures the whole desktop at full resolution as H.264 MP4. "
                    "Files are named by date and time.")
        note.setAlignment(Qt.AlignCenter)
        body.addWidget(note)
        self.rec_qtimer = QTimer(self)
        self.rec_qtimer.setInterval(500)
        self.rec_qtimer.timeout.connect(self._update_rec_timer)
        return Page('rec', "Capture", "Screen recorder", 'ph.monitor',
                    "Record your screen, with or without microphone audio, to an MP4 file.",
                    self._form_page([label("Save recordings to", "sectionLabel"), self.rec_src,
                                     apn, pn]),
                    source=self.rec_src)

    # -- microphone selection --------------------------------------------- #
    def _load_microphones(self):
        if self._mic_thread is not None and self._mic_thread.isRunning():
            return
        self.rec_mic.blockSignals(True)
        self.rec_mic.clear()
        self.rec_mic.addItem("Looking for microphones…", None)
        self.rec_mic.blockSignals(False)
        self.rec_mic.setEnabled(False)
        self._mic_thread = media.AudioInputsThread(self)
        self._mic_thread.ready.connect(self._on_microphones)
        self._mic_thread.start()

    def _on_microphones(self, devices):
        self.rec_mic.blockSignals(True)
        self.rec_mic.clear()
        remembered = config.load_setting('record_mic')
        for name, device_id in devices:
            self.rec_mic.addItem(name, device_id)
        if not devices:
            self.rec_mic.addItem("No microphone found", None)
        else:
            idx = self.rec_mic.findText(remembered) if remembered else -1
            self.rec_mic.setCurrentIndex(max(0, idx))
        self.rec_mic.blockSignals(False)
        self._on_rec_audio_toggled(self.rec_audio.isChecked())

    def _on_rec_audio_toggled(self, on):
        config.save_setting('record_audio', bool(on))
        has_mic = self.rec_mic.currentData() is not None
        busy = self.rec_process is not None
        self.rec_mic.setEnabled(on and has_mic and not busy)
        self.rec_mic_refresh.setEnabled(on and not busy)
        if not on:
            self.rec_audio_note.setText("The recording will be silent.")
        elif has_mic:
            self.rec_audio_note.setText("Sound from the chosen microphone is recorded with the "
                                        "screen. To capture what your PC plays, enable "
                                        "“Stereo Mix” in Windows Sound settings and pick it here.")
        elif self.rec_mic.count() and self.rec_mic.itemText(0).startswith("Looking"):
            self.rec_audio_note.setText("")
        else:
            self.rec_audio_note.setText("No microphone was found. Plug one in, then press refresh.")

    def _on_mic_chosen(self, _index):
        if self.rec_mic.currentData() is not None:
            config.save_setting('record_mic', self.rec_mic.currentText())

    # ----------------------------------------------------- navigation/theme #
    def _select(self, idx):
        trim_page = self._page('trim')[1].widget
        if self.stack.currentWidget() is trim_page and self.pages[idx].widget is not trim_page:
            self.trim.pause()
        self.stack.setCurrentIndex(idx)
        self.nav_group.button(idx).setChecked(True)
        page = self.pages[idx]
        self.page_title.setText(page.title)
        self.page_desc.setText(page.desc)
        self._refresh_nav_icons()

    def _page(self, key):
        for i, p in enumerate(self.pages):
            if p.key == key:
                return i, p
        raise KeyError(key)

    def _refresh_nav_icons(self):
        current = self.stack.currentIndex()
        for i, b in enumerate(self.nav_buttons):
            icons.bind(b, self.pages[i].icon, 'accent' if i == current else 'subtext', 17)

    def _toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        config.save_theme(self.theme)
        self._apply_theme()

    def _apply_theme(self):
        pal = THEMES[self.theme]
        icons.set_palette(pal)
        # App-wide, so dialogs, menus and popups follow the theme too.
        QApplication.instance().setStyleSheet(build_qss(pal))
        self._refresh_nav_icons()
        dark = self.theme == 'dark'
        icons.bind(self.theme_btn, 'ph.sun' if dark else 'ph.moon', 'subtext', 16)
        self._theme_label = "Light theme" if dark else "Dark theme"
        self.theme_btn.setToolTip("Switch to " + self._theme_label.lower())
        self._apply_collapse(self._collapsed or False, force=True)
        self.trim.apply_theme(pal)

    # -------------------------------------------------------- responsiveness #
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_collapse(self.width() < COLLAPSE_BELOW)

    def _apply_collapse(self, collapsed, force=False):
        if collapsed == self._collapsed and not force:
            return
        self._collapsed = collapsed
        self.sidebar.setFixedWidth(SIDEBAR_RAIL if collapsed else SIDEBAR_WIDE)
        flag = "true" if collapsed else "false"
        self.brand_text.setVisible(not collapsed)
        # Section captions keep their height in the rail, acting as group gaps.
        for sec in self.section_labels:
            sec.setText("" if collapsed else sec.property('full'))
        for i, b in enumerate(self.nav_buttons):
            b.setText("" if collapsed else "  " + self.pages[i].title.replace('&', '&&'))
            b.setToolTip(self.pages[i].title if collapsed else "")
            b.setProperty('collapsed', flag)
            repolish(b)
        self.theme_btn.setText("" if collapsed else "  " + self._theme_label)
        self.theme_btn.setProperty('collapsed', flag)
        repolish(self.theme_btn)
        self.engine_state.setVisible(not collapsed)

    # ----------------------------------------------------------- drag & drop #
    def _set_drop_active(self, active):
        # Re-styling the whole window on hover would be slow; use the status bar.
        self._drop_ok = active
        if active:
            self._status_before_drop = (self.status_label.text(), self.status_label.property('state'))
            self._set_status("Release to open the file", 'busy')
        elif getattr(self, '_status_before_drop', None):
            self._set_status(*self._status_before_drop)
            self._status_before_drop = None

    def drop_accepts(self, paths):
        return any(dnd.kind_of(p) is not None or dnd.is_unknown_file(p) for p in paths)

    def drop_handle(self, paths):
        current = self.pages[self.stack.currentIndex()]
        if current.accepts(paths) and current.take(paths):
            return
        kinds = [dnd.kind_of(p) for p in paths]
        for i, k in enumerate(kinds):
            if k is None and dnd.is_unknown_file(paths[i]):
                # Unfamiliar extension: ask FFmpeg what the file really is.
                info = media.probe(paths[i])
                kinds[i] = info.kind if info.ok else None
        key, batch = None, False
        if 'video' in kinds:
            key = 'cv'
        elif 'audio' in kinds:
            key = 'ca'
        elif 'image' in kinds:
            key = 'ci'
        elif 'dir' in kinds:
            counts = dnd.folder_counts(paths[kinds.index('dir')])
            key = ('cv' if counts['video'] >= max(1, counts['image'])
                   else 'ci' if counts['image'] else 'ca')
            batch = True
        if key is None:
            self._set_status("FFmpeg can't read that file.", 'error')
            return
        idx, page = self._page(key)
        if page.batch is not None:
            page.batch.setChecked(batch)
        target = page.source.usable_drop(paths)
        if target:
            page.source.setText(target)
            self._select(idx)
            self._set_status(f"Opened in {page.title}.")

    # ------------------------------------------------------------- recording #
    def _remember_rec_dir(self, path):
        if path and os.path.isdir(path):
            try:
                config.save_output_dir(path)
            except Exception:
                pass

    def _toggle_recording(self):
        if self.rec_process is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        out_dir = self.rec_src.text()
        if not out_dir or not os.path.isdir(out_dir):
            QMessageBox.information(self, "Choose a folder", "Choose where recordings should be saved first.")
            return
        if os.name != 'nt':
            QMessageBox.information(self, "Windows only", "Screen recording is only available on Windows.")
            return
        mic = self.rec_mic.currentData() if self.rec_audio.isChecked() else None
        if self.rec_audio.isChecked() and mic is None:
            QMessageBox.information(self, "No microphone",
                                    "No microphone is available. Connect one and press refresh, "
                                    "or untick “Record audio” to record without sound.")
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = os.path.join(out_dir, f"recording_{ts}.mp4")
        cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error',
               '-thread_queue_size', '1024', '-f', 'gdigrab', '-framerate', '30', '-i', 'desktop']
        if mic:
            # DirectShow capture of the chosen input. The device id (not the
            # display name) is used so identical-looking devices can't clash.
            cmd += ['-thread_queue_size', '1024', '-rtbufsize', '64M',
                    '-f', 'dshow', '-i', f'audio={mic}', '-map', '0:v', '-map', '1:a']
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p']
        if mic:
            cmd += ['-c:a', 'aac', '-b:a', '160k']
        cmd += ['-y', out]
        self._rec_log = os.path.join(tempfile.gettempdir(), "mmmp_recording.log")
        try:
            log = open(self._rec_log, 'wb')
            self.rec_process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                                stdout=subprocess.DEVNULL, stderr=log,
                                                creationflags=config.CREATE_NO_WINDOW)
            log.close()
        except Exception as e:
            QMessageBox.critical(self, "Recording failed", str(e))
            self.rec_process = None
            return
        self._rec_with_audio = bool(mic)
        self._on_rec_audio_toggled(self.rec_audio.isChecked())
        self.rec_audio.setEnabled(False)
        # If FFmpeg can't open the screen or the microphone it exits at once.
        QTimer.singleShot(1500, self._check_recording_alive)
        self._rec_out = out
        self._rec_start = time.time()
        self.rec_btn.setText("Stop recording")
        self.rec_btn.setObjectName("recording")
        icons.bind(self.rec_btn, 'ph.stop-fill', 'danger', 15)
        repolish(self.rec_btn)
        self.rec_timer_label.setText("00:00:00")
        what = f"screen and {self.rec_mic.currentText()}" if mic else "screen (no audio)"
        self.rec_state.setText(f"Recording the {what}…")
        self._set_status(f"Recording the {what}…", 'busy')
        self.rec_qtimer.start()

    def _check_recording_alive(self):
        proc = self.rec_process
        if proc is None or proc.poll() is None:
            return
        # FFmpeg quit on its own: tell the user why instead of pretending.
        self.rec_process = None
        self.rec_qtimer.stop()
        self._reset_record_ui()
        try:
            with open(self._rec_log, 'r', encoding='utf-8', errors='replace') as f:
                reason = f.read().strip().splitlines()[-3:]
        except Exception:
            reason = []
        self.rec_state.setText("Recording failed")
        self._set_status("Recording failed.", 'error')
        hint_text = ("\n\nThe microphone may be in use by another app, or unplugged."
                     if self._rec_with_audio else "")
        QMessageBox.warning(self, "Recording failed",
                            "FFmpeg stopped right after starting." + hint_text +
                            ("\n\nDetails:\n" + "\n".join(reason) if reason else ""))

    def _reset_record_ui(self):
        self.rec_btn.setText("Start recording")
        self.rec_btn.setObjectName("record")
        icons.bind(self.rec_btn, 'ph.record-fill', '#ffffff', 15)
        repolish(self.rec_btn)
        self.rec_audio.setEnabled(True)
        self._on_rec_audio_toggled(self.rec_audio.isChecked())

    def _update_rec_timer(self):
        elapsed = int(time.time() - self._rec_start)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        self.rec_timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _stop_recording(self, notify=True):
        self.rec_qtimer.stop()
        proc, self.rec_process = self.rec_process, None
        try:
            proc.stdin.write(b'q')
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.terminate()
        self._reset_record_ui()
        length = self.rec_timer_label.text()
        self.rec_state.setText(f"Saved a {length} recording")
        if os.path.exists(getattr(self, '_rec_out', "")):
            self._last_output = self._rec_out
            self._set_status(f"Recording saved: {os.path.basename(self._rec_out)}", 'ok')
            self.reveal_btn.show()
            if notify:
                audio = "with audio" if self._rec_with_audio else "without audio"
                self._show_success(f"Recording saved ({length}, {audio}).\n\nSaved to:\n"
                                   f"{self._rec_out}", self._rec_out, "Recording saved")

    # ------------------------------------------------------ validation/launch #
    def _launch(self, task, params):
        if self.is_busy():
            QMessageBox.information(self, "Please wait", "Another task is still running.")
            return
        self.console.clear()
        self.progress.setValue(0)
        self.progress.show()
        self.reveal_btn.hide()
        self.cancel_btn.show()
        for b in self._run_buttons:
            b.setEnabled(False)
        self._set_status("Starting…", 'busy')
        self.worker = Worker(task, params)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(lambda s: self._set_status(s.replace('...', '…'), 'busy'))
        self.worker.log.connect(self.console.appendPlainText)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _start(self, page):
        """Validate the page's source and launch its task."""
        problem = page.source.problem()
        if problem:
            QMessageBox.information(self, page.title, problem)
            return
        path = page.source.text()
        batch = page.batch is not None and page.batch.isChecked()
        mode = 'folder' if batch else 'single'
        if page.key == 'cv':
            self._launch('compress_videos' if batch else 'compress_video',
                         {'input': path, 'level': self.cv_level.level(),
                          'ext': self.cv_fmt.currentData()})
        elif page.key == 'ci':
            self._launch('compress_images' if batch else 'compress_image',
                         {'input': path, 'level': self.ci_level.level(),
                          'ext': self.ci_fmt.currentData()})
        elif page.key == 'ea':
            self._launch('extract_audio', {'input': path, 'mode': mode})
        elif page.key == 'ca':
            self._launch('convert_media', {'input': path, 'ext': self.ca_ext.currentText(),
                                           'mode': mode, 'kind': 'audio'})
        elif page.key == 'cim':
            self._launch('convert_media', {'input': path, 'ext': self.cim_ext.currentText(),
                                           'mode': mode, 'kind': 'image'})

    # ---------------------------------------------------------- task results #
    def _set_status(self, text, state=""):
        self.status_label.setText(text)
        if self.status_label.property('state') != state:
            self.status_label.setProperty('state', state)
            repolish(self.status_label)

    def _reset_buttons(self):
        for b in self._run_buttons:
            needs = b.property('needsMedia')
            b.setEnabled(needs is None or bool(needs))
        self.cancel_btn.hide()

    @staticmethod
    def _summary(message):
        lines = [l.strip() for l in message.splitlines() if l.strip()]
        keep = []
        for l in lines:
            if l.lower().startswith("saved to"):
                break
            keep.append(l.rstrip('.'))
        return "  ·  ".join(keep) if keep else "Done"

    def _on_done(self, message, out_path):
        self.progress.setValue(100)
        self._reset_buttons()
        self._last_output = out_path
        self._set_status(self._summary(message), 'ok')
        self.reveal_btn.setVisible(bool(out_path))
        QTimer.singleShot(1500, lambda: None if self.is_busy() else self.progress.hide())
        QApplication.alert(self)
        self._show_success(message, out_path)

    def _show_success(self, message, out_path, title="Done"):
        """A success dialog with shortcuts to the result."""
        lines = [l.strip() for l in message.splitlines()]
        try:
            cut = next(i for i, l in enumerate(lines) if l.lower().startswith("saved to"))
        except StopIteration:
            cut = len(lines)
        summary = [l for l in lines[:cut] if l]
        out_path = os.path.normpath(out_path) if out_path else ""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIconPixmap(icons.pixmap('ph.check-circle-fill', icons.palette()['success'], 40))
        box.setText(f"<b>{html.escape(summary[0] if summary else 'Finished')}</b>")
        details = [html.escape(l) for l in summary[1:]]
        if out_path:
            name = os.path.basename(out_path.rstrip('\\/')) or out_path
            folder = os.path.dirname(out_path.rstrip('\\/'))
            # Long paths have no spaces to wrap at: shorten the middle instead.
            folder = box.fontMetrics().elidedText(folder, Qt.ElideMiddle, 420)
            details.append(f"<span style='font-weight:600'>{html.escape(name)}</span><br>"
                           f"<span style='color:{icons.palette()['subtext']}'>"
                           f"in {html.escape(folder)}</span>")
        box.setInformativeText("<br>".join(details))
        # Room for long paths, and buttons sized to their text.
        box.setStyleSheet("QLabel#qt_msgbox_label, QLabel#qt_msgbox_informativelabel "
                          "{ min-width: 380px; }")
        open_btn = None
        if out_path and os.path.isfile(out_path):
            open_btn = box.addButton("Open", QMessageBox.ActionRole)
        folder_btn = box.addButton("Show in folder", QMessageBox.ActionRole) if out_path else None
        close_btn = box.addButton("Close", QMessageBox.RejectRole)
        for b in box.buttons():
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + 40)
            b.setCursor(Qt.PointingHandCursor)
        box.setDefaultButton(close_btn)
        box.setEscapeButton(close_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is open_btn and open_btn is not None:
            config.open_file(out_path)
        elif clicked is folder_btn and folder_btn is not None:
            config.open_in_explorer(out_path)

    def _on_failed(self, message):
        self._reset_buttons()
        self.progress.hide()
        self._set_status(message, 'error')
        if message.strip().lower() != "cancelled.":
            QMessageBox.warning(self, "Task failed", message)

    def _cancel_task(self):
        if self.is_busy():
            self.worker.cancel()
            self._set_status("Cancelling…", 'busy')

    def closeEvent(self, event):
        if self.rec_process is not None:
            self._stop_recording(notify=False)
        if self.is_busy():
            self.worker.cancel()
            self.worker.wait(3000)
        self.trim.shutdown()
        event.accept()
