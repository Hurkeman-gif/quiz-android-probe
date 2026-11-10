# -*- coding: utf-8 -*-
"""题号导航面板：整屏浮层 + 可上下拖动的题号网格（每行 5 个）。

为什么不用 QScrollArea：
Android 上 QAbstractScrollArea 走位块搬移（blit）滚动，配合大量自绘子控件时
会在屏幕左侧留下半截残影（数字被裁切、两帧叠加），把子控件逐帧挪动改成
「一个自绘控件 + 内部滚动偏移」后就没这个问题：每帧整块重绘，逻辑也更好控。

手指拖动、桌面滚轮、点击选题都在 NumberGrid 里处理。
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

COLUMNS = 5
CELL_HEIGHT = 48
CELL_GAP = 12
PANEL_TITLE = "题号导航"
DRAG_THRESHOLD = 8

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


class NumberGrid(QWidget):
    """题号网格：单控件自绘 + 内部滚动偏移，手指拖动可滚。"""

    numberChosen = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = []          # [(state, current), ...] 与题号一一对应
        self._offset = 0.0
        self._press = None         # 按下时的 (x, y)
        self._press_offset = 0.0
        self._dragging = False
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        font = QFont(self.font())
        font.setPointSizeF(11.5)
        font.setBold(True)
        self._font = font

    # ---------------------------------------------------------------- 数据
    def set_states(self, states):
        self._states = list(states)
        self._offset = 0.0
        self.update()

    def refresh_states(self, states):
        self._states = list(states)
        self.update()

    def ensure_visible(self, index: int):
        if not self._states:
            return
        row = index // COLUMNS
        top = row * (CELL_HEIGHT + CELL_GAP)
        bottom = top + CELL_HEIGHT
        if top < self._offset:
            self._offset = float(top)
        elif bottom > self._offset + self.height():
            self._offset = float(bottom - self.height())
        self._clamp()
        self.update()

    # ---------------------------------------------------------------- 几何
    def _cell_width(self) -> float:
        width = max(1.0, float(self.width()))
        total_gap = CELL_GAP * (COLUMNS - 1)
        return max(28.0, (width - total_gap) / COLUMNS)

    def _row_height(self) -> float:
        return CELL_HEIGHT + CELL_GAP

    def _content_height(self) -> float:
        rows = (len(self._states) + COLUMNS - 1) // COLUMNS
        if rows <= 0:
            return 0.0
        return rows * self._row_height() - CELL_GAP

    def _max_offset(self) -> float:
        return max(0.0, self._content_height() - self.height())

    def _clamp(self):
        self._offset = max(0.0, min(self._offset, self._max_offset()))

    def _index_at(self, pos) -> int:
        if not self._states:
            return -1
        cw = self._cell_width()
        col = int(pos.x() // (cw + CELL_GAP))
        row = int((pos.y() + self._offset) // self._row_height())
        if col < 0 or col >= COLUMNS or row < 0:
            return -1
        index = row * COLUMNS + col
        return index if 0 <= index < len(self._states) else -1

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(CARD_BG))
        if not self._states:
            painter.end()
            return

        cw = self._cell_width()
        rh = self._row_height()
        first_row = max(0, int(self._offset // rh))
        last_row = int((self._offset + self.height()) // rh) + 1
        rows = (len(self._states) + COLUMNS - 1) // COLUMNS
        painter.setFont(self._font)

        for row in range(first_row, min(last_row + 1, rows)):
            for col in range(COLUMNS):
                index = row * COLUMNS + col
                if index >= len(self._states):
                    break
                state, current = self._states[index]
                x = col * (cw + CELL_GAP)
                y = row * rh - self._offset
                self._paint_cell(painter, QRectF(x, y, cw, CELL_HEIGHT),
                                 index + 1, state, current)
        painter.end()

    def _paint_cell(self, painter, rect, number, state, current):
        # 当前题在整块外侧画蓝环，作答状态在内侧填色，两种信息互不干扰
        ring = 3.0 if current else 0.0
        inner = rect.adjusted(1.0 + ring, 1.0 + ring, -1.0 - ring, -1.0 - ring)
        path = QPainterPath()
        path.addRoundedRect(inner, 10.0, 10.0)
        if state == STATE_UNANSWERED:
            fill, text = (CURRENT_FILL if current else FILL[STATE_UNANSWERED])
        else:
            fill, text = FILL[state]
        painter.fillPath(path, QColor(fill))
        pen = QPen(QColor(fill))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        if current:
            ring_rect = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            ring_path = QPainterPath()
            ring_path.addRoundedRect(ring_rect, 13.0, 13.0)
            ring_pen = QPen(QColor(CURRENT_BORDER))
            ring_pen.setWidthF(3.0)
            painter.setPen(ring_pen)
            painter.drawPath(ring_path)

        painter.setPen(QColor(text))
        painter.drawText(rect, Qt.AlignCenter, str(number))

    # ---------------------------------------------------------------- 交互
    def mousePressEvent(self, event):
        self._press = event.position()
        self._press_offset = self._offset
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press is None:
            return
        dy = event.position().y() - self._press.y()
        if not self._dragging and abs(dy) > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            self._offset = self._press_offset - dy
            self._clamp()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is not None and not self._dragging:
            index = self._index_at(event.position())
            if index >= 0:
                self.numberChosen.emit(index)
        self._press = None
        self._dragging = False
        event.accept()

    def wheelEvent(self, event):
        self._offset -= event.angleDelta().y() / 2.0
        self._clamp()
        self.update()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp()


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
        card_layout.setContentsMargins(16, 14, 16, 16)
        card_layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title_label = QLabel(PANEL_TITLE)
        font = QFont(self.title_label.font())
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

        self.grid = NumberGrid()
        self.grid.numberChosen.connect(self.numberChosen.emit)
        card_layout.addWidget(self.grid, 1)

        outer.addWidget(self.card, 1)

    # ------------------------------------------------------------ 数据接口
    def set_session(self, session, type_label: str = ""):
        """装载题目列表，重建题号网格并滚动到当前题。"""
        self._session = session
        self._type_label = type_label or ""
        self.title_label.setText(
            f"{PANEL_TITLE} · {self._type_label}" if self._type_label else PANEL_TITLE)
        states = self._build_states()
        self.grid.set_states(states)
        if self._session is not None:
            self.grid.ensure_visible(max(0, self._session.current_index))

    def refresh_states(self):
        if not self._session:
            return
        self.grid.refresh_states(self._build_states())

    def _build_states(self):
        states = []
        if not self._session:
            return states
        for index, qid in enumerate(self._session.question_ids):
            progress = self._session.progress_for(qid)
            if progress is None:
                state = STATE_UNANSWERED
            else:
                state = STATE_CORRECT if progress.get("correct") else STATE_WRONG
            states.append((state, index == self._session.current_index))
        return states

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
