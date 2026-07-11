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
        ext = self.p.get('ext') or os.path.splitext(inp)[1].lstrip('.')
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
        ext = self.p.get('ext') or os.path.splitext(inp)[1].lstrip('.')
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
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(folder, fname); stem = os.path.splitext(fname)[0]
                ext = new_ext or os.path.splitext(fname)[1].lstrip('.')
                dst = os.path.join(out_dir, f"{stem}.{ext}"); orig = config.file_size_kb(src)
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
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(inp, fname); dst = os.path.join(out_dir, os.path.splitext(fname)[0] + '.mp3')
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
            for i, fname in enumerate(files):
                if self._cancel:
                    self.failed.emit("Cancelled."); return
                src = os.path.join(inp, fname); dst = os.path.join(out_dir, os.path.splitext(fname)[0] + f'.{ext}')
                self.status.emit(f"Converting {i+1}/{total}: {fname}")
                base = int(i / total * 100); span = int(1 / total * 100)
                dur = self._duration(src) if kind == 'audio' else 0
                self._run([config.FFMPEG, '-i', src, '-y', dst], dur, base, span)
                if kind == 'image':
                    self.progress.emit(base + span)
            self.progress.emit(100)
            self.done.emit(f"Converted {total} file(s) to .{ext}.\n\nSaved to:\n{out_dir}", out_dir)

    def trim_media(self):
        inp = self.p['input']
        start = self.p.get('start') or "00:00:00.000"
        end = self.p.get('end')                 # may be None -> to end of file
        reencode = bool(self.p.get('reencode', False))
        d, name = os.path.split(inp); stem, ext = os.path.splitext(name)
        out = os.path.join(d, f"{stem}_trimmed{ext}")

        s_sec = config.hhmmss_to_sec(start)
        e_sec = config.hhmmss_to_sec(end) if end else 0.0
        dur = max(0.0, e_sec - s_sec) if end else 0.0

        if reencode:
            # Accurate: decode then seek/cut, re-encode.
            cmd = [config.FFMPEG, '-i', inp, '-ss', start]
            if end:
                cmd += ['-to', end]
            cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                    '-c:a', 'aac', '-y', out]
            self.status.emit("Trimming (precise re-encode)...")
        else:
            # Fast: stream copy. -ss before -i for quick seek, -t for duration.
            cmd = [config.FFMPEG, '-ss', start, '-i', inp]
            if end and dur > 0:
                cmd += ['-t', f"{dur:.3f}"]
            cmd += ['-c', 'copy', '-avoid_negative_ts', 'make_zero', '-y', out]
            self.status.emit("Trimming (fast copy)...")

        self.progress.emit(10)
        rc = self._run(cmd, dur, 10, 88)
        if self._cancel:
            self.failed.emit("Cancelled."); return
        if rc != 0:
            self.failed.emit("FFmpeg failed to trim. Check the in/out points."); return
        self.progress.emit(100)
        self.done.emit(f"Trimmed successfully.\n\nSaved to:\n{out}", out)
