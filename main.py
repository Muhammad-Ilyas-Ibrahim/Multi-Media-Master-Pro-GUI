#!/usr/bin/env python3
"""
Multi-Media-Master-Pro - desktop GUI
====================================
Entry point. Run with:  python main.py

Package layout (mediamaster/):
    core/                    backend layer
        config.py            constants, paths, ffmpeg discovery, helpers
        media.py             probing, filmstrip and waveform generation
        playback.py          FFmpeg-driven video/audio preview engine
        worker.py            background FFmpeg thread (all tasks)
    ui/                      presentation layer
        icons.py             theme-aware Phosphor icons (qtawesome)
        theme.py             light/dark palettes + stylesheet
        dnd.py               drag-and-drop helpers
        widgets.py           layouts, source picker, form controls
        timeline.py          zoomable trim timeline (in/out handles)
        video_view.py        preview surface
        trim_studio.py       trim & preview page
        main_window.py       the main window that ties it together

Requires: PyQt5, qtawesome  (pip install -r requirements.txt)
"""

import os
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication, QFont


def _configure_high_dpi():
    """Scale cleanly at 100/125/150/175% and on mixed-DPI multi-monitor setups."""
    # Per-monitor DPI awareness so moving between screens rescales properly.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # Without this Qt rounds 125% down to 100% and 150% up to 200%, which makes
    # the UI tiny or huge. PassThrough uses the exact Windows scale factor.
    if hasattr(QGuiApplication, "setHighDpiScaleFactorRoundingPolicy"):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)


def main():
    _configure_high_dpi()
    app = QApplication(sys.argv)

    from mediamaster.core import config
    from mediamaster.ui.main_window import MainWindow

    app.setApplicationName(config.APP_NAME)
    app.setStyle("Fusion")                   # consistent rendering under the stylesheet
    font = QFont("Segoe UI")
    font.setPixelSize(13)
    app.setFont(font)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
