"""Font Awesome icon helpers (via qtawesome, with graceful fallback)."""

from PyQt5.QtGui import QIcon, QPixmap

try:
    import qtawesome as qta
    HAS_QTA = True
except Exception:
    HAS_QTA = False


def fa(name, color):
    if HAS_QTA:
        try:
            return qta.icon(name, color=color)
        except Exception:
            pass
    return QIcon()


def fa_pixmap(name, color, px):
    if HAS_QTA:
        try:
            return qta.icon(name, color=color).pixmap(px, px)
        except Exception:
            pass
    return QPixmap()
