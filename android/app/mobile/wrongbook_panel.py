# -*- coding: utf-8 -*-
"""错题本弹层：错题列表 + 开始练习 + 移除单题 + 清空（二次确认由主窗口负责）。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..session import TYPE_LABELS
from .overlay import BACKDROP, OverlayCard
from .record_list import RecordList


class WrongbookPanel(QWidget):
    """错题本列表弹层（只做展示与选择，数据全部由主窗口读写）。"""

    startPractice = Signal(list)
    removeRequested = Signal(int)
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
        self.title_label = QLabel("错题本")
        self.title_label.setObjectName("panelTitle")
        self.count_label = QLabel("")
        self.count_label.setObjectName("panelSub")
        header.addWidget(self.title_label)
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelClose")
        self.close_button.setMinimumHeight(36)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_button)
        lay.addLayout(header)

        self.list = RecordList(self.card)
        lay.addWidget(self.list, 1)

        self.empty_label = QLabel(
            "错题本为空\n在普通练习中答错的题目会自动收录到这里")
        self.empty_label.setObjectName("panelEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        lay.addWidget(self.empty_label, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.start_button = QPushButton("开始练习")
        self.start_button.setObjectName("panelPrimary")
        self.start_button.setMinimumHeight(48)
        self.start_button.setFocusPolicy(Qt.NoFocus)
        self.start_button.clicked.connect(self._on_start)
        self.remove_button = QPushButton("移除选中")
        self.remove_button.setObjectName("panelGhost")
        self.remove_button.setMinimumHeight(48)
        self.remove_button.setFocusPolicy(Qt.NoFocus)
        self.remove_button.clicked.connect(self._on_remove)
        row1.addWidget(self.start_button, 2)
        row1.addWidget(self.remove_button, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.clear_button = QPushButton("清空错题本")
        self.clear_button.setObjectName("panelDanger")
        self.clear_button.setMinimumHeight(46)
        self.clear_button.setFocusPolicy(Qt.NoFocus)
        self.clear_button.clicked.connect(self.clearRequested.emit)
        row2.addWidget(self.clear_button, 1)
        lay.addLayout(row2)

        outer.addWidget(self.card)

    # ------------------------------------------------------------------ API
    def set_rows(self, rows):
        """rows: [{question_id, stem, type, wrong_count, missing}]"""
        self._rows = list(rows or [])
        self.list.set_rows([])
        has_rows = bool(self._rows)
        self.count_label.setText("共 " + str(len(self._rows)) + " 题")
        self.list.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.remove_button.setEnabled(has_rows)
        self.clear_button.setEnabled(has_rows)
        # 「开始练习」始终可点：错题本为空时点它会给出提示（需求要求有反馈）
        self.start_button.setEnabled(True)
        if not has_rows:
            self.empty_label.setText(
                "错题本为空\n在普通练习中答错的题目会自动收录到这里")
            return
        items = []
        for i, row in enumerate(self._rows, 1):
            type_label = TYPE_LABELS.get(row.get("type") or "",
                                         row.get("type") or "")
            stem = row.get("stem") or ""
            if row.get("missing"):
                stem = "（题库中已不存在该题）"
            subtitle = "答错 " + str(row.get("wrong_count") or 0) + " 次"
            if type_label:
                subtitle += " · " + type_label
            if row.get("missing"):
                subtitle += " · 无法练习"
            items.append({
                "lines": [str(i) + ". " + stem, subtitle],
                "payload": int(row["question_id"]),
            })
        self.list.set_rows(items)

    def selected_question_id(self):
        payload = self.list.selected_payload()
        if payload is None:
            return None
        try:
            return int(payload)
        except (TypeError, ValueError):
            return None

    def playable_ids(self):
        ids = []
        for row in self._rows:
            if row.get("missing"):
                continue
            try:
                ids.append(int(row["question_id"]))
            except (TypeError, ValueError, KeyError):
                continue
        return ids

    # ------------------------------------------------------------- 事件处理
    def _on_start(self):
        ids = self.playable_ids()
        if not ids:
            self.list.setVisible(False)
            self.empty_label.setText("错题本为空，暂无题目可以练习。")
            self.empty_label.setVisible(True)
            return
        self.startPractice.emit(ids)

    def _on_remove(self):
        qid = self.selected_question_id()
        if qid is None:
            self.list.setVisible(False)
            self.empty_label.setText("请先选择要移除的题目。")
            self.empty_label.setVisible(True)
            return
        self.removeRequested.emit(int(qid))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
