"""Colour palettes and the Qt stylesheet builder."""

THEMES = {
    'dark': {
        'window': '#0f1117', 'surface': '#181b24', 'surface2': '#20242f',
        'sidebar_top': '#161922', 'sidebar_bottom': '#1d212c',
        'text': '#e7ebf3', 'subtext': '#98a2b3', 'border': '#2a2f3c',
        'input_bg': '#20242f', 'accent': '#5b8cff', 'accent2': '#8b5cf6',
        'accent_text': '#ffffff', 'success': '#2ec27e', 'danger': '#ff5f56',
        'nav_hover': '#232838', 'nav_active': '#293251',
        'track': '#242a38', 'header_top': '#5b8cff', 'header_bottom': '#8b5cf6',
        'video_bg': '#05060a',
    },
    'light': {
        'window': '#eef1f7', 'surface': '#ffffff', 'surface2': '#f4f6fb',
        'sidebar_top': '#ffffff', 'sidebar_bottom': '#eaf0fb',
        'text': '#1a1d27', 'subtext': '#5c6675', 'border': '#e2e7f0',
        'input_bg': '#f6f8fc', 'accent': '#4a6cf7', 'accent2': '#7c5cff',
        'accent_text': '#ffffff', 'success': '#12a05f', 'danger': '#e04545',
        'nav_hover': '#eef2fd', 'nav_active': '#e2ebff',
        'track': '#e7ecf5', 'header_top': '#4a6cf7', 'header_bottom': '#7c5cff',
        'video_bg': '#0b0d12',
    },
}


