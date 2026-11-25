"""Colour palettes and the Qt stylesheet.

The look follows desktop tools rather than web dashboards: neutral graphite
surfaces, hairline separators, 4-6px corners, one accent colour reserved for
selection and the primary action, and no gradients or drop shadows. All sizes
are logical pixels, so Qt's high-DPI scaling keeps them proportional at any
Windows display scale.
"""

import os
import tempfile

THEMES = {
    'dark': {
        'window': '#1e1f22',
        'surface': '#25272b',
        'surface2': '#2b2d31',
        'surface3': '#35373c',
        'sidebar': '#1a1b1e',
        'border': '#36383d',
        'border_strong': '#4a4d53',
        'text': '#dfe1e5',
        'subtext': '#a4a8b0',
        'muted': '#71757d',
        'accent': '#3d7ef0',
        'accent_hover': '#4f8bf3',
        'accent_press': '#3270dc',
        'accent_soft': 'rgba(61, 126, 240, 0.18)',
        'accent_text': '#ffffff',
        'success': '#5aab76',
        'warn': '#d7a24c',
        'warn_soft': 'rgba(215, 162, 76, 0.14)',
        'danger': '#e25c5c',
        'danger_hover': '#e87070',
        'track': '#2b2d31',
        'video_bg': '#111214',
        'overlay': 'rgba(0, 0, 0, 0.55)',
    },
    'light': {
        'window': '#f6f7f9',
        'surface': '#ffffff',
        'surface2': '#ffffff',
        'surface3': '#eceef2',
        'sidebar': '#eef0f3',
        'border': '#dcdfe4',
        'border_strong': '#c3c7ce',
        'text': '#1f2124',
        'subtext': '#565b64',
        'muted': '#878c95',
        'accent': '#2f6fe4',
        'accent_hover': '#3f7cea',
        'accent_press': '#2660cc',
        'accent_soft': 'rgba(47, 111, 228, 0.12)',
        'accent_text': '#ffffff',
        'success': '#2c8a55',
        'warn': '#a66b0c',
        'warn_soft': 'rgba(166, 107, 12, 0.10)',
        'danger': '#cf3a3a',
        'danger_hover': '#db4a4a',
        'track': '#e6e8ec',
        'video_bg': '#141517',
        'overlay': 'rgba(0, 0, 0, 0.55)',
    },
}

MONO = "'Cascadia Mono', 'Consolas', monospace"


_GLYPHS = {
    'chevron': "M2 3.5 L5 6.5 L8 3.5",          # combo-box arrow
    'check': "M2.2 5.2 L4.2 7.2 L7.8 3.2",      # checkbox tick
}


def _glyph_file(name, color):
    """Write a tiny stroked SVG glyph in `color` and return its path for QSS.

    Qt stylesheets can't draw arrows or ticks themselves, and qtawesome icons
    can't be referenced from QSS, so one small SVG per glyph and colour is
    cached on disk.
    """
    folder = os.path.join(tempfile.gettempdir(), "mmmp_ui")
    path = os.path.join(folder, f"{name}_{color.lstrip('#')}.svg")
    if not os.path.exists(path):
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                        f'viewBox="0 0 10 10"><path d="{_GLYPHS[name]}" fill="none" '
                        f'stroke="{color}" stroke-width="1.4" stroke-linecap="round" '
                        'stroke-linejoin="round"/></svg>')
        except OSError:
            return ""
    return path.replace("\\", "/")


