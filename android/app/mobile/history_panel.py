# -*- coding: utf-8 -*-
"""答题记录弹层：记录列表 + 明细列表（删除/清空由主窗口二次确认后执行）。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..session import MODE_LABELS, TYPE_LABELS
from .overlay import BACKDROP, OverlayCard, make_record_list


def display_accuracy(record) -> str:
    """列表正确率：按 答对/总题数（完成页口径）；分母为 0 时 "--"。"""
    try:
        total = int(record.get("total_count") or 0)
        correct = int(record.get("correct_count") or 0)
    except (TypeError, ValueError):
        total, correct = 0, 0
    if total > 0:
        return "%.1f%%" % (correct / total * 100.0)
    try:
        rate = float(record.get("score_rate") or 0.0)
    except (TypeError, ValueError):
        rate = 0.0
    return ("%.1f%%" % rate) if rate > 0 else "--"


def _join_keys(keys) -> str:
    keys = [str(k) for k in (keys or [])]
    return "、".join(keys) if keys else "（未作答）"


class HistoryPanel(QWidget):
    """答题记录列表弹层。"""

    detailRequested = Signal(dict)
    deleteRequested = Signal(int)
    clearRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 96, 14, 52)
        outer.setSpacing(0)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_label = QLabel("答题记录")
        self.title_label.setObjectName("panelTitle")
        self.count_label = QLabel("")
        self.count_label.setObjectName("panelSub")
        header.addWidget(self.title_label)
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.close_top_button = QPushButton("关闭")
        self.close_top_button.setObjectName("panelClose")
        self.close_top_button.setMinimumHeight(36)
        self.close_top_button.setFocusPolicy(Qt.NoFocus)
        self.close_top_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_top_button)
        lay.addLayout(header)

        self.list = make_record_list(self.card)
        lay.addWidget(self.list, 1)

        self.empty_label = QLabel(
            "暂无答题记录\n完成一次练习（含提前交卷）后会自动记录")
        self.empty_label.setObjectName("panelEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        lay.addWidget(self.empty_label, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.detail_button = QPushButton("查看明细")
        self.detail_button.setObjectName("panelPrimary")
        self.detail_button.setMinimumHeight(48)
        self.detail_button.setFocusPolicy(Qt.NoFocus)
        self.detail_button.clicked.connect(self._on_detail)
        self.delete_button = QPushButton("删除选中")
        self.delete_button.setObjectName("panelDanger")
        self.delete_button.setMinimumHeight(48)
        self.delete_button.setFocusPolicy(Qt.NoFocus)
        self.delete_button.clicked.connect(self._on_delete)
        row1.addWidget(self.detail_button, 2)
        row1.addWidget(self.delete_button, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.clear_button = QPushButton("清空全部")
        self.clear_button.setObjectName("panelDanger")
        self.clear_button.setMinimumHeight(46)
        self.clear_button.setFocusPolicy(Qt.NoFocus)
        self.clear_button.clicked.connect(self.clearRequested.emit)
        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelGhost")
        self.close_button.setMinimumHeight(46)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        row2.addWidget(self.clear_button, 1)
        row2.addWidget(self.close_button, 1)
        lay.addLayout(row2)

        outer.addWidget(self.card)

    # ------------------------------------------------------------------ API
    def set_rows(self, rows):
        self._rows = list(rows or [])
        self.list.clear()
        has_rows = bool(self._rows)
        self.count_label.setText("共 " + str(len(self._rows)) + " 条")
        self.list.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        for button in (self.detail_button, self.delete_button, self.clear_button):
            button.setEnabled(has_rows)
        if not has_rows:
            return
        for rec in self._rows:
            mode_label = MODE_LABELS.get(rec.get("mode") or "",
                                         rec.get("mode") or "")
            qtype = rec.get("question_type") or ""
            type_label = TYPE_LABELS.get(qtype, qtype) if qtype else "混合题型"
            text = (str(rec.get("created_at") or "") + "\n" + mode_label + " · "
                    + type_label + " · 共 " + str(rec.get("total_count") or 0)
                    + " 题 · 正确率 " + display_accuracy(rec))
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, int(rec.get("id") or 0))
            self.list.addItem(item)
        self.list.clearSelection()
        self.list.setCurrentRow(-1)

    def selected_record(self):
        row = self.list.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def current_id(self):
        item = self.list.currentItem()
        if item is None:
            return None
        try:
            return int(item.data(Qt.UserRole))
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------- 事件处理
    def _on_detail(self):
        rec = self.selected_record()
        if rec is None:
            self._show_hint("请先选择一条记录。")
            return
        self.detailRequested.emit(rec)

    def _on_delete(self):
        hid = self.current_id()
        if hid is None:
            self._show_hint("请先选择要删除的记录。")
            return
        self.deleteRequested.emit(int(hid))

    def _show_hint(self, text):
        self.list.setVisible(False)
        self.empty_label.setText(text)
        self.empty_label.setVisible(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)


class HistoryDetailPanel(QWidget):
    """单条历史明细：每题 你的答案 / 正确答案 / 结果 / 未答判错 / 解析。"""

    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 96, 14, 52)
        outer.setSpacing(0)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_label = QLabel("答题明细")
        self.title_label.setObjectName("panelTitle")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.close_top_button = QPushButton("关闭")
        self.close_top_button.setObjectName("panelClose")
        self.close_top_button.setMinimumHeight(36)
        self.close_top_button.setFocusPolicy(Qt.NoFocus)
        self.close_top_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_top_button)
        lay.addLayout(header)

        self.info_label = QLabel("")
        self.info_label.setObjectName("panelSub")
        self.info_label.setWordWrap(True)
        lay.addWidget(self.info_label)

        self.list = make_record_list(self.card)
        lay.addWidget(self.list, 1)

        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelGhost")
        self.close_button.setMinimumHeight(46)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self.close_button)

        outer.addWidget(self.card)

    def set_record(self, record):
        record = record or {}
        mode_label = MODE_LABELS.get(record.get("mode") or "",
                                     record.get("mode") or "")
        qtype = record.get("question_type") or ""
        type_label = TYPE_LABELS.get(qtype, qtype) if qtype else "混合题型"
        self.info_label.setText(
            str(record.get("created_at") or "") + " · " + mode_label + " · "
            + type_label + " · 共 " + str(record.get("total_count") or 0)
            + " 题 · 正确率 " + display_accuracy(record))
        details = record.get("details") or []
        self.list.clear()
        for i, d in enumerate(details, 1):
            forced = bool(d.get("is_forced_unanswered"))
            if forced:
                result = "未答（强制判错）"
            elif d.get("is_correct"):
                result = "正确"
            else:
                result = "错误"
            text = (str(i) + ". " + (d.get("stem_summary") or "") + "\n"
                    + "你的答案 " + _join_keys(d.get("selected"))
                    + " ｜ 正确答案 " + _join_keys(d.get("correct_answer"))
                    + " ｜ " + result)
            explanation = (d.get("explanation") or "").strip()
            if explanation:
                text += "\n解析：" + explanation
            self.list.addItem(QListWidgetItem(text))
        self.list.verticalScrollBar().setValue(0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
