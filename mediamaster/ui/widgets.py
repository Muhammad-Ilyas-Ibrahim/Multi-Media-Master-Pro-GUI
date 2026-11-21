"""Reusable widgets: layout helpers, source picker, segmented control, timecode."""

import os

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QHBoxLayout, QVBoxLayout, QFrame,
    QButtonGroup, QFileDialog, QSizePolicy, QLayout, QSpacerItem, QFormLayout
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QFontMetrics

from . import dnd
from . import icons
from ..core import config
from ..core import media


# ------------------------------------------------------------------ layouts #
class FlowLayout(QLayout):
    """Lays items out left to right and wraps them onto new lines as needed.

    `addStretch()` inserts an expanding gap: on a line that has spare room it
    pushes the following items to the right edge, which gives the familiar
    "controls left, actions right" toolbar that still wraps on narrow windows.
    """

    def __init__(self, parent=None, hspacing=8, vspacing=8):
        super().__init__(parent)
        self._items = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    # QLayout plumbing
    def addItem(self, item):
        self._items.append(item)

    def addStretch(self):
        self.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._visible():
            if item.spacerItem() is None:
                size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # layout
    def _visible(self):
        out = []
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            out.append(item)
        return out

    def _layout(self, rect, apply):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        lines, line, line_w = [], [], 0
        for item in self._visible():
            w = 0 if item.spacerItem() is not None else item.sizeHint().width()
            needed = w if not line else line_w + self._h + w
            if line and needed > area.width() and item.spacerItem() is None:
                lines.append(line)
                line, line_w = [], 0
                needed = w
            line.append(item)
            line_w = needed
        if line:
            lines.append(line)

        y = area.y()
        for line in lines:
            # A stretch at the end of a line has nothing to push; drop it.
            while line and line[-1].spacerItem() is not None and len(line) > 1:
                line = line[:-1]
            real = [it for it in line if it.spacerItem() is None]
            if not real:
                continue
            line_h = max(it.sizeHint().height() for it in real)
            used = sum(it.sizeHint().width() for it in real) + self._h * (len(line) - 1)
            spacers = [it for it in line if it.spacerItem() is not None]
            extra = max(0, area.width() - used)
            per = extra // len(spacers) if spacers else 0
            x = area.x()
            for it in line:
                if it.spacerItem() is not None:
                    x += per + self._h
                    continue
                hint = it.sizeHint()
                if apply:
                    width = min(hint.width(), area.width())
                    it.setGeometry(QRect(QPoint(x, y + (line_h - hint.height()) // 2),
                                         QSize(width, hint.height())))
                x += hint.width() + self._h
            y += line_h + self._v
        return max(0, y - self._v - rect.y() + m.bottom())


def hbox(*items, spacing=6, margins=(0, 0, 0, 0)):
    """A horizontal box from widgets, layouts, ints (spacing) and None (stretch)."""
    lay = QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, int):
            lay.addSpacing(it)
        elif isinstance(it, QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    return lay


def group(*items, spacing=6):
    """Wrap a few widgets in one QWidget so a FlowLayout keeps them together."""
    w = QWidget()
    w.setLayout(hbox(*items, spacing=spacing))
    return w


def label(text, name=None, wrap=False):
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def hint(text, wrap=True):
    return label(text, "hint", wrap)


def vsep():
    line = QFrame()
    line.setObjectName("vsep")
    line.setFixedHeight(18)
    return line


def panel(title=None):
    """A bordered settings panel. Returns (frame, body_layout)."""
    frame = QFrame()
    frame.setObjectName("panel")
    body = QVBoxLayout(frame)
    body.setContentsMargins(16, 14, 16, 16)
    body.setSpacing(12)
    if title:
        body.addWidget(label(title, "panelTitle"))
    return frame, body


def form():
    """A label/field form that drops labels above fields when space runs out."""
    lay = QFormLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setHorizontalSpacing(18)
    lay.setVerticalSpacing(12)
    lay.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    lay.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    lay.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    lay.setRowWrapPolicy(QFormLayout.WrapLongRows)
    return lay


def form_label(text):
    lbl = label(text, "formLabel")
    lbl.setMinimumWidth(120)
    return lbl


def button(text, kind="secondary", icon_name=None, role=None, tooltip=None):
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if icon_name:
        if role is None:
            role = 'accent_text' if kind == 'primary' else 'subtext'
        icons.bind(b, icon_name, role, 15)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def tool_button(icon_name, tooltip, role='subtext', checkable=False, px=16):
    b = QPushButton()
    b.setObjectName("tool")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.TabFocus)
    icons.bind(b, icon_name, role, px)
    return b


