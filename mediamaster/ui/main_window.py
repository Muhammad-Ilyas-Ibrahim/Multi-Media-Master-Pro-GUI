"""The main application window: sidebar, header, pages and progress bar."""

import os

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFrame, QStackedWidget, QComboBox, QCheckBox,
    QButtonGroup, QRadioButton, QProgressBar, QPlainTextEdit, QMessageBox,
    QScrollArea, QApplication
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon
import time
import subprocess
from datetime import datetime

from ..core import config
from .theme import THEMES, build_qss
from .icons import fa, fa_pixmap
from ..core.worker import Worker
from .widgets import PathInput, LevelSelector, make_card, field
from .trim_studio import TrimStudio


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.theme = config.load_saved_theme()
        self.worker = None
        self.rec_process = None
        self._run_buttons = []
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.resize(1160, 780)
        self.setMinimumSize(980, 660)

        icon_path = os.path.join(config.resource_base(), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._apply_theme()
        self._select_page(0)

    # ---- public API used by sub-widgets --------------------------------- #
    def register_run_button(self, btn):
        self._run_buttons.append(btn)

    def launch(self, task, params):
        self._launch(task, params)

    # ---- UI construction ------------------------------------------------- #
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())
        outer.addWidget(self._build_main(), 1)

    def _build_sidebar(self):
        bar = QFrame(); bar.setObjectName("sidebar"); bar.setFixedWidth(250)
        lay = QVBoxLayout(bar); lay.setContentsMargins(16, 22, 16, 18); lay.setSpacing(6)
        brand = QLabel("Multi-Media"); brand.setObjectName("brand")
        sub = QLabel("MASTER-PRO  •  v" + config.APP_VERSION); sub.setObjectName("brandSub")
        lay.addWidget(brand); lay.addWidget(sub); lay.addSpacing(18)

        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.pages_meta = [
            ("fa5s.file-video", "Compress Video", "Shrink a single video file"),
            ("fa5s.photo-video", "Batch Videos", "Compress a whole folder of videos"),
            ("fa5s.file-image", "Compress Image", "Shrink a single image"),
            ("fa5s.images", "Batch Images", "Compress a whole folder of images"),
            ("fa5s.desktop", "Screen Record", "Record your screen (no audio)"),
            ("fa5s.music", "Extract Audio", "Pull audio out of a video"),
            ("fa5s.file-audio", "Convert Audio", "Change audio format"),
            ("fa5s.sync-alt", "Convert Image", "Change image format"),
            ("fa5s.cut", "Trim Studio", "Play, scrub and trim precisely"),
        ]
        self.nav_buttons = []
        for i, (icon, name, _desc) in enumerate(self.pages_meta):
            b = QPushButton("   " + name); b.setObjectName("nav"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor); b.setIconSize(QSize(20, 20))
            b.clicked.connect(lambda _, idx=i: self._select_page(idx))
            self.nav_group.addButton(b, i); self.nav_buttons.append(b); lay.addWidget(b)
        lay.addStretch()
        tip = QLabel("FFmpeg " + ("detected" if config.ffmpeg_available() else "not found"))
        tip.setObjectName("hint"); tip.setWordWrap(True); lay.addWidget(tip)
        return bar

    def _build_main(self):
        wrap = QWidget(); lay = QVBoxLayout(wrap)
        lay.setContentsMargins(24, 22, 24, 18); lay.setSpacing(16)

        self.header = QFrame(); self.header.setObjectName("header"); self.header.setFixedHeight(96)
        hl = QHBoxLayout(self.header); hl.setContentsMargins(26, 0, 22, 0)
        self.header_icon = QLabel(); self.header_icon.setFixedWidth(46); self.header_icon.setAlignment(Qt.AlignCenter)
        hl.addWidget(self.header_icon, 0)
        txt = QVBoxLayout(); txt.setSpacing(3)
        self.page_title = QLabel(""); self.page_title.setObjectName("pageTitle")
        self.page_desc = QLabel(""); self.page_desc.setObjectName("pageDesc")
        txt.addStretch(); txt.addWidget(self.page_title); txt.addWidget(self.page_desc); txt.addStretch()
        hl.addLayout(txt, 1)
        self.theme_btn = QPushButton(); self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setFixedSize(40, 40); self.theme_btn.setIconSize(QSize(20, 20))
        self.theme_btn.setCursor(Qt.PointingHandCursor); self.theme_btn.setToolTip("Toggle light / dark theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        hl.addWidget(self.theme_btn, 0, Qt.AlignVCenter)
        lay.addWidget(self.header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        self.stack = QStackedWidget()
        self.trim_studio = TrimStudio(self, THEMES[self.theme])
        builders = [
            self._page_compress_video, self._page_batch_video,
            self._page_compress_image, self._page_batch_image,
            self._page_record, self._page_extract_audio,
            self._page_convert_audio, self._page_convert_image,
        ]
        for b in builders:
            self.stack.addWidget(b())
        self.stack.addWidget(self._scroll_page(self.trim_studio))
        scroll.setWidget(self.stack); lay.addWidget(scroll, 1)

        lay.addWidget(self._build_progress())
        return wrap

    def _build_progress(self):
        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(18, 14, 18, 14); lay.setSpacing(8)
        row = QHBoxLayout()
        self.status_label = QLabel("Ready."); self.status_label.setObjectName("status")
        self.log_toggle = QPushButton("Show log"); self.log_toggle.setObjectName("ghost")
        self.log_toggle.setCursor(Qt.PointingHandCursor); self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setCursor(Qt.PointingHandCursor); self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_task)
        row.addWidget(self.status_label, 1); row.addWidget(self.log_toggle); row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.progress = QProgressBar(); self.progress.setValue(0); self.progress.setTextVisible(True)
        lay.addWidget(self.progress)
        self.console = QPlainTextEdit(); self.console.setObjectName("console")
        self.console.setReadOnly(True); self.console.setFixedHeight(150); self.console.hide()
        lay.addWidget(self.console)
        return card

    # ---- pages ---------------------------------------------------------- #
    def _scroll_page(self, inner):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(2, 2, 2, 2); pl.setSpacing(16)
        pl.addWidget(inner); pl.addStretch()
        return page

    def _page_compress_video(self):
        card, lay = make_card("Source & options")
        self.cv_input = PathInput('file', "Choose a video file...", "Videos (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v)")
        lay.addWidget(field("Video file")); lay.addWidget(self.cv_input)
        lay.addWidget(field("Compression level")); self.cv_level = LevelSelector('video'); lay.addWidget(self.cv_level)
        self.cv_ext = self._ext_row(lay, "mp4")
        lay.addWidget(self._run_button("Compress Video", self._start_compress_video), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_batch_video(self):
        card, lay = make_card("Source & options")
        self.bv_input = PathInput('dir', "Choose a folder of videos...")
        lay.addWidget(field("Videos folder")); lay.addWidget(self.bv_input)
        lay.addWidget(field("Compression level")); self.bv_level = LevelSelector('video'); lay.addWidget(self.bv_level)
        self.bv_ext = self._ext_row(lay, "mp4")
        hint = QLabel("Output goes to a new \"<folder>_compressed\" folder, plus a CSV report."); hint.setObjectName("hint"); lay.addWidget(hint)
        lay.addWidget(self._run_button("Compress Folder", self._start_batch_video), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_compress_image(self):
        card, lay = make_card("Source & options")
        self.ci_input = PathInput('file', "Choose an image file...", "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.gif)")
        lay.addWidget(field("Image file")); lay.addWidget(self.ci_input)
        lay.addWidget(field("Compression level")); self.ci_level = LevelSelector('image'); lay.addWidget(self.ci_level)
        self.ci_ext = self._ext_row(lay, "jpg")
        lay.addWidget(self._run_button("Compress Image", self._start_compress_image), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_batch_image(self):
        card, lay = make_card("Source & options")
        self.bi_input = PathInput('dir', "Choose a folder of images...")
        lay.addWidget(field("Images folder")); lay.addWidget(self.bi_input)
        lay.addWidget(field("Compression level")); self.bi_level = LevelSelector('image'); lay.addWidget(self.bi_level)
        self.bi_ext = self._ext_row(lay, "jpg")
        hint = QLabel("Output goes to a new \"<folder>_compressed\" folder, plus a CSV report."); hint.setObjectName("hint"); lay.addWidget(hint)
        lay.addWidget(self._run_button("Compress Folder", self._start_batch_image), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_record(self):
        card, lay = make_card("Screen recording")
        lay.addWidget(field("Output folder (remembered between sessions)"))
        self.rec_input = PathInput('dir', "Where recordings are saved...")
        saved = config.load_saved_output_dir()
        if saved:
            self.rec_input.setText(saved)
        lay.addWidget(self.rec_input)
        save_btn = QPushButton("Save output folder"); save_btn.setObjectName("ghost")
        save_btn.setIcon(fa('fa5s.folder-open', THEMES[self.theme]['text']))
        save_btn.setCursor(Qt.PointingHandCursor); save_btn.clicked.connect(self._save_rec_dir)
        lay.addWidget(save_btn, 0, Qt.AlignLeft)
        self.rec_timer_label = QLabel("00:00:00"); self.rec_timer_label.setObjectName("recTimer")
        self.rec_timer_label.setAlignment(Qt.AlignCenter); lay.addSpacing(6); lay.addWidget(self.rec_timer_label)
        self.rec_status = QLabel("Ready to record."); self.rec_status.setObjectName("hint")
        self.rec_status.setAlignment(Qt.AlignCenter); lay.addWidget(self.rec_status)
        self.rec_btn = QPushButton("   Start Recording"); self.rec_btn.setObjectName("record")
        self.rec_btn.setIcon(fa('fa5s.circle', "#ffffff")); self.rec_btn.setIconSize(QSize(18, 18))
        self.rec_btn.setCursor(Qt.PointingHandCursor); self.rec_btn.setFixedWidth(260)
        self.rec_btn.clicked.connect(self._toggle_recording); lay.addSpacing(4); lay.addWidget(self.rec_btn, 0, Qt.AlignHCenter)
        note = QLabel("Recording captures the full desktop with no audio. Files are named by date and time.")
        note.setObjectName("hint"); note.setAlignment(Qt.AlignCenter); note.setWordWrap(True); lay.addWidget(note)
        self.rec_qtimer = QTimer(self); self.rec_qtimer.setInterval(1000); self.rec_qtimer.timeout.connect(self._update_rec_timer)
        return self._scroll_page(card)

    def _page_extract_audio(self):
        card, lay = make_card("Extract audio")
        self.ea_mode = self._mode_row(lay, self._on_ea_mode); lay.addWidget(field("Input"))
        self.ea_input = PathInput('file', "Choose a video file...", "Videos (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v)")
        lay.addWidget(self.ea_input)
        hint = QLabel("Audio is saved as MP3 (best quality)."); hint.setObjectName("hint"); lay.addWidget(hint)
        lay.addWidget(self._run_button("Extract Audio", self._start_extract_audio), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_convert_audio(self):
        card, lay = make_card("Convert audio")
        self.ca_mode = self._mode_row(lay, self._on_ca_mode); lay.addWidget(field("Input"))
        self.ca_input = PathInput('file', "Choose an audio file...", "Audio (*.mp3 *.wav *.flac *.aac *.ogg *.m4a *.wma *.opus)")
        lay.addWidget(self.ca_input); lay.addWidget(field("Convert to"))
        self.ca_ext = QComboBox(); self.ca_ext.addItems(['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'opus', 'wma']); self.ca_ext.setFixedWidth(160)
        lay.addWidget(self.ca_ext)
        lay.addWidget(self._run_button("Convert Audio", self._start_convert_audio), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    def _page_convert_image(self):
        card, lay = make_card("Convert image")
        self.cim_mode = self._mode_row(lay, self._on_cim_mode); lay.addWidget(field("Input"))
        self.cim_input = PathInput('file', "Choose an image file...", "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.gif *.ico)")
        lay.addWidget(self.cim_input); lay.addWidget(field("Convert to"))
        self.cim_ext = QComboBox(); self.cim_ext.addItems(['png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp', 'gif', 'ico']); self.cim_ext.setFixedWidth(160)
        lay.addWidget(self.cim_ext)
        lay.addWidget(self._run_button("Convert Image", self._start_convert_image), 0, Qt.AlignLeft)
        return self._scroll_page(card)

    # ---- small helpers -------------------------------------------------- #
    def _ext_row(self, lay, default):
        cb = QCheckBox("Also change output extension"); cb.setCursor(Qt.PointingHandCursor)
        combo = QComboBox()
        if default == 'mp4':
            combo.addItems(['mp4', 'mkv', 'mov', 'avi', 'webm'])
        else:
            combo.addItems(['jpg', 'png', 'webp', 'bmp', 'tiff'])
        combo.setEnabled(False); combo.setFixedWidth(140); cb.toggled.connect(combo.setEnabled)
        row = QHBoxLayout(); row.addWidget(cb); row.addWidget(combo); row.addStretch(); lay.addLayout(row)
        return (cb, combo)

    def _mode_row(self, lay, callback):
        lay.addWidget(field("Mode")); row = QHBoxLayout(); row.setSpacing(18)
        group = QButtonGroup(self)
        single = QRadioButton("Single file"); single.setChecked(True); single.setCursor(Qt.PointingHandCursor)
        folder = QRadioButton("Whole folder"); folder.setCursor(Qt.PointingHandCursor)
        group.addButton(single, 0); group.addButton(folder, 1); group.buttonToggled.connect(callback)
        row.addWidget(single); row.addWidget(folder); row.addStretch(); lay.addLayout(row)
        return group

    def _run_button(self, text, slot, icon='fa5s.play'):
        b = QPushButton("  " + text); b.setObjectName("primary")
        b.setIcon(fa(icon, "#ffffff")); b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot)
        self._run_buttons.append(b)
        return b

    # ---- navigation / theme -------------------------------------------- #
    def _select_page(self, idx):
        self.stack.setCurrentIndex(idx); self.nav_group.button(idx).setChecked(True)
        icon, name, desc = self.pages_meta[idx]
        self.page_title.setText(name); self.page_desc.setText(desc)
        self.header_icon.setPixmap(fa_pixmap(icon, "#ffffff", 30)); self._refresh_nav_icons()

    def _refresh_nav_icons(self):
        pal = THEMES[self.theme]; current = self.stack.currentIndex()
        for i, b in enumerate(self.nav_buttons):
            color = pal['accent'] if i == current else pal['subtext']
            b.setIcon(fa(self.pages_meta[i][0], color))

    def _toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        config.save_theme(self.theme); self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(build_qss(THEMES[self.theme])); self._refresh_nav_icons()
        self.theme_btn.setIcon(fa('fa5s.moon' if self.theme == 'dark' else 'fa5s.sun', "#ffffff"))
        if hasattr(self, 'trim_studio'):
            self.trim_studio.apply_theme(THEMES[self.theme])
        if getattr(self, 'rec_process', None) is not None:
            self.rec_btn.setIcon(fa('fa5s.stop', "#ffffff"))
        elif hasattr(self, 'rec_btn'):
            self.rec_btn.setIcon(fa('fa5s.circle', "#ffffff"))

    def _toggle_log(self, on):
        self.console.setVisible(on); self.log_toggle.setText("Hide log" if on else "Show log")

    # ---- recording ------------------------------------------------------ #
    def _save_rec_dir(self):
        path = self.rec_input.text()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid folder", "Please choose an existing folder."); return
        try:
            config.save_output_dir(path); self.rec_status.setText("Output folder saved.")
        except Exception as e:
            QMessageBox.critical(self, "Could not save", str(e))

    def _toggle_recording(self):
        if self.rec_process is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        out_dir = self.rec_input.text()
        if not out_dir or not os.path.isdir(out_dir):
            QMessageBox.warning(self, "No output folder", "Choose and save an output folder first."); return
        if os.name != 'nt':
            QMessageBox.information(self, "Windows only", "Screen recording is only available on Windows."); return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = os.path.join(out_dir, f"recording_{ts}.mp4")
        cmd = [config.FFMPEG, '-f', 'gdigrab', '-i', 'desktop', '-c:v', 'libx264', '-crf', '25', '-pix_fmt', 'yuv420p', '-y', out]
        try:
            self.rec_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=config.CREATE_NO_WINDOW)
            self._rec_out = out; self._rec_start = time.time()
            self.rec_btn.setText("   Stop Recording"); self.rec_btn.setObjectName("recording")
            self.rec_btn.setStyleSheet(""); self._apply_theme(); self.rec_btn.setIcon(fa('fa5s.stop', "#ffffff"))
            self.rec_timer_label.setText("00:00:00"); self.rec_status.setText("Recording in progress..."); self.rec_qtimer.start()
        except Exception as e:
            QMessageBox.critical(self, "Recording failed", str(e)); self.rec_process = None

    def _update_rec_timer(self):
        if getattr(self, '_rec_start', None) is None:
            return
        elapsed = int(time.time() - self._rec_start)
        h, rem = divmod(elapsed, 3600); m, s = divmod(rem, 60)
        self.rec_timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        self.rec_status.setText("Recording in progress...")

    def _stop_recording(self):
        self.rec_qtimer.stop()
        try:
            self.rec_process.stdin.write(b'q'); self.rec_process.stdin.flush()
        except Exception:
            pass
        try:
            self.rec_process.wait(timeout=8)
        except Exception:
            self.rec_process.terminate()
        self.rec_process = None; final = self.rec_timer_label.text()
        self.rec_btn.setText("   Start Recording"); self.rec_btn.setObjectName("record")
        self._apply_theme(); self.rec_btn.setIcon(fa('fa5s.circle', "#ffffff"))
        self.rec_status.setText(f"Recording saved  ({final})")
        if getattr(self, '_rec_out', None) and os.path.exists(self._rec_out):
            config.open_in_explorer(self._rec_out)

    # ---- mode toggles --------------------------------------------------- #
    def _swap_pathinput(self, current, is_folder, placeholder_file, file_filter):
        current.mode = 'dir' if is_folder else 'file'
        current.edit.setPlaceholderText("Choose a folder..." if is_folder else placeholder_file)
        current.file_filter = file_filter; current.edit.clear()

    def _on_ea_mode(self, btn, checked):
        if not checked:
            return
        folder = (self.ea_mode.checkedId() == 1)
        self._swap_pathinput(self.ea_input, folder, "Choose a video file...", "Videos (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v)")

    def _on_ca_mode(self, btn, checked):
        if not checked:
            return
        folder = (self.ca_mode.checkedId() == 1)
        self._swap_pathinput(self.ca_input, folder, "Choose an audio file...", "Audio (*.mp3 *.wav *.flac *.aac *.ogg *.m4a *.wma *.opus)")

    def _on_cim_mode(self, btn, checked):
        if not checked:
            return
        folder = (self.cim_mode.checkedId() == 1)
        self._swap_pathinput(self.cim_input, folder, "Choose an image file...", "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.gif *.ico)")

    # ---- validation / launch ------------------------------------------- #
    def _busy(self):
        return self.worker is not None and self.worker.isRunning()

    def _validate_file(self, path):
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "File needed", "Please choose a valid file."); return False
        return True

    def _validate_dir(self, path):
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Folder needed", "Please choose a valid folder."); return False
        return True

    def _launch(self, task, params):
        if self._busy():
            QMessageBox.information(self, "Please wait", "A task is already running."); return
        self.console.clear(); self.progress.setValue(0)
        for b in self._run_buttons:
            b.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker = Worker(task, params)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.log.connect(self._append_log)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _start_compress_video(self):
        p = self.cv_input.text()
        if not self._validate_file(p):
            return
        ext = self.cv_ext[1].currentText() if self.cv_ext[0].isChecked() else None
        self._launch('compress_video', {'input': p, 'level': self.cv_level.level(), 'ext': ext})

    def _start_batch_video(self):
        p = self.bv_input.text()
        if not self._validate_dir(p):
            return
        ext = self.bv_ext[1].currentText() if self.bv_ext[0].isChecked() else None
        self._launch('compress_videos', {'input': p, 'level': self.bv_level.level(), 'ext': ext})

    def _start_compress_image(self):
        p = self.ci_input.text()
        if not self._validate_file(p):
            return
        ext = self.ci_ext[1].currentText() if self.ci_ext[0].isChecked() else None
        self._launch('compress_image', {'input': p, 'level': self.ci_level.level(), 'ext': ext})

    def _start_batch_image(self):
        p = self.bi_input.text()
        if not self._validate_dir(p):
            return
        ext = self.bi_ext[1].currentText() if self.bi_ext[0].isChecked() else None
        self._launch('compress_images', {'input': p, 'level': self.bi_level.level(), 'ext': ext})

    def _start_extract_audio(self):
        folder = (self.ea_mode.checkedId() == 1); p = self.ea_input.text()
        if folder and not self._validate_dir(p):
            return
        if not folder and not self._validate_file(p):
            return
        self._launch('extract_audio', {'input': p, 'mode': 'folder' if folder else 'single'})

    def _start_convert_audio(self):
        folder = (self.ca_mode.checkedId() == 1); p = self.ca_input.text()
        if folder and not self._validate_dir(p):
            return
        if not folder and not self._validate_file(p):
            return
        self._launch('convert_media', {'input': p, 'ext': self.ca_ext.currentText(), 'mode': 'folder' if folder else 'single', 'kind': 'audio'})

    def _start_convert_image(self):
        folder = (self.cim_mode.checkedId() == 1); p = self.cim_input.text()
        if folder and not self._validate_dir(p):
            return
        if not folder and not self._validate_file(p):
            return
        self._launch('convert_media', {'input': p, 'ext': self.cim_ext.currentText(), 'mode': 'folder' if folder else 'single', 'kind': 'image'})

    # ---- worker callbacks ---------------------------------------------- #
    def _append_log(self, line):
        self.console.appendPlainText(line)

    def _reset_buttons(self):
        for b in self._run_buttons:
            b.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_done(self, message, out_path):
        self.progress.setValue(100); self.status_label.setText("Done."); self._reset_buttons()
        box = QMessageBox(self); box.setWindowTitle("Success"); box.setIcon(QMessageBox.Information); box.setText(message)
        open_btn = box.addButton("Open folder", QMessageBox.AcceptRole); box.addButton("Close", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() == open_btn and out_path:
            config.open_in_explorer(out_path)

    def _on_failed(self, message):
        self.status_label.setText(message); self._reset_buttons()
        QMessageBox.critical(self, "Something went wrong", message)

    def _cancel_task(self):
        if self._busy():
            self.worker.cancel(); self.status_label.setText("Cancelling...")

    def closeEvent(self, event):
        if self.rec_process is not None:
            self._stop_recording()
        if self._busy():
            self.worker.cancel(); self.worker.wait(3000)
        event.accept()
