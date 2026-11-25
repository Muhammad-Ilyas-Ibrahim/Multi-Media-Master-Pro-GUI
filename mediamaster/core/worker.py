"""Background FFmpeg worker thread. Never blocks the UI."""

import os
import csv
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from . import config


class Worker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    done = pyqtSignal(str, str)      # message, path to reveal
    failed = pyqtSignal(str)

    def __init__(self, task, params):
        super().__init__()
        self.task = task
        self.p = params
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # -- ffmpeg helpers --------------------------------------------------- #
    def _duration(self, path):
        try:
            proc = subprocess.Popen(
                [config.FFMPEG, '-i', path], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
                creationflags=config.CREATE_NO_WINDOW)
            err = proc.communicate()[1]
            for line in err.split('\n'):
                if 'Duration:' in line:
                    d = line.split('Duration:')[1].split(',')[0].strip()
                    h, m, s = d.split(':')
                    return float(h) * 3600 + float(m) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _time_from_line(line):
        try:
            if 'time=' in line:
                t = line.split('time=')[1].split(' ')[0].strip()
                h, m, s = t.split(':')
                return float(h) * 3600 + float(m) * 60 + float(s)
        except Exception:
            pass
        return None

    def _run(self, cmd, duration, base, span):
        """Run ffmpeg, mapping its time= output onto [base, base+span]."""
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1, universal_newlines=True,
            creationflags=config.CREATE_NO_WINDOW)
        last = base
        while True:
            if self._cancel:
                proc.terminate()
                return 1
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            self.log.emit(line.rstrip())
            cur = self._time_from_line(line)
            if cur is not None and duration > 0:
                val = int(base + min(cur / duration, 1.0) * span)
                if val > last:
                    last = val
                    self.progress.emit(min(val, base + span))
        proc.wait()
        return proc.returncode

    def run(self):
        try:
            getattr(self, self.task)()
        except Exception as e:
            self.failed.emit(str(e))

    @staticmethod
    def _video_params(level):
        return {1: ("20", "128k"), 2: ("25", "96k"), 3: ("30", "64k")}[level]

    @staticmethod
    def _image_quality(level):
        return {1: "3", 2: "6", 3: "12"}[level]

    # -- tasks ------------------------------------------------------------ #
    def compress_video(self):
        inp = self.p['input']; level = self.p['level']
        ext = self.p.get('ext') or config.output_ext(config.ext_of(inp), 'video')
        self.status.emit("Analyzing video..."); self.progress.emit(4)
        original = config.file_size_kb(inp); dur = self._duration(inp)
        d, name = os.path.split(inp); stem = os.path.splitext(name)[0]
        suffix = {1: "_low", 2: "_compressed", 3: "_high"}[level]
        out = os.path.join(d, f"{stem}{suffix}.{ext}")
        crf, ab = self._video_params(level)
        cmd = [config.FFMPEG, '-i', inp, '-c:v', 'libx264', '-preset', 'medium',
               '-crf', crf, '-c:a', 'aac', '-b:a', ab, '-movflags', '+faststart', '-y', out]
        self.status.emit("Compressing video..."); self.progress.emit(8)
        rc = self._run(cmd, dur, 8, 88)
        if self._cancel:
            self.failed.emit("Cancelled."); return
        if rc != 0:
            self.failed.emit("FFmpeg failed to compress the video."); return
        comp = config.file_size_kb(out); self.progress.emit(100)
        msg = (f"Video compressed successfully.\n\nOriginal: {config.human_size(original)}\n"
               f"New: {config.human_size(comp)}")
        if original:
            msg += f"\nReduction: {((original-comp)/original*100):.1f}%"
        msg += f"\n\nSaved to:\n{out}"
        self.done.emit(msg, out)

    def compress_videos(self):
        self._batch_compress(config.VIDEO_EXTS, is_video=True)

    def compress_image(self):
        inp = self.p['input']; level = self.p['level']
        ext = self.p.get('ext') or config.output_ext(config.ext_of(inp), 'image')
        original = config.file_size_kb(inp)
        d, name = os.path.split(inp); stem = os.path.splitext(name)[0]
        suffix = {1: "_q_high", 2: "_compressed", 3: "_q_low"}[level]
        out = os.path.join(d, f"{stem}{suffix}.{ext}")
        q = self._image_quality(level)
        self.status.emit("Compressing image..."); self.progress.emit(30)
        rc = self._run([config.FFMPEG, '-i', inp, '-q:v', q, '-y', out], 0, 30, 0)
        if rc != 0:
            self.failed.emit("FFmpeg failed to compress the image."); return
        comp = config.file_size_kb(out); self.progress.emit(100)
        msg = (f"Image compressed successfully.\n\nOriginal: {config.human_size(original)}\n"
               f"New: {config.human_size(comp)}")
        if original:
            msg += f"\nReduction: {((original-comp)/original*100):.1f}%"
        msg += f"\n\nSaved to:\n{out}"
        self.done.emit(msg, out)

    def compress_images(self):
        self._batch_compress(config.IMAGE_EXTS, is_video=False)

    @staticmethod
    def _batch_dst(out_dir, fname, ext, used):
        """Output path for one file of a batch. Two sources that would map to
        the same name (clip.rm and clip.vob -> clip.mp4) keep their original
        format in the name instead of overwriting each other."""
        stem, src_ext = os.path.splitext(fname)
        name = f"{stem}.{ext}"
        if name.lower() in used:
            name = f"{stem}_{src_ext.lstrip('.').lower()}.{ext}"
        used.add(name.lower())
        return os.path.join(out_dir, name)

    def _batch_compress(self, exts, is_video):
        folder = self.p['input']; level = self.p['level']; new_ext = self.p.get('ext')
        files = [f for f in os.listdir(folder)
                 if f.lower().endswith(tuple('.' + e for e in exts))]
        if not files:
            self.failed.emit("No matching media files found in that folder."); return
        out_dir = folder.rstrip('/\\') + "_compressed"; os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, 'compression_data.csv'); total = len(files)
        self.status.emit(f"Found {total} file(s). Starting batch...")
        with open(csv_path, 'w', newline='') as cf:
            w = csv.writer(cf)
            w.writerow(['File', 'Original (KB)', 'Compressed (KB)', 'Reduction (%)'])
            used = set()
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(folder, fname); stem = os.path.splitext(fname)[0]
                ext = new_ext or config.output_ext(config.ext_of(fname),
                                                   'video' if is_video else 'image')
                dst = self._batch_dst(out_dir, fname, ext, used); orig = config.file_size_kb(src)
                base = int(i / total * 100); span = int(1 / total * 100)
                self.status.emit(f"Processing {i+1}/{total}: {fname}")
                if is_video:
                    crf, ab = self._video_params(level)
                    cmd = [config.FFMPEG, '-i', src, '-c:v', 'libx264', '-preset', 'medium',
                           '-crf', crf, '-c:a', 'aac', '-b:a', ab, '-movflags', '+faststart', '-y', dst]
                    self._run(cmd, self._duration(src), base, span)
                else:
                    q = self._image_quality(level)
                    self._run([config.FFMPEG, '-i', src, '-q:v', q, '-y', dst], 0, 0, 0)
                    self.progress.emit(base + span)
                comp = config.file_size_kb(dst)
                red = f"{((orig-comp)/orig*100):.1f}" if orig else "0"
                w.writerow([fname, orig, comp, red]); self.log.emit(f"Done: {fname}  ({red}% smaller)")
        self.progress.emit(100)
        self.done.emit(f"Batch complete. {total} file(s) compressed.\n\nSaved to:\n{out_dir}", out_dir)

    def extract_audio(self):
        mode = self.p['mode']; inp = self.p['input']
        if mode == 'single':
            d, name = os.path.split(inp); out = os.path.join(d, os.path.splitext(name)[0] + '.mp3')
            dur = self._duration(inp); self.status.emit("Extracting audio..."); self.progress.emit(6)
            rc = self._run([config.FFMPEG, '-i', inp, '-q:a', '0', '-map', 'a', '-y', out], dur, 6, 90)
            if rc != 0:
                self.failed.emit("FFmpeg failed to extract audio."); return
            self.progress.emit(100); self.done.emit(f"Audio extracted successfully.\n\nSaved to:\n{out}", out)
        else:
            files = [f for f in os.listdir(inp)
                     if f.lower().endswith(tuple('.' + e for e in config.VIDEO_EXTS))]
            if not files:
                self.failed.emit("No video files found in that folder."); return
            out_dir = inp.rstrip('/\\') + "_audio"; os.makedirs(out_dir, exist_ok=True); total = len(files)
            used = set()
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(inp, fname); dst = self._batch_dst(out_dir, fname, 'mp3', used)
                self.status.emit(f"Extracting {i+1}/{total}: {fname}")
                base = int(i / total * 100); span = int(1 / total * 100)
                self._run([config.FFMPEG, '-i', src, '-q:a', '0', '-map', 'a', '-y', dst],
                          self._duration(src), base, span)
            self.progress.emit(100)
            self.done.emit(f"Extracted audio from {total} file(s).\n\nSaved to:\n{out_dir}", out_dir)

    def convert_media(self):
        mode = self.p['mode']; inp = self.p['input']; ext = self.p['ext']; kind = self.p['kind']
        if mode == 'single':
            d, name = os.path.split(inp); out = os.path.join(d, os.path.splitext(name)[0] + f'.{ext}')
            dur = self._duration(inp) if kind == 'audio' else 0
            self.status.emit(f"Converting to .{ext}..."); self.progress.emit(20 if kind == 'image' else 6)
            rc = self._run([config.FFMPEG, '-i', inp, '-y', out], dur, 6, 90)
            if rc != 0:
                self.failed.emit("FFmpeg failed to convert the file."); return
            self.progress.emit(100); self.done.emit(f"Converted successfully.\n\nSaved to:\n{out}", out)
        else:
            src_exts = config.AUDIO_EXTS if kind == 'audio' else config.IMAGE_EXTS
            files = [f for f in os.listdir(inp)
                     if f.lower().endswith(tuple('.' + e for e in src_exts))]
            if not files:
                self.failed.emit("No matching files found in that folder."); return
            out_dir = inp.rstrip('/\\') + f"_{ext}"; os.makedirs(out_dir, exist_ok=True); total = len(files)
            used = set()
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(inp, fname); dst = self._batch_dst(out_dir, fname, ext, used)
                self.status.emit(f"Converting {i+1}/{total}: {fname}")
                base = int(i / total * 100); span = int(1 / total * 100)
                dur = self._duration(src) if kind == 'audio' else 0
                self._run([config.FFMPEG, '-i', src, '-y', dst], dur, base, span)
                if kind == 'image':
                    self.progress.emit(base + span)
            self.progress.emit(100)
            self.done.emit(f"Converted {total} file(s) to .{ext}.\n\nSaved to:\n{out_dir}", out_dir)

    # Encoder choices per output container, used when a trim is re-encoded.
    _AUDIO_CODECS = {
        'mp3': ['-c:a', 'libmp3lame', '-q:a', '2'],
        'wav': ['-c:a', 'pcm_s16le'],
        'flac': ['-c:a', 'flac'],
        'm4a': ['-c:a', 'aac', '-b:a', '192k'],
        'm4b': ['-c:a', 'aac', '-b:a', '192k'],
        'aac': ['-c:a', 'aac', '-b:a', '192k'],
        'ogg': ['-c:a', 'libvorbis', '-q:a', '5'],
        'oga': ['-c:a', 'libvorbis', '-q:a', '5'],
        'opus': ['-c:a', 'libopus', '-b:a', '160k'],
        'wma': ['-c:a', 'wmav2', '-b:a', '192k'],
        'aiff': ['-c:a', 'pcm_s16be'],
        'mka': ['-c:a', 'flac'],
        'aif': ['-c:a', 'pcm_s16be'],
    }
    _VIDEO_CODECS = {
        'webm': ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-row-mt', '1',
                 '-deadline', 'good', '-cpu-used', '4', '-c:a', 'libopus', '-b:a', '128k'],
        'avi': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-c:a', 'libmp3lame', '-q:a', '2'],
        'wmv': ['-c:v', 'wmv2', '-q:v', '3', '-c:a', 'wmav2', '-b:a', '192k'],
        'mpg': ['-c:v', 'mpeg2video', '-q:v', '3', '-c:a', 'mp2', '-b:a', '192k'],
        'mpeg': ['-c:v', 'mpeg2video', '-q:v', '3', '-c:a', 'mp2', '-b:a', '192k'],
        'flv': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k'],
    }
    _H264_AAC = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k']

    def trim_media(self):
        """Cut [start_ms, end_ms] out of a video or audio file.

        params:
            input       source path
            start_ms    in point
            end_ms      out point
            precise     re-encode for a frame-exact cut (else stream copy)
            out_ext     target extension, or None to keep the source's
            audio_only  drop the picture (e.g. export a clip's sound as MP3)
        """
        inp = self.p['input']
        start_ms = max(0, int(self.p.get('start_ms', 0)))
        end_ms = int(self.p.get('end_ms', 0))
        audio_only = bool(self.p.get('audio_only', False))
        src_ext = os.path.splitext(inp)[1].lstrip('.').lower()
        precise = bool(self.p.get('precise', False))
        out_ext = (self.p.get('out_ext') or '').lower()
        if not out_ext:
            kind = config.kind_of_ext(src_ext) or ('video' if self.p.get('has_video', True) else 'audio')
            if kind == 'image':
                kind = 'video'
            writable = config.WRITABLE_VIDEO if kind == 'video' else config.WRITABLE_AUDIO
            if src_ext in writable:
                out_ext = src_ext
            elif precise:
                out_ext = 'mp4' if kind == 'video' else 'mp3'
            else:
                # Matroska can hold almost any codec, so a lossless copy of a
                # file whose own container FFmpeg can't write still works.
                out_ext = 'mkv' if kind == 'video' else 'mka'
        # A container change can't be stream-copied reliably, so encode it.
        same_family = out_ext == src_ext or (out_ext in ('mkv', 'mka') and not self.p.get('out_ext'))
        precise = precise or not same_family or audio_only

        d, name = os.path.split(inp); stem = os.path.splitext(name)[0]
        out = config.unique_path(os.path.join(d, f"{stem}_trimmed.{out_ext}"))
        dur = max(0.0, (end_ms - start_ms) / 1000.0)
        if dur <= 0:
            self.failed.emit("The trim range is empty."); return

        def build(precise, out_ext, out):
            cmd = [config.FFMPEG, '-hide_banner', '-nostdin',
                   '-ss', f"{start_ms / 1000.0:.3f}", '-i', inp, '-t', f"{dur:.3f}"]
            is_audio_target = audio_only or (out_ext in config.AUDIO_EXTS
                                             and out_ext not in config.VIDEO_EXTS)
            if precise:
                if is_audio_target:
                    cmd += ['-vn', '-sn', '-dn'] + self._AUDIO_CODECS.get(out_ext, [])
                else:
                    cmd += ['-sn', '-dn'] + self._VIDEO_CODECS.get(out_ext, self._H264_AAC)
                    if out_ext in ('mp4', 'm4v', 'mov'):
                        cmd += ['-movflags', '+faststart']
            else:
                # Input-side -ss seeks to the keyframe at/before the in point.
                cmd += ['-map', '0:v?', '-map', '0:a?', '-c', 'copy',
                        '-avoid_negative_ts', 'make_zero']
            return cmd + ['-map_metadata', '0', '-y', out]

        def attempt(precise, out_ext, out):
            self.status.emit("Trimming (precise re-encode)..." if precise
                             else "Trimming (fast copy)...")
            cmd = build(precise, out_ext, out)
            self.log.emit(" ".join(f'"{c}"' if ' ' in c else c for c in cmd))
            rc = self._run(cmd, dur, 5, 93)
            ok = rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0
            if not ok:
                self._discard(out)
            return ok

        self.progress.emit(5)
        ok = attempt(precise, out_ext, out)
        if not ok and not precise and not self._cancel:
            # Some codecs (old RealMedia, game formats, ...) can't be copied into
            # any container FFmpeg writes. Re-encode instead of giving up.
            self.log.emit("Fast copy isn't possible for this file; re-encoding instead.")
            if not self.p.get('out_ext'):
                kind_video = out_ext in config.VIDEO_EXTS
                if out_ext in ('mkv', 'mka'):
                    out_ext = 'mp4' if kind_video else 'mp3'
                    out = config.unique_path(os.path.join(d, f"{stem}_trimmed.{out_ext}"))
            self.progress.emit(5)
            ok = attempt(True, out_ext, out)
        if self._cancel:
            self._discard(out)
            self.failed.emit("Cancelled."); return
        if not ok:
            self.failed.emit("FFmpeg could not trim this file. Open the log for details."); return
        self.progress.emit(100)
        self.done.emit(f"Clip saved ({config.fmt_duration(end_ms - start_ms)}).\n\nSaved to:\n{out}", out)

    @staticmethod
    def _discard(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
