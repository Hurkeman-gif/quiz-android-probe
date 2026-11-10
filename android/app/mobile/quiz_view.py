# -*- coding: utf-8 -*-
"""移动端答题视图：题干、选项、判定颜色、解析。

只负责渲染与交互：判定结果与统计全部交给 app.session.PracticeSession，
本视图不保存进度、不写错题本、不写历史记录。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CORRECT_TEXT = "回答正确"
WRONG_TEXT = "回答错误"


class MobileOptionButton(QPushButton):
    """触屏选项按钮：显示 “A. 文本”，长文本按当前宽度自动换行。"""

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.opt_key = key
        self._raw_text = f"{key}. {text}"
        self.setProperty("opt", "normal")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setText(self._raw_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rewrap()

    def _rewrap(self):
        width = max(self.width() - 56, 120)
        fm = self.fontMetrics()
        lines = []
        for para in self._raw_text.split("\n"):
            if not para:
                lines.append("")
                continue
            current = ""
            for ch in para:
                if fm.horizontalAdvance(current + ch) <= width:
                    current += ch
                else:
                    lines.append(current)
                    current = ch
            lines.append(current)
        wrapped = "\n".join(lines)
        if wrapped != self.text():
            self.setText(wrapped)

    def set_state(self, state: str):
        if self.property("opt") == state:
            return
        self.setProperty("opt", state)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class MobileQuizView(QWidget):
    """单题答题区：题干 + 选项 + 判定结果 + 解析。"""

    answered = Signal(bool)     # 本题刚判定：True 答对
    statsChanged = Signal()     # 已选状态变化或统计需要刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self.answered_now = False
        self._buttons = []
        self._selected = []
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("quizScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("quizBody")
        box = QVBoxLayout(body)
        box.setContentsMargins(14, 10, 14, 14)
        box.setSpacing(10)

        self.stem_label = QLabel("")
        self.stem_label.setObjectName("stemLabel")
        self.stem_label.setWordWrap(True)
        self.stem_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.stem_label)

        self.options_layout = QVBoxLayout()
        self.options_layout.setSpacing(9)
        box.addLayout(self.options_layout)

        self.result_label = QLabel("")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setWordWrap(True)
        box.addWidget(self.result_label)

        self.answer_label = QLabel("")
        self.answer_label.setObjectName("answerLabel")
        self.answer_label.setWordWrap(True)
        box.addWidget(self.answer_label)

        self.explanation_frame = QFrame()
        self.explanation_frame.setObjectName("explainFrame")
        exp_box = QVBoxLayout(self.explanation_frame)
        exp_box.setContentsMargins(12, 10, 12, 10)
        self.explanation_label = QLabel("")
        self.explanation_label.setObjectName("explainLabel")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        exp_box.addWidget(self.explanation_label)
        box.addWidget(self.explanation_frame)

        box.addStretch(1)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll)
        self._hide_feedback()

    # ------------------------------------------------------------ 数据接口
    def set_session(self, session):
        self.session = session
        self.load_current()

    def selected_keys(self):
        return list(self._selected)

    def show_message(self, text: str):
        """题库加载失败等场景：只显示一段提示，不出现选项。"""
        self._clear_options()
        self.stem_label.setText(text)
        self.answered_now = True
        self._hide_feedback()

    # ------------------------------------------------------------ 渲染
    def load_current(self):
        self.answered_now = False
        self._selected = []
        self._clear_options()
        if not self.session:
            self.stem_label.setText("暂无题目")
            self._hide_feedback()
            return
        question = self.session.current_question()
        if not question:
            self.stem_label.setText("暂无题目")
            self._hide_feedback()
            return
        self.stem_label.setText(question.get("stem") or "")
        for opt in question.get("options") or []:
            key = str(opt.get("key") or "")
            btn = MobileOptionButton(key, str(opt.get("text") or ""))
            btn.clicked.connect(lambda _checked=False, k=key: self.pick(k))
            self.options_layout.addWidget(btn)
            self._buttons.append(btn)

        progress = self.session.progress_for(question["id"])
        if progress:
            self.answered_now = True
            self._selected = [str(k) for k in (progress.get("selected") or [])]
            self._apply_states(bool(progress.get("correct")), self._selected, question)
            self._show_feedback(bool(progress.get("correct")), question)
        else:
            self._hide_feedback()
        self.scroll.verticalScrollBar().setValue(0)
        self.statsChanged.emit()

    def _clear_options(self):
        for btn in self._buttons:
            self.options_layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons = []

    # ------------------------------------------------------------ 交互
    def pick(self, key: str):
        if not self.session or self.answered_now:
            return
        question = self.session.current_question()
        if not question:
            return
        if question.get("type") == "multiple":
            if key in self._selected:
                self._selected.remove(key)
            else:
                self._selected.append(key)
            for btn in self._buttons:
                btn.set_state("picked" if btn.opt_key in self._selected else "normal")
            self.statsChanged.emit()
        else:
            self.submit([key])

    def submit(self, selection=None):
        """提交判定；已判定或无选择时返回 None。答对返回 True，答错返回 False。"""
        if not self.session or self.answered_now:
            return None
        question = self.session.current_question()
        if not question:
            return None
        option_keys = [str(o.get("key") or "") for o in (question.get("options") or [])]
        raw = self._selected if selection is None else list(selection)
        selected = [str(k) for k in raw if str(k) in option_keys]
        if not selected:
            return None
        answer = [str(k) for k in (question.get("answer") or [])]
        correct = sorted(selected) == sorted(answer)
        self.answered_now = True
        self._selected = selected
        self.session.record_answer(question["id"], correct, selected)
        self._apply_states(correct, selected, question)
        self._show_feedback(correct, question)
        self.answered.emit(correct)
        self.statsChanged.emit()
        return correct

    # ------------------------------------------------------------ 判定颜色
    def _apply_states(self, correct: bool, selection, question):
        answer = [str(k) for k in (question.get("answer") or [])]
        for btn in self._buttons:
            btn.setEnabled(False)
            if btn.opt_key in answer:
                btn.set_state("correct")
            elif btn.opt_key in selection:
                btn.set_state("wrong")
            else:
                btn.set_state("dim")

    def _show_feedback(self, correct: bool, question):
        self.result_label.setText(CORRECT_TEXT if correct else WRONG_TEXT)
        color = "#15803D" if correct else "#B91C1C"
        self.result_label.setStyleSheet(
            f"color: {color}; font-size: 16pt; font-weight: 700;")
        self.result_label.show()

        answer = [str(k) for k in (question.get("answer") or [])]
        self.answer_label.setText("正确答案：" + "、".join(answer))
        self.answer_label.show()

        text = (question.get("explanation") or "").strip()
        self.explanation_label.setText(text if text else "暂无解析")
        self.explanation_frame.show()

    def _hide_feedback(self):
        self.result_label.hide()
        self.answer_label.hide()
        self.explanation_frame.hide()
