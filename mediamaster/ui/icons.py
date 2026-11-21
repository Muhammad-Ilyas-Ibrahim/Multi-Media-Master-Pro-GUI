"""Icon helpers (Phosphor icons via qtawesome) with theme-aware re-tinting.

`bind(widget, name, role)` sets an icon on a button or label and remembers it,
so `set_palette()` can recolour every bound icon when the theme changes.
`role` is a palette key ('subtext', 'accent', ...) or a literal '#rrggbb'.
"""

import weakref

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QAbstractButton, QLabel

try:
    import qtawesome as qta
    HAS_QTA = True
except Exception:                                   # pragma: no cover
    HAS_QTA = False

try:
    from PyQt5 import sip
except Exception:                                   # pragma: no cover
    import sip

from .theme import THEMES

_palette = dict(THEMES['dark'])
_bound = []                                         # [(weakref, name, role, px)]


def _color(role):
    if role.startswith('#'):
        return role
    return _palette.get(role, _palette['subtext'])


def icon(name, color):
    """A QIcon for a Phosphor name like 'ph.scissors' (or any qtawesome name)."""
    if HAS_QTA:
        try:
            return qta.icon(name, color=color, color_disabled=_palette['muted'])
        except Exception:
            pass
    return QIcon()


def pixmap(name, color, px):
    return icon(name, color).pixmap(QSize(px, px)) if HAS_QTA else QPixmap()


# Backwards-compatible names used elsewhere in the package.
fa = icon
fa_pixmap = pixmap


def _apply(widget, name, role, px):
    if isinstance(widget, QAbstractButton):
        widget.setIcon(icon(name, _color(role)))
        if px:
            widget.setIconSize(QSize(px, px))
    elif isinstance(widget, QLabel):
        widget.setPixmap(pixmap(name, _color(role), px or 16))


def bind(widget, name, role='subtext', px=None):
    """Set an icon now and keep it tinted to the theme from then on."""
    for i, (ref, _n, _r, _p) in enumerate(_bound):
        if ref() is widget:
            _bound[i] = (ref, name, role, px)
            break
    else:
        _bound.append((weakref.ref(widget), name, role, px))
    _apply(widget, name, role, px)


def set_palette(pal):
    _palette.clear()
    _palette.update(pal)
    alive = []
    for ref, name, role, px in _bound:
        w = ref()
        if w is None or sip.isdeleted(w):
            continue
        _apply(w, name, role, px)
        alive.append((ref, name, role, px))
    _bound[:] = alive


def palette():
    return _palette