def build_qss(p):
    p = dict(p, mono=MONO, chevron=_glyph_file('chevron', p['subtext']),
             check=_glyph_file('check', p['accent_text']))
    return """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QWidget { color: %(text)s; font-size: 13px; }
QMainWindow, QWidget#root, QWidget#mainColumn { background: %(window)s; }
QToolTip {
    background: %(surface3)s; color: %(text)s; border: 1px solid %(border_strong)s;
    padding: 4px 7px; font-size: 12px;
}

/* ----------------------------------------------------------------- sidebar */
QFrame#sidebar { background: %(sidebar)s; border: none; border-right: 1px solid %(border)s; }
QLabel#brand { color: %(text)s; font-size: 13px; font-weight: 600; }
QLabel#brandVersion { color: %(muted)s; font-size: 11px; }
QLabel#navSection {
    color: %(muted)s; font-size: 11px; font-weight: 600; padding: 0 10px;
}
QPushButton#nav {
    text-align: left; padding: 0 10px; min-height: 30px; max-height: 30px;
    border: none; border-radius: 5px; background: transparent;
    color: %(subtext)s; font-size: 13px;
}
QPushButton#nav[collapsed="true"] { text-align: center; padding: 0; }
QPushButton#nav:hover { background: %(surface3)s; color: %(text)s; }
QPushButton#nav:checked { background: %(accent_soft)s; color: %(text)s; }
QPushButton#sideTool {
    text-align: left; padding: 0 10px; min-height: 30px; max-height: 30px;
    border: none; border-radius: 5px; background: transparent;
    color: %(subtext)s; font-size: 12px;
}
QPushButton#sideTool[collapsed="true"] { text-align: center; padding: 0; }
QPushButton#sideTool:hover { background: %(surface3)s; color: %(text)s; }
QLabel#engineState { color: %(muted)s; font-size: 11px; padding: 0 10px; }

/* ------------------------------------------------------------------ header */
QFrame#pageHeader { background: %(window)s; border: none; border-bottom: 1px solid %(border)s; }
QLabel#pageTitle { color: %(text)s; font-size: 16px; font-weight: 600; }
QLabel#pageDesc  { color: %(subtext)s; font-size: 12px; }

/* ----------------------------------------------------------------- panels */
QFrame#panel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; }
QLabel#panelTitle { color: %(text)s; font-size: 12px; font-weight: 600; }
QLabel#formLabel { color: %(subtext)s; font-size: 12px; }
QLabel#hint { color: %(subtext)s; font-size: 12px; }
QLabel#meta { color: %(muted)s; font-size: 11.5px; }
QLabel#sectionLabel { color: %(subtext)s; font-size: 11.5px; font-weight: 600; }
QFrame#rule { background: %(border)s; border: none; }

/* ---------------------------------------------------------- source picker */
QFrame#source {
    background: %(surface)s; border: 1px dashed %(border_strong)s; border-radius: 6px;
}
QFrame#source:hover { border-color: %(muted)s; }
QFrame#source[filled="true"] { border: 1px solid %(border)s; }
QFrame#source[dropActive="true"] {
    background: %(accent_soft)s; border: 1px dashed %(accent)s;
}
QLabel#sourceTitle { color: %(text)s; font-size: 13px; font-weight: 600; }
QLabel#sourceMeta { color: %(subtext)s; font-size: 12px; }
QLabel#sourceMeta[error="true"] { color: %(danger)s; }

/* ------------------------------------------------------------ inputs */
QLineEdit, QComboBox {
    background: %(surface2)s; border: 1px solid %(border)s; border-radius: 4px;
    padding: 4px 8px; min-height: 20px; color: %(text)s;
    selection-background-color: %(accent)s; selection-color: %(accent_text)s;
}
QLineEdit:hover, QComboBox:hover { border-color: %(border_strong)s; }
QLineEdit:focus, QComboBox:focus { border-color: %(accent)s; }
QLineEdit:disabled, QComboBox:disabled { color: %(muted)s; background: %(window)s; }
QLineEdit[invalid="true"] { border-color: %(danger)s; }
QLineEdit#timecode { padding: 4px 6px; }
QComboBox { padding-right: 22px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: url("%(chevron)s"); width: 10px; height: 10px; margin-right: 6px; }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(border_strong)s; padding: 3px;
    selection-background-color: %(accent)s; selection-color: %(accent_text)s; outline: none;
}

/* ----------------------------------------------------------------- buttons */
QPushButton { min-height: 20px; }
QPushButton#primary {
    background: %(accent)s; color: %(accent_text)s; border: 1px solid %(accent)s;
    border-radius: 4px; padding: 5px 16px; font-weight: 600;
}
QPushButton#primary:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton#primary:pressed { background: %(accent_press)s; border-color: %(accent_press)s; }
QPushButton#primary:disabled { background: %(surface3)s; border-color: %(border)s; color: %(muted)s; }

QPushButton#secondary {
    background: %(surface2)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 4px; padding: 5px 12px;
}
QPushButton#secondary:hover { background: %(surface3)s; border-color: %(border_strong)s; }
QPushButton#secondary:pressed { background: %(surface)s; }
QPushButton#secondary:disabled { color: %(muted)s; }

QPushButton#tool {
    background: transparent; border: 1px solid transparent; border-radius: 4px;
    padding: 0; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
}
QPushButton#tool:hover { background: %(surface3)s; }
QPushButton#tool:pressed { background: %(border)s; }
QPushButton#tool:checked { background: %(accent_soft)s; }
QPushButton#tool:disabled { background: transparent; }

QPushButton#play {
    background: %(accent)s; border: none; border-radius: 16px;
    min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0;
}
QPushButton#play:hover { background: %(accent_hover)s; }
QPushButton#play:pressed { background: %(accent_press)s; }
QPushButton#play:disabled { background: %(surface3)s; }

QPushButton#link {
    background: transparent; border: none; color: %(accent)s; padding: 0 2px;
}
QPushButton#link:hover { color: %(accent_hover)s; text-decoration: underline; }

QPushButton#record {
    background: %(danger)s; color: #ffffff; border: 1px solid %(danger)s;
    border-radius: 4px; padding: 6px 18px; font-weight: 600;
}
QPushButton#record:hover { background: %(danger_hover)s; border-color: %(danger_hover)s; }
QPushButton#recording {
    background: %(surface2)s; color: %(danger)s; border: 1px solid %(danger)s;
    border-radius: 4px; padding: 6px 18px; font-weight: 600;
}
QPushButton#recording:hover { background: %(surface3)s; }

/* Segmented control: checkable buttons sharing one outline. */
QPushButton[seg="true"] {
    background: %(surface2)s; color: %(subtext)s; border: 1px solid %(border)s;
    padding: 4px 12px; border-radius: 0; margin: 0; border-left-width: 0;
}
QPushButton[seg="true"][segFirst="true"] {
    border-left-width: 1px; border-top-left-radius: 4px; border-bottom-left-radius: 4px;
}
QPushButton[seg="true"][segLast="true"] {
    border-top-right-radius: 4px; border-bottom-right-radius: 4px;
}
QPushButton[seg="true"]:hover { background: %(surface3)s; color: %(text)s; }
QPushButton[seg="true"]:checked { background: %(accent_soft)s; color: %(text)s; border-color: %(accent)s; border-left-width: 1px; }
QPushButton[seg="true"]:disabled { color: %(muted)s; }

/* ------------------------------------------------------- checks / radios */
QCheckBox, QRadioButton { spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }
QCheckBox::indicator {
    border: 1px solid %(border_strong)s; border-radius: 3px; background: %(surface2)s;
}
QCheckBox::indicator:checked {
    border-color: %(accent)s; background: %(accent)s; image: url("%(check)s");
}
QRadioButton::indicator {
    border: 1px solid %(border_strong)s; border-radius: 7px; background: %(surface2)s;
}
QRadioButton::indicator:checked { border: 4px solid %(accent)s; background: %(surface)s; }

/* ---------------------------------------------------------------- progress */
QProgressBar {
    background: %(track)s; border: none; border-radius: 2px;
    max-height: 4px; min-height: 4px; text-align: center; color: transparent;
}
QProgressBar::chunk { border-radius: 2px; background: %(accent)s; }

/* ----------------------------------------------------------------- sliders */
QSlider::groove:horizontal { height: 3px; background: %(border_strong)s; border-radius: 1px; }
QSlider::sub-page:horizontal { background: %(subtext)s; border-radius: 1px; }
QSlider::handle:horizontal {
    background: %(text)s; width: 11px; height: 11px; margin: -4px 0; border-radius: 5px;
}
QSlider::handle:horizontal:hover { background: %(accent)s; }

/* ------------------------------------------------------- trim studio */
QFrame#editorBar { background: %(window)s; border: none; }
QFrame#editorPanel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; }
QLabel#fileName { color: %(text)s; font-weight: 600; }
QLabel#timeReadout { color: %(text)s; font-family: %(mono)s; font-size: 13px; }
QLabel#timeReadoutDim { color: %(muted)s; font-family: %(mono)s; font-size: 13px; }
QLabel#readoutValue { color: %(text)s; font-family: %(mono)s; font-size: 12.5px; }
QFrame#vsep { background: %(border)s; border: none; min-width: 1px; max-width: 1px; }

/* ------------------------------------------------------- status / console */
QFrame#statusBar { background: %(sidebar)s; border: none; border-top: 1px solid %(border)s; }
QLabel#status { color: %(subtext)s; font-size: 12px; }
QLabel#status[state="busy"] { color: %(text)s; }
QLabel#status[state="ok"] { color: %(success)s; }
QLabel#status[state="error"] { color: %(danger)s; }
QPushButton#statusBtn {
    background: transparent; border: none; border-radius: 3px; color: %(subtext)s;
    padding: 2px 8px; font-size: 12px;
}
QPushButton#statusBtn:hover { background: %(surface3)s; color: %(text)s; }
QPushButton#statusBtn:checked { color: %(text)s; }
QPushButton#statusBtn:disabled { color: %(muted)s; }
QPlainTextEdit#console {
    background: %(sidebar)s; border: none; border-top: 1px solid %(border)s;
    color: %(subtext)s; font-family: %(mono)s; font-size: 11.5px; padding: 6px 10px;
}

QLabel#recTimer { color: %(text)s; font-size: 40px; font-weight: 300; font-family: %(mono)s; }
QLabel#recDot { color: %(danger)s; font-size: 12px; font-weight: 600; }

/* ------------------------------------------------------------- containers */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget#pageBody { background: %(window)s; }
QStackedWidget { background: %(window)s; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: %(muted)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 3px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ----------------------------------------------------------------- menus */
QMenu { background: %(surface)s; border: 1px solid %(border_strong)s; padding: 4px; }
QMenu::item { padding: 5px 24px 5px 10px; border-radius: 3px; }
QMenu::item:selected { background: %(accent)s; color: %(accent_text)s; }
QMenu::item:disabled { color: %(muted)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 4px 6px; }

/* ----------------------------------------------------------------- dialogs */
QMessageBox, QDialog { background: %(surface)s; }
QMessageBox QLabel { background: transparent; }
QMessageBox QPushButton, QDialog QPushButton {
    background: %(surface2)s; border: 1px solid %(border)s; border-radius: 4px;
    padding: 5px 14px; min-width: 76px;
}
QMessageBox QPushButton:hover, QDialog QPushButton:hover { background: %(surface3)s; }
QMessageBox QPushButton:default, QDialog QPushButton:default {
    background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s;
}
""" % p
