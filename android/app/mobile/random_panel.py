# -*- coding: utf-8 -*-
"""随机练习设置弹层：范围 / 题数 / 顺序。

与其它弹层一致，不新开窗口，画在主窗口里的白色圆角卡片。
校验不通过时只在卡片内提示，绝不直接开练。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .overlay import BACKDROP, OverlayCard

SCOPE_ALL = "all"
SCOPE_LABELS = (
    (SCOPE_ALL, "全部题型"),
    ("single", "仅单选"),
    ("multiple", "仅多选"),
    ("judge", "仅判断"),
)

ORDER_SHUFFLE = "shuffle"
ORDER_SOURCE = "source"
ORDER_LABELS = (
    (ORDER_SHUFFLE, "随机顺序"),
    (ORDER_SOURCE, "原顺序"),
)


class RandomSetupPanel(QWidget):
    """随机练习设置：范围 + 题数（或全部）+ 顺序。"""

    startRequested = Signal(dict)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._counts = {SCOPE_ALL: 0, "single": 0, "multiple": 0, "judge": 0}
        self._scope = SCOPE_ALL
        self._order = ORDER_SHUFFLE
        self._build_ui()
        self.reset_defaults()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 0, 22, 0)
        outer.addStretch(1)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        title = QLabel("随机练习")
        title.setObjectName("panelTitle")
        lay.addWidget(title)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("panelSub")
        self.sub_label.setWordWrap(True)
        lay.addWidget(self.sub_label)

        lay.addSpacing(2)
        lay.addWidget(self._section("范围"))
        scope_row = QHBoxLayout()
        scope_row.setSpacing(6)
        self.scope_buttons = {}
        for scope, text in SCOPE_LABELS:
            btn = QPushButton(text)
            btn.setObjectName("segBtn")
            btn.setProperty("active", "false")
            btn.setMinimumHeight(38)
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _c=False, s=scope: self.set_scope(s))
            scope_row.addWidget(btn, 1)
            self.scope_buttons[scope] = btn
        lay.addLayout(scope_row)

        lay.addWidget(self._section("题数"))
        count_row = QHBoxLayout()
        count_row.setSpacing(10)
        self.count_edit = QLineEdit()
        self.count_edit.setObjectName("countEdit")
        self.count_edit.setValidator(QIntValidator(1, 9999, self))
        self.count_edit.setMinimumHeight(42)
        self.count_edit.setText("10")
        self.count_edit.textChanged.connect(self._refresh_hint)
        count_row.addWidget(self.count_edit, 1)
        self.all_check = QCheckBox("全部随机")
        self.all_check.setObjectName("allCheck")
        self.all_check.setMinimumHeight(42)
        self.all_check.toggled.connect(self._on_all_toggled)
        count_row.addWidget(self.all_check, 0)
        lay.addLayout(count_row)

        lay.addWidget(self._section("顺序"))
        order_row = QHBoxLayout()
        order_row.setSpacing(6)
        self.order_buttons = {}
        for order, text in ORDER_LABELS:
            btn = QPushButton(text)
            btn.setObjectName("segBtn")
            btn.setProperty("active", "false")
            btn.setMinimumHeight(38)
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _c=False, o=order: self.set_order(o))
            order_row.addWidget(btn, 1)
            self.order_buttons[order] = btn
        lay.addLayout(order_row)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("randomHint")
        self.hint_label.setWordWrap(True)
        lay.addWidget(self.hint_label)

        lay.addSpacing(4)
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("panelGhost")
        self.cancel_button.setMinimumHeight(46)
        self.cancel_button.setFocusPolicy(Qt.NoFocus)
        self.cancel_button.clicked.connect(self.closeRequested.emit)
        self.start_button = QPushButton("开始练习")
        self.start_button.setObjectName("panelPrimary")
        self.start_button.setMinimumHeight(46)
        self.start_button.setFocusPolicy(Qt.NoFocus)
        self.start_button.clicked.connect(self._on_start)
        button_row.addWidget(self.cancel_button, 1)
        button_row.addWidget(self.start_button, 2)
        lay.addLayout(button_row)

        outer.addWidget(self.card)
        outer.addStretch(1)

    def _section(self, text):
        label = QLabel(text)
        label.setObjectName("drawerSection")
        return label

    # ------------------------------------------------------------------ 状态
    def reset_defaults(self):
        self._scope = SCOPE_ALL
        self._order = ORDER_SHUFFLE
        self.all_check.setChecked(False)
        self.count_edit.setEnabled(True)
        self.count_edit.setText("10")
        self._sync_buttons()
        self._refresh_hint()

    def set_context(self, set_name, counts):
        self._counts = dict(counts or {})
        total = self._counts.get(SCOPE_ALL, 0)
        self.sub_label.setText(f"从「{set_name or '当前题库'}」中抽题（共 {total} 题）")
        self.reset_defaults()
        # 默认按当前范围能抽的最多 10 题；题目太少时直接给全部
        available = self.available_count()
        if 0 < available < 10:
            self.count_edit.setText(str(available))

    def available_count(self, scope=None):
        scope = scope or self._scope
        return int(self._counts.get(scope, 0) or 0)

    def set_scope(self, scope):
        self._scope = scope
        self._sync_buttons()
        self._refresh_hint()

    def set_order(self, order):
        self._order = order
        self._sync_buttons()
        self._refresh_hint()

    def _sync_buttons(self):
        for scope, btn in self.scope_buttons.items():
            self._set_active(btn, scope == self._scope)
        all_random = self.all_check.isChecked()
        for order, btn in self.order_buttons.items():
            self._set_active(btn, (not all_random) and order == self._order)
            btn.setEnabled(not all_random)

    @staticmethod
    def _set_active(btn, active):
        btn.setProperty("active", "true" if active else "false")
        style = btn.style()
        style.unpolish(btn)
        style.polish(btn)

    def _on_all_toggled(self, checked):
        self.count_edit.setEnabled(not checked)
        if checked:
            self.count_edit.setText(str(self.available_count()))
        self._sync_buttons()
        self._refresh_hint()

    def _refresh_hint(self):
        available = self.available_count()
        if available <= 0:
            self._set_hint("当前范围没有可用题目，请换个范围。", error=True)
            self.start_button.setEnabled(False)
            return
        self.start_button.setEnabled(True)
        if self.all_check.isChecked():
            self._set_hint(f"全部随机：抽满 {available} 题并打乱顺序。")
            return
        self._set_hint(f"当前范围可用 {available} 题，最多可抽 {available} 题。")

    def _set_hint(self, text, error=False):
        self.hint_label.setText(text)
        self.hint_label.setProperty("state", "error" if error else "normal")
        style = self.hint_label.style()
        style.unpolish(self.hint_label)
        style.polish(self.hint_label)

    # ------------------------------------------------------------------ 提交
    def _on_start(self):
        available = self.available_count()
        if available <= 0:
            self._set_hint("当前范围没有可用题目，请换个范围。", error=True)
            return
        all_random = self.all_check.isChecked()
        if all_random:
            count = available
            shuffle = True
        else:
            try:
                count = int(self.count_edit.text().strip() or "0")
            except ValueError:
                count = 0
            if count < 1:
                self._set_hint("请输入不小于 1 的题数。", error=True)
                return
            if count > available:
                self._set_hint(f"题数超过可用题目（{available} 题），请调小。",
                               error=True)
                return
            shuffle = self._order == ORDER_SHUFFLE
        self.startRequested.emit({
            "scope": self._scope,
            "count": int(count),
            "shuffle": bool(shuffle),
            "all": bool(all_random),
        })

    # ------------------------------------------------------------- 事件处理
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
