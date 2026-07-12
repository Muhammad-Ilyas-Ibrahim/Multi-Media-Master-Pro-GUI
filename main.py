#!/usr/bin/env python3
"""
Multi-Media-Master-Pro v1.3 - Professional GUI (modular)
========================================================
Entry point. Run with:  python main.py

Package layout (mediamaster/):
    core/                    backend layer
        config.py            constants, paths, ffmpeg discovery, helpers
        worker.py            background FFmpeg thread (all tasks)
    ui/                      presentation layer
        icons.py             Font Awesome icon helpers (qtawesome)
        theme.py             light/dark palettes + stylesheet
        widgets.py           reusable form widgets
        timeline.py          scrubbable trim timeline (in/out handles)
        trim_studio.py       media-player trim page
        main_window.py       the main window that ties it together

Requires: PyQt5, qtawesome  (pip install -r requirements.txt)
"""

import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from mediamaster.core import config
from mediamaster.ui.main_window import MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
