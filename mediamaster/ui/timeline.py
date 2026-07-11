"""A custom timeline widget: playhead scrubbing + draggable in/out handles."""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath

from .theme import THEMES


class TrimTimeline(QWidget):
    """
    Shows the full media duration as a track. The user can:
      * click / drag anywhere to move the playhead (seek)
      * drag the green (start) and blue (end) handles to set the trim range
    Emits seekRequested(ms) and rangeChanged(start_ms, end_ms).
    """

    seekRequested = pyqtSignal(int)
    rangeChanged = pyqtSignal(int, int)

    PAD = 12            # left/right padding so handles never clip
    MIN_GAP = 200       # minimum trim length in ms

    def __init__(self, theme='dark'):
        super().__init__()
        self._dur = 0
        self._pos = 0
        self._start = 0
        self._end = 0
        self._drag = None          # 'start' | 'end' | 'seek' | None
        self.pal = THEMES[theme]
        self.setMinimumHeight(74)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # -- palette ---------------------------------------------------------- #
    def set_palette(self, pal):
        self.pal = pal
        self.update()

    # -- state setters ---------------------------------------------------- #
    def set_duration(self, ms):
        self._dur = max(0, int(ms))
        if self._end == 0 or self._end > self._dur:
            self._end = self._dur
        self._start = min(self._start, max(0, self._end - self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_position(self, ms):
        self._pos = max(0, min(int(ms), self._dur))
        self.update()

    def set_start(self, ms):
        self._start = max(0, min(int(ms), self._end - self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_end(self, ms):
        self._end = min(self._dur, max(int(ms), self._start + self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def reset_range(self):
        self._start = 0
        self._end = self._dur
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def start(self):
        return self._start

    def end(self):
        return self._end

    def duration(self):
        return self._dur

    # -- geometry --------------------------------------------------------- #
    def _usable(self):
        return max(1, self.width() - 2 * self.PAD)

    def _ms_to_x(self, ms):
        if self._dur <= 0:
            return self.PAD
        return self.PAD + (ms / self._dur) * self._usable()

    def _x_to_ms(self, x):
        if self._dur <= 0:
            return 0
        frac = (x - self.PAD) / self._usable()
        return int(max(0, min(1.0, frac)) * self._dur)

    # -- painting --------------------------------------------------------- #
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        mid = h / 2
        track_h = 10

        # base track
        track = QRectF(self.PAD, mid - track_h / 2, w - 2 * self.PAD, track_h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.pal['track']))
        p.drawRoundedRect(track, 5, 5)

        if self._dur <= 0:
            p.setPen(QColor(self.pal['subtext']))
            p.drawText(self.rect(), Qt.AlignCenter, "Load media to see the timeline")
            return

        xs = self._ms_to_x(self._start)
        xe = self._ms_to_x(self._end)

        # selected range band
        band = QRectF(xs, mid - track_h / 2, max(1.0, xe - xs), track_h)
        grad = QColor(self.pal['accent'])
        p.setBrush(grad)
        p.drawRoundedRect(band, 5, 5)

        # start / end handles (tall rounded bars)
        self._draw_handle(p, xs, h, QColor(self.pal['success']))
        self._draw_handle(p, xe, h, QColor(self.pal['accent']))

        # playhead
        xp = self._ms_to_x(self._pos)
        pen = QPen(QColor('#ffffff'), 2)
        p.setPen(pen)
        p.drawLine(int(xp), 8, int(xp), h - 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(xp - 5, mid - 5, 10, 10))

    def _draw_handle(self, p, x, h, color):
        bar_w = 8
        rect = QRectF(x - bar_w / 2, 6, bar_w, h - 12)
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
        # grip notch
        p.setPen(QPen(QColor(255, 255, 255, 180), 1))
        cx = x
        p.drawLine(int(cx), int(h / 2 - 6), int(cx), int(h / 2 + 6))

    # -- interaction ------------------------------------------------------ #
    def _nearest(self, x):
        xs = self._ms_to_x(self._start)
        xe = self._ms_to_x(self._end)
        ds = abs(x - xs)
        de = abs(x - xe)
        if ds <= 12 or de <= 12:
            return 'start' if ds <= de else 'end'
        return 'seek'

    def mousePressEvent(self, e):
        if self._dur <= 0:
            return
        x = e.pos().x()
        self._drag = self._nearest(x)
        if self._drag == 'seek':
            self._pos = self._x_to_ms(x)
            self.update()
            self.seekRequested.emit(self._pos)
        else:
            self._apply_handle(x)

    def mouseMoveEvent(self, e):
        if self._drag is None or self._dur <= 0:
            return
        x = e.pos().x()
        if self._drag == 'seek':
            self._pos = self._x_to_ms(x)
            self.update()
            self.seekRequested.emit(self._pos)
        else:
            self._apply_handle(x)

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def _apply_handle(self, x):
        ms = self._x_to_ms(x)
        if self._drag == 'start':
            self._start = max(0, min(ms, self._end - self.MIN_GAP))
        else:
            self._end = min(self._dur, max(ms, self._start + self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)
