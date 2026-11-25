"""Application constants, paths and small helpers."""

import os
import sys
import shutil
import subprocess

APP_NAME = "Multi-Media-Master-Pro"
APP_VERSION = "2.0"

# Every extension the bundled FFmpeg can read, grouped by what the file holds.
# Built from FFmpeg's own demuxer list (`ffmpeg -h demuxer=...`), plus the
# formats it recognises by content (WAV, MPEG-TS, ASF/WMV, RealMedia, ...) and
# the image2 reader's still-image types. Common formats come first; that order
# is what hints show. Each extension belongs to exactly one kind.
# Files with an extension that isn't listed are still accepted: they are
# identified by asking FFmpeg what they contain (see media.probe / kind).
VIDEO_EXTS = (
    'mp4', 'mkv', 'mov', 'avi', 'webm', 'wmv', 'm4v', 'mpg', 'mpeg', 'flv',
    'ts', 'm2ts', 'mts', '3gp', '3g2', 'ogv', 'vob', 'mxf', 'asf', 'f4v',
    'rm', 'rmvb', 'divx', 'dv', 'qt', 'mk3d', 'mpe', 'm1v', 'm2v', 'mp2v',
    'mpv', 'm2t', 'tp', 'trp', 'tsv', 'ogm', 'ogx', 'rv', 'xvid', 'dif',
    'gxf', 'nut', 'nsv', 'wtv', 'dvr-ms', 'ismv', 'ism', 'psp', 'mj2', 'amv',
    'y4m', 'yuv', 'h264', '264', 'h26l', 'avc', 'hevc', 'h265', '265',
    'h266', '266', 'vvc', 'obu', 'ivf', 'vc1', 'rcv', 'evc', 'mjpg', 'mjpeg',
    'bik', 'bk2', 'smk', 'roq', 'mve', 'thp', 'str', 'cpk', 'film', '4xm',
    'wve', 'flc', 'fli', 'flx', 'cdg', 'cdxl', 'dav', 'ifv', 'lvf', 'ty',
    'viv', 'xmv', 'yop', 'pdv', 'ser', 'moflex', 'mods', 'swf', 'mvi', 'mxg',
    'nuv', 'r3d', 'vivo', 'imx', 'ipu', 'flm', 'sga', 'kux', 'v210', 'yuv10',
)
AUDIO_EXTS = (
    'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'wma', 'aiff', 'aif',
    'alac', 'ac3', 'eac3', 'ec3', 'dts', 'amr', 'ape', 'mka', 'oga', 'mp2',
    'm4b', 'm4p', 'm4r', 'caf', 'au', 'snd', 'aifc', 'w64', 'rf64', 'bwf',
    'wave', 'adts', 'm2a', 'mpa', 'mp1', 'spx', 'mogg', 'isma', '3ga', 'awb',
    'ra', 'wv', 'tta', 'tak', 'mpc', 'mp+', 'shn', 'thd', 'truehd', 'mlp',
    'dtshd', 'ac4', 'apl', 'mac', 'gsm', 'voc', 'vox', 'sln', '8svx', 'iff',
    'sf', 'ircam', 'nist', 'sph', 'al', 'ul', 'sw', 'sb', 'uw', 'ub', 'dsf',
    'dff', 'wsd', 'aa', 'aax', 'oma', 'omg', 'aa3', 'xa', 'adx', 'hca', 'aix',
    'ast', 'brstm', 'bfstm', 'bcstm', 'vag', 'xvag', 'msf', 'mtaf', 'svag',
    'ads', 'ss2', 'vpk', 'genh', 'sdx', 'sds', 'dss', 'dfpwm', 'g722', '722',
    'g729', 'bit', 'tco', 'rco', 'sbc', 'msbc', 'aptx', 'aptxhd', 'bonk',
    'laf', 'rka', 'binka', 'fsb', 'musx', 'xmd', 'fwse', 'rsd', 'rso', 'pvf',
    'vqf', 'vql', 'vqe', 'way', 'wa', 'mca', 'nsp', 'acm', 'qcp', 'mmf',
    'avr', 'paf', 'fap', '302', 'daud', 'c2', 'dtk', 'adp', 'aea', 'afc',
    'sdns', 'son', 'xwma', 'apc', 'mod', 'xm', 's3m', 'it', 'mptm',
    'mo3', '669', 'amf', 'ams', 'dbm', 'digi', 'dmf', 'dsm', 'dtm', 'far',
    'gdm', 'imf', 'j2b', 'm15', 'mdl', 'med', 'mmcmp', 'mms', 'mt2', 'mtm',
    'nst', 'okt', 'plm', 'psm', 'pt36', 'ptm', 'sfx', 'sfx2', 'st26', 'stk',
    'stm', 'stp', 'ult', 'umx', 'wow', 'xpk',
)
IMAGE_EXTS = (
    'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'ico', 'avif',
    'jxl', 'tga', 'jfif', 'jpe', 'pjpeg', 'pjp', 'apng', 'dib', 'psd', 'dds',
    'exr', 'hdr', 'dpx', 'jp2', 'j2k', 'j2c', 'jpc', 'jpf', 'jpx', 'jls',
    'qoi', 'pcx', 'pbm', 'pgm', 'ppm', 'pnm', 'pam', 'pfm', 'phm', 'sgi',
    'rgb', 'rgba', 'bw', 'int', 'inta', 'ras', 'sun', 'sunras', 'im1', 'im8',
    'im24', 'xbm', 'xpm', 'xwd', 'icb', 'vda', 'vst', 'pix', 'cri', 'vbn',
    'mpo', 'pgmyuv', 'gem', 'msp',
)

