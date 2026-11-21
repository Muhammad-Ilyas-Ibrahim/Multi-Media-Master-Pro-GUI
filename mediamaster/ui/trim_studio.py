"""Trim & Preview: play a video or audio file, mark in/out points, export.

Playback runs on the FFmpeg engine in core/playback.py, so anything FFmpeg
can decode previews here. The timeline shows a filmstrip for video or a
waveform for audio; the export writes the selected range with either a
lossless stream copy or a frame-exact re-encode.

Keyboard (while this page has focus):
    Space        play / pause            I / O        set in / out point
    Left/Right   step one frame          Shift+arrow  step one second
    Home / End   go to in / out point    M            mute
    Ctrl+O       open a file             + / -        zoom timeline
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFileDialog, QMessageBox,
    QComboBox, QSlider, QShortcut, QSizePolicy, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWIDGETSIZE_MAX
from PyQt5.QtGui import QKeySequence

from . import dnd
from . import icons
from .widgets import (
    FlowLayout, ElidedLabel, SegmentedControl, TimecodeEdit, group, label,
    button, tool_button, vsep, hint
)
from .timeline import TrimTimeline
from .video_view import VideoView
from ..core import config
from ..core import media
from ..core.playback import PlaybackEngine


MEDIA_FILTER = ("Video and audio (" + " ".join(
    f"*.{e}" for e in dict.fromkeys(config.VIDEO_EXTS + config.AUDIO_EXTS)) + ");;"
    "Video (" + " ".join(f"*.{e}" for e in config.VIDEO_EXTS) + ");;"
    "Audio (" + " ".join(f"*.{e}" for e in config.AUDIO_EXTS) + ");;All files (*.*)")

# (label, extension or None for "same as source", audio_only)
VIDEO_FORMATS = [
    ("MP4 video (H.264)", 'mp4', False),
    ("MKV video (H.264)", 'mkv', False),
    ("WebM video (VP9)", 'webm', False),
    ("MP3 audio only", 'mp3', True),
    ("WAV audio only", 'wav', True),
    ("M4A audio only (AAC)", 'm4a', True),
]
AUDIO_FORMATS = [
    ("MP3", 'mp3', False),
    ("WAV (uncompressed)", 'wav', False),
    ("FLAC (lossless)", 'flac', False),
    ("M4A (AAC)", 'm4a', False),
    ("OGG Vorbis", 'ogg', False),
    ("Opus", 'opus', False),
]


class TrimStudio(QWidget):
    """`host` must provide launch(task, params) and register_run_button(btn)."""

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.path = ""
        self.info = None
        self._probe = None
        self.engine = PlaybackEngine(self)
        self._build()
        self._wire()
        self._set_loaded(False)

    # ---------------------------------------------------------------- build #
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(10)

        # file bar
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.open_btn = button("Open…", "secondary", 'ph.folder-open',
                               tooltip="Open a video or audio file (Ctrl+O)")
        self.file_name = ElidedLabel("No file open", Qt.ElideMiddle)
        self.file_name.setObjectName("fileName")
        self.file_meta = ElidedLabel("", Qt.ElideRight)
        self.file_meta.setObjectName("meta")
        self.close_btn = tool_button('ph.x', "Close file")
        bar.addWidget(self.open_btn)
        bar.addWidget(self.file_name, 2)
        bar.addWidget(self.file_meta, 3)
        bar.addWidget(self.close_btn)
        root.addLayout(bar)

        # preview
        self.view = VideoView()
        self.view.setFocusPolicy(Qt.ClickFocus)
        root.addWidget(self.view, 1)

        # editor panel
        panel = QFrame()
        panel.setObjectName("editorPanel")
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(12, 10, 12, 12)
        pl.setSpacing(10)

        # transport
        self.to_in_btn = tool_button('ph.skip-back-fill', "Go to in point (Home)")
        self.prev_btn = tool_button('ph.caret-left', "Previous frame (Left)")
        self.play_btn = tool_button('ph.play-fill', "Play / pause (Space)", '#ffffff', px=14)
        self.play_btn.setObjectName("play")
        self.next_btn = tool_button('ph.caret-right', "Next frame (Right)")
        self.to_out_btn = tool_button('ph.skip-forward-fill', "Go to out point (End)")
        self.limit_btn = tool_button('ph.brackets-square', "Play only the selected range",
                                     checkable=True)
        self.limit_btn.setChecked(True)
        self.time_now = label("00:00:00.000", "timeReadout")
        self.time_total = label("/ 00:00:00.000", "timeReadoutDim")

        self.zoom_out_btn = tool_button('ph.magnifying-glass-minus', "Zoom out (-)")
        self.zoom_fit_btn = tool_button('ph.arrows-out-line-horizontal', "Show whole file")
        self.zoom_in_btn = tool_button('ph.magnifying-glass-plus', "Zoom in (+)")
        self.mute_btn = tool_button('ph.speaker-high', "Mute (M)", checkable=True)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(88)
        self.volume.setToolTip("Volume")
        self.volume.setCursor(Qt.PointingHandCursor)

        transport = FlowLayout(hspacing=10, vspacing=6)
        transport.addWidget(group(self.to_in_btn, self.prev_btn, self.play_btn,
                                  self.next_btn, self.to_out_btn, spacing=2))
        transport.addWidget(group(self.time_now, self.time_total, spacing=6))
        transport.addStretch()
        transport.addWidget(group(self.limit_btn, vsep(), self.zoom_out_btn,
                                  self.zoom_fit_btn, self.zoom_in_btn, spacing=2))
        transport.addWidget(group(self.mute_btn, self.volume, spacing=4))
        pl.addLayout(transport)

        # timeline
        self.timeline = TrimTimeline(theme='dark')
        self.timeline.set_palette(icons.palette())
        pl.addWidget(self.timeline)

        # in / out
        self.in_edit = TimecodeEdit()
        self.out_edit = TimecodeEdit()
        self.set_in_btn = button("Set in", "secondary", tooltip="Mark the in point at the playhead (I)")
        self.set_out_btn = button("Set out", "secondary", tooltip="Mark the out point at the playhead (O)")
        self.length_value = label("00:00:00.000", "readoutValue")
        self.reset_btn = button("Select all", "link", tooltip="Select the whole file")
        rng = FlowLayout(hspacing=18, vspacing=8)
        rng.addWidget(group(label("In", "formLabel"), self.in_edit, self.set_in_btn))
        rng.addWidget(group(label("Out", "formLabel"), self.out_edit, self.set_out_btn))
        rng.addWidget(group(label("Length", "formLabel"), self.length_value, spacing=8))
        rng.addStretch()
        rng.addWidget(self.reset_btn)
        pl.addLayout(rng)

        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        pl.addWidget(rule)

        # export
        self.mode = SegmentedControl([
            ("Fast copy", 'copy', "Lossless and near-instant; video cuts snap to keyframes"),
            ("Precise", 'precise', "Re-encode for a frame-exact cut"),
        ], default='copy')
        self.format = QComboBox()
        self.format.setMinimumWidth(190)
        self.export_btn = button("Export clip", "primary", 'ph.export')
        self.host.register_run_button(self.export_btn)
        exp = FlowLayout(hspacing=18, vspacing=8)
        exp.addWidget(group(label("Cut", "formLabel"), self.mode, spacing=8))
        exp.addWidget(group(label("Format", "formLabel"), self.format, spacing=8))
        exp.addStretch()
        exp.addWidget(self.export_btn)
        pl.addLayout(exp)
        self.mode_hint = hint("")
        pl.addWidget(self.mode_hint)

        root.addWidget(panel, 0)

    def _wire(self):
        self.open_btn.clicked.connect(self.open_dialog)
        self.close_btn.clicked.connect(self.unload)
        self.view.openRequested.connect(self.open_dialog)
        self.view.clicked.connect(self.toggle_play)
        self.view.filesDropped.connect(lambda paths: self.load(paths[0]))
        self.view.viewSizeChanged.connect(self.engine.set_view_size)

        self.engine.frameReady.connect(self.view.set_image)
        self.engine.positionChanged.connect(self._on_position)
        self.engine.playingChanged.connect(self._on_playing)

        self.play_btn.clicked.connect(self.toggle_play)
        self.prev_btn.clicked.connect(lambda: self.engine.step(-1))
        self.next_btn.clicked.connect(lambda: self.engine.step(1))
        self.to_in_btn.clicked.connect(lambda: self._seek(self.timeline.start()))
        self.to_out_btn.clicked.connect(lambda: self._seek(self.timeline.end()))
        self.limit_btn.toggled.connect(lambda _on: self._update_stop_point())
        self.zoom_in_btn.clicked.connect(lambda: self.timeline.zoom_by(1.6))
        self.zoom_out_btn.clicked.connect(lambda: self.timeline.zoom_by(1 / 1.6))
        self.zoom_fit_btn.clicked.connect(self.timeline.zoom_all)
        self.mute_btn.toggled.connect(self._on_mute)
        self.volume.valueChanged.connect(lambda v: self.engine.set_volume(v / 100.0))
        self.engine.set_volume(0.8)

        self.timeline.seekRequested.connect(self._seek)
        self.timeline.rangeChanged.connect(self._on_range)
        self.in_edit.timeEdited.connect(self.timeline.set_start)
        self.out_edit.timeEdited.connect(self.timeline.set_end)
        self.set_in_btn.clicked.connect(self.mark_in)
        self.set_out_btn.clicked.connect(self.mark_out)
        self.reset_btn.clicked.connect(self.timeline.reset_range)

        self.mode.changed.connect(lambda _v: self._update_mode_hint())
        self.format.currentIndexChanged.connect(lambda _i: self._on_format())
        self.export_btn.clicked.connect(self.export)

        keys = [
            ("Space", self.toggle_play), ("I", self.mark_in), ("O", self.mark_out),
            ("Left", lambda: self.engine.step(-1)), ("Right", lambda: self.engine.step(1)),
            ("Shift+Left", lambda: self._seek(self.engine.position() - 1000)),
            ("Shift+Right", lambda: self._seek(self.engine.position() + 1000)),
            ("Home", lambda: self._seek(self.timeline.start())),
            ("End", lambda: self._seek(self.timeline.end())),
            ("M", self.mute_btn.toggle), ("Ctrl+O", self.open_dialog),
            ("+", lambda: self.timeline.zoom_by(1.6)), ("=", lambda: self.timeline.zoom_by(1.6)),
            ("-", lambda: self.timeline.zoom_by(1 / 1.6)),
        ]
        for seq, slot in keys:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

    # -------------------------------------------------------------- loading #
    @staticmethod
    def _playable(path):
        # Unfamiliar extensions are let through; the probe in load() decides.
        return dnd.kind_of(path) in ('video', 'audio') or dnd.is_unknown_file(path)

    def accepts(self, paths):
        return any(self._playable(p) for p in paths)

    def take(self, paths):
        for p in paths:
            if self._playable(p):
                self.load(p)
                return True
        return False

    def open_dialog(self):
        start = os.path.dirname(self.path) if self.path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open video or audio", start, MEDIA_FILTER)
        if path:
            self.load(os.path.normpath(path))

    def load(self, path):
        self.engine.close()
        self.timeline.clear_media()
        self.path = path
        self.info = None
        self.file_name.setText(os.path.basename(path))
        self.file_meta.setText("Reading file…")
        self.view.show_loading(os.path.basename(path))
        self._set_loaded(False)
        self._probe = media.ProbeThread(path, self)
        self._probe.ready.connect(self._on_probed)
        self._probe.finished.connect(self._probe.deleteLater)
        self._probe.start()

    def _on_probed(self, path, info):
        if path != self.path:
            return                                  # another file was opened since
        if not info.ok or info.duration_ms <= 0:
            self.view.show_empty()
            self.file_meta.setText("")
            self.file_name.setText("No file open")
            self.path = ""
            QMessageBox.warning(self, "Can't open file",
                                f"{os.path.basename(path)} doesn't contain playable audio or video.")
            return
        self.info = info
        self.file_meta.setText("  ·  ".join(info.summary_chips()))

        self.timeline.set_duration(info.duration_ms)
        self.timeline.set_frame_ms(info.frame_ms)
        self.timeline.reset_range()
        self.timeline.set_media(path, info)
        self.in_edit.set_maximum(info.duration_ms)
        self.out_edit.set_maximum(info.duration_ms)
        self.time_total.setText("/ " + config.fmt_ms(info.duration_ms))

        if info.has_video:
            self.view.show_video()
        else:
            parts = [c for c in (info.acodec, f"{info.sample_rate / 1000:g} kHz" if info.sample_rate else "",
                                 config.fmt_clock(info.duration_ms)) if c]
            self.view.show_audio(os.path.basename(path), "  ·  ".join(parts))
        self.engine.open(path, info)
        self._fill_formats()
        self.mode.set_value('copy')
        self._set_loaded(True)
        self._update_stop_point()
        self.view.setFocus(Qt.OtherFocusReason)

    def unload(self):
        self.engine.close()
        self.timeline.clear_media()
        self.path = ""
        self.info = None
        self.file_name.setText("No file open")
        self.file_meta.setText("")
        self.view.show_empty()
        self.format.clear()
        self.time_now.setText(config.fmt_ms(0))
        self.time_total.setText("/ " + config.fmt_ms(0))
        self._set_loaded(False)

    def _set_loaded(self, loaded):
        for w in (self.to_in_btn, self.prev_btn, self.play_btn, self.next_btn, self.to_out_btn,
                  self.zoom_in_btn, self.zoom_out_btn, self.zoom_fit_btn, self.in_edit,
                  self.out_edit, self.set_in_btn, self.set_out_btn, self.reset_btn, self.mode,
                  self.format, self.close_btn, self.limit_btn):
            w.setEnabled(loaded)
        self.export_btn.setProperty('needsMedia', loaded)
        if not getattr(self.host, 'is_busy', lambda: False)():
            self.export_btn.setEnabled(loaded)
        if not loaded:
            self.mode_hint.setText("Open or drop a video or audio file to start. "
                                   "Space plays, I and O mark the in and out points.")

    # ------------------------------------------------------------- playback #
    def toggle_play(self):
        if not self.engine.has_media():
            return
        if self.engine.is_playing():
            self.engine.pause()
            return
        if self.limit_btn.isChecked():
            pos = self.engine.position()
            if pos < self.timeline.start() or pos >= self.timeline.end() - 5:
                self.engine.seek(self.timeline.start())
        self._update_stop_point()
        self.engine.play()

    def pause(self):
        self.engine.pause()

    def _seek(self, ms):
        self.engine.seek(ms)
        self._update_stop_point()

    def _update_stop_point(self):
        if not self.engine.has_media():
            return
        pos = self.engine.position()
        if self.limit_btn.isChecked() and pos < self.timeline.end():
            self.engine.set_stop_at(self.timeline.end())
        else:
            self.engine.set_stop_at(None)

    def _on_position(self, ms):
        self.timeline.set_position(ms)
        self.time_now.setText(config.fmt_ms(ms))

    def _on_playing(self, playing):
        icons.bind(self.play_btn, 'ph.pause-fill' if playing else 'ph.play-fill', '#ffffff', 14)

    def _on_mute(self, muted):
        self.engine.set_muted(muted)
        icons.bind(self.mute_btn, 'ph.speaker-x' if muted else 'ph.speaker-high', 'subtext', 16)

    def mark_in(self):
        if self.engine.has_media():
            self.timeline.set_start(self.engine.position())

    def mark_out(self):
        if self.engine.has_media():
            self.timeline.set_end(self.engine.position())

    def _on_range(self, start, end):
        self.in_edit.set_value(start)
        self.out_edit.set_value(end)
        self.length_value.setText(config.fmt_ms(max(0, end - start)))
        self._update_stop_point()

    # --------------------------------------------------------------- export #
    def _fill_formats(self):
        self.format.blockSignals(True)
        self.format.clear()
        src = os.path.splitext(self.path)[1].lstrip('.').lower()
        writable = config.WRITABLE_VIDEO if self.info.has_video else config.WRITABLE_AUDIO
        if src in writable:
            self.format.addItem(f"Same as source (.{src})", (None, False))
        else:
            # FFmpeg reads this container but can't write it: the worker keeps
            # the original streams in Matroska, or re-encodes to MP4 / MP3.
            self.format.addItem(f"Automatic (.{src} can't be written back)", (None, False))
        options = VIDEO_FORMATS if self.info.has_video else AUDIO_FORMATS
        for text, ext, audio_only in options:
            if ext == src and not audio_only:
                continue
            if audio_only and not self.info.has_audio:
                continue
            self.format.addItem(text, (ext, audio_only))
        self.format.setCurrentIndex(0)
        self.format.blockSignals(False)
        self._on_format()

    def _on_format(self):
        data = self.format.currentData()
        converting = bool(data and data[0])
        if converting:
            self.mode.set_value('precise')
        self.mode.set_option_enabled('copy', not converting)
        self._update_mode_hint()

    def _update_mode_hint(self):
        if not self.info:
            return
        data = self.format.currentData()
        if data and data[0]:
            self.mode_hint.setText("Changing the format re-encodes the clip, so the cut is exact.")
        elif self.mode.value() == 'copy':
            if self.info.has_video:
                self.mode_hint.setText("Fast copy keeps the original quality and is near-instant, "
                                       "but the clip starts on the nearest keyframe before the in point.")
            else:
                self.mode_hint.setText("Fast copy keeps the original audio untouched and is accurate "
                                       "to within a few milliseconds.")
        else:
            self.mode_hint.setText("Precise re-encodes the clip so it starts and ends exactly on your "
                                   "marks. Takes longer for long video clips.")

    def export(self):
        if not self.path or not os.path.isfile(self.path) or not self.info:
            QMessageBox.information(self, "Nothing to export", "Open a video or audio file first.")
            return
        start, end = self.timeline.start(), self.timeline.end()
        if end - start < self.timeline.MIN_GAP:
            QMessageBox.information(self, "Range too short", "Make the selection a little longer.")
            return
        self.engine.pause()
        ext, audio_only = self.format.currentData() or (None, False)
        self.host.launch('trim_media', {
            'input': self.path,
            'start_ms': start,
            'end_ms': end,
            'precise': self.mode.value() == 'precise',
            'out_ext': ext,
            'audio_only': audio_only,
            'has_video': self.info.has_video,
        })

    # ------------------------------------------------------------ lifecycle #
    def _fix_readout_sizes(self):
        # The clock changes every frame; a fixed-size label lets Qt skip
        # re-laying out the page on each update. Sized once styles apply.
        for lbl in (self.time_now, self.time_total):
            lbl.setMinimumSize(0, 0)
            lbl.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
            lbl.ensurePolished()
            hint = lbl.sizeHint()
            lbl.setFixedSize(hint.width() + 2, hint.height())

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, '_readouts_fixed', False):
            self._readouts_fixed = True
            self._fix_readout_sizes()

    def apply_theme(self, pal):
        self.timeline.set_palette(pal)
        self.view.update()

    def shutdown(self):
        self.engine.shutdown()
        self.timeline.shutdown()
