"""FFmpeg-driven media playback.

Qt5's own QMediaPlayer relies on DirectShow on Windows, which cannot decode
most real-world files (even plain H.264 MP4 reports "invalid media"). So the
preview decodes with the bundled FFmpeg instead:

    video   ffmpeg -> raw RGB frames over a pipe -> small queue -> GUI
    audio   ffmpeg -> 48 kHz s16 PCM over a pipe  -> QAudioOutput (push mode)

Audio is the master clock: the position is derived from how many samples the
sound device has actually consumed, and video frames are shown when their
timestamp comes due (late frames are dropped rather than slowing playback).
Without an audio track the clock falls back to a monotonic timer.

While paused, seeks are served by a one-shot frame grabber that always works
on the newest request, so dragging across the timeline stays responsive.
"""

import collections
import subprocess
import threading

from PyQt5.QtCore import QObject, QTimer, QElapsedTimer, Qt, pyqtSignal
from PyQt5.QtGui import QImage

from . import config

try:
    from PyQt5.QtMultimedia import QAudioOutput, QAudioFormat, QAudioDeviceInfo, QAudio
    HAS_AUDIO = True
except Exception:                                   # pragma: no cover
    HAS_AUDIO = False

SAMPLE_RATE = 48000
CHANNELS = 2
BYTES_PER_SAMPLE_FRAME = 2 * CHANNELS               # s16le, stereo
BYTES_PER_MS = SAMPLE_RATE * BYTES_PER_SAMPLE_FRAME / 1000.0

MAX_PREVIEW_W = 1920
MAX_PREVIEW_H = 1080
MAX_PREVIEW_FPS = 60.0


def _spawn(cmd):
    return subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=config.CREATE_NO_WINDOW)


def _kill(proc):
    if proc is None:
        return
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.stdout.close()
    except Exception:
        pass


def _even(n):
    n = max(2, int(n))
    return n - (n % 2)


def fit_size(src_w, src_h, box_w, box_h):
    """Largest even size with the source's aspect that fits inside the box,
    never larger than the source itself or the preview cap."""
    box_w = min(max(64, int(box_w)), MAX_PREVIEW_W)
    box_h = min(max(36, int(box_h)), MAX_PREVIEW_H)
    if src_w <= 0 or src_h <= 0:
        return _even(box_w), _even(box_h)
    scale = min(box_w / src_w, box_h / src_h, 1.0)
    return _even(src_w * scale), _even(src_h * scale)


# --------------------------------------------------------------------------- #
#  Decoder threads (plain Python threads: they only touch their own buffers)  #
# --------------------------------------------------------------------------- #
class _VideoDecoder(threading.Thread):
    """Decode frames from `start_ms` into a small bounded queue."""

    QUEUE = 10

    def __init__(self, path, start_ms, width, height, fps):
        super().__init__(daemon=True)
        self.path = path
        self.start_ms = start_ms
        self.w, self.h = width, height
        self.fps = fps
        self.frames = collections.deque()
        self.cond = threading.Condition()
        self.eof = False
        self._halt = False
        self._proc = None

    def stop(self):
        self._halt = True
        with self.cond:
            self.cond.notify_all()
        _kill(self._proc)

    def pop_due(self, now_ms):
        """Remove and return the newest frame whose time has come (or None)."""
        frame = None
        with self.cond:
            while self.frames and self.frames[0][0] <= now_ms:
                frame = self.frames.popleft()
            if frame is not None:
                self.cond.notify_all()
        return frame

    def has_frames(self):
        return bool(self.frames)

    def done(self):
        return self.eof and not self.frames

    def run(self):
        cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', f"{self.start_ms / 1000.0:.3f}", '-i', self.path,
               '-an', '-sn', '-dn',
               '-vf', f"fps={self.fps:.5f},scale={self.w}:{self.h}:flags=bilinear",
               '-pix_fmt', 'bgra', '-f', 'rawvideo', '-']
        try:
            self._proc = _spawn(cmd)
        except Exception:
            self.eof = True
            return
        size = self.w * self.h * 4
        step = 1000.0 / self.fps
        index = 0
        try:
            while not self._halt:
                data = self._proc.stdout.read(size)
                if not data or len(data) < size:
                    break
                img = QImage(data, self.w, self.h, self.w * 4, QImage.Format_RGB32).copy()
                pts = self.start_ms + index * step
                index += 1
                with self.cond:
                    while len(self.frames) >= self.QUEUE and not self._halt:
                        self.cond.wait(0.1)
                    if self._halt:
                        break
                    self.frames.append((pts, img))
        except Exception:
            pass
        finally:
            self.eof = True
            _kill(self._proc)
            self._proc = None


