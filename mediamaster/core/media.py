"""Media inspection and filmstrip generation, backed by the bundled FFmpeg.

Nothing here needs ffprobe: everything is parsed out of `ffmpeg -i`'s banner,
so the app keeps working with only ffmpeg.exe next to it.
"""

import os
import re
import shutil
import subprocess
import tempfile

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

from . import config

_DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_BITRATE = re.compile(r"bitrate:\s*(\d+)\s*kb/s")
_VIDEO_STREAM = re.compile(r"Stream #\d+:\d+(?:\[[^\]]*\])?(?:\([^)]*\))?:\s*Video:\s*([\w]+)")
_AUDIO_STREAM = re.compile(r"Stream #\d+:\d+(?:\[[^\]]*\])?(?:\([^)]*\))?:\s*Audio:\s*([\w]+)")
_RESOLUTION = re.compile(r"\s(\d{2,5})x(\d{2,5})[\s,\[]")
_FPS = re.compile(r"([\d.]+)\s*fps")
_SAMPLE_RATE = re.compile(r"(\d+)\s*Hz")

_CONTAINER = re.compile(r"Input #0,\s*([^\n]+?),\s*from ")
# Demuxers that read single pictures (image2 plus the per-format *_pipe ones).
_IMAGE_DEMUXERS = {'image2', 'gif', 'ico', 'apng', 'jpegxl_anim', 'alias_pix', 'brender_pix'}


class MediaInfo:
    """What we could learn about one media file. Always safe to read."""

    def __init__(self, path=""):
        self.path = path
        self.duration_ms = 0
        self.has_video = False
        self.has_audio = False
        self.vcodec = ""
        self.acodec = ""
        self.width = 0
        self.height = 0
        self.fps = 0.0
        self.bitrate_kbps = 0
        self.sample_rate = 0
        self.size_bytes = 0
        self.has_cover = False       # audio file with embedded artwork
        self.container = ""          # FFmpeg demuxer name(s), e.g. 'mov,mp4,m4a'
        self.ok = False

    # -- derived ---------------------------------------------------------- #
    @property
    def kind(self):
        """'video', 'audio', 'image' or 'unknown', judged from the content."""
        demuxers = set(self.container.split(','))
        if self.has_video and not self.has_audio and (
                demuxers & _IMAGE_DEMUXERS or any(d.endswith('_pipe') for d in demuxers)):
            return 'image'
        # A picture with no timeline (no duration, no sound): AVIF, HEIF-style
        # stills in MP4 boxes, single-frame files with an unusual extension.
        if self.has_video and not self.has_audio and self.duration_ms <= 0:
            return 'image'
        if self.has_video:
            return 'video'
        if self.has_audio:
            return 'audio'
        return 'unknown'

    @property
    def frame_ms(self):
        """Length of a single frame in ms (25 fps assumed when unknown)."""
        fps = self.fps if self.fps and self.fps > 0 else 25.0
        return max(1.0, 1000.0 / fps)

    @property
    def aspect(self):
        if self.width > 0 and self.height > 0:
            return self.width / self.height
        return 16 / 9

    def summary_chips(self):
        """Short strings for the UI's info row."""
        chips = []
        if self.duration_ms > 0:
            chips.append(config.fmt_clock(self.duration_ms))
        if self.width and self.height:
            chips.append(f"{self.width}x{self.height}")
        if self.fps:
            chips.append(f"{self.fps:g} fps")
        if self.vcodec:
            chips.append(self.vcodec)
        if self.acodec:
            chips.append(self.acodec)
            if not self.has_video and self.sample_rate:
                chips.append(f"{self.sample_rate / 1000:g} kHz")
        elif self.has_video:
            chips.append("no audio")
        if self.size_bytes:
            chips.append(config.fmt_bytes(self.size_bytes))
        return chips


def _banner(path):
    """Return ffmpeg's stderr banner for `path` (it exits non-zero by design)."""
    try:
        proc = subprocess.Popen(
            [config.FFMPEG, '-hide_banner', '-nostdin', '-i', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            errors='replace', creationflags=config.CREATE_NO_WINDOW)
        return proc.communicate(timeout=20)[1] or ""
    except Exception:
        return ""


def probe(path):
    """Inspect one media file. Never raises."""
    info = MediaInfo(path)
    if not path or not os.path.isfile(path):
        return info
    try:
        info.size_bytes = os.path.getsize(path)
    except OSError:
        pass

    text = _banner(path)
    if not text:
        return info

    m = _CONTAINER.search(text)
    if m:
        info.container = m.group(1).strip()

    m = _DURATION.search(text)
    if m:
        h, mi, s = m.group(1), m.group(2), m.group(3)
        info.duration_ms = int((int(h) * 3600 + int(mi) * 60 + float(s)) * 1000)

    m = _BITRATE.search(text)
    if m:
        info.bitrate_kbps = int(m.group(1))

    # Walk the stream lines so resolution/fps are read from the video line only.
    for line in text.splitlines():
        vm = _VIDEO_STREAM.search(line)
        if vm and 'attached pic' in line:
            # Cover art on an audio file is not a video track.
            info.has_cover = True
            continue
        if vm and not info.has_video:
            info.has_video = True
            info.vcodec = vm.group(1)
            rm = _RESOLUTION.search(line)
            if rm:
                info.width, info.height = int(rm.group(1)), int(rm.group(2))
            fm = _FPS.search(line)
            if fm:
                try:
                    info.fps = float(fm.group(1))
                except ValueError:
                    pass
            continue
        am = _AUDIO_STREAM.search(line)
        if am and not info.has_audio:
            info.has_audio = True
            info.acodec = am.group(1)
            sm = _SAMPLE_RATE.search(line)
            if sm:
                info.sample_rate = int(sm.group(1))

    info.ok = bool(info.has_video or info.has_audio)
    return info


class ProbeThread(QThread):
    """Probe a file without blocking the UI."""

    ready = pyqtSignal(str, object)      # path, MediaInfo

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.ready.emit(self.path, probe(self.path))
        except Exception:
            self.ready.emit(self.path, MediaInfo(self.path))


class WaveformThread(QThread):
    """Render an audio waveform image for the whole file, in one FFmpeg pass.

    Used as the timeline backdrop for audio-only media, where a filmstrip has
    nothing to show. Skipped for very long files, which would take too long to
    decode for what is only a visual aid.
    """

    MAX_DURATION_MS = 30 * 60 * 1000

    ready = pyqtSignal(QImage)

    def __init__(self, path, width=1600, height=56, color="#4c8dff", parent=None):
        super().__init__(parent)
        self.path = path
        self.width = max(200, int(width))
        self.height = max(24, int(height))
        self.color = color.lstrip('#')
        self._stop = False
        self._proc = None

    def stop(self):
        self._stop = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def run(self):
        tmp = None
        try:
            tmp = tempfile.mkdtemp(prefix='mmmp_wave_')
            out = os.path.join(tmp, 'wave.png')
            spec = (f"aformat=channel_layouts=mono,"
                    f"showwavespic=s={self.width}x{self.height}"
                    f":colors=0x{self.color}:scale=lin")
            cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
                   '-i', self.path, '-filter_complex', spec,
                   '-frames:v', '1', '-y', out]
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=config.CREATE_NO_WINDOW)
            self._proc.wait(timeout=180)
            if self._stop or not os.path.exists(out):
                return
            img = QImage(out)
            if not img.isNull():
                self.ready.emit(img.copy())
        except Exception:
            pass
        finally:
            self._proc = None
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)


