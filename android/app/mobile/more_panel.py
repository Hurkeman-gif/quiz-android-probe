# -*- coding: utf-8 -*-
"""「更多」弹层：错题本 / 答题记录入口（对应 Windows 版的菜单项）。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from .overlay import BACKDROP, OverlayCard


class MorePanel(QWidget):
    """应用内「更多」菜单：不新开窗口，触摸一定落在自己的按钮上。"""

    wrongbookRequested = Signal()
    historyRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 0, 48, 0)
        outer.addStretch(1)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        title = QLabel("更多功能")
        title.setObjectName("panelTitle")
        lay.addWidget(title)

        self.wrongbook_button = QPushButton("错题本")
        self.wrongbook_button.setObjectName("panelGhost")
        self.wrongbook_button.setMinimumHeight(48)
        self.wrongbook_button.setFocusPolicy(Qt.NoFocus)
        self.wrongbook_button.clicked.connect(self.wrongbookRequested.emit)
        lay.addWidget(self.wrongbook_button)

        self.history_button = QPushButton("答题记录")
        self.history_button.setObjectName("panelGhost")
        self.history_button.setMinimumHeight(48)
        self.history_button.setFocusPolicy(Qt.NoFocus)
        self.history_button.clicked.connect(self.historyRequested.emit)
        lay.addWidget(self.history_button)

        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelClose")
        self.close_button.setMinimumHeight(44)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self.close_button)

        outer.addWidget(self.card)
        outer.addStretch(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
