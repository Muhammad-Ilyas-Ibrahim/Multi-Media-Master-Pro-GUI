"""The trim timeline: time ruler, filmstrip, in/out selection, zoom and pan.

Layout, top to bottom:
    ruler     time ticks and labels, plus the playhead marker
    track     filmstrip (or audio waveform) with the selection drawn over it
    overview  the whole file, showing where the zoomed view sits

Everything is in milliseconds; `_view_start`/`_view_end` define the visible
window, so zooming is just narrowing that window.
"""

from PyQt5.QtWidgets import QWidget, QMenu
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QRect, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QPainterPath, QFont

from .theme import THEMES
from ..core import config
from ..core import media

# Candidate ruler steps in ms, coarsest-last.
_TICK_STEPS = [
    50, 100, 200, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000,
    60000, 120000, 300000, 600000, 900000, 1800000, 3600000, 7200000,
]


class TrimTimeline(QWidget):
    """Scrub, mark in/out, and zoom into a media file's duration.

    Mouse:
        click / drag on the ruler or track   move the playhead
        drag a handle                        move the in or out point
        drag inside the selection            slide the whole selection
        drag on the overview                 pan the zoomed view
        wheel                                zoom around the cursor
        shift + wheel                        pan
        double-click                         zoom to selection / zoom out
        right-click                          set in/out, zoom actions
    Hold Shift while dragging a handle to bypass snapping.
    """

    seekRequested = pyqtSignal(int)
    rangeChanged = pyqtSignal(int, int)
    viewChanged = pyqtSignal(int, int)

    PAD = 10                # left/right padding so handles never clip
    MIN_GAP = 40            # minimum trim length in ms
    HANDLE_GRAB = 7         # px either side of a handle that grabs it
    SNAP_PX = 6             # snap distance in px
    MIN_VIEW_MS = 250       # don't zoom in tighter than this

    RULER_H = 15
    TRACK_TOP = 19
    TRACK_H = 58
    OVERVIEW_H = 11
    OVERVIEW_GAP = 7

    def __init__(self, theme='dark', parent=None):
        super().__init__(parent)
        self._dur = 0
        self._pos = 0
        self._start = 0
        self._end = 0
        self._view_start = 0
        self._view_end = 0
        self._frame_ms = 40.0

        self._drag = None               # 'start'|'end'|'body'|'seek'|'view'|None
        self._drag_anchor_ms = 0
        self._drag_span = 0
        self._hover_x = None

        self._path = ""
        self._tiles = {}                # index -> QPixmap
        self._strip_count = 0
        self._strip_range = (0, 0)
        self._strip_thread = None
        self._wave = None               # QPixmap for audio-only media
        self._wave_thread = None
        self._backdrop_state = ""       # "", 'loading', 'ready', 'none'

        self.pal = THEMES[theme] if theme in THEMES else THEMES['dark']
        self.setMinimumHeight(self.TRACK_TOP + self.TRACK_H
                              + self.OVERVIEW_GAP + self.OVERVIEW_H + 2)
        self.setMinimumWidth(240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        # Regenerating the backdrop on every zoom step would thrash FFmpeg.
        self._strip_timer = QTimer(self)
        self._strip_timer.setSingleShot(True)
        self._strip_timer.setInterval(450)
        self._strip_timer.timeout.connect(self._refresh_backdrop)

    # ------------------------------------------------------------- palette #
    def set_palette(self, pal):
        self.pal = pal
        if self._wave is not None and self._path:
            self._start_waveform()      # recolour to the new accent
        self.update()

    # --------------------------------------------------------------- state #
    def set_duration(self, ms):
        self._dur = max(0, int(ms))
        if self._end == 0 or self._end > self._dur:
            self._end = self._dur
        self._start = min(self._start, max(0, self._end - self.MIN_GAP))
        self.zoom_all(quiet=True)
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_frame_ms(self, frame_ms):
        self._frame_ms = max(1.0, float(frame_ms))

    def set_position(self, ms):
        self._pos = max(0, min(int(ms), self._dur))
        # Keep the playhead in sight while zoomed in and playing.
        if self._drag is None and self._dur > 0:
            span = self._view_end - self._view_start
            if span > 0 and span < self._dur:
                if self._pos > self._view_end:
                    self._set_view(self._pos - span * 0.1, self._pos + span * 0.9)
                elif self._pos < self._view_start:
                    self._set_view(self._pos - span * 0.1, self._pos + span * 0.9)
        self.update()

    def set_start(self, ms):
        self._start = max(0, min(int(ms), self._end - self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_end(self, ms):
        self._end = min(self._dur, max(int(ms), self._start + self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_range(self, start, end):
        start = max(0, int(start))
        end = min(self._dur, int(end))
        if end - start < self.MIN_GAP:
            end = min(self._dur, start + self.MIN_GAP)
        self._start, self._end = start, end
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

    def selection_ms(self):
        return max(0, self._end - self._start)

    # ------------------------------------------------------------ backdrop #
    def set_media(self, path, info=None):
        """Point the timeline at a file and build its visual backdrop."""
        self._stop_threads()
        self._path = path or ""
        self._tiles = {}
        self._strip_count = 0
        self._strip_range = (0, 0)
        self._wave = None
        self._backdrop_state = ""
        if not self._path or self._dur <= 0:
            self.update()
            return
        has_video = bool(info.has_video) if info is not None else True
        if has_video:
            self._start_filmstrip(self._view_start, self._view_end)
        elif info is None or info.has_audio:
            self._start_waveform()
        else:
            self._backdrop_state = 'none'
        self.update()

    def clear_media(self):
        self._stop_threads()
        self._path = ""
        self._tiles = {}
        self._wave = None
        self._strip_count = 0
        self._strip_range = (0, 0)
        self._backdrop_state = ""
        self._dur = 0
        self._pos = 0
        self._start = 0
        self._end = 0
        self._view_start = self._view_end = 0
        self.update()

    def _stop_threads(self):
        for attr in ('_strip_thread', '_wave_thread'):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            for signal_name in ('tile', 'strip', 'ready'):
                signal = getattr(thread, signal_name, None)
                if signal is None:
                    continue
                try:
                    signal.disconnect()
                except TypeError:
                    pass                    # nothing was connected
            thread.stop()
            thread.wait(1500)
            setattr(self, attr, None)
        self._strip_timer.stop()

    def shutdown(self):
        """Stop background FFmpeg work. Called when the app closes."""
        self._stop_threads()

    def _tile_slot_w(self):
        for pm in self._tiles.values():
            if not pm.isNull() and pm.width() > 0:
                return pm.width()
        return int(self.TRACK_H * 16 / 9)

    def _start_filmstrip(self, start_ms, end_ms):
        if not self._path or self._dur <= 0:
            return
        if self._strip_thread is not None:
            self._strip_thread.stop()
            self._strip_thread.wait(1200)
            self._strip_thread = None
        width = max(1, self.width() - 2 * self.PAD)
        count = max(6, min(64, int(width / max(32, self._tile_slot_w())) + 2))
        self._tiles = {}
        self._backdrop_state = 'loading'
        self._strip_thread = media.FilmstripThread(
            self._path, start_ms, end_ms, count, height=self.TRACK_H - 2, parent=self)
        self._strip_thread.strip.connect(self._on_strip_started)
        self._strip_thread.tile.connect(self._on_tile)
        self._strip_thread.start()

    def _on_strip_started(self, count, start_ms, end_ms):
        self._strip_count = count
        self._strip_range = (start_ms, end_ms)
        self.update()

    def _on_tile(self, index, image):
        if image is None or image.isNull():
            return
        self._tiles[index] = QPixmap.fromImage(image)
        self._backdrop_state = 'ready'
        self.update()

    def _start_waveform(self):
        if not self._path or self._dur <= 0:
            return
        if self._dur > media.WaveformThread.MAX_DURATION_MS:
            self._backdrop_state = 'none'
            return
        if self._wave_thread is not None:
            self._wave_thread.stop()
            self._wave_thread.wait(1200)
            self._wave_thread = None
        self._backdrop_state = 'loading'
        self._wave_thread = media.WaveformThread(
            self._path, width=1600, height=self.TRACK_H - 6,
            color=self.pal['accent'], parent=self)
        self._wave_thread.ready.connect(self._on_wave)
        self._wave_thread.start()

    def _on_wave(self, image):
        if image is None or image.isNull():
            self._backdrop_state = 'none'
            return
        self._wave = QPixmap.fromImage(image)
        self._backdrop_state = 'ready'
        self.update()

    def _refresh_backdrop(self):
        """After a zoom settles, re-cut the filmstrip for the visible range."""
        if not self._path or self._wave is not None or self._dur <= 0:
            return
        strip_span = self._strip_range[1] - self._strip_range[0]
        view_span = self._view_end - self._view_start
        if view_span <= 0:
            return
        covered = (self._strip_range[0] <= self._view_start
                   and self._strip_range[1] >= self._view_end)
        # Re-cut when the view has moved off the strip, or zoomed well into it.
        if not covered or (strip_span > 0 and view_span < strip_span * 0.6):
            self._start_filmstrip(self._view_start, self._view_end)

    # ------------------------------------------------------------ zoom/pan #
    def _set_view(self, start, end, quiet=False):
        if self._dur <= 0:
            self._view_start = self._view_end = 0
            return
        span = max(self.MIN_VIEW_MS, min(float(end - start), float(self._dur)))
        start = max(0.0, min(float(start), self._dur - span))
        self._view_start = int(round(start))
        self._view_end = int(round(start + span))
        self.update()
        if not quiet:
            self.viewChanged.emit(self._view_start, self._view_end)
            self._strip_timer.start()

    def zoom_all(self, quiet=False):
        self._set_view(0, self._dur, quiet=quiet)

    def zoom_to_selection(self):
        if self._dur <= 0:
            return
        span = max(self.MIN_VIEW_MS, self._end - self._start)
        margin = span * 0.08
        self._set_view(self._start - margin, self._end + margin)

    def is_zoomed(self):
        return self._dur > 0 and (self._view_end - self._view_start) < self._dur

    def zoom_by(self, factor, pivot_ms=None):
        if self._dur <= 0:
            return
        span = self._view_end - self._view_start
        if span <= 0:
            return
        if pivot_ms is None:
            pivot_ms = self._pos
        pivot_ms = max(self._view_start, min(pivot_ms, self._view_end))
        frac = (pivot_ms - self._view_start) / span if span else 0.5
        new_span = max(self.MIN_VIEW_MS, min(span / factor, self._dur))
        self._set_view(pivot_ms - frac * new_span, pivot_ms - frac * new_span + new_span)

    def pan_by(self, ms):
        span = self._view_end - self._view_start
        if span <= 0:
            return
        self._set_view(self._view_start + ms, self._view_end + ms)

    # ------------------------------------------------------------ geometry #
    def _track_rect(self):
        return QRectF(self.PAD, self.TRACK_TOP,
                      max(1, self.width() - 2 * self.PAD), self.TRACK_H)

    def _overview_rect(self):
        y = self.TRACK_TOP + self.TRACK_H + self.OVERVIEW_GAP
        return QRectF(self.PAD, y, max(1, self.width() - 2 * self.PAD), self.OVERVIEW_H)

    def _usable(self):
        return max(1, self.width() - 2 * self.PAD)

    def _view_span(self):
        span = self._view_end - self._view_start
        return span if span > 0 else max(1, self._dur)

    def _ms_to_x(self, ms):
        if self._dur <= 0:
            return float(self.PAD)
        return self.PAD + ((ms - self._view_start) / self._view_span()) * self._usable()

    def _x_to_ms(self, x):
        if self._dur <= 0:
            return 0
        frac = (x - self.PAD) / self._usable()
        return int(round(self._view_start + frac * self._view_span()))

    def _ms_to_x_full(self, ms):
        if self._dur <= 0:
            return float(self.PAD)
        return self.PAD + (ms / self._dur) * self._usable()

    def _x_to_ms_full(self, x):
        if self._dur <= 0:
            return 0
        frac = (x - self.PAD) / self._usable()
        return int(round(max(0.0, min(1.0, frac)) * self._dur))

    def _px_per_ms(self):
        return self._usable() / float(self._view_span())

    # ------------------------------------------------------------- painting #
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pal = self.pal

        if self._dur <= 0:
            track = self._track_rect()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal['track']))
            p.drawRoundedRect(track, 4, 4)
            p.setPen(QColor(pal['muted']))
            p.drawText(track, Qt.AlignCenter, "Load media to see the timeline")
            return

        self._paint_ruler(p)
        self._paint_track(p)
        self._paint_overview(p)

    # -- ruler ------------------------------------------------------------ #
    def _pick_step(self):
        px_per_ms = self._px_per_ms()
        for step in _TICK_STEPS:
            if step * px_per_ms >= 72:
                return step
        return _TICK_STEPS[-1]

    def _paint_ruler(self, p):
        pal = self.pal
        step = self._pick_step()
        font = QFont(p.font())
        font.setPointSizeF(7.5)
        font.setFamily('Consolas')
        p.setFont(font)

        first = (self._view_start // step) * step
        t = first
        baseline = self.RULER_H
        while t <= self._view_end + step:
            x = self._ms_to_x(t)
            if x >= self.PAD - 1 and x <= self.width() - self.PAD + 1 and t >= 0:
                p.setPen(QPen(QColor(pal['border_strong']), 1))
                p.drawLine(int(x), baseline - 4, int(x), baseline)
                p.setPen(QColor(pal['muted']))
                label = self._tick_label(t, step)
                box = QRect(int(x) - 32, 0, 64, baseline - 4)
                align = Qt.AlignVCenter | Qt.AlignHCenter
                if x - 32 < self.PAD:
                    box = QRect(int(self.PAD), 0, 64, baseline - 4)
                    align = Qt.AlignVCenter | Qt.AlignLeft
                elif x + 32 > self.width() - self.PAD:
                    box = QRect(int(self.width() - self.PAD - 64), 0, 64, baseline - 4)
                    align = Qt.AlignVCenter | Qt.AlignRight
                p.drawText(box, align, label)
                # midpoint tick
                mx = self._ms_to_x(t + step / 2.0)
                if mx < self.width() - self.PAD:
                    p.setPen(QPen(QColor(pal['border']), 1))
                    p.drawLine(int(mx), baseline - 2, int(mx), baseline)
            t += step

    @staticmethod
    def _tick_label(ms, step):
        total = max(0, int(ms))
        h = total // 3600000
        m = (total % 3600000) // 60000
        s = (total % 60000) // 1000
        frac = total % 1000
        if step < 1000:
            return f"{m}:{s:02d}.{frac // 100}"
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    # -- track ------------------------------------------------------------ #
    def _paint_track(self, p):
        pal = self.pal
        track = self._track_rect()

        clip = QPainterPath()
        clip.addRoundedRect(track, 4, 4)
        p.save()
        p.setClipPath(clip)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal['video_bg'] if self._path else pal['track']))
        p.drawRect(track)

        if self._wave is not None:
            self._paint_waveform(p, track)
        elif self._tiles:
            self._paint_filmstrip(p, track)
        elif self._backdrop_state == 'loading':
            p.setPen(QColor(pal['muted']))
            p.drawText(track, Qt.AlignCenter, "Building preview…")

        # Dim everything outside the selection so the kept part stands out.
        xs = self._ms_to_x(self._start)
        xe = self._ms_to_x(self._end)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 132))
        if xs > track.left():
            p.drawRect(QRectF(track.left(), track.top(),
                              min(xs, track.right()) - track.left(), track.height()))
        if xe < track.right():
            p.drawRect(QRectF(max(xe, track.left()), track.top(),
                              track.right() - max(xe, track.left()), track.height()))
        p.restore()

        # Selection outline
        sel_left = max(xs, track.left())
        sel_right = min(xe, track.right())
        if sel_right > sel_left:
            p.setPen(QPen(QColor(pal['accent']), 2))
            p.setBrush(Qt.NoBrush)
            p.drawLine(int(sel_left), int(track.top() + 1), int(sel_right), int(track.top() + 1))
            p.drawLine(int(sel_left), int(track.bottom() - 1), int(sel_right), int(track.bottom() - 1))

        # Frame
        p.setPen(QPen(QColor(pal['border']), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(track, 4, 4)

        self._paint_handle(p, xs, track, 'start')
        self._paint_handle(p, xe, track, 'end')
        self._paint_hover(p, track)
        self._paint_playhead(p, track)

    def _paint_filmstrip(self, p, track):
        strip_start, strip_end = self._strip_range
        strip_span = strip_end - strip_start
        if strip_span <= 0 or self._strip_count <= 0:
            return
        slot_w = max(24, self._tile_slot_w())
        x = track.left()
        while x < track.right():
            w = min(slot_w, track.right() - x)
            t = self._x_to_ms(x + w / 2.0)
            if strip_start <= t <= strip_end:
                idx = int((t - strip_start) / strip_span * self._strip_count)
                idx = max(0, min(self._strip_count - 1, idx))
                pm = self._tiles.get(idx)
                if pm is not None and not pm.isNull():
                    # Centre-crop the tile into its slot so nothing is squashed.
                    src_w = min(pm.width(), max(1, int(w * pm.height() / track.height())))
                    src_x = max(0, (pm.width() - src_w) // 2)
                    p.drawPixmap(QRectF(x, track.top() + 1, w, track.height() - 2),
                                 pm, QRectF(src_x, 0, src_w, pm.height()))
            x += slot_w

    def _paint_waveform(self, p, track):
        if self._dur <= 0:
            return
        # Map the visible time window onto the slice of the waveform image.
        frac0 = self._view_start / float(self._dur)
        frac1 = self._view_end / float(self._dur)
        sx = frac0 * self._wave.width()
        sw = max(1.0, (frac1 - frac0) * self._wave.width())
        p.drawPixmap(QRectF(track.left(), track.top() + 3,
                            track.width(), track.height() - 6),
                     self._wave, QRectF(sx, 0, sw, self._wave.height()))

    def _paint_handle(self, p, x, track, which):
        pal = self.pal
        if x < track.left() - 6 or x > track.right() + 6:
            return
        bar_w = 7.0
        if which == 'start':
            rect = QRectF(x - bar_w, track.top(), bar_w, track.height())
        else:
            rect = QRectF(x, track.top(), bar_w, track.height())
        active = self._drag == which
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal['accent_hover'] if active else pal['accent']))
        path = QPainterPath()
        path.addRoundedRect(rect, 2, 2)
        p.drawPath(path)
        # grip lines
        p.setPen(QPen(QColor(255, 255, 255, 190), 1))
        cy = rect.center().y()
        cx = rect.center().x()
        for dy in (-4, 0, 4):
            p.drawLine(int(cx - 1), int(cy + dy), int(cx + 1), int(cy + dy))

    def _paint_playhead(self, p, track):
        x = self._ms_to_x(self._pos)
        if x < track.left() - 1 or x > track.right() + 1:
            return
        p.setPen(QPen(QColor('#ffffff'), 1))
        p.drawLine(int(x), int(self.RULER_H - 4), int(x), int(track.bottom()))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#ffffff'))
        head = QPainterPath()
        head.moveTo(x - 4, self.RULER_H - 9)
        head.lineTo(x + 4, self.RULER_H - 9)
        head.lineTo(x, self.RULER_H - 2)
        head.closeSubpath()
        p.drawPath(head)

    def _paint_hover(self, p, track):
        if self._hover_x is None or self._drag is not None or self._dur <= 0:
            return
        x = self._hover_x
        if x < track.left() or x > track.right():
            return
        p.setPen(QPen(QColor(self.pal['subtext']), 1, Qt.DotLine))
        p.drawLine(int(x), int(track.top() + 1), int(x), int(track.bottom() - 1))

        # Time badge, kept inside the track so it never clips.
        label = config.fmt_ms(self._x_to_ms(x))
        font = QFont(p.font())
        font.setPointSizeF(7.5)
        font.setFamily('Consolas')
        p.setFont(font)
        w = p.fontMetrics().horizontalAdvance(label) + 10
        bx = min(max(x + 6, track.left() + 2), track.right() - w - 2)
        box = QRectF(bx, track.bottom() - 19, w, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor('#ffffff'))
        p.drawText(box, Qt.AlignCenter, label)

    # -- overview --------------------------------------------------------- #
    def _paint_overview(self, p):
        pal = self.pal
        rect = self._overview_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal['track']))
        p.drawRoundedRect(rect, 3, 3)

        # whole-file selection extent
        xs = self._ms_to_x_full(self._start)
        xe = self._ms_to_x_full(self._end)
        if xe > xs:
            p.setBrush(QColor(pal['accent']))
            p.drawRoundedRect(QRectF(xs, rect.top(), max(2.0, xe - xs), rect.height()), 3, 3)

        # the zoomed view window
        if self.is_zoomed():
            vx0 = self._ms_to_x_full(self._view_start)
            vx1 = self._ms_to_x_full(self._view_end)
            win = QRectF(vx0, rect.top() - 1, max(6.0, vx1 - vx0), rect.height() + 2)
            p.setBrush(QColor(255, 255, 255, 36))
            p.setPen(QPen(QColor(pal['text']), 1))
            p.drawRoundedRect(win, 3, 3)

        # playhead tick
        px = self._ms_to_x_full(self._pos)
        p.setPen(QPen(QColor('#ffffff'), 1))
        p.drawLine(int(px), int(rect.top() - 2), int(px), int(rect.bottom() + 2))

    # ---------------------------------------------------------- hit testing #
    def _zone(self, pos):
        y = pos.y()
        if y >= self._overview_rect().top() - 3:
            return 'overview'
        if y < self.TRACK_TOP:
            return 'ruler'
        return 'track'

    def _what_at(self, x):
        xs = self._ms_to_x(self._start)
        xe = self._ms_to_x(self._end)
        if abs(x - xs) <= self.HANDLE_GRAB + 2:
            return 'start'
        if abs(x - xe) <= self.HANDLE_GRAB + 2:
            return 'end'
        if xs < x < xe:
            return 'body'
        return 'seek'

    def _snap(self, ms, bypass):
        if bypass or self._dur <= 0:
            return ms
        tol = self.SNAP_PX / max(1e-9, self._px_per_ms())
        for target in (0, self._dur, self._pos):
            if abs(ms - target) <= tol:
                return int(target)
        return ms

    # ------------------------------------------------------------ mouse/key #
    def mousePressEvent(self, e):
        if self._dur <= 0:
            return
        self.setFocus(Qt.MouseFocusReason)
        x = e.pos().x()
        zone = self._zone(e.pos())

        if e.button() == Qt.MiddleButton:
            self._drag = 'pan'
            self._drag_anchor_ms = self._x_to_ms(x)
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return

        if zone == 'overview':
            self._drag = 'overview'
            self._center_view_on(self._x_to_ms_full(x))
            return
        if zone == 'ruler':
            self._drag = 'seek'
            self._seek_to(self._x_to_ms(x))
            return

        what = self._what_at(x)
        self._drag = what
        if what == 'body':
            self._drag_anchor_ms = self._x_to_ms(x)
            self._drag_span = self._end - self._start
        elif what == 'seek':
            self._seek_to(self._x_to_ms(x))
        else:
            self._apply_handle(x, e.modifiers() & Qt.ShiftModifier)
        self.update()

    def mouseMoveEvent(self, e):
        x = e.pos().x()
        if self._drag is None:
            self._hover_x = x if self._zone(e.pos()) == 'track' else None
            self._update_cursor(e.pos())
            self.update()
            return
        if self._dur <= 0:
            return

        if self._drag == 'overview':
            self._center_view_on(self._x_to_ms_full(x))
            return
        if self._drag == 'pan':
            # Keep the time that was grabbed pinned under the cursor.
            self.pan_by(self._drag_anchor_ms - self._x_to_ms(x))
            return
        if self._drag == 'seek':
            self._seek_to(self._x_to_ms(x))
            return
        if self._drag == 'body':
            delta = self._x_to_ms(x) - self._drag_anchor_ms
            new_start = max(0, min(self._start + delta, self._dur - self._drag_span))
            self._drag_anchor_ms = self._x_to_ms(x)
            self._start = int(new_start)
            self._end = int(new_start + self._drag_span)
            self.update()
            self.rangeChanged.emit(self._start, self._end)
            return
        self._apply_handle(x, e.modifiers() & Qt.ShiftModifier)

    def mouseReleaseEvent(self, e):
        self._drag = None
        self._update_cursor(e.pos())
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self._dur <= 0:
            return
        if self._zone(e.pos()) == 'overview' or self.is_zoomed():
            self.zoom_all()
        else:
            self.zoom_to_selection()

    def leaveEvent(self, _e):
        self._hover_x = None
        self.update()

    def wheelEvent(self, e):
        if self._dur <= 0:
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        if e.modifiers() & Qt.ShiftModifier:
            self.pan_by(int(-delta / 120.0 * self._view_span() * 0.15))
        else:
            self.zoom_by(1.25 if delta > 0 else 1 / 1.25,
                         pivot_ms=self._x_to_ms(e.pos().x()))
        e.accept()

    def contextMenuEvent(self, e):
        if self._dur <= 0:
            return
        ms = self._x_to_ms(e.pos().x())
        menu = QMenu(self)
        a_in = menu.addAction(f"Set in point here  ({config.fmt_ms(ms)})")
        a_out = menu.addAction(f"Set out point here  ({config.fmt_ms(ms)})")
        menu.addSeparator()
        a_play = menu.addAction("Move playhead here")
        menu.addSeparator()
        a_fit = menu.addAction("Zoom to selection")
        a_all = menu.addAction("Zoom out to whole file")
        a_reset = menu.addAction("Select whole file")
        chosen = menu.exec_(e.globalPos())
        if chosen is a_in:
            self.set_start(ms)
        elif chosen is a_out:
            self.set_end(ms)
        elif chosen is a_play:
            self._seek_to(ms)
        elif chosen is a_fit:
            self.zoom_to_selection()
        elif chosen is a_all:
            self.zoom_all()
        elif chosen is a_reset:
            self.reset_range()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._path and self._dur > 0 and self._wave is None:
            self._strip_timer.start()

    # -- helpers ---------------------------------------------------------- #
    def _update_cursor(self, pos):
        zone = self._zone(pos)
        if zone == 'overview':
            self.setCursor(Qt.PointingHandCursor)
            return
        if zone == 'ruler' or self._dur <= 0:
            self.setCursor(Qt.PointingHandCursor)
            return
        what = self._what_at(pos.x())
        if what in ('start', 'end'):
            self.setCursor(Qt.SizeHorCursor)
        elif what == 'body':
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)

    def _seek_to(self, ms):
        self._pos = max(0, min(int(ms), self._dur))
        self.update()
        self.seekRequested.emit(self._pos)

    def _center_view_on(self, ms):
        span = self._view_span()
        self._set_view(ms - span / 2.0, ms + span / 2.0)

    def _apply_handle(self, x, shift):
        ms = self._snap(self._x_to_ms(x), bool(shift))
        if self._drag == 'start':
            self._start = max(0, min(ms, self._end - self.MIN_GAP))
        else:
            self._end = min(self._dur, max(ms, self._start + self.MIN_GAP))
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def closeEvent(self, e):
        self._stop_threads()
        super().closeEvent(e)