class _AudioDecoder(threading.Thread):
    """Decode PCM from `start_ms` into a bounded byte buffer."""

    MAX_BUFFER = int(BYTES_PER_MS * 1500)
    CHUNK = 16384

    def __init__(self, path, start_ms):
        super().__init__(daemon=True)
        self.path = path
        self.start_ms = start_ms
        self.buf = bytearray()
        self.cond = threading.Condition()
        self.eof = False
        self._halt = False
        self._proc = None

    def stop(self):
        self._halt = True
        with self.cond:
            self.cond.notify_all()
        _kill(self._proc)

    def take(self, n):
        n -= n % BYTES_PER_SAMPLE_FRAME
        if n <= 0:
            return b""
        with self.cond:
            chunk = bytes(self.buf[:n])
            del self.buf[:n]
            self.cond.notify_all()
        return chunk

    def available(self):
        return len(self.buf)

    def done(self):
        return self.eof and not self.buf

    def run(self):
        cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', f"{self.start_ms / 1000.0:.3f}", '-i', self.path,
               '-vn', '-sn', '-dn', '-ac', str(CHANNELS), '-ar', str(SAMPLE_RATE),
               '-f', 's16le', '-']
        try:
            self._proc = _spawn(cmd)
        except Exception:
            self.eof = True
            return
        try:
            while not self._halt:
                data = self._proc.stdout.read1(self.CHUNK) if hasattr(
                    self._proc.stdout, 'read1') else self._proc.stdout.read(self.CHUNK)
                if not data:
                    break
                with self.cond:
                    while len(self.buf) >= self.MAX_BUFFER and not self._halt:
                        self.cond.wait(0.1)
                    if self._halt:
                        break
                    self.buf.extend(data)
        except Exception:
            pass
        finally:
            self.eof = True
            _kill(self._proc)
            self._proc = None


class _Grabbed(QObject):
    ready = pyqtSignal(int, int, QImage)            # generation, ms, image


class _FrameGrabber(threading.Thread):
    """Grab single frames for paused seeking. Only the newest request counts."""

    def __init__(self):
        super().__init__(daemon=True)
        self.signals = _Grabbed()
        self.cond = threading.Condition()
        self._request = None
        self._halt = False
        self._proc = None

    def request(self, gen, path, ms, w, h):
        with self.cond:
            self._request = (gen, path, ms, w, h)
            self.cond.notify_all()

    def stop(self):
        self._halt = True
        with self.cond:
            self.cond.notify_all()
        _kill(self._proc)

    def _grab(self, path, ms, w, h):
        cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', f"{max(0, ms) / 1000.0:.3f}", '-i', path,
               '-frames:v', '1', '-an', '-sn', '-dn',
               '-vf', f"scale={w}:{h}:flags=bilinear",
               '-pix_fmt', 'bgra', '-f', 'rawvideo', '-']
        try:
            self._proc = _spawn(cmd)
            data = self._proc.stdout.read(w * h * 4)
        except Exception:
            return None
        finally:
            _kill(self._proc)
            self._proc = None
        if not data or len(data) < w * h * 4:
            return None
        return QImage(data, w, h, w * 4, QImage.Format_RGB32).copy()

    def run(self):
        while not self._halt:
            with self.cond:
                while self._request is None and not self._halt:
                    self.cond.wait()
                if self._halt:
                    return
                gen, path, ms, w, h = self._request
                self._request = None
            img = self._grab(path, ms, w, h)
            if img is None and ms > 0:
                # Past the last decodable frame: show the closest one before it.
                img = self._grab(path, max(0, ms - 1500), w, h)
            if img is not None and not self._halt:
                self.signals.ready.emit(gen, ms, img)


