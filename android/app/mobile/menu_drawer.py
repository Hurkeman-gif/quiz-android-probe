# -*- coding: utf-8 -*-
"""左侧主菜单抽屉：普通练习 / 随机练习 / 错题本 / 历史记录 / 清空当前进度。

Android 上不新开窗口（QDialog 收不到触摸），直接在同一个 QWidget 里画遮罩 + 卡片。
点卡片以外的遮罩区域即关闭。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .overlay import BACKDROP, OverlayCard


class MenuDrawer(QWidget):
    """左侧抽屉：宽度随窗口变化，条目全部走信号由主窗口分发。"""

    normalRequested = Signal()
    randomRequested = Signal()
    wrongbookRequested = Signal()
    historyRequested = Signal()
    clearProgressRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = QHBoxLayout(self)
        # 顶部留 44px：真机状态栏会压住卡片标题
        outer.setContentsMargins(0, 44, 0, 40)
        outer.setSpacing(0)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(8)

        title = QLabel("答题练习")
        title.setObjectName("drawerTitle")
        lay.addWidget(title)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("drawerSub")
        self.sub_label.setWordWrap(True)
        lay.addWidget(self.sub_label)
        lay.addSpacing(6)

        self.normal_button = self._add_item(lay, "普通练习", self.normalRequested)
        self.random_button = self._add_item(lay, "随机练习", self.randomRequested)
        self.wrongbook_button = self._add_item(lay, "错题本", self.wrongbookRequested)
        self.history_button = self._add_item(lay, "答题记录", self.historyRequested)

        lay.addSpacing(4)
        self.clear_button = QPushButton("清空当前进度")
        self.clear_button.setObjectName("drawerDanger")
        self.clear_button.setMinimumHeight(48)
        self.clear_button.setFocusPolicy(Qt.NoFocus)
        self.clear_button.clicked.connect(self.clearProgressRequested.emit)
        lay.addWidget(self.clear_button)

        lay.addStretch(1)

        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelClose")
        self.close_button.setMinimumHeight(42)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self.close_button)

        outer.addWidget(self.card)
        outer.addStretch(1)

    def _add_item(self, lay, text, signal):
        btn = QPushButton(text)
        btn.setObjectName("drawerItem")
        btn.setMinimumHeight(52)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(signal.emit)
        lay.addWidget(btn)
        return btn

    # ------------------------------------------------------------------ API
    def set_context(self, text, allow_clear=True):
        self.sub_label.setText(text)
        self.clear_button.setEnabled(bool(allow_clear))

    def refresh_width(self):
        width = int(self.width() * 0.8)
        width = max(240, min(320, width))
        self.card.setFixedWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_width()

    # ------------------------------------------------------------- 事件处理
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if event.position().toPoint().x() > self.card.width():
            self.closeRequested.emit()
        super().mousePressEvent(event)
