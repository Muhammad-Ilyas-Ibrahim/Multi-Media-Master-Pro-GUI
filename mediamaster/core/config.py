"""Application constants, paths and small helpers."""

import os
import sys
import shutil
import subprocess

APP_NAME = "Multi-Media-Master-Pro"
APP_VERSION = "1.2"

AUDIO_EXTS = (
    'aac', 'ac3', 'aif', 'aiff', 'alac', 'amr', 'ape', 'au', 'awb', 'flac',
    'gsm', 'm4a', 'm4b', 'm4p', 'mp3', 'ogg', 'oga', 'mogg', 'opus', 'ra',
    'wav', 'wma', 'webm'
)
IMAGE_EXTS = ('jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'gif', 'webp', 'ico')
VIDEO_EXTS = ('mp4', 'avi', 'mkv', 'mov', 'flv', 'wmv', 'webm', 'm4v', 'mpg', 'mpeg')

# Windows: hide the console window FFmpeg would otherwise flash open.
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def resource_base():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    # this file: mediamaster/core/config.py -> up 3 levels = project root
    # (GUI_Version) which holds ffmpeg.exe / icon.ico
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_ffmpeg():
    """Find ffmpeg: bundled next to the app, in _internal, or on PATH."""
    base = resource_base()
    for c in (os.path.join(base, 'ffmpeg.exe'),
              os.path.join(base, '_internal', 'ffmpeg.exe'),
              os.path.join(os.getcwd(), 'ffmpeg.exe'),
              os.path.join(base, 'ffmpeg')):
        if os.path.exists(c):
            return c
    found = shutil.which('ffmpeg')
    return found if found else 'ffmpeg'


FFMPEG = resolve_ffmpeg()


def config_dir():
    """A per-user, always-writable directory for app settings."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(
            os.path.expanduser('~'), '.config')
    path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return os.path.expanduser('~')


def output_dir_file():
    return os.path.join(config_dir(), 'output_dir.txt')


def theme_file():
    return os.path.join(config_dir(), 'theme.txt')


def load_saved_output_dir():
    try:
        with open(output_dir_file(), 'r') as f:
            return f.read().strip()
    except Exception:
        return ""


def save_output_dir(path):
    with open(output_dir_file(), 'w') as f:
        f.write(path)


def load_saved_theme():
    try:
        with open(theme_file(), 'r') as f:
            t = f.read().strip().lower()
            return t if t in ('dark', 'light') else 'dark'
    except Exception:
        return 'dark'


def save_theme(name):
    try:
        with open(theme_file(), 'w') as f:
            f.write(name)
    except Exception:
        pass


def human_size(kb):
    return f"{kb/1024:.2f} MB" if kb >= 1024 else f"{kb} KB"


def file_size_kb(path):
    try:
        return os.path.getsize(path) // 1024
    except Exception:
        return 0


def ffmpeg_available():
    return FFMPEG != 'ffmpeg' or shutil.which('ffmpeg') is not None


def open_in_explorer(path):
    """Open a folder (or the folder containing a file) in the OS file manager."""
    try:
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if os.name == 'nt':
            os.startfile(path)  # noqa
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


def probe_duration_ms(path):
    """Read a media file's duration (in milliseconds) using FFmpeg.

    This does not depend on Qt's playback backend, so the trim timeline can
    always be made usable even when the video preview can't decode the file.
    """
    try:
        proc = subprocess.Popen(
            [FFMPEG, '-i', path], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW)
        err = proc.communicate()[1]
        for line in err.split('\n'):
            if 'Duration:' in line:
                d = line.split('Duration:')[1].split(',')[0].strip()
                h, m, s = d.split(':')
                return int((float(h) * 3600 + float(m) * 60 + float(s)) * 1000)
    except Exception:
        pass
    return 0


def fmt_ms(ms):
    """Milliseconds -> 'HH:MM:SS.mmm'."""
    total = max(0, int(ms))
    h = total // 3600000
    m = (total % 3600000) // 60000
    s = (total % 60000) // 1000
    msec = total % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{msec:03d}"


def fmt_clock(ms):
    """Milliseconds -> 'M:SS' for compact display."""
    total = max(0, int(ms)) // 1000
    return f"{total // 60}:{total % 60:02d}"


def hhmmss_to_sec(text):
    """'HH:MM:SS.mmm' -> float seconds."""
    try:
        h, m, s = text.split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        return 0.0
