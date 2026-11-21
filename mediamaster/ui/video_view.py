"""The preview surface: paints decoded frames, letterboxed, and takes drops.

Frames arrive as QImages from the playback engine and are drawn scaled to fit
with the source aspect ratio. Being a plain painted widget (no native video
window), it composites correctly inside scroll areas and layouts at any DPI.
"""

from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QPainter, QColor, QFont, QPen

from . import dnd
from . import icons


class VideoView(dnd.DropTarget, QWidget):
    clicked = pyqtSignal()
    doubleClicked = pyqtSignal()
    openRequested = pyqtSignal()
    filesDropped = pyqtSignal(list)
    viewSizeChanged = pyqtSignal(int, int)          # device pixels

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 140)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._image = None
        self._mode = 'empty'            # 'empty' | 'video' | 'audio' | 'loading'
        self._title = ""
        self._subtitle = ""
        self._message = ""
        self.init_drops()

        self._size_timer = QTimer(self)
        self._size_timer.setSingleShot(True)
        self._size_timer.setInterval(200)
        self._size_timer.timeout.connect(self._emit_size)

    def sizeHint(self):
        # Small on purpose: the page lets it grow, and a short window then
        # scrolls only once the preview is at its minimum.
        return QSize(480, 200)

    # -- state ------------------------------------------------------------ #
    def set_image(self, image):
        # Frames are decoded at the view's device-pixel size; tagging them with
        # the ratio lets them be drawn 1:1 without a resample.
        image.setDevicePixelRatio(self.devicePixelRatioF())
        self._image = image
        if self._mode == 'loading':
            self._mode = 'video'
        self.update()

    def show_empty(self):
        self._mode = 'empty'
        self._image = None
        self._message = ""
        self.update()

    def show_loading(self, title):
        self._mode = 'loading'
        self._image = None
        self._title = title
        self._message = ""
        self.update()

    def show_video(self):
        self._mode = 'video'
        self.update()

    def show_audio(self, title, subtitle=""):
        self._mode = 'audio'
        self._image = None
        self._title = title
        self._subtitle = subtitle
        self.update()

    def set_message(self, text):
        """A short note drawn over the frame (e.g. 'preview unavailable')."""
        self._message = text or ""
        self.update()

    # -- drops ------------------------------------------------------------ #
    def drop_accepts(self, paths):
        return any(dnd.kind_of(p) in ('video', 'audio') for p in paths)

    def drop_handle(self, paths):
        self.filesDropped.emit([p for p in paths if dnd.kind_of(p) in ('video', 'audio')])

    # -- events ----------------------------------------------------------- #
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            if self._mode == 'empty':
                self.openRequested.emit()
            else:
                self.clicked.emit()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self._mode != 'empty':
            self.doubleClicked.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._size_timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        self._size_timer.start()

    def _emit_size(self):
        dpr = self.devicePixelRatioF()
        self.viewSizeChanged.emit(int(self.width() * dpr), int(self.height() * dpr))

    # -- painting --------------------------------------------------------- #
    def paintEvent(self, _e):
        pal = icons.palette()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(pal['video_bg']))
        drop_on = self.property('dropActive') == "true"

        if self._image is not None and not self._image.isNull() and self._mode == 'video':
            dpr = self._image.devicePixelRatioF() or 1.0
            iw, ih = self._image.width() / dpr, self._image.height() / dpr
            scale = min(self.width() / iw, self.height() / ih)
            w, h = iw * scale, ih * scale
            x, y = (self.width() - w) / 2, (self.height() - h) / 2
            if 0.985 < scale < 1.015:
                p.drawImage(QPointF(round((self.width() - iw) / 2), round((self.height() - ih) / 2)),
                            self._image)
            else:
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(QRectF(x, y, w, h), self._image)
        elif self._mode == 'empty':
            self._paint_empty(p, pal)
        elif self._mode == 'audio':
            self._paint_audio(p, pal)
        elif self._mode == 'loading':
            self._paint_caption(p, pal, 'ph.film-strip', self._title, "Loading preview…")

        if self._message:
            self._paint_message(p)
        if drop_on:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor(pal['accent']), 2))
            p.setBrush(QColor(61, 126, 240, 40))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 4, 4)
        p.end()

    def _paint_caption(self, p, pal, icon_name, title, sub):
        p.setRenderHint(QPainter.Antialiasing, True)
        cy = self.height() / 2
        px = icons.pixmap(icon_name, '#6f747c', 36)
        dpr = px.devicePixelRatioF() or 1.0
        pw, ph = px.width() / dpr, px.height() / dpr
        p.drawPixmap(int(self.width() / 2 - pw / 2), int(cy - ph - 8), px)
        f = QFont(self.font())
        f.setPixelSize(14)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor('#d5d7db'))
        fm = p.fontMetrics()
        p.drawText(QRectF(16, cy + 2, self.width() - 32, 22), Qt.AlignHCenter | Qt.AlignTop,
                   fm.elidedText(title, Qt.ElideMiddle, self.width() - 32))
        if sub:
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(QColor('#8a8f97'))
            p.drawText(QRectF(16, cy + 24, self.width() - 32, 20), Qt.AlignHCenter | Qt.AlignTop, sub)

    def _paint_empty(self, p, pal):
        p.setRenderHint(QPainter.Antialiasing, True)
        box = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        pen = QPen(QColor(255, 255, 255, 38), 1, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box, 6, 6)
        self._paint_caption(p, pal, 'ph.upload-simple', "Drop a video or audio file here",
                            "or click to open one")

    def _paint_audio(self, p, pal):
        self._paint_caption(p, pal, 'ph.music-notes', self._title, self._subtitle)

    def _paint_message(self, p):
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        fm = p.fontMetrics()
        w = min(self.width() - 24, fm.horizontalAdvance(self._message) + 24)
        rect = QRectF((self.width() - w) / 2, 12, w, 26)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QColor('#e6e6e6'))
        p.drawText(rect, Qt.AlignCenter, fm.elidedText(self._message, Qt.ElideRight, int(w - 16)))
