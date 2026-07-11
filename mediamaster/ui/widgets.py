"""Reusable form widgets used across the pages."""

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QHBoxLayout, QVBoxLayout,
    QFrame, QButtonGroup, QRadioButton, QFileDialog
)
from PyQt5.QtCore import Qt, QSize

from .icons import fa


class PathInput(QWidget):
    """A line-edit with a Browse button for a file or folder."""

    def __init__(self, mode='file', placeholder='', file_filter='All Files (*.*)'):
        super().__init__()
        self.mode = mode
        self.file_filter = file_filter
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("  Browse")
        btn.setObjectName("ghost")
        btn.setIcon(fa('fa5s.folder-open', "#8b93a3"))
        btn.setIconSize(QSize(15, 15))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)

    def _browse(self):
        if self.mode == 'dir':
            path = QFileDialog.getExistingDirectory(self, "Select folder")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file", "", self.file_filter)
        if path:
            self.edit.setText(path)

    def text(self):
        return self.edit.text().strip().strip('"')

    def setText(self, t):
        self.edit.setText(t)


class LevelSelector(QWidget):
    """Three-way compression level radio group."""

    def __init__(self, kind='video'):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        self.group = QButtonGroup(self)
        if kind == 'video':
            labels = [("Low (CRF 20)", 1), ("Balanced (CRF 25)", 2), ("High (CRF 30)", 3)]
        else:
            labels = [("Low", 1), ("Balanced", 2), ("High", 3)]
        for text, val in labels:
            rb = QRadioButton(text)
            rb.setCursor(Qt.PointingHandCursor)
            if val == 2:
                rb.setChecked(True)
            self.group.addButton(rb, val)
            lay.addWidget(rb)
        lay.addStretch()

    def level(self):
        return self.group.checkedId()


def make_card(title=None):
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 20)
    lay.setSpacing(14)
    if title:
        t = QLabel(title)
        t.setObjectName("cardTitle")
        lay.addWidget(t)
    return card, lay


def field(label_text):
    lbl = QLabel(label_text)
    lbl.setObjectName("sectionLabel")
    return lbl
