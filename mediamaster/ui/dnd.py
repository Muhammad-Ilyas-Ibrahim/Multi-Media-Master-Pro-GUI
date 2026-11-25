"""Drag-and-drop plumbing shared by the path inputs, trim studio and window.

Three pieces:
  * `kind_of(path)`  - classify a dropped path as video / image / audio / dir
  * `paths_from(mime)` - pull local filesystem paths out of a drop event
  * `DropTarget`     - mixin giving a widget accept/highlight/drop behaviour
"""

import os

from PyQt5.QtCore import Qt

from ..core import config

# Every extension the app knows how to work with, grouped by kind.
KIND_EXTS = {
    'video': config.VIDEO_EXTS,
    'image': config.IMAGE_EXTS,
    'audio': config.AUDIO_EXTS,
}


def ext_of(path):
    return config.ext_of(path)


def kind_of(path):
    """'dir', 'video', 'image', 'audio', or None when the extension is unknown.

    None does not mean unusable: FFmpeg reads many formats by content, so a
    file with an unfamiliar extension is identified with a probe later
    (see is_unknown_file and SourceField).
    """
    if not path:
        return None
    if os.path.isdir(path):
        return 'dir'
    return config.kind_of_ext(ext_of(path))


def is_unknown_file(path):
    """A regular file whose extension doesn't tell us what it holds (and
    isn't obviously a document, archive, program, ...)."""
    return (bool(path) and kind_of(path) is None
            and ext_of(path) not in config.NON_MEDIA_EXTS and os.path.isfile(path))


def folder_counts(path):
    """How many video / image / audio files sit directly in a folder."""
    counts = {'video': 0, 'image': 0, 'audio': 0}
    try:
        entries = os.listdir(path)
    except OSError:
        return counts
    for name in entries:
        if os.path.isdir(os.path.join(path, name)):
            continue
        kind = kind_of(os.path.join(path, name))
        if kind in counts:
            counts[kind] += 1
    return counts


def paths_from(mime):
    """Local paths carried by a drop, in the order they were dragged."""
    if mime is None or not mime.hasUrls():
        return []
    out = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = os.path.normpath(url.toLocalFile())
        if path and path not in out:
            out.append(path)
    return out


def filter_paths(paths, kinds):
    """Keep only the paths whose kind is in `kinds` (a set of kind names)."""
    return [p for p in paths if kind_of(p) in kinds]


def matches_filter(path, file_filter):
    """True when `path`'s extension appears in a Qt file-dialog filter string.

    Used so a drop is only accepted where the matching Browse dialog would
    have accepted it too. Filters without a concrete pattern accept anything.
    """
    if not file_filter or '*.*' in file_filter:
        return True
    return ('*.' + ext_of(path)) in file_filter.lower()


class DropTarget:
    """Mixin that wires a QWidget up as a drop target.

    The host widget must implement:
        drop_accepts(paths) -> bool     should this drop be taken?
        drop_handle(paths)  -> None     act on an accepted drop

    While a valid drag hovers, the widget's `dropActive` Qt property is set to
    "true" so the stylesheet can highlight it.
    """

    #: Widget whose property is flipped for highlighting (defaults to self).
    drop_highlight_target = None

    def init_drops(self):
        self._drop_ok = False
        self.setAcceptDrops(True)

    # -- highlight -------------------------------------------------------- #
    def _set_drop_active(self, active):
        self._drop_ok = active
        widget = self.drop_highlight_target or self
        flag = "true" if active else "false"
        if widget.property('dropActive') == flag:
            return
        widget.setProperty('dropActive', flag)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    # -- events ----------------------------------------------------------- #
    def dragEnterEvent(self, event):
        paths = paths_from(event.mimeData())
        if paths and self.drop_accepts(paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self._set_drop_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if getattr(self, '_drop_ok', False):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_active(False)
        event.accept()

    def dropEvent(self, event):
        self._set_drop_active(False)
        paths = paths_from(event.mimeData())
        if paths and self.drop_accepts(paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self.drop_handle(paths)
        else:
            event.ignore()

    # -- defaults --------------------------------------------------------- #
    def drop_accepts(self, paths):          # pragma: no cover - overridden
        return False

    def drop_handle(self, paths):           # pragma: no cover - overridden
        pass
