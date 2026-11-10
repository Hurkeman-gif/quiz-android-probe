# -*- coding: utf-8 -*-
"""移动端答题视图：题干、选项、判定颜色、解析。

渲染策略（针对 Android 触屏重做）：
- 选项是「卡片按钮」：QPushButton + 子 QLabel，文字换行交给 QLabel 的 wordWrap，
  不再在 resizeEvent 里改按钮文字（旧做法会让 sizeHint 反复变化、布局与绘制错位）；
- 卡片左右内边距由布局 margins 决定，不靠 QSS padding，避免边框/内边距挤压文字；
- 判定颜色用动态属性 opt + QSS；子标签颜色也由 QSS 决定，不在运行时改内联样式；
- 结果提示与解析放在独立的 feedback 容器里，作为一个整体 addWidget 进主布局。

只负责渲染与交互：判定结果与统计全部交给 app.session.PracticeSession，
本视图不保存进度、不写错题本、不写历史记录。
"""
from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CORRECT_TEXT = "回答正确"
WRONG_TEXT = "回答错误"
PAGE_BG = "#F5F7FA"


class OptionCard(QPushButton):
    """触屏选项卡片：左侧字母 key，右侧题面文字，自动换行、自动撑高。"""

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.opt_key = str(key)
        self.setText("")
        self.setObjectName("optionCard")
        self.setProperty("opt", "normal")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(64)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(10)

        self.key_label = QLabel(self.opt_key, self)
        self.key_label.setObjectName("optionKey")
        self.key_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.key_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.key_label.setMinimumWidth(20)

        self.text_label = QLabel(str(text or ""), self)
        self.text_label.setObjectName("optionText")
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Minimum)

        row.addWidget(self.key_label, 0, Qt.AlignTop)
        row.addWidget(self.text_label, 1)

    # 卡片底色自己用 QPainter 画：不依赖 QSS 的 border-radius 九宫格绘制，
    # 避免高 DPI / 局部重绘时色块与圆角错位（表现为左侧缺角、整块向右偏移）。
    def paintEvent(self, event):
        opt = self.property("opt")
        if opt == "correct":
            fill, border, width = QColor("#16A34A"), QColor("#16A34A"), 1.0
        elif opt == "wrong":
            fill, border, width = QColor("#DC2626"), QColor("#DC2626"), 1.0
        elif opt == "picked":
            fill, border, width = QColor("#E8F1FF"), QColor("#2563EB"), 2.0
        elif opt == "dim":
            fill, border, width = QColor("#F3F4F6"), QColor("#E5E7EB"), 1.0
        else:
            fill, border, width = QColor("#FFFFFF"), QColor("#D5DCE6"), 1.0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 先用页面底色铺满整个控件：圆角以外的四个角落如果不清，
        # 会留下上一帧（白卡）的像素，看起来像缺角。
        painter.fillRect(self.rect(), QColor(PAGE_BG))
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14.0, 14.0)
        painter.fillPath(path, fill)
        pen = QPen(border)
        pen.setWidthF(width)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def set_state(self, state: str):
        if self.property("opt") == state:
            return
        self.setProperty("opt", state)
        for widget in (self, self.key_label, self.text_label):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
        self.update()
        self.repaint()