def build_qss(p):
    return """
* { font-family: 'Segoe UI', 'Inter', Arial, sans-serif; }
QMainWindow, QWidget#root { background: %(window)s; }
QWidget { color: %(text)s; font-size: 15px; }

QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(sidebar_top)s, stop:1 %(sidebar_bottom)s);
    border-right: 1px solid %(border)s;
}
QLabel#brand { color: %(text)s; font-size: 20px; font-weight: 800; }
QLabel#brandSub { color: %(subtext)s; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QPushButton#nav {
    text-align: left; padding: 13px 16px; border: none; border-radius: 10px;
    color: %(subtext)s; font-size: 15.5px; font-weight: 600; background: transparent;
}
QPushButton#nav:hover { background: %(nav_hover)s; color: %(text)s; }
QPushButton#nav:checked {
    background: %(nav_active)s; color: %(text)s; border-left: 3px solid %(accent)s;
}

QFrame#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 %(header_top)s, stop:1 %(header_bottom)s);
    border-radius: 16px;
}
QLabel#pageTitle { color: #ffffff; font-size: 25px; font-weight: 800; }
QLabel#pageDesc  { color: rgba(255,255,255,0.90); font-size: 14px; }

QFrame#card {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px;
}
QLabel#cardTitle { font-size: 17px; font-weight: 700; color: %(text)s; }
QLabel#hint { color: %(subtext)s; font-size: 13px; }
QLabel#sectionLabel { color: %(subtext)s; font-size: 13.5px; font-weight: 700; }
QLabel#recTimer { color: %(text)s; font-size: 40px; font-weight: 800;
    font-family: 'Consolas', 'Segoe UI', monospace; letter-spacing: 2px; }
QLabel#timeReadout { color: %(text)s; font-size: 15px; font-weight: 700;
    font-family: 'Consolas', 'Segoe UI', monospace; }
QLabel#chipStart { color: %(success)s; font-weight: 700; font-family: 'Consolas', monospace; }
QLabel#chipEnd { color: %(accent)s; font-weight: 700; font-family: 'Consolas', monospace; }
QFrame#videoFrame { background: %(video_bg)s; border: 1px solid %(border)s; border-radius: 12px; }
QLabel#videoHint { color: #7f8896; font-size: 14px; }

QMessageBox, QDialog { background: %(surface)s; }
QMessageBox QLabel, QDialog QLabel { color: %(text)s; font-size: 15px; background: transparent; }
QMessageBox QPushButton, QDialog QPushButton {
    background: %(surface2)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 8px 20px; font-weight: 700; min-width: 96px;
}
QMessageBox QPushButton:hover, QDialog QPushButton:hover { border: 1px solid %(accent)s; color: %(accent)s; }
QMessageBox QPushButton:default {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(accent)s, stop:1 %(accent2)s);
    color: #ffffff; border: none;
}

QLineEdit, QComboBox {
    background: %(input_bg)s; border: 1px solid %(border)s; border-radius: 9px;
    padding: 10px 13px; color: %(text)s; font-size: 15px; selection-background-color: %(accent)s;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid %(accent)s; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(border)s;
    selection-background-color: %(accent)s; selection-color: #ffffff; outline: none;
}

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(accent)s, stop:1 %(accent2)s);
    color: %(accent_text)s; border: none; border-radius: 10px;
    padding: 12px 26px; font-size: 15.5px; font-weight: 700;
}
QPushButton#primary:hover { background: %(accent)s; }
QPushButton#primary:disabled { background: %(track)s; color: %(subtext)s; }
QPushButton#ghost {
    background: %(surface2)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 9px; padding: 10px 18px; font-size: 14.5px; font-weight: 600;
}
QPushButton#ghost:hover { border: 1px solid %(accent)s; color: %(accent)s; }
QPushButton#record {
    background: %(danger)s; color: #ffffff; border: none; border-radius: 10px;
    padding: 12px 24px; font-size: 15px; font-weight: 700;
}
QPushButton#record:hover { background: #ff7b73; }
QPushButton#recording {
    background: %(success)s; color: #ffffff; border: none; border-radius: 10px;
    padding: 12px 24px; font-size: 15px; font-weight: 700;
}
QPushButton#playbtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(accent)s, stop:1 %(accent2)s);
    color: #ffffff; border: none; border-radius: 22px; font-weight: 700;
}
QPushButton#playbtn:hover { background: %(accent)s; }
QPushButton#themeToggle {
    background: rgba(255,255,255,0.18); color: #ffffff; border: none;
    border-radius: 18px; font-size: 16px; font-weight: 700;
}
QPushButton#themeToggle:hover { background: rgba(255,255,255,0.32); }

QRadioButton, QCheckBox { color: %(text)s; spacing: 9px; font-weight: 600; font-size: 15px; }
QRadioButton::indicator, QCheckBox::indicator { width: 19px; height: 19px; }
QRadioButton::indicator { border: 2px solid %(subtext)s; border-radius: 9px; background: %(input_bg)s; }
QRadioButton::indicator:checked {
    border: 2px solid %(accent)s;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 %(accent)s, stop:0.45 %(accent)s, stop:0.5 %(input_bg)s);
}
QCheckBox::indicator { border: 2px solid %(subtext)s; border-radius: 5px; background: %(input_bg)s; }
QCheckBox::indicator:checked { border: 2px solid %(accent)s; background: %(accent)s; }

QProgressBar {
    background: %(track)s; border: none; border-radius: 8px; height: 16px;
    text-align: center; color: %(text)s; font-size: 11px; font-weight: 700;
}
QProgressBar::chunk {
    border-radius: 8px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(accent)s, stop:1 %(accent2)s);
}

QPlainTextEdit#console {
    background: %(surface2)s; border: 1px solid %(border)s; border-radius: 10px;
    color: %(subtext)s; font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px; padding: 8px;
}
QLabel#status { color: %(subtext)s; font-size: 13.5px; font-weight: 600; }

/* Opaque page backgrounds so switching pages fully repaints
   (transparent pages ghost the previous page under a native video widget). */
QScrollArea { border: none; background: %(window)s; }
QScrollArea > QWidget { background: %(window)s; }
QStackedWidget { background: %(window)s; }
QStackedWidget > QWidget { background: %(window)s; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
""" % p