def repolish(widget):
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)
    widget.update()


# ------------------------------------------------------------- elided label #
class ElidedLabel(QLabel):
    """A single-line label that shortens itself with an ellipsis instead of
    forcing its parent wider."""

    def __init__(self, text="", mode=Qt.ElideMiddle, parent=None):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        super().setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 40 else "")
        self._refresh()

    def text(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, self._mode, max(10, self.width())))

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(min(fm.horizontalAdvance(self._full) + 2, 600), fm.height())

    def minimumSizeHint(self):
        return QSize(40, self.fontMetrics().height())


# ---------------------------------------------------------- source picker #
_KIND_ICONS = {
    'video': 'ph.film-strip', 'audio': 'ph.music-notes', 'image': 'ph.image',
    'dir': 'ph.folder',
}
_KIND_NOUNS = {
    'video': "video", 'audio': "audio file", 'image': "image", 'dir': "folder",
}


def _article(noun):
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


class SourceField(dnd.DropTarget, QFrame):
    """The input of a page: a drop target that also browses.

    Empty, it invites a drop. Once filled, it shows the file name and what the
    app learned about it (size, length, resolution, codecs; or for a folder,
    how many matching files it holds), with Change and Clear actions.
    """

    pathChanged = pyqtSignal(str)

    def __init__(self, mode='file', kinds=('video',), file_filter='', empty_hint=None,
                 count_files=True, parent=None):
        """`count_files=False` is for output folders: show the path only,
        not how many matching files the folder already holds."""
        QFrame.__init__(self, parent)
        self.empty_hint = empty_hint
        self.count_files = count_files
        self.setObjectName("source")
        self.setProperty('filled', "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mode = mode
        self.kinds = tuple(kinds)
        self.file_filter = file_filter
        self._path = ""
        self._info = None
        self._probe = None
        self._probing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedSize(28, 28)
        self.icon.setAlignment(Qt.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = ElidedLabel("", Qt.ElideMiddle)
        self.title.setObjectName("sourceTitle")
        self.meta = ElidedLabel("", Qt.ElideRight)
        self.meta.setObjectName("sourceMeta")
        text.addWidget(self.title)
        text.addWidget(self.meta)
        self.browse_btn = button("Browse…", "secondary")
        self.browse_btn.clicked.connect(self.browse)
        self.clear_btn = tool_button('ph.x', "Clear")
        self.clear_btn.clicked.connect(self.clear)
        lay.addWidget(self.icon)
        lay.addLayout(text, 1)
        lay.addWidget(self.browse_btn)
        lay.addWidget(self.clear_btn)
        self.setMinimumHeight(64)
        self.init_drops()

        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(120)
        self._probe_timer.timeout.connect(self._start_probe)
        self._refresh()

    # -- configuration ---------------------------------------------------- #
    def set_mode(self, mode, kinds=None, file_filter=None):
        """Switch between one file and a whole folder. Going to folder mode
        with a file selected keeps working on that file's folder."""
        previous = self._path
        self.mode = mode
        if kinds is not None:
            self.kinds = tuple(kinds)
        if file_filter is not None:
            self.file_filter = file_filter
        self._path = ""
        self._info = None
        self._probing = False
        if mode == 'dir' and previous and os.path.isfile(previous):
            self.setText(os.path.dirname(previous))
        else:
            self._refresh()
            self.pathChanged.emit("")

    def accepted_kinds(self):
        return {'dir'} if self.mode == 'dir' else set(self.kinds)

    # -- drop policy ------------------------------------------------------ #
    def usable_drop(self, paths):
        """The first dropped path this field can use, or None."""
        for path in paths:
            kind = dnd.kind_of(path)
            if self.mode == 'dir':
                if kind == 'dir':
                    return path
                continue
            # Unfamiliar extensions are taken too: FFmpeg identifies them.
            if kind in self.kinds or dnd.is_unknown_file(path):
                return path
        return None

    def drop_accepts(self, paths):
        return self.usable_drop(paths) is not None

    def drop_handle(self, paths):
        target = self.usable_drop(paths)
        if target:
            self.setText(target)

    # -- api -------------------------------------------------------------- #
    def text(self):
        return self._path

    def info(self):
        return self._info

    def detected_kind(self):
        """What the selected file holds: from its extension, or from FFmpeg's
        probe when the extension is unfamiliar ('unknown' until it finishes)."""
        if not self._path:
            return None
        if self.mode == 'dir':
            return 'dir'
        kind = dnd.kind_of(self._path)
        if kind is not None:
            return kind
        if self._info is None or not self._info.ok:
            return 'unknown'
        return self._info.kind

    def problem(self):
        """Why the current selection can't be used, or None if it's fine."""
        path = self._path
        if not path:
            return f"Choose {_article(self._noun())} first."
        if self.mode == 'dir':
            return None if os.path.isdir(path) else "That folder no longer exists."
        if not os.path.isfile(path):
            return "That file no longer exists."
        if self._probing and dnd.kind_of(path) is None:
            return "Still identifying this file. Try again in a moment."
        info = self._info
        if info is not None and not info.ok:
            return (f"FFmpeg can't read {os.path.basename(path)}: it isn't a media "
                    "format FFmpeg understands, or the file is damaged.")
        kind = self.detected_kind()
        if kind not in self.kinds and kind != 'unknown':
            want = " or ".join(_KIND_NOUNS.get(k, k) for k in self.kinds)
            return (f"{os.path.basename(path)} is {_article(_KIND_NOUNS.get(kind, kind))}, "
                    f"not {_article(want)}.")
        return None

    def setText(self, path):
        path = os.path.normpath(path.strip().strip('"')) if path else ""
        if path == self._path:
            return
        self._path = path
        self._info = None
        self._refresh()
        self._probing = bool(path) and self.mode == 'file'
        if self._probing:
            self._probe_timer.start()
        self.pathChanged.emit(path)

    def clear(self):
        self.setText("")

    def browse(self):
        start = self._path if os.path.exists(self._path) else ""
        if self.mode == 'dir':
            path = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file", start,
                                                  self.file_filter or "All files (*.*)")
        if path:
            self.setText(path)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.browse()
        super().mouseReleaseEvent(e)

    # -- presentation ----------------------------------------------------- #
    def _noun(self):
        if self.mode == 'dir':
            return "folder"
        if len(self.kinds) == 1:
            return _KIND_NOUNS.get(self.kinds[0], "file")
        return "file"

    def _refresh(self):
        filled = bool(self._path)
        if self.property('filled') != ("true" if filled else "false"):
            self.setProperty('filled', "true" if filled else "false")
            repolish(self)
        self.clear_btn.setVisible(filled)
        self.browse_btn.setText("Change…" if filled else "Browse…")
        if not filled:
            icons.bind(self.icon, 'ph.upload-simple', 'muted', 22)
            self.title.setText(f"Drop {_article(self._noun())} here")
            self._set_meta(self._formats_hint())
            return
        kind = self.detected_kind()
        bad = self.mode == 'file' and not self._probing and self.problem() is not None
        icons.bind(self.icon, 'ph.warning-circle' if bad else _KIND_ICONS.get(kind, 'ph.file'),
                   'danger' if bad else 'accent', 22)
        name = os.path.basename(self._path.rstrip('\\/')) or self._path
        self.title.setText(name)
        self._set_meta(self._describe(), error=bad)

    def _set_meta(self, text, error=False):
        self.meta.setText(text)
        flag = "true" if error else "false"
        if self.meta.property('error') != flag:
            self.meta.setProperty('error', flag)
            repolish(self.meta)

    def _formats_hint(self):
        if self.empty_hint:
            return self.empty_hint
        if self.mode == 'dir':
            return "or click to browse  ·  every matching file inside is processed"
        exts = []
        for k in self.kinds:
            exts += [e.upper() for e in dnd.KIND_EXTS.get(k, ())[:4]]
        shown = ", ".join(dict.fromkeys(exts))
        return (f"or click to browse  ·  {shown} and any other format FFmpeg reads"
                if shown else "or click to browse")

    def _describe(self):
        path = self._path
        if os.path.isdir(path) and not self.count_files:
            return path
        if os.path.isdir(path):
            counts = dnd.folder_counts(path)
            parts = [f"{counts[k]} {_KIND_NOUNS[k]}{'s' if counts[k] != 1 else ''}"
                     for k in self.kinds if counts.get(k)]
            folder = os.path.dirname(path.rstrip('\\/'))
            return (folder + "  ·  " if folder else "") + (
                ", ".join(parts) if parts else "no matching files")
        if not os.path.isfile(path):
            return "File not found"
        size = config.fmt_bytes(config.file_size_kb(path) * 1024)
        unfamiliar = dnd.kind_of(path) is None
        if self._info is None:
            if unfamiliar:
                return f"{size}  ·  Unfamiliar format, asking FFmpeg what it is…"
            return "  ·  ".join([os.path.dirname(path), size])
        problem = self.problem()
        if problem:
            return problem
        parts = []
        if unfamiliar:
            parts.append(f"{_KIND_NOUNS.get(self._info.kind, 'media').capitalize()} "
                         f"({self._info.container.split(',')[0]}), identified by FFmpeg")
        else:
            parts.append(os.path.dirname(path))
        parts.append(size)
        parts += [c for c in self._info.summary_chips() if not c.endswith(("KB", "MB", "GB", " B"))]
        return "  ·  ".join(p for p in parts if p)

    # -- background probe ------------------------------------------------- #
    def _start_probe(self):
        path = self._path
        if not path or not os.path.isfile(path):
            self._probing = False
            return
        self._probe = media.ProbeThread(path, self)
        self._probe.ready.connect(self._on_probed)
        self._probe.finished.connect(self._probe.deleteLater)
        self._probe.start()

    def _on_probed(self, path, info):
        if path != self._path:
            return
        self._info = info
        self._probing = False
        self._refresh()


# ---------------------------------------------------------- segmented control #
class SegmentedControl(QWidget):
    """A compact row of mutually exclusive options."""

    changed = pyqtSignal(object)

    def __init__(self, options, default=None, parent=None):
        """`options` is a list of (label, value) or (label, value, tooltip)."""
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._values = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        last = len(options) - 1
        for i, opt in enumerate(options):
            text, value = opt[0], opt[1]
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty('seg', "true")
            b.setProperty('segFirst', "true" if i == 0 else "false")
            b.setProperty('segLast', "true" if i == last else "false")
            if len(opt) > 2 and opt[2]:
                b.setToolTip(opt[2])
            self._values[i] = value
            self.group.addButton(b, i)
            lay.addWidget(b)
            if (default is None and i == 0) or value == default:
                b.setChecked(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.group.buttonToggled.connect(self._on_toggled)

    def _on_toggled(self, btn, checked):
        if checked:
            self.changed.emit(self._values.get(self.group.id(btn)))

    def value(self):
        return self._values.get(self.group.checkedId())

    def set_value(self, value):
        for idx, val in self._values.items():
            if val == value:
                self.group.button(idx).setChecked(True)
                return

    def set_option_enabled(self, value, enabled):
        for idx, val in self._values.items():
            if val == value:
                self.group.button(idx).setEnabled(enabled)


class LevelSelector(SegmentedControl):
    """Compression level: light / balanced / strong."""

    DESCRIPTIONS = {
        'video': {1: "CRF 20 · near-original quality, modest savings",
                  2: "CRF 25 · good quality, much smaller (recommended)",
                  3: "CRF 30 · smallest files, visible softening"},
        'image': {1: "High quality, modest savings",
                  2: "Good quality, much smaller (recommended)",
                  3: "Smallest files, visible artefacts"},
    }

    def __init__(self, kind='video', parent=None):
        super().__init__([("Light", 1), ("Balanced", 2), ("Strong", 3)], default=2, parent=parent)
        self.kind = kind

    def level(self):
        return self.value()

    def description(self):
        return self.DESCRIPTIONS[self.kind][self.value()]


# ------------------------------------------------------------------ timecode #
class TimecodeEdit(QLineEdit):
    """An editable HH:MM:SS.mmm field.

    Typing is forgiving ("90", "1:30", "00:01:30.500" all work) and the text is
    normalised on commit. Up/Down nudge by a step; Page Up/Down by ten steps.
    """

    timeEdited = pyqtSignal(int)         # milliseconds

    def __init__(self, step_ms=100, parent=None):
        super().__init__(parent)
        self.setObjectName("timecode")
        self._ms = 0
        self._max_ms = 0
        self.step_ms = step_ms
        self.setAlignment(Qt.AlignCenter)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPixelSize(13)
        self.setFont(mono)
        self.setText(config.fmt_ms(0))
        self.setFixedWidth(QFontMetrics(mono).horizontalAdvance("00:00:00.000") + 26)
        self.setToolTip("Type a time (e.g. 1:30.5). Up/Down nudges, Shift for larger steps.")
        self.editingFinished.connect(self._commit)
        self.textEdited.connect(self._mark_validity)

    def value(self):
        return self._ms

    def set_value(self, ms, notify=False):
        ms = max(0, int(ms))
        if self._max_ms > 0:
            ms = min(ms, self._max_ms)
        self._ms = ms
        if not self.hasFocus() or notify:
            self.setText(config.fmt_ms(ms))
        self._set_invalid(False)
        if notify:
            self.timeEdited.emit(ms)

    def set_maximum(self, ms):
        self._max_ms = max(0, int(ms))

    def _mark_validity(self, text):
        self._set_invalid(config.parse_timecode(text) is None)

    def _set_invalid(self, invalid):
        flag = "true" if invalid else "false"
        if self.property('invalid') != flag:
            self.setProperty('invalid', flag)
            repolish(self)

    def _commit(self):
        ms = config.parse_timecode(self.text())
        if ms is None:
            self.setText(config.fmt_ms(self._ms))
            self._set_invalid(False)
            return
        previous = self._ms
        self.set_value(ms)
        self.setText(config.fmt_ms(self._ms))
        if self._ms != previous:
            self.timeEdited.emit(self._ms)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            step = self.step_ms * (10 if key in (Qt.Key_PageUp, Qt.Key_PageDown) else 1)
            if event.modifiers() & Qt.ShiftModifier:
                step *= 10
            self.set_value(self._ms + (step if key in (Qt.Key_Up, Qt.Key_PageUp) else -step),
                           notify=True)
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            if key == Qt.Key_Escape:
                self.setText(config.fmt_ms(self._ms))
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)
