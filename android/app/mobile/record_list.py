# -*- coding: utf-8 -*-
"""自绘滚动记录列表（错题本 / 答题记录 / 明细共用）。

为什么不用 QListWidget / QScrollArea：
Android 上 Qt 只提交局部脏区，列表滚动时未标脏的区域会保留上一帧像素，
于是出现文字叠影、上下行错位（题号导航最初也是这个毛病）。
最终方案与题号导航一致：整块自绘 + 拖动滚动 + 每次滚动强制整块重绘
（self.repaint() 后再 window().update()）。
"""
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

BG_COLOR = QColor("#FFFFFF")
TITLE_COLOR = QColor("#111827")
SUB_COLOR = QColor("#6B7280")
SEPARATOR_COLOR = QColor("#E5E7EB")
SELECTED_BG = QColor("#E8F1FF")
SELECTED_TEXT = QColor("#1D4ED8")

PAD_X = 6
PAD_TOP = 10
PAD_BOTTOM = 10
LINE_GAP = 3

DRAG_THRESHOLD = 8
FLING_MIN = 260.0
FLING_TICK_MS = 16
FLING_DECAY = 0.90


def wrap_text(metrics, text, width):
    """按像素宽度逐字换行（中英文混排、长题干都适用）。"""
    text = "" if text is None else str(text)
    if width <= 0:
        return [text]
    lines = []
    current = ""
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
            continue
        trial = current + ch
        if current and metrics.horizontalAdvance(trial) > width:
            lines.append(current)
            current = ch
        else:
            current = trial
    lines.append(current)
    return lines


