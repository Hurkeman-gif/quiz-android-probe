# -*- coding: utf-8 -*-
"""移动端主窗口：顶部信息条 + 答题视图 + 底部导航（上一题/提交/下一题）。

约束：
- 题库只读，本窗口不写题库、不写 progress.db、不写错题本、不写历史记录；
- 判定与统计全部走 app.session.PracticeSession，界面只负责展示；
- 答对约 0.8 秒自动下一题；答错不自动跳，必须手动点「下一题」。
"""
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import database
from ..models import TYPE_LABELS
from ..session import MODE_NORMAL, PracticeSession
from .quiz_view import MobileQuizView

DELAY_CORRECT_MS = 800

MOBILE_QSS = """
QWidget#mobileRoot {
    background: #F5F7FA;
}
QLabel {
    color: #1F2937;
}
#headerBar {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
}
#typeBadge {
    background: #E8F1FF;
    color: #1D4ED8;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 12pt;
    font-weight: 700;
}
#typeBadge[finished="true"] {
    background: #DCFCE7;
    color: #15803D;
}
#indexLabel {
    color: #4B5563;
    font-size: 11pt;
}
#statsLabel {
    color: #4B5563;
    font-size: 11pt;
}
#quizScroll, #quizBody {
    background: #F5F7FA;
    border: none;
}
#stemLabel {
    font-size: 15pt;
    font-weight: 600;
    color: #111827;
}
#answerLabel {
    font-size: 12pt;
    color: #15803D;
}
#explainFrame {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-radius: 10px;
}
#explainLabel {
    color: #92400E;
    font-size: 11pt;
}
#bottomBar {
    background: #FFFFFF;
    border-top: 1px solid #E5E7EB;
}
QPushButton#navBtn {
    min-height: 48px;
    border-radius: 10px;
    font-size: 14pt;
    background: #F3F4F6;
    color: #374151;
    border: 1px solid #E5E7EB;
}
QPushButton#navBtn:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
}
QPushButton#submitBtn {
    min-height: 48px;
    border-radius: 10px;
    font-size: 14pt;
    font-weight: 700;
    background: #2563EB;
    color: #FFFFFF;
    border: none;
}
QPushButton#submitBtn:disabled {
    background: #BFDBFE;
    color: #EFF6FF;
}
/* 选项卡片：内边距由 OptionCard 的布局 margins 控制，这里只管底色与边框 */
QPushButton#optionCard {
    border-radius: 14px;
    background: #FFFFFF;
    border: 1px solid #D5DCE6;
    font-size: 14pt;
}
QPushButton#optionCard[opt="picked"] {
    background: #E8F1FF;
    border: 2px solid #2563EB;
}
QPushButton#optionCard[opt="correct"] {
    background: #16A34A;
    border: 1px solid #16A34A;
}
QPushButton#optionCard[opt="wrong"] {
    background: #DC2626;
    border: 1px solid #DC2626;
}
QPushButton#optionCard[opt="dim"] {
    background: #F3F4F6;
    border: 1px solid #E5E7EB;
}
QLabel#optionKey {
    background: transparent;
    color: #374151;
    font-size: 15pt;
    font-weight: 700;
}
QLabel#optionText {
    background: transparent;
    color: #1F2937;
    font-size: 14pt;
}
QPushButton#optionCard[opt="picked"] QLabel#optionKey,
QPushButton#optionCard[opt="picked"] QLabel#optionText {
    color: #1D4ED8;
}
QPushButton#optionCard[opt="correct"] QLabel#optionKey,
QPushButton#optionCard[opt="correct"] QLabel#optionText {
    color: #FFFFFF;
}
QPushButton#optionCard[opt="wrong"] QLabel#optionKey,
QPushButton#optionCard[opt="wrong"] QLabel#optionText {
    color: #FFFFFF;
}
QPushButton#optionCard[opt="dim"] QLabel#optionKey,
QPushButton#optionCard[opt="dim"] QLabel#optionText {
    color: #9CA3AF;
}
QLabel#resultLabel {
    background: transparent;
    font-size: 16pt;
    font-weight: 700;
}
QLabel#resultLabel[state="correct"] {
    color: #15803D;
}
QLabel#resultLabel[state="wrong"] {
    color: #DC2626;
}
QLabel#explainTitle {
    background: transparent;
    color: #B45309;
    font-size: 11pt;
    font-weight: 700;
}
"""


