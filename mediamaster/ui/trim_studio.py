"""Trim Studio: play/scrub media and pick exact in/out points, then trim."""

import os

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
    QCheckBox, QFileDialog, QMessageBox, QSizePolicy, QStackedLayout
)
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QPalette, QColor

from .icons import fa
from .widgets import make_card, field
from .timeline import TrimTimeline
from ..core import config

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    HAS_MEDIA = True
except Exception:
    HAS_MEDIA = False


class TrimStudio(QWidget):
    """
    A self-contained trimming page. `host` must provide:
      * launch(task, params)        -> start a Worker on the shared progress bar
      * register_run_button(button) -> disable it while a task runs
    """

    MEDIA_FILTER = ("Media (*.mp4 *.avi *.mkv *.mov *.webm *.m4v *.flv *.wmv "
                    "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus)")

    def __init__(self, host, theme_palette):
        super().__init__()
        self.host = host
        self.pal = theme_palette
        self.path = ""
        self.player = None
        self._build()

    # -- construction ----------------------------------------------------- #
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(16)

        card, lay = make_card("Trim studio")

        # open row
        open_row = QHBoxLayout()
        self.file_label = QLabel("No media loaded")
        self.file_label.setObjectName("hint")
        open_btn = QPushButton("  Open media…")
        open_btn.setObjectName("ghost")
        open_btn.setIcon(fa('fa5s.folder-open', "#8b93a3"))
        open_btn.setIconSize(QSize(15, 15))
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self._open)
        open_row.addWidget(open_btn)
        open_row.addWidget(self.file_label, 1)
        lay.addLayout(open_row)

        # video area: a single-page stack showing EITHER the hint OR the video
        self.video_frame = QFrame()
        self.video_frame.setObjectName("videoFrame")
        self.video_frame.setMinimumHeight(300)
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.vstack = QStackedLayout(self.video_frame)   # default: StackOne
        self.vstack.setContentsMargins(0, 0, 0, 0)
        self.video_hint = QLabel("Open a video or audio file to preview it here")
        self.video_hint.setObjectName("videoHint")
        self.video_hint.setAlignment(Qt.AlignCenter)
        self.vstack.addWidget(self.video_hint)           # index 0

        if HAS_MEDIA:
            self.video_widget = QVideoWidget()
            pal = self.video_widget.palette()
            pal.setColor(QPalette.Window, QColor('#05060a'))
            self.video_widget.setAutoFillBackground(True)
            self.video_widget.setPalette(pal)
            self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self.player.setVideoOutput(self.video_widget)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
            self.player.stateChanged.connect(self._on_state)
            if hasattr(self.player, 'error'):
                self.player.error.connect(self._on_media_error)
            self.vstack.addWidget(self.video_widget)     # index 1
        self.vstack.setCurrentIndex(0)
        lay.addWidget(self.video_frame, 1)

        # controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("playbtn")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setIcon(fa('fa5s.play', "#ffffff"))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.clicked.connect(self._toggle_play)
        self.time_readout = QLabel("0:00 / 0:00")
        self.time_readout.setObjectName("timeReadout")
        ctrl.addWidget(self.play_btn)
        ctrl.addWidget(self.time_readout)
        ctrl.addStretch()
        set_start = QPushButton("  Set start")
        set_start.setObjectName("ghost")
        set_start.setIcon(fa('fa5s.step-backward', self.pal['success']))
        set_start.setCursor(Qt.PointingHandCursor)
        set_start.clicked.connect(self._set_start_here)
        set_end = QPushButton("  Set end")
        set_end.setObjectName("ghost")
        set_end.setIcon(fa('fa5s.step-forward', self.pal['accent']))
        set_end.setCursor(Qt.PointingHandCursor)
        set_end.clicked.connect(self._set_end_here)
        reset = QPushButton("Reset")
        reset.setObjectName("ghost")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset)
        ctrl.addWidget(set_start)
        ctrl.addWidget(set_end)
        ctrl.addWidget(reset)
        lay.addLayout(ctrl)

        # timeline
        self.timeline = TrimTimeline(theme='dark')
        self.timeline.set_palette(self.pal)
        self.timeline.seekRequested.connect(self._on_seek)
        self.timeline.rangeChanged.connect(self._on_range)
        lay.addWidget(self.timeline)

        # in/out chips
        chips = QHBoxLayout()
        self.start_chip = QLabel("Start  00:00:00.000")
        self.start_chip.setObjectName("chipStart")
        self.end_chip = QLabel("End  00:00:00.000")
        self.end_chip.setObjectName("chipEnd")
        self.len_chip = QLabel("Length  0.000s")
        self.len_chip.setObjectName("hint")
        chips.addWidget(self.start_chip)
        chips.addStretch()
        chips.addWidget(self.len_chip)
        chips.addStretch()
        chips.addWidget(self.end_chip)
        lay.addLayout(chips)

        # options + trim
        bottom = QHBoxLayout()
        self.precise = QCheckBox("Precise cut (re-encode — exact, a little slower)")
        self.precise.setCursor(Qt.PointingHandCursor)
        bottom.addWidget(self.precise)
        bottom.addStretch()
        self.trim_btn = QPushButton("  Trim & Save")
        self.trim_btn.setObjectName("primary")
        self.trim_btn.setIcon(fa('fa5s.cut', "#ffffff"))
        self.trim_btn.setIconSize(QSize(16, 16))
        self.trim_btn.setCursor(Qt.PointingHandCursor)
        self.trim_btn.clicked.connect(self._trim)
        bottom.addWidget(self.trim_btn)
        lay.addLayout(bottom)

        if host_has := getattr(self.host, "register_run_button", None):
            host_has(self.trim_btn)

        if not HAS_MEDIA:
            self.video_hint.setText("Media preview needs QtMultimedia. Trimming still works.")

        outer.addWidget(card, 1)

    # -- theme ------------------------------------------------------------ #
    def apply_theme(self, pal):
        self.pal = pal
        self.timeline.set_palette(pal)

    # -- media loading ---------------------------------------------------- #
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open media", "", self.MEDIA_FILTER)
        if path:
            self.load(path)

    def load(self, path):
        self.path = path
        self.file_label.setText(os.path.basename(path))

        # Activate the timeline immediately from FFmpeg's own duration read.
        # This is independent of Qt's media backend, so the user can always
        # scrub and set in/out points even if the preview can't decode.
        dur = config.probe_duration_ms(path)
        if dur > 0:
            self.timeline.set_duration(dur)
            self.timeline.reset_range()
            self._update_readout(0)
        else:
            self.timeline.set_duration(0)

        if self.player is not None:
            self.vstack.setCurrentIndex(1)          # show the video surface
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.player.pause()

    # -- playback --------------------------------------------------------- #
    def _toggle_play(self):
        if self.player is None:
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            pos = self.player.position()
            if pos < self.timeline.start() or pos >= self.timeline.end():
                self.player.setPosition(self.timeline.start())
            self.player.play()

    def _on_state(self, state):
        playing = (state == QMediaPlayer.PlayingState)
        self.play_btn.setIcon(fa('fa5s.pause' if playing else 'fa5s.play', "#ffffff"))

    def _on_media_error(self, *_a):
        # Preview couldn't decode this file, but trimming via FFmpeg still works.
        self.video_hint.setText("Preview unavailable for this file — "
                                "you can still scrub the timeline and trim.")
        self.vstack.setCurrentIndex(0)

    def _on_position(self, ms):
        self.timeline.set_position(ms)
        self._update_readout(ms)
        # stop preview at the out-point
        if (self.player is not None
                and self.player.state() == QMediaPlayer.PlayingState
                and ms >= self.timeline.end() > 0):
            self.player.pause()
            self.player.setPosition(self.timeline.end())

    def _on_duration(self, ms):
        # Some Qt backends emit 0 (or a late value) before the real duration.
        # Only trust a positive value, and never let it wipe an FFmpeg-probed
        # timeline back to zero.
        if ms and ms > 0:
            keep_start = self.timeline.start()
            keep_end = self.timeline.end()
            self.timeline.set_duration(ms)
            if keep_end > 0:
                self.timeline.set_start(keep_start)
                self.timeline.set_end(min(keep_end, ms))
        self._update_readout(self.player.position() if self.player else 0)

    def _update_readout(self, ms):
        dur = self.timeline.duration()
        self.time_readout.setText(f"{config.fmt_clock(ms)} / {config.fmt_clock(dur)}")

    # -- markers ---------------------------------------------------------- #
    def _current_ms(self):
        return self.player.position() if self.player else self.timeline._pos

    def _set_start_here(self):
        self.timeline.set_start(self._current_ms())

    def _set_end_here(self):
        self.timeline.set_end(self._current_ms())

    def _reset(self):
        self.timeline.reset_range()

    def _on_seek(self, ms):
        if self.player is not None:
            self.player.setPosition(ms)
        self._update_readout(ms)

    def _on_range(self, start, end):
        self.start_chip.setText("Start  " + config.fmt_ms(start))
        self.end_chip.setText("End  " + config.fmt_ms(end))
        self.len_chip.setText(f"Length  {(end-start)/1000:.3f}s")

    # -- trim ------------------------------------------------------------- #
    def _trim(self):
        if not self.path or not os.path.isfile(self.path):
            QMessageBox.warning(self, "No media", "Open a media file first.")
            return
        start = self.timeline.start()
        end = self.timeline.end()
        if end - start < self.timeline.MIN_GAP:
            QMessageBox.warning(self, "Range too short", "Make the trim range a little longer.")
            return
        params = {
            'input': self.path,
            'start': config.fmt_ms(start),
            'end': config.fmt_ms(end),
            'reencode': self.precise.isChecked(),
        }
        self.host.launch('trim_media', params)
