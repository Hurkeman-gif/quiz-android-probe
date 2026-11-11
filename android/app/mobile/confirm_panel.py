"""应用内确认弹层。

Android 上 QMessageBox 会另开一个窗口，真机触摸事件投递不到按钮上，
因此改成画在同一个 QWidget 里的确认卡片：背景遮罩 + 圆角卡片 + 两个按钮。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

BACKDROP = QColor(17, 24, 39, 130)
CARD_BG = "#FFFFFF"
CARD_RADIUS = 16


class _Card(QWidget):
    """白色圆角卡片背景，避免方块底色透出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(CARD_BG))
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), CARD_RADIUS, CARD_RADIUS)
        painter.fillPath(path, QColor(CARD_BG))
        painter.end()
        super().paintEvent(event)


class ConfirmPanel(QWidget):
    """应用内确认弹层：不新开窗口，触摸一定落在自己的按钮上。"""

    confirmed = Signal()
    rejected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 0, 28, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.card = _Card(self)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        self.title_label = QLabel("", self.card)
        title_font = QFont(self.title_label.font())
        title_font.setPointSizeF(13.5)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)

        self.message_label = QLabel("", self.card)
        message_font = QFont(self.message_label.font())
        message_font.setPointSizeF(11.5)
        self.message_label.setFont(message_font)
        self.message_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.cancel_button = QPushButton("取消", self.card)
        self.cancel_button.setObjectName("confirmCancel")
        self.cancel_button.setMinimumHeight(44)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.ok_button = QPushButton("提交", self.card)
        self.ok_button.setObjectName("confirmOk")
        self.ok_button.setMinimumHeight(44)
        self.ok_button.clicked.connect(self._on_ok)
        button_row.addWidget(self.cancel_button, 1)
        button_row.addWidget(self.ok_button, 1)

        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.message_label)
        card_layout.addLayout(button_row)

        outer.addWidget(self.card)
        outer.addStretch(1)

    # ------------------------------------------------------------------ API
    def show_confirm(self, title, message, ok_text="提交", cancel_text="取消"):
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.ok_button.setText(ok_text)
        self.cancel_button.setText(cancel_text)
        self.ok_button.setDefault(False)
        self.setGeometry(self.parentWidget().rect() if self.parentWidget() else self.rect())
        self.raise_()
        self.show()

    def hide_panel(self):
        self.hide()

    def _on_ok(self):
        self.hide()
        self.confirmed.emit()

    def _on_cancel(self):
        self.hide()
        self.rejected.emit()

    # ------------------------------------------------------------- 事件处理
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def _card_rect(self):
        return self.card.geometry()

    def mousePressEvent(self, event):
        # 点卡片外面视为取消
        if not self._card_rect().contains(event.position().toPoint()):
            self._on_cancel()
        super().mousePressEvent(event)