class MobileMainWindow(QWidget):
    """移动端主窗口：信息条 + 单题视图 + 底部操作栏。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mobileRoot")
        self.setWindowTitle("答题练习软件")
        self.setStyleSheet(MOBILE_QSS)
        self.session = None
        self.set_name = None
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._auto_advance)
        self._auto_qid = None
        self._build_ui()
        self._load_bank()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("headerBar")
        hv = QVBoxLayout(header)
        hv.setContentsMargins(14, 10, 14, 8)
        hv.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.type_label = QLabel("")
        self.type_label.setObjectName("typeBadge")
        self.index_label = QLabel("")
        self.index_label.setObjectName("indexLabel")
        self.index_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.type_label)
        row.addStretch(1)
        row.addWidget(self.index_label)
        hv.addLayout(row)

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setWordWrap(True)
        hv.addWidget(self.stats_label)
        root.addWidget(header)

        self.quiz_view = MobileQuizView()
        self.quiz_view.answered.connect(self._on_answered)
        self.quiz_view.statsChanged.connect(self._refresh_chrome)
        root.addWidget(self.quiz_view, 1)

        bar = QWidget()
        bar.setObjectName("bottomBar")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(12, 8, 12, 12)
        bh.setSpacing(10)
        self.prev_button = QPushButton("上一题")
        self.prev_button.setObjectName("navBtn")
        self.submit_button = QPushButton("提交答案")
        self.submit_button.setObjectName("submitBtn")
        self.next_button = QPushButton("下一题")
        self.next_button.setObjectName("navBtn")
        self.prev_button.clicked.connect(self.goto_prev)
        self.submit_button.clicked.connect(self.submit_multiple)
        self.next_button.clicked.connect(self.goto_next)
        bh.addWidget(self.prev_button, 1)
        bh.addWidget(self.submit_button, 1)
        bh.addWidget(self.next_button, 1)
        root.addWidget(bar)

    # ------------------------------------------------------------ 加载题库
    def _load_bank(self):
        try:
            bank_path = database.get_default_db_path()
            database.open_bank(bank_path)
            sets = database.list_sets()
            self.set_name = sets[0] if sets else None
            questions = database.list_questions(set_name=self.set_name)
            if not questions:
                raise RuntimeError("题库为空，没有可练习的题目。")
            self.session = PracticeSession(MODE_NORMAL, questions)
            self.quiz_view.set_session(self.session)
            self._refresh_chrome()
        except Exception as exc:
            self.session = None
            self.type_label.setText("加载失败")
            self.index_label.setText("")
            self.stats_label.setText("题库加载失败：" + str(exc))
            self.quiz_view.show_message(
                "题库加载失败\n\n" + str(exc) + "\n\n" + traceback.format_exc())
            self.prev_button.setEnabled(False)
            self.submit_button.setEnabled(False)
            self.submit_button.setVisible(False)
            self.next_button.setEnabled(False)

    # ------------------------------------------------------------ 刷新界面
    def _refresh_chrome(self):
        if not self.session:
            return
        stats = self.session.get_live_stats()
        total = self.session.count()
        index = self.session.current_index
        all_answered = self.session.is_all_answered()
        if all_answered:
            self.type_label.setText("练习完成")
            self.type_label.setProperty("finished", "true")
        else:
            question = self.session.current_question()
            label = TYPE_LABELS.get(question.get("type"), question.get("type")) \
                if question else "—"
            self.type_label.setText(label)
            self.type_label.setProperty("finished", "false")
        style = self.type_label.style()
        style.unpolish(self.type_label)
        style.polish(self.type_label)

        self.index_label.setText(f"第 {index + 1} 题 / 共 {total} 题")
        self.stats_label.setText(
            f"已答 {stats['answered_count']} · 答对 {stats['correct_count']} · "
            f"答错 {stats['wrong_count']} · 正确率 {stats['accuracy_text']}")
        self._update_buttons(all_answered)
        self._force_repaint()

    def _force_repaint(self):
        """标题栏与统计文字同样会被 Android 的局部重绘牵连（数字缺笔画），
        这里整窗重绘一次，并再排一次 0ms 重绘兜住布局刚结算完的那一帧。"""
        self.update()
        self.repaint()
        QTimer.singleShot(0, self._repaint_window)

    def _repaint_window(self):
        self.update()
        self.repaint()

    def _update_buttons(self, all_answered):
        question = self.session.current_question() if self.session else None
        index = self.session.current_index if self.session else 0
        total = self.session.count() if self.session else 0
        is_multiple = bool(question and question.get("type") == "multiple")
        answered = bool(question and self.session.progress_for(question["id"]))
        self.submit_button.setVisible(is_multiple and not all_answered)
        self.submit_button.setEnabled(
            is_multiple and not answered and bool(self.quiz_view.selected_keys()))
        self.prev_button.setEnabled(not all_answered and index > 0)
        self.next_button.setEnabled(not all_answered and index < total - 1)

    # ------------------------------------------------------------ 判定回调
    def _on_answered(self, correct):
        self._cancel_auto()
        self._refresh_chrome()
        if not correct or not self.session:
            return
        question = self.session.current_question()
        self._auto_qid = question["id"] if question else None
        self._auto_timer.start(DELAY_CORRECT_MS)

    def _cancel_auto(self):
        self._auto_timer.stop()
        self._auto_qid = None

    def _auto_advance(self):
        if not self.session:
            return
        question = self.session.current_question()
        if question is None:
            return
        if self._auto_qid is not None and question["id"] != self._auto_qid:
            return
        self._auto_qid = None
        self.goto_next()

    # ------------------------------------------------------------ 导航
    def goto_next(self):
        if not self.session:
            return
        self._cancel_auto()
        if self.session.is_all_answered():
            self._refresh_chrome()
            return
        if self.session.navigate_to_question(self.session.current_index + 1):
            self.quiz_view.load_current()
            self._refresh_chrome()

    def goto_prev(self):
        if not self.session:
            return
        self._cancel_auto()
        if self.session.is_all_answered():
            self._refresh_chrome()
            return
        if self.session.current_index <= 0:
            return
        if self.session.navigate_to_question(self.session.current_index - 1):
            self.quiz_view.load_current()
            self._refresh_chrome()

    def submit_multiple(self):
        if not self.session:
            return
        self.quiz_view.submit()