class FilmstripThread(QThread):
    """Extract evenly spaced thumbnails across a time range, one by one.

    Tiles are emitted as they are decoded so the timeline fills in progressively
    instead of waiting for the whole strip.
    """

    tile = pyqtSignal(int, QImage)       # index, image
    strip = pyqtSignal(int, int, int)    # count, range_start_ms, range_end_ms

    def __init__(self, path, start_ms, end_ms, count, height=56, parent=None):
        super().__init__(parent)
        self.path = path
        self.start_ms = max(0, int(start_ms))
        self.end_ms = max(self.start_ms + 1, int(end_ms))
        self.count = max(1, int(count))
        self.height = max(24, int(height))
        self._stop = False
        self._proc = None
        self._tmp = None

    def stop(self):
        self._stop = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def run(self):
        try:
            self._tmp = tempfile.mkdtemp(prefix='mmmp_strip_')
        except Exception:
            return
        try:
            self.strip.emit(self.count, self.start_ms, self.end_ms)
            span = self.end_ms - self.start_ms
            for i in range(self.count):
                if self._stop:
                    return
                # Sample the middle of each slot so tiles represent their slice.
                t_ms = self.start_ms + span * (i + 0.5) / self.count
                img = self._grab(i, t_ms / 1000.0)
                if self._stop:
                    return
                if img is not None and not img.isNull():
                    self.tile.emit(i, img)
        finally:
            self._proc = None
            if self._tmp:
                shutil.rmtree(self._tmp, ignore_errors=True)

    def _grab(self, index, t_sec):
        out = os.path.join(self._tmp, f"t{index:04d}.jpg")
        cmd = [config.FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', f"{max(0.0, t_sec):.3f}", '-i', self.path,
               '-frames:v', '1', '-an', '-sn',
               '-vf', f'scale=-2:{self.height}:flags=fast_bilinear',
               '-q:v', '5', '-f', 'image2', '-y', out]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=config.CREATE_NO_WINDOW)
            self._proc.wait(timeout=20)
        except Exception:
            return None
        finally:
            self._proc = None
        if not os.path.exists(out):
            return None
        img = QImage(out)
        try:
            os.remove(out)
        except OSError:
            pass
        # Detach from the file's backing store before handing it to the GUI thread.
        return img.copy() if not img.isNull() else None


# --------------------------------------------------------------------------- #
#  Capture devices                                                            #
# --------------------------------------------------------------------------- #
_DSHOW_DEVICE = re.compile(r'\]\s+"(.+)"\s+\((audio|video|none)\)\s*$')
_DSHOW_ALT = re.compile(r'\]\s+Alternative name\s+"(.+)"\s*$')


def list_audio_inputs():
    """Microphones and other recording inputs FFmpeg can capture (Windows).

    Returns [(friendly_name, device_id)]. The device id (DirectShow's
    "alternative name") is unique even when two devices share a name, so it
    is what gets passed to FFmpeg; the friendly name is for display.
    """
    if os.name != 'nt':
        return []
    try:
        proc = subprocess.run(
            [config.FFMPEG, '-hide_banner', '-list_devices', 'true', '-f', 'dshow',
             '-i', 'dummy'], capture_output=True, timeout=15,
            creationflags=config.CREATE_NO_WINDOW)
        text = proc.stderr.decode('utf-8', errors='replace')
    except Exception:
        return []
    devices, current = [], None
    for line in text.splitlines():
        m = _DSHOW_DEVICE.search(line)
        if m:
            current = [m.group(1), m.group(1)] if m.group(2) == 'audio' else None
            if current:
                devices.append(current)
            continue
        m = _DSHOW_ALT.search(line)
        if m and current is not None:
            current[1] = m.group(1)
    return [tuple(d) for d in devices]


class AudioInputsThread(QThread):
    """List recording devices without blocking the UI."""

    ready = pyqtSignal(list)

    def run(self):
        self.ready.emit(list_audio_inputs())