class MobileQuizView(QWidget):
    """单题答题区：题干 + 选项 + 判定结果 + 解析。"""

    answered = Signal(bool)     # 本题刚判定：True 答对
    statsChanged = Signal()     # 已选状态变化或统计需要刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("quizView")
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
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("quizBody")
        self._body = body
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        # 主内容列：所有子控件都通过 addWidget 进入这同一个垂直布局
        box = QVBoxLayout(body)
        box.setContentsMargins(18, 16, 18, 20)
        box.setSpacing(12)

        self.stem_label = QLabel("")
        self.stem_label.setObjectName("stemLabel")
        self.stem_label.setWordWrap(True)
        self.stem_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stem_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                      QSizePolicy.Policy.Minimum)
        box.addWidget(self.stem_label)

        self.options_layout = QVBoxLayout()
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_layout.setSpacing(10)
        box.addLayout(self.options_layout)

        # 反馈区整体作为一个容器，避免提示标签脱离主布局
        self.feedback_box = QWidget()
        self.feedback_box.setObjectName("feedbackBox")
        fb = QVBoxLayout(self.feedback_box)
        fb.setContentsMargins(0, 4, 0, 0)
        fb.setSpacing(8)

        self.result_label = QLabel("")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setProperty("state", "correct")
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Minimum)
        fb.addWidget(self.result_label)

        self.answer_label = QLabel("")
        self.answer_label.setObjectName("answerLabel")
        self.answer_label.setWordWrap(True)
        self.answer_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Minimum)
        fb.addWidget(self.answer_label)

        self.explanation_frame = QFrame()
        self.explanation_frame.setObjectName("explainFrame")
        self.explanation_frame.setSizePolicy(QSizePolicy.Policy.Preferred,
                                             QSizePolicy.Policy.Minimum)
        exp_box = QVBoxLayout(self.explanation_frame)
        exp_box.setContentsMargins(14, 10, 14, 10)
        exp_box.setSpacing(4)
        self.explain_title = QLabel("解析")
        self.explain_title.setObjectName("explainTitle")
        exp_box.addWidget(self.explain_title)
        self.explanation_label = QLabel("")
        self.explanation_label.setObjectName("explainLabel")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.explanation_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                             QSizePolicy.Policy.Minimum)
        exp_box.addWidget(self.explanation_label)
        fb.addWidget(self.explanation_frame)

        box.addWidget(self.feedback_box)
        box.addStretch(1)

        self._box = box
        self.scroll.setWidget(body)
        self.scroll.viewport().installEventFilter(self)
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
        self.refresh_layout()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._sync_heights()
        return super().eventFilter(obj, event)

    def refresh_layout(self):
        """按当前视口宽度重算逐行文字高度，再强制重绘。

        QLabel 的自动换行只有在拿到确定的宽度后才能算出行高；光靠布局的
        sizeHint 会让长题干/长选项被截断，所以这里显式调用 heightForWidth。
        """
        self._sync_heights()
        body = self.scroll.widget()
        if body is not None:
            body.update()
            body.repaint()
        self.scroll.viewport().update()
        self.scroll.viewport().repaint()
        self.update()
        self.force_repaint()

    def force_repaint(self):
        """整窗重绘一次。

        Android 上只提交局部脏区域时，Qt 的图层合成偶发把一块区域画到
        偏移位置（表现为文字缺笔画、圆角缺角、整块右移）。整窗重绘代价很小，
        但能保证显示与布局完全对齐。
        """
        win = self.window()
        if win is not None:
            win.update()
            win.repaint()

    def _sync_heights(self):
        body = self.scroll.widget()
        if body is None:
            return
        width = self.scroll.viewport().width()
        if width <= 0:
            return
        margins = self._box.contentsMargins()
        inner = max(160, width - margins.left() - margins.right())

        # 先让 QSS 的字体生效，否则新加进来的控件还是默认小字号，
        # 算出来的行高会明显偏小（长选项被截断）。
        for widget in (self.stem_label, self.answer_label, self.explanation_label):
            widget.ensurePolished()
        for card in self._buttons:
            card.ensurePolished()
            card.key_label.ensurePolished()
            card.text_label.ensurePolished()

        stem_h = self.stem_label.heightForWidth(inner)
        if stem_h <= 0:
            stem_h = self.stem_label.sizeHint().height()
        self.stem_label.setFixedHeight(stem_h)

        for card in self._buttons:
            card_layout = card.layout()
            cm = card_layout.contentsMargins()
            key_w = max(20, card.key_label.sizeHint().width())
            text_w = max(60, inner - cm.left() - cm.right() - key_w
                         - card_layout.spacing())
            text_h = card.text_label.heightForWidth(text_w)
            if text_h <= 0:
                text_h = card.text_label.sizeHint().height()
            card.setFixedHeight(max(64, text_h + cm.top() + cm.bottom()))

        exp_w = max(80, inner - 28)
        exp_h = self.explanation_label.heightForWidth(exp_w)
        if exp_h <= 0:
            exp_h = self.explanation_label.sizeHint().height()
        self.explanation_label.setFixedHeight(exp_h)

        ans_h = self.answer_label.heightForWidth(inner)
        if ans_h <= 0:
            ans_h = self.answer_label.sizeHint().height()
        self.answer_label.setFixedHeight(ans_h)

        self._box.activate()
        body.setMinimumHeight(self._box.sizeHint().height())
        # 内容宽度钉死在视口宽度上：内容一旦比视口宽就会被横向裁掉（左侧缺角/缺字）
        if body.width() != width:
            body.setFixedWidth(width)
        body.update()

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
            card = OptionCard(key, str(opt.get("text") or ""))
            card.clicked.connect(lambda _checked=False, k=key: self.pick(k))
            self.options_layout.addWidget(card)
            self._buttons.append(card)

        progress = self.session.progress_for(question["id"])
        if progress:
            self.answered_now = True
            self._selected = [str(k) for k in (progress.get("selected") or [])]
            self._apply_states(bool(progress.get("correct")), self._selected, question)
            self._show_feedback(bool(progress.get("correct")), question)
        else:
            self._hide_feedback()
        self.scroll.verticalScrollBar().setValue(0)
        self.refresh_layout()
        self.statsChanged.emit()

    def _clear_options(self):
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
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
            for card in self._buttons:
                card.set_state("picked" if card.opt_key in self._selected else "normal")
            self.statsChanged.emit()
        else:
            return self.submit([key])
        return None

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
        self.refresh_layout()
        self.answered.emit(correct)
        self.statsChanged.emit()
        return correct

    # ------------------------------------------------------------ 判定颜色
    def _apply_states(self, correct: bool, selection, question):
        answer = [str(k) for k in (question.get("answer") or [])]
        for card in self._buttons:
            card.setEnabled(False)
            if card.opt_key in answer:
                card.set_state("correct")
            elif card.opt_key in selection:
                card.set_state("wrong")
            else:
                card.set_state("dim")

    def _show_feedback(self, correct: bool, question):
        self.result_label.setText(CORRECT_TEXT if correct else WRONG_TEXT)
        self.result_label.setProperty("state", "correct" if correct else "wrong")
        style = self.result_label.style()
        style.unpolish(self.result_label)
        style.polish(self.result_label)

        answer = [str(k) for k in (question.get("answer") or [])]
        self.answer_label.setText("正确答案：" + "、".join(answer))

        text = (question.get("explanation") or "").strip()
        self.explanation_label.setText(text if text else "暂无解析")
        self.feedback_box.show()
        # 反馈区显示后立刻激活外层布局；否则只做局部重绘，色块与文字会整体错位
        self._box.invalidate()
        self._box.activate()

    def _hide_feedback(self):
        self.feedback_box.hide()