# --------------------------------------------------------------------------- #
#  The engine                                                                  #
# --------------------------------------------------------------------------- #
class PlaybackEngine(QObject):
    """Play, pause and seek a media file; emits frames and position."""

    frameReady = pyqtSignal(QImage)
    positionChanged = pyqtSignal(int)
    playingChanged = pyqtSignal(bool)
    finished = pyqtSignal()                 # reached the end (or the stop point)

    TICK_MS = 4
    # The sound device reports progress in whole periods (~40 ms on Windows).
    # Between those steps the clock is interpolated, but never by more than
    # this, so a stalled device can't let video run ahead of the sound.
    AUDIO_SLACK_MS = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self._dur = 0
        self._has_video = False
        self._has_audio = False
        self._src_w = 0
        self._src_h = 0
        self._fps = 30.0
        self._box = (960, 540)

        self._pos = 0
        self._playing = False
        self._stop_at = None
        self._volume = 0.8
        self._muted = False

        self._vdec = None
        self._adec = None
        self._play_start = 0
        self._primed = False
        self._mode = None                   # 'audio' | 'wall'
        self._wall = QElapsedTimer()
        self._wall_base = 0
        self._wall_running = False
        self._mono = QElapsedTimer()
        self._raw_last = None
        self._raw_at = 0
        self._smooth_last = 0.0
        self._last_emit = -1

        self._audio = None
        self._adev = None
        self._written = 0
        self._audio_ok = HAS_AUDIO
        self._audio_warm = False

        self._grab_gen = 0
        self._grabber = _FrameGrabber()
        self._grabber.signals.ready.connect(self._on_grabbed)
        self._grabber.start()

        self._tick = QTimer(self)
        self._tick.setTimerType(Qt.PreciseTimer)
        self._tick.setInterval(self.TICK_MS)
        self._tick.timeout.connect(self._on_tick)

        # Seeking while playing restarts FFmpeg; coalesce rapid seeks.
        self._resume = QTimer(self)
        self._resume.setSingleShot(True)
        self._resume.setInterval(140)
        self._resume.timeout.connect(self._resume_after_seek)
        self._seek_hold = False

    # ------------------------------------------------------------- public #
    def open(self, path, info):
        self.close()
        self._path = path
        self._dur = max(0, int(info.duration_ms))
        self._has_video = bool(info.has_video)
        self._has_audio = bool(info.has_audio)
        self._src_w, self._src_h = info.width, info.height
        fps = info.fps if info.fps and info.fps > 0 else 30.0
        self._fps = min(fps, MAX_PREVIEW_FPS)
        self._pos = 0
        self.positionChanged.emit(0)
        self.refresh_frame()
        if self._has_audio and not self._audio_warm:
            # Opening the sound device for the first time in a process takes
            # ~0.5 s on Windows. Do it once now, while the file is loading,
            # so pressing Play responds instantly.
            QTimer.singleShot(0, self._warm_audio)

    def close(self):
        self._stop_playback(emit=True)
        self._grab_gen += 1
        self._path = ""
        self._dur = 0
        self._pos = 0
        self._stop_at = None

    def shutdown(self):
        self.close()
        self._grabber.stop()
        if self._audio is not None:
            try:
                self._audio.stop()
            except Exception:
                pass

    def has_media(self):
        return bool(self._path) and self._dur > 0

    def has_video(self):
        return self._has_video

    def duration(self):
        return self._dur

    def position(self):
        if self._playing and not self._seek_hold:
            return int(self._clock())
        return self._pos

    def is_playing(self):
        return self._playing

    def frame_ms(self):
        return 1000.0 / self._fps

    def set_view_size(self, w, h):
        """Pixel size of the area frames are shown in (device pixels)."""
        old = self._box
        self._box = (max(64, int(w)), max(36, int(h)))
        grew = self._box[0] > old[0] * 1.25 or self._box[1] > old[1] * 1.25
        if grew and not self._playing:
            self.refresh_frame()

    def set_stop_at(self, ms):
        """Pause automatically when playback reaches `ms` (None = file end)."""
        self._stop_at = None if ms is None else int(ms)

    def set_volume(self, volume):
        self._volume = max(0.0, min(1.0, float(volume)))
        self._apply_volume()

    def set_muted(self, muted):
        self._muted = bool(muted)
        self._apply_volume()

    def play(self):
        if not self.has_media() or self._playing:
            return
        if self._pos >= self._dur - 1:
            self._pos = 0
        self._playing = True
        self._start_decoders(self._pos)
        self.playingChanged.emit(True)

    def pause(self):
        if not self._playing:
            return
        self._pos = self.position()
        self._stop_playback(emit=True)
        self.positionChanged.emit(self._pos)

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def seek(self, ms):
        if not self.has_media():
            return
        self._pos = max(0, min(int(ms), self._dur))
        self.positionChanged.emit(self._pos)
        if self._playing:
            self._stop_decoders()
            self._seek_hold = True
            self._resume.start()
        self.refresh_frame()

    def step(self, frames):
        """Pause and move by a number of frames (negative = backwards)."""
        if not self.has_media():
            return
        if self._playing:
            self.pause()
        self.seek(self._pos + frames * self.frame_ms())

    def refresh_frame(self):
        """Re-grab the frame at the current position (paused display)."""
        if not self._path or not self._has_video:
            return
        w, h = self._decode_size()
        self._grab_gen += 1
        self._grabber.request(self._grab_gen, self._path, self._pos, w, h)

    # ------------------------------------------------------------ private #
    def _decode_size(self):
        return fit_size(self._src_w, self._src_h, *self._box)

    def _on_grabbed(self, gen, _ms, img):
        if gen != self._grab_gen:
            return                          # a newer request superseded it
        if self._playing and not self._seek_hold:
            return                          # the live decoder owns the screen
        self.frameReady.emit(img)

    def _resume_after_seek(self):
        self._seek_hold = False
        if self._playing:
            self._start_decoders(self._pos)

    def _apply_volume(self):
        if self._audio is not None:
            self._audio.setVolume(0.0 if self._muted else self._volume)

    def _ensure_audio(self):
        if not self._audio_ok:
            return False
        if self._audio is not None:
            return True
        try:
            fmt = QAudioFormat()
            fmt.setSampleRate(SAMPLE_RATE)
            fmt.setChannelCount(CHANNELS)
            fmt.setSampleSize(16)
            fmt.setCodec("audio/pcm")
            fmt.setByteOrder(QAudioFormat.LittleEndian)
            fmt.setSampleType(QAudioFormat.SignedInt)
            device = QAudioDeviceInfo.defaultOutputDevice()
            if device.isNull() or not device.isFormatSupported(fmt):
                self._audio_ok = False
                return False
            self._audio = QAudioOutput(device, fmt, self)
            # ~120 ms of device buffering keeps the clock tight but safe.
            self._audio.setBufferSize(int(BYTES_PER_MS * 120))
            self._apply_volume()
            return True
        except Exception:
            self._audio_ok = False
            self._audio = None
            return False

    def _warm_audio(self):
        if self._audio_warm or self._playing or not self._ensure_audio():
            return
        self._audio_warm = True
        try:
            self._audio.start()
            self._audio.stop()
        except Exception:
            pass

    def _start_decoders(self, start_ms):
        self._stop_decoders()
        self._play_start = start_ms
        self._last_emit = -1
        self._primed = False
        self._wall_running = False
        self._wall_base = start_ms
        self._mono.start()
        self._raw_last = None
        self._raw_at = 0
        self._smooth_last = float(start_ms)

        if self._has_video:
            w, h = self._decode_size()
            self._vdec = _VideoDecoder(self._path, start_ms, w, h, self._fps)
            self._vdec.start()

        self._mode = 'wall'
        if self._has_audio and self._ensure_audio():
            self._adec = _AudioDecoder(self._path, start_ms)
            self._adec.start()
            self._written = 0
            self._audio_warm = True
            try:
                self._adev = self._audio.start()
                self._mode = 'audio'
            except Exception:
                self._adev = None
                self._adec.stop()
                self._adec = None
        self._tick.start()

    def _stop_decoders(self):
        self._tick.stop()
        for dec in (self._vdec, self._adec):
            if dec is not None:
                dec.stop()
        self._vdec = None
        self._adec = None
        if self._audio is not None:
            try:
                self._audio.stop()
            except Exception:
                pass
        self._adev = None
        self._wall_running = False

    def _stop_playback(self, emit):
        self._resume.stop()
        self._seek_hold = False
        self._stop_decoders()
        was = self._playing
        self._playing = False
        if emit and was:
            self.playingChanged.emit(False)

    def _device_buffered(self):
        try:
            return max(0, self._audio.bufferSize() - self._audio.bytesFree())
        except Exception:
            return 0

    def _clock(self):
        if self._mode == 'audio' and self._audio is not None:
            played = max(0, self._written - self._device_buffered())
            raw = self._play_start + played / BYTES_PER_MS
            if self._written == 0:
                return raw
            now = self._mono.elapsed()
            if raw != self._raw_last:
                self._raw_last = raw
                self._raw_at = now
            est = min(raw + (now - self._raw_at), raw + self.AUDIO_SLACK_MS)
            est = max(est, self._smooth_last)          # never step backwards
            self._smooth_last = est
            return est
        if self._wall_running:
            return self._wall_base + self._wall.elapsed()
        return self._wall_base

    def _switch_to_wall(self, at_ms):
        self._mode = 'wall'
        self._wall_base = at_ms
        self._wall.restart()
        self._wall_running = True

    def _on_tick(self):
        if not self._playing or self._seek_hold:
            return

        # Hold the clock until the first video frame is ready, so the start of
        # playback isn't spent dropping frames that arrived "late".
        if not self._primed:
            if self._vdec is not None and not (self._vdec.has_frames() or self._vdec.eof):
                return
            if self._mode == 'audio' and self._adec is not None \
                    and self._adec.available() == 0 and not self._adec.eof:
                return
            self._primed = True
            if self._mode == 'wall':
                self._switch_to_wall(self._play_start)

        if self._mode == 'audio' and self._adev is not None:
            try:
                free = self._audio.bytesFree()
                if free >= BYTES_PER_SAMPLE_FRAME:
                    chunk = self._adec.take(free)
                    if chunk:
                        self._adev.write(chunk)
                        self._written += len(chunk)
            except Exception:
                self._switch_to_wall(self._clock())

        now = self._clock()

        shown = False
        if self._vdec is not None:
            frame = self._vdec.pop_due(now)
            if frame is not None:
                self.frameReady.emit(frame[1])
                shown = True

        pos = int(min(now, self._dur))
        if shown or self._last_emit < 0 or abs(pos - self._last_emit) >= 33:
            self._last_emit = pos
            self.positionChanged.emit(pos)

        if self._stop_at is not None and now >= self._stop_at:
            self._finish(self._stop_at)
            return

        audio_done = (self._adec is None or
                      (self._adec.done() and self._device_buffered() == 0))
        video_done = self._vdec is None or self._vdec.done()
        if self._mode == 'audio' and audio_done and not video_done:
            self._switch_to_wall(now)       # audio track shorter than video
        elif audio_done and video_done:
            self._finish(min(now, self._dur))
        elif now > self._dur + 1500:
            self._finish(self._dur)

    def _finish(self, at_ms):
        self._pos = int(max(0, min(at_ms, self._dur)))
        self._stop_playback(emit=True)
        self.positionChanged.emit(self._pos)
        self.finished.emit()