class RecordList(QWidget):
    """记录列表：每条记录若干行文本，第一行加粗，其余灰色。

    rows: [{"lines": [第一行, 第二行, ...], "payload": 任意对象}]
    """

    itemActivated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recordList")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumSize(1, 1)

        self._rows = []
        self._wrapped = []
        self._heights = []
        self._total = 0
        self._offset = 0.0
        self._selected = -1

        self._press_pos = None
        self._press_offset = 0.0
        self._last_y = 0.0
        self._last_time = 0.0
        self._velocity = 0.0
        self._dragging = False

        self._font_title = QFont()
        self._font_title.setPointSizeF(11.5)
        self._font_title.setBold(True)
        self._font_sub = QFont()
        self._font_sub.setPointSizeF(10.0)

        self._fling_timer = QTimer(self)
        self._fling_timer.setInterval(FLING_TICK_MS)
        self._fling_timer.timeout.connect(self._on_fling)

    # ------------------------------------------------------------------ API
    def set_rows(self, rows):
        self._rows = list(rows or [])
        self._selected = -1
        self._offset = 0.0
        self._stop_fling()
        self._recompute()
        self._refresh()

    def clear(self):
        self.set_rows([])

    def row_count(self):
        return len(self._rows)

    def selected_index(self):
        return self._selected

    def selected_payload(self):
        if 0 <= self._selected < len(self._rows):
            return self._rows[self._selected].get("payload")
        return None

    def clear_selection(self):
        if self._selected != -1:
            self._selected = -1
            self._refresh()

    def scroll_to_top(self):
        self._stop_fling()
        self._offset = 0.0
        self._refresh()

    def scroll_offset(self):
        return int(self._offset)

    # -------------------------------------------------------------- 尺寸计算
    def _max_offset(self):
        return max(0.0, float(self._total - self.height()))

    def _recompute(self):
        avail = max(40, self.width() - PAD_X * 2)
        title_metrics = QFontMetrics(self._font_title)
        sub_metrics = QFontMetrics(self._font_sub)
        self._wrapped = []
        self._heights = []
        total = 0
        for row in self._rows:
            lines = row.get("lines") or []
            if not lines:
                lines = [""]
            wrapped = []
            height = PAD_TOP + PAD_BOTTOM
            for index, text in enumerate(lines):
                metrics = title_metrics if index == 0 else sub_metrics
                parts = wrap_text(metrics, text, avail)
                wrapped.append(parts)
                height += len(parts) * metrics.height()
                if index > 0:
                    height += LINE_GAP
            self._wrapped.append(wrapped)
            self._heights.append(height)
            total += height
        self._total = total
        self._offset = max(0.0, min(self._offset, self._max_offset()))

    def _index_at(self, y):
        pos = y + self._offset
        top = 0
        for index, height in enumerate(self._heights):
            if top <= pos < top + height:
                return index
            top += height
        return None

    # ---------------------------------------------------------------- 滚动
    def _set_offset(self, value):
        target = max(0.0, min(float(value), self._max_offset()))
        if abs(target - self._offset) < 0.01:
            self._offset = target
            return False
        self._offset = target
        self._refresh()
        return True

    def _refresh(self):
        # Android 上必须整块重绘，否则滚动会出现文字叠影
        self.repaint()
        window = self.window()
        if window is not None and window is not self:
            window.update()

    def _stop_fling(self):
        if self._fling_timer.isActive():
            self._fling_timer.stop()

    def _start_fling(self):
        if abs(self._velocity) < FLING_MIN:
            return
        self._fling_timer.start()

    def _on_fling(self):
        self._velocity *= FLING_DECAY
        if abs(self._velocity) < FLING_MIN * 0.5:
            self._stop_fling()
            return
        step = -self._velocity * (FLING_TICK_MS / 1000.0)
        if not self._set_offset(self._offset + step):
            self._stop_fling()

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BG_COLOR)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        title_metrics = QFontMetrics(self._font_title)
        sub_metrics = QFontMetrics(self._font_sub)
        y = -self._offset
        for index, wrapped in enumerate(self._wrapped):
            height = self._heights[index]
            if y + height < 0:
                y += height
                continue
            if y > self.height():
                break
            selected = index == self._selected
            if selected:
                painter.fillRect(0, int(y), self.width(), height, SELECTED_BG)
            ty = y + PAD_TOP
            for line_index, parts in enumerate(wrapped):
                if line_index == 0:
                    painter.setFont(self._font_title)
                    painter.setPen(SELECTED_TEXT if selected else TITLE_COLOR)
                    metrics = title_metrics
                else:
                    painter.setFont(self._font_sub)
                    painter.setPen(SELECTED_TEXT if selected else SUB_COLOR)
                    metrics = sub_metrics
                    ty += LINE_GAP
                for part in parts:
                    painter.drawText(PAD_X, int(ty) + metrics.ascent(), part)
                    ty += metrics.height()
            painter.setPen(QPen(SEPARATOR_COLOR, 1))
            painter.drawLine(PAD_X, int(y + height - 1),
                             self.width() - PAD_X, int(y + height - 1))
            y += height
        painter.end()

    # ---------------------------------------------------------------- 事件
    def mousePressEvent(self, event):
        self._stop_fling()
        pos = event.position()
        self._press_pos = pos
        self._press_offset = self._offset
        self._last_y = pos.y()
        self._last_time = time.monotonic()
        self._velocity = 0.0
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_pos is None:
            return
        pos = event.position()
        delta = pos.y() - self._press_pos.y()
        if not self._dragging and abs(delta) > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            now = time.monotonic()
            elapsed = max(0.001, now - self._last_time)
            self._velocity = (pos.y() - self._last_y) / elapsed
            self._last_y = pos.y()
            self._last_time = now
            self._set_offset(self._press_offset - delta)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._press_pos is None:
            return
        if not self._dragging:
            index = self._index_at(event.position().y())
            if index is not None:
                self._selected = index
                self._refresh()
                self.itemActivated.emit(index)
        else:
            self._start_fling()
        self._press_pos = None
        self._dragging = False
        event.accept()

    def wheelEvent(self, event):
        self._stop_fling()
        step = event.angleDelta().y() / 2.0
        self._set_offset(self._offset - step)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute()
        self._refresh()