# Containers FFmpeg can also *write* with the codecs this app encodes to.
# A source in any other container gets a compatible fallback (output_ext).
WRITABLE_VIDEO = ('mp4', 'mkv', 'mov', 'm4v', 'avi', 'webm', 'flv', 'ts',
                  'm2ts', 'mts', '3gp', 'mpg', 'mpeg', 'wmv', 'asf', 'ogv')
WRITABLE_AUDIO = ('mp3', 'wav', 'flac', 'aac', 'm4a', 'm4b', 'ogg', 'oga',
                  'opus', 'wma', 'aiff', 'aif', 'mka', 'ac3', 'w64', 'caf', 'au')
WRITABLE_IMAGE = ('jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff', 'gif',
                  'tga', 'jxl', 'avif', 'jp2', 'qoi', 'pcx', 'ppm', 'pgm',
                  'pbm', 'pam', 'sgi', 'dpx', 'exr', 'xbm', 'xwd', 'ras')


# Files that are certainly not media. They are never offered to FFmpeg as
# "unfamiliar formats" (FFmpeg would even open .txt as ANSI art).
NON_MEDIA_EXTS = frozenset((
    'txt', 'md', 'rtf', 'log', 'ini', 'cfg', 'json', 'xml', 'yaml', 'yml', 'csv',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
    'epub', 'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'iso', 'exe', 'msi',
    'dll', 'sys', 'bat', 'cmd', 'ps1', 'sh', 'py', 'pyc', 'js', 'html',
    'htm', 'css', 'c', 'cpp', 'h', 'java', 'cs', 'lnk', 'url', 'torrent', 'db',
    'sqlite', 'srt', 'ass', 'ssa', 'vtt', 'sub', 'nfo', 'cue', 'm3u', 'm3u8', 'pls',
    'ttf', 'otf', 'woff', 'woff2', 'apk', 'jar',
))


def ext_of(path):
    return os.path.splitext(path)[1].lstrip('.').lower()


def kind_of_ext(ext):
    """'video', 'audio', 'image' or None from an extension alone."""
    ext = (ext or '').lower()
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in IMAGE_EXTS:
        return 'image'
    return None


def output_ext(src_ext, kind):
    """The source's extension if FFmpeg can write that container, otherwise a
    widely compatible fallback: MP4 for video, MP3 for audio, JPEG for images."""
    src_ext = (src_ext or '').lower()
    writable = {'video': WRITABLE_VIDEO, 'audio': WRITABLE_AUDIO,
                'image': WRITABLE_IMAGE}.get(kind, ())
    if src_ext in writable:
        return src_ext
    return {'video': 'mp4', 'audio': 'mp3', 'image': 'jpg'}.get(kind, src_ext)


def file_filter(title, exts):
    """A Qt file-dialog filter listing every extension, plus 'All files'."""
    return f"{title} (" + " ".join(f"*.{e}" for e in exts) + ");;All files (*.*)"


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


def _settings_file():
    return os.path.join(config_dir(), 'settings.json')


def load_setting(key, default=None):
    """Read one remembered preference (small values only)."""
    import json
    try:
        with open(_settings_file(), 'r', encoding='utf-8') as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


def save_setting(key, value):
    import json
    data = {}
    try:
        with open(_settings_file(), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        pass
    data[key] = value
    try:
        with open(_settings_file(), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


def human_size(kb):
    return f"{kb/1024:.2f} MB" if kb >= 1024 else f"{kb} KB"


def fmt_bytes(n):
    """Byte count -> a compact human string."""
    n = float(max(0, n))
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def unique_path(path):
    """Return `path`, or `name_1.ext`, `name_2.ext`... so nothing is overwritten."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    for i in range(1, 1000):
        candidate = f"{stem}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
    return path


def file_size_kb(path):
    try:
        return os.path.getsize(path) // 1024
    except Exception:
        return 0


def ffmpeg_available():
    return FFMPEG != 'ffmpeg' or shutil.which('ffmpeg') is not None


def open_file(path):
    """Open a file with its default application (plays a clip, shows an image)."""
    try:
        if os.name == 'nt':
            os.startfile(path)  # noqa
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


def open_in_explorer(path):
    """Show a file (selected) or a folder in the OS file manager."""
    try:
        if os.name == 'nt' and os.path.isfile(path):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            return
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
    """Milliseconds -> 'M:SS', or 'H:MM:SS' once the hour mark is passed."""
    total = max(0, int(ms)) // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_duration(ms):
    """Milliseconds -> a readable length like '1m 23.450s'."""
    total = max(0, int(ms))
    h = total // 3600000
    m = (total % 3600000) // 60000
    sec = (total % 60000) / 1000.0
    if h:
        return f"{h}h {m}m {sec:.3f}s"
    if m:
        return f"{m}m {sec:.3f}s"
    return f"{sec:.3f}s"


def parse_timecode(text):
    """Parse a timecode into milliseconds, forgiving about the format.

    Accepts 'HH:MM:SS.mmm', 'MM:SS.mmm', 'SS.mmm' and plain numbers.
    Returns None when the text can't be read as a time at all.
    """
    if text is None:
        return None
    text = str(text).strip().replace(',', '.')
    if not text:
        return None
    parts = text.split(':')
    if len(parts) > 3:
        return None
    try:
        values = [float(p) if p.strip() else 0.0 for p in parts]
    except ValueError:
        return None
    if any(v < 0 for v in values):
        return None
    seconds = 0.0
    for v in values:                     # left-to-right: h, m, s (or m, s / s)
        seconds = seconds * 60 + v
    return int(round(seconds * 1000))


def hhmmss_to_sec(text):
    """'HH:MM:SS.mmm' -> float seconds."""
    ms = parse_timecode(text)
    return (ms / 1000.0) if ms is not None else 0.0
