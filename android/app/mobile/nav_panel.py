# -*- coding: utf-8 -*-
"""题号导航面板：整屏浮层 + 可滚动题号网格（每行 5 个）。

为什么自己画按钮和卡片：
Android 上 QSS 的 border-radius 在局部重绘时会错位（表现为缺角、整块偏移），
所以题号按钮与面板卡片都用 QPainter 自绘，只保留布局与交互由 Qt 负责。
"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

COLUMNS = 5
BUTTON_SIZE = 46
BUTTON_HEIGHT = 48
PANEL_TITLE = "题号导航"

STATE_UNANSWERED = "unanswered"
STATE_CORRECT = "correct"
STATE_WRONG = "wrong"

FILL = {
    STATE_UNANSWERED: ("#E5E7EB", "#374151"),
    STATE_CORRECT: ("#16A34A", "#FFFFFF"),
    STATE_WRONG: ("#DC2626", "#FFFFFF"),
}
CURRENT_FILL = ("#2563EB", "#FFFFFF")
CURRENT_BORDER = "#2563EB"
CARD_BG = "#FFFFFF"
BACKDROP = QColor(17, 24, 39, 130)


class NumberButton(QPushButton):
    """题号按钮：自绘圆角底色，最小 46x46dp，适合手指点击。"""

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.number = index + 1
        self.state = STATE_UNANSWERED
        self.current = False
        self.setText("")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        # 宽度随列拉伸、高度固定：整行自适应屏宽，不留过宽或过窄的边距
        self.setMinimumSize(BUTTON_SIZE, BUTTON_HEIGHT)
        self.setFixedHeight(BUTTON_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        font = self.font()
        font.setPointSizeF(11.5)
        font.setBold(True)
        self.setFont(font)

    def set_state(self, state: str, current: bool):
        if self.state == state and self.current == current:
            return
        self.state = state
        self.current = current
        self.update()
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 先铺面板底色，避免圆角外残留上一帧像素
        painter.fillRect(self.rect(), QColor(CARD_BG))

        # 当前题：整块外侧画一圈蓝环（不覆盖作答颜色），
        # 作答状态：内缩 3px 填充绿/红/灰，两种信息互不干扰。
        ring = 3.0 if self.current else 0.0
        rect = QRectF(self.rect()).adjusted(
            1.0 + ring, 1.0 + ring, -1.0 - ring, -1.0 - ring)
        path = QPainterPath()
        path.addRoundedRect(rect, 10.0, 10.0)
        if self.state == STATE_UNANSWERED:
            fill, text = (CURRENT_FILL if self.current
                          else FILL[STATE_UNANSWERED])
        else:
            fill, text = FILL[self.state]
        painter.fillPath(path, QColor(fill))
        pen = QPen(QColor(fill))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        if self.current:
            ring_rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            ring_path = QPainterPath()
            ring_path.addRoundedRect(ring_rect, 13.0, 13.0)
            ring_pen = QPen(QColor(CURRENT_BORDER))
            ring_pen.setWidthF(3.0)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(ring_path)
        painter.setPen(QColor(text))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, str(self.number))
        painter.end()


class _ScrollArea(QScrollArea):
    """滚动容器：滚动后强制整块重绘。

    Android 上 QAbstractScrollArea 默认用位块搬移（blit）滚动，
    与自绘按钮叠加时会留下上一帧的残影（屏幕左侧出现被裁切的数字）。
    这里在父类滚动之后再整块 update()，用一次全量重绘换掉残影。
    """

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.viewport().update()


class _Card(QWidget):
    """面板白卡片：自绘圆角背景。"""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 16.0, 16.0)
        painter.fillPath(path, QColor(CARD_BG))
        painter.end()


class NumberPanel(QWidget):
    """整屏浮层：点「题号」后弹出，选号后自动关闭。"""

    numberChosen = Signal(int)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("numberPanel")
        self._buttons = []
        self._session = None
        self._type_label = ""
        # 浮层几何由外部按主窗口 rect 指定，不参与窗口尺寸计算
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(1, 1)
        self.hide()
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 60, 16, 56)
        outer.setSpacing(0)

        self.card = _Card(self)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title_label = QLabel(PANEL_TITLE)
        font = self.title_label.font()
        font.setPointSizeF(12.5)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #111827; background: transparent;")
        self.close_button = QPushButton("关闭")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.setMinimumHeight(36)
        self.close_button.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: none;"
            " border-radius: 8px; padding: 0 14px; font-size: 11pt; }"
            "QPushButton:pressed { background: #E5E7EB; }")
        self.close_button.clicked.connect(self.closeRequested.emit)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        title_row.addWidget(self.close_button)
        card_layout.addLayout(title_row)

        self.scroll = _ScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: #D1D5DB;"
            " border-radius: 3px; min-height: 32px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            " background: transparent; }")

        # 手指滑动：没有它就只能拖右侧细滚动条
        QScroller.grabGesture(
            self.scroll.viewport(),
            QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Minimum)
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        for col in range(COLUMNS):
            self.grid.setColumnStretch(col, 1)
        self.scroll.setWidget(self.body)
        card_layout.addWidget(self.scroll, 1)

        outer.addWidget(self.card, 1)

    # ------------------------------------------------------------ 数据接口
    def set_session(self, session, type_label: str = ""):
        """装载题目列表，重建题号网格并滚动到当前题。"""
        self._session = session
        self._type_label = type_label or ""
        self.title_label.setText(
            f"{PANEL_TITLE} · {self._type_label}" if self._type_label else PANEL_TITLE)
        self._rebuild()

    def refresh_states(self):
        if not self._session:
            return
        for btn, qid in zip(self._buttons, self._session.question_ids):
            progress = self._session.progress_for(qid)
            if progress is None:
                state = STATE_UNANSWERED
            else:
                state = STATE_CORRECT if progress.get("correct") else STATE_WRONG
            btn.set_state(state, btn.index == self._session.current_index)

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._buttons = []

        if not self._session or not self._session.question_ids:
            return
        for index in range(len(self._session.question_ids)):
            btn = NumberButton(index)
            btn.clicked.connect(
                lambda _checked=False, i=index: self.numberChosen.emit(i))
            self.grid.addWidget(btn, index // COLUMNS, index % COLUMNS)
            self._buttons.append(btn)
        # 末尾补一个占位行，保证最后一行的按钮不会被拉高
        rows = (len(self._buttons) + COLUMNS - 1) // COLUMNS
        spacer = QWidget()
        spacer.setFixedHeight(1)
        self.grid.addWidget(spacer, rows, 0, 1, COLUMNS)
        self.refresh_states()
        self.scroll.verticalScrollBar().setValue(0)
        self.body.update()
        self.scroll.viewport().update()
        if self._buttons:
            idx = max(0, min(self._session.current_index, len(self._buttons) - 1))
            self.scroll.ensureWidgetVisible(self._buttons[idx], 0, 80)

    # ---------------------------------------------------------------- 事件
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        # 点卡片以外的空白区域关闭面板
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
