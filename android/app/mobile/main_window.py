# -*- coding: utf-8 -*-
"""移动端主窗口：顶部信息条 + 答题/完成页（QStackedWidget） + 底部操作栏。

约束：
- 题库只读，本窗口只读写 progress.db（普通练习进度），不写题库、不写错题本；
- 判定与统计全部走 app.session.PracticeSession，界面只负责展示；
- 答对约 0.8 秒自动跳到下一道未答题；答错不自动跳，必须手动点「下一题」；
- 手动提交（提前交卷）只把未答题标记为强制判错，绝不写错题本；
- 进度保存时机：每次提交答案后、手动提交后、切换题型前、退到后台/关闭窗口。
"""
import os
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import data_backup, database, progress_store, random_picker, wrongbook
from ..models import TYPE_LABELS
from ..session import (
    MODE_NORMAL,
    MODE_RANDOM,
    MODE_WRONGBOOK,
    VIEW_FINISH,
    VIEW_QUIZ,
    PracticeSession,
)
from .confirm_panel import ConfirmPanel
from .finish_view import FinishView
from .history_panel import HistoryDetailPanel, HistoryPanel
from .menu_drawer import MenuDrawer, MenuIconButton
from .nav_panel import NumberPanel
from .quiz_view import MobileQuizView
from .set_panel import BackupPanel, SetPickerPanel
from .random_panel import SCOPE_ALL, RandomSetupPanel
from .wrongbook_panel import WrongbookPanel

DELAY_CORRECT_MS = 800
DELAY_WRONG_MS = 2000

MANUAL_SUBMIT_TIP = "未作答题目将按错误计入本次成绩，但不会加入错题本。是否提交？"

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
QPushButton#typeBtn {
    min-height: 34px;
    border-radius: 9px;
    padding: 0 8px;
    font-size: 11.5pt;
    background: #F3F4F6;
    color: #4B5563;
    border: 1px solid #E5E7EB;
}
QPushButton#typeBtn[active="true"] {
    background: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
    font-weight: 700;
}
QPushButton#navToggleBtn {
    min-height: 34px;
    border-radius: 9px;
    padding: 0 12px;
    font-size: 11.5pt;
    background: #E8F1FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
}
QPushButton#navToggleBtn:pressed {
    background: #DBEAFE;
}
#indexLabel {
    color: #4B5563;
    font-size: 10.5pt;
}
#rateLabel {
    color: #4B5563;
    font-size: 10.5pt;
}
#statsLabel {
    color: #6B7280;
    font-size: 10pt;
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
    min-height: 44px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 700;
    background: #2563EB;
    color: #FFFFFF;
    border: none;
}
QPushButton#submitBtn:disabled {
    background: #BFDBFE;
    color: #EFF6FF;
}
QPushButton#manualBtn {
    min-height: 44px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 600;
    background: #FFFBEB;
    color: #B45309;
    border: 1px solid #FCD34D;
}
QPushButton#manualBtn:pressed {
    background: #FEF3C7;
}
QPushButton#manualBtn:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
}
QPushButton#resultBtn {
    min-height: 44px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 600;
    background: #E8F1FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
}
QPushButton#resultBtn:pressed {
    background: #DBEAFE;
}
QPushButton#confirmOk {
    min-height: 44px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 600;
    background: #2563EB;
    color: #FFFFFF;
    border: none;
}
QPushButton#confirmOk:pressed {
    background: #1D4ED8;
}
QPushButton#confirmCancel {
    min-height: 44px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 600;
    background: #F3F4F6;
    color: #374151;
    border: 1px solid #E5E7EB;
}
QPushButton#confirmCancel:pressed {
    background: #E5E7EB;
}
/* 完成页 */
QWidget#finishView {
    background: #F5F7FA;
}
#finishTitle {
    font-size: 24pt;
    font-weight: 700;
    color: #15803D;
}
#finishStat {
    font-size: 13pt;
    color: #374151;
}
#finishStatStrong {
    font-size: 15pt;
    font-weight: 700;
    color: #2563EB;
}
QPushButton#restartBtn {
    min-height: 50px;
    border-radius: 12px;
    font-size: 14pt;
    font-weight: 700;
    background: #DC2626;
    color: #FFFFFF;
    border: none;
}
QPushButton#restartBtn:pressed {
    background: #B91C1C;
}
QPushButton#reviewBtn {
    min-height: 50px;
    border-radius: 12px;
    font-size: 14pt;
    font-weight: 700;
    background: #2563EB;
    color: #FFFFFF;
    border: none;
}
QPushButton#reviewBtn:pressed {
    background: #1D4ED8;
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
QLabel[state="wrong"] {
    color: #DC2626;
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
/* 应用内弹层：错题本 / 答题记录 */
#panelTitle {
    font-size: 14pt;
    font-weight: 700;
    color: #111827;
}
#panelSub {
    font-size: 10.5pt;
    color: #6B7280;
}
#panelEmpty {
    font-size: 11.5pt;
    color: #6B7280;
}
QPushButton#panelClose {
    min-height: 36px;
    border-radius: 8px;
    padding: 0 12px;
    font-size: 11.5pt;
    background: #F3F4F6;
    color: #374151;
    border: 1px solid #E5E7EB;
}
QPushButton#panelPrimary {
    min-height: 46px;
    border-radius: 10px;
    font-size: 13pt;
    font-weight: 700;
    background: #2563EB;
    color: #FFFFFF;
    border: none;
}
QPushButton#panelPrimary:pressed {
    background: #1D4ED8;
}
QPushButton#panelPrimary:disabled {
    background: #BFDBFE;
    color: #EFF6FF;
}
QPushButton#panelGhost {
    min-height: 44px;
    border-radius: 10px;
    font-size: 12.5pt;
    background: #F3F4F6;
    color: #374151;
    border: 1px solid #E5E7EB;
}
QPushButton#panelGhost:pressed {
    background: #E5E7EB;
}
QPushButton#panelGhost:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
}
QPushButton#panelDanger {
    min-height: 44px;
    border-radius: 10px;
    font-size: 12.5pt;
    font-weight: 600;
    background: #FEF2F2;
    color: #B91C1C;
    border: 1px solid #FECACA;
}
QPushButton#panelDanger:pressed {
    background: #FEE2E2;
}
QPushButton#panelDanger:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
}
QWidget#recordList {
    background: #FFFFFF;
    border: none;
}
/* 主菜单抽屉 */
#drawerTitle {
    font-size: 17pt;
    font-weight: 700;
    color: #111827;
}
#drawerSub {
    font-size: 10.5pt;
    color: #6B7280;
}
#drawerSection {
    font-size: 10.5pt;
    color: #6B7280;
    padding-top: 2px;
}
QPushButton#drawerItem {
    min-height: 52px;
    border-radius: 10px;
    padding-left: 16px;
    text-align: left;
    font-size: 13.5pt;
    background: #F3F4F6;
    color: #111827;
    border: 1px solid #E5E7EB;
}
QPushButton#drawerItem:pressed {
    background: #E5E7EB;
}
QPushButton#drawerDanger {
    min-height: 48px;
    border-radius: 10px;
    font-size: 12.5pt;
    font-weight: 600;
    background: #FEF2F2;
    color: #B91C1C;
    border: 1px solid #FECACA;
}
QPushButton#drawerDanger:pressed {
    background: #FEE2E2;
}
QPushButton#drawerDanger:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
}
/* 随机设置弹层 */
QPushButton#segBtn {
    min-height: 38px;
    border-radius: 9px;
    padding: 0 6px;
    font-size: 11pt;
    background: #F3F4F6;
    color: #4B5563;
    border: 1px solid #E5E7EB;
}
QPushButton#segBtn[active="true"] {
    background: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
    font-weight: 700;
}
QPushButton#segBtn:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
}
QLineEdit#countEdit {
    min-height: 42px;
    border-radius: 9px;
    padding: 0 12px;
    font-size: 13pt;
    background: #FFFFFF;
    color: #111827;
    border: 1px solid #D1D5DB;
}
QLineEdit#countEdit:disabled {
    background: #F3F4F6;
    color: #6B7280;
}
QCheckBox#allCheck {
    font-size: 12pt;
    color: #374151;
    spacing: 8px;
}
#randomHint {
    font-size: 10.5pt;
    color: #6B7280;
}
#randomHint[state="error"] {
    color: #DC2626;
}
#backupStatus {
    font-size: 10.5pt;
    color: #15803D;
}
#backupStatus[state="error"] {
    color: #DC2626;
}
"""


class MobileMainWindow(QWidget):
    """移动端主窗口：信息条 + 答题页/完成页 + 底部操作栏。"""

    TYPE_ORDER = ("single", "multiple", "judge")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mobileRoot")
        self.setWindowTitle("答题练习软件")
        self.setStyleSheet(MOBILE_QSS)
        self.session = None
        self.set_name = None
        self.current_type = None
        self._bank_key = ""
        # 会话创建时记录的键：避免切换过程中被新题型覆盖导致存错位置
        self._session_key = ("", "", "")
        self._question_cache = {}
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._auto_advance)
        self._auto_qid = None
        self._auto_action = None
        self._build_ui()
        self.number_panel = NumberPanel(self)
        self.number_panel.numberChosen.connect(self._on_number_chosen)
        self.number_panel.closeRequested.connect(self.close_number_panel)
        # 提前交卷 / 移除 / 删除 / 清空 共用同一个确认弹层，按 _confirm_action 分发
        self._confirm_action = None
        self.confirm_panel = ConfirmPanel(self)
        self.confirm_panel.confirmed.connect(self._on_confirm_confirmed)
        # 主菜单抽屉 / 随机练习设置：同样是同窗口弹层（Android 上独立窗口收不到触摸）
        self.drawer_panel = MenuDrawer(self)
        self.drawer_panel.normalRequested.connect(self._on_drawer_normal)
        self.drawer_panel.randomRequested.connect(self._on_drawer_random)
        self.drawer_panel.setRequested.connect(self.open_set_panel)
        self.drawer_panel.wrongbookRequested.connect(self.open_wrongbook_panel)
        self.drawer_panel.historyRequested.connect(self.open_history_panel)
        self.drawer_panel.dataRequested.connect(self.open_backup_panel)
        self.drawer_panel.clearProgressRequested.connect(
            self._on_clear_progress_requested)
        self.drawer_panel.closeRequested.connect(self.close_overlays)
        self.random_panel = RandomSetupPanel(self)
        self.random_panel.startRequested.connect(self._on_random_start)
        self.random_panel.closeRequested.connect(self.close_overlays)
        self.wrongbook_panel = WrongbookPanel(self)
        self.wrongbook_panel.startPractice.connect(self._start_wrongbook_practice)
        self.wrongbook_panel.removeRequested.connect(
            self._on_wrongbook_remove_requested)
        self.wrongbook_panel.clearRequested.connect(
            self._on_wrongbook_clear_requested)
        self.wrongbook_panel.closeRequested.connect(self.close_overlays)
        self.history_panel = HistoryPanel(self)
        self.history_panel.detailRequested.connect(self._on_history_detail_requested)
        self.history_panel.deleteRequested.connect(self._on_history_delete_requested)
        self.history_panel.clearRequested.connect(self._on_history_clear_requested)
        self.history_panel.closeRequested.connect(self.close_overlays)
        self.history_detail_panel = HistoryDetailPanel(self)
        self.history_detail_panel.closeRequested.connect(self.close_history_detail)
        # 切换套题 / 数据备份
        self.set_panel = SetPickerPanel(self)
        self.set_panel.setChosen.connect(self._on_set_chosen)
        self.set_panel.closeRequested.connect(self.close_overlays)
        self.backup_panel = BackupPanel(self)
        self.backup_panel.exportRequested.connect(self._on_export_requested)
        self.backup_panel.exportAsRequested.connect(self._on_export_as_requested)
        self.backup_panel.importRequested.connect(self._on_import_requested)
        self.backup_panel.pickFileRequested.connect(self._on_pick_backup_file)
        self.backup_panel.closeRequested.connect(self.close_overlays)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)
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

        # 第一行：☰ 主菜单 + 题型分段按钮（当前题型高亮，点击即切题） + 题号导航
        row = QHBoxLayout()
        row.setSpacing(6)
        self.menu_button = MenuIconButton()
        self.menu_button.setFixedWidth(46)
        self.menu_button.setMinimumHeight(34)
        self.menu_button.setFocusPolicy(Qt.NoFocus)
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.clicked.connect(self.open_drawer)
        row.addWidget(self.menu_button, 0)
        self.type_buttons = {}
        for qtype in self.TYPE_ORDER:
            btn = QPushButton(TYPE_LABELS[qtype])
            btn.setObjectName("typeBtn")
            btn.setProperty("active", "false")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda _checked=False, t=qtype: self.select_type(t))
            row.addWidget(btn, 1)
            self.type_buttons[qtype] = btn
        self.nav_button = QPushButton("题号")
        self.nav_button.setObjectName("navToggleBtn")
        self.nav_button.setFocusPolicy(Qt.NoFocus)
        self.nav_button.setCursor(Qt.PointingHandCursor)
        self.nav_button.setMinimumHeight(34)
        self.nav_button.clicked.connect(self.open_number_panel)
        row.addWidget(self.nav_button, 0)
        hv.addLayout(row)

        # 第二行：题号/总数 + 正确率
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self.index_label = QLabel("")
        self.index_label.setObjectName("indexLabel")
        self.index_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.rate_label = QLabel("")
        self.rate_label.setObjectName("rateLabel")
        self.rate_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_row.addWidget(self.index_label)
        info_row.addStretch(1)
        info_row.addWidget(self.rate_label)
        hv.addLayout(info_row)

        # 第三行：已答/答对/答错
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hv.addWidget(self.stats_label)
        root.addWidget(header)

        # 答题页 / 完成页
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.quiz_view = MobileQuizView()
        self.quiz_view.answered.connect(self._on_answered)
        self.quiz_view.statsChanged.connect(self._refresh_chrome)
        self.finish_view = FinishView()
        self.finish_view.restartRequested.connect(self._on_restart_requested)
        self.finish_view.reviewRequested.connect(self._on_review_requested)
        self.stack.addWidget(self.quiz_view)
        self.stack.addWidget(self.finish_view)
        root.addWidget(self.stack, 1)

        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("bottomBar")
        # QWidget 默认不画 QSS 背景：不设这个属性时底栏是透明的，Android 会把
        # 上一版布局的像素留在屏幕上，造成「看到的位置点不到」。
        self.bottom_bar.setAttribute(Qt.WA_StyledBackground, True)
        bv = QVBoxLayout(self.bottom_bar)
        # 底部多留 44px：Android 手势条/导航栏会吞掉贴底的点击
        bv.setContentsMargins(12, 8, 12, 44)
        bv.setSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.submit_button = QPushButton("提交答案")
        self.submit_button.setObjectName("submitBtn")
        self.submit_button.clicked.connect(self.submit_multiple)
        self.manual_button = QPushButton("提前交卷")
        self.manual_button.setObjectName("manualBtn")
        self.manual_button.clicked.connect(self.manual_submit)
        # 全部答完后回到作答区时，用它重新打开完成页，避免无处可点
        self.result_button = QPushButton("查看结果")
        self.result_button.setObjectName("resultBtn")
        self.result_button.clicked.connect(self._show_completion)
        action_row.addWidget(self.submit_button, 1)
        action_row.addWidget(self.manual_button, 1)
        action_row.addWidget(self.result_button, 1)
        bv.addLayout(action_row)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)
        self.prev_button = QPushButton("上一题")
        self.prev_button.setObjectName("navBtn")
        self.next_button = QPushButton("下一题")
        self.next_button.setObjectName("navBtn")
        self.prev_button.clicked.connect(self.goto_prev)
        self.next_button.clicked.connect(self.goto_next)
        nav_row.addWidget(self.prev_button, 1)
        nav_row.addWidget(self.next_button, 1)
        bv.addLayout(nav_row)
        root.addWidget(self.bottom_bar)

    # ------------------------------------------------------------ 加载题库
    def _load_bank(self):
        try:
            bank_path = database.get_default_db_path()
            database.open_bank(bank_path)
            self._bank_key = os.path.basename(bank_path) or "quiz.db"
            sets = database.list_sets()
            # 恢复上次使用的套题（进度/错题/记录都按套题隔离）
            saved_set = ""
            try:
                saved_set = progress_store.get_setting("last_set", "") or ""
            except Exception:
                traceback.print_exc()
            if saved_set and saved_set in sets:
                self.set_name = saved_set
            else:
                self.set_name = sets[0] if sets else None
            self._question_cache = {}
            start = None
            for qtype in self.TYPE_ORDER:
                if self._questions_for_type(qtype):
                    start = qtype
                    break
            if start is None:
                raise RuntimeError("题库为空，没有可练习的题目。")
            self.select_type(start)
        except Exception as exc:
            self.session = None
            self.index_label.setText("")
            self.rate_label.setText("")
            self.stats_label.setText("题库加载失败")
            self.quiz_view.show_message(
                "题库加载失败\n\n" + str(exc) + "\n\n" + traceback.format_exc())
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.submit_button.setVisible(False)
            self.manual_button.setVisible(False)

    def _questions_for_type(self, qtype):
        """只读查询某题型的题目列表（带缓存，切换题型不重复读库）。"""
        if qtype not in self._question_cache:
            self._question_cache[qtype] = database.list_questions(
                qtype=qtype, set_name=self.set_name)
        return self._question_cache[qtype]

    # ------------------------------------------------------------ 会话与进度
    def select_type(self, qtype):
        """切换题型：先保存当前进度，再加载该题型并恢复已保存的进度。"""
        if qtype not in TYPE_LABELS:
            return
        self._cancel_auto()
        self._save_progress_now()
        self.close_overlays()
        self.current_type = qtype
        self._start_normal_session(qtype)

    def _start_normal_session(self, qtype):
        questions = self._questions_for_type(qtype)
        self.close_number_panel()
        if not questions:
            self.session = None
            self._ensure_quiz_view()
            self.quiz_view.show_message(f"「{TYPE_LABELS[qtype]}」暂无题目")
            self._refresh_chrome()
            return

        self._session_key = (self._bank_key, qtype, self.set_name or "")
        state = self._load_saved_state(questions)
        session = PracticeSession(MODE_NORMAL, questions)
        if state:
            session.restore_state(state)
        self.session = session

        if session.view_mode == VIEW_FINISH and session.is_all_answered():
            self.quiz_view.set_session(session)
            self._show_completion()
        else:
            self._ensure_quiz_view()
            self.quiz_view.set_session(session)
            self._refresh_chrome()

    def _load_saved_state(self, questions):
        """读取并清洗已保存进度：题目若已不在题库中则跳过，绝不修改题库。"""
        try:
            state = progress_store.load_progress(*self._session_key)
        except Exception:
            return None
        if not state:
            return None
        try:
            ids = [int(i) for i in (state.get("question_ids") or [])]
        except (TypeError, ValueError):
            return None
        existing = {int(q["id"]) for q in questions}
        valid = [i for i in ids if i in existing]
        if not valid:
            return None
        state["question_ids"] = valid
        return state

    def _save_progress_now(self):
        """保存当前普通练习进度（只写 progress.db，不碰题库）。"""
        if self.session is None or self.session.mode != MODE_NORMAL:
            return
        if not self.session.question_ids:
            return
        try:
            progress_store.save_progress(
                *self._session_key, self.session.serialize())
        except Exception as exc:
            traceback.print_exc()
            self.stats_label.setText(f"进度保存失败：{exc}")

    def _on_app_state_changed(self, state):
        """退到后台时保存进度（Android 上按 Home / 切走应用）。"""
        if state != Qt.ApplicationActive:
            self._save_progress_now()

    def closeEvent(self, event):
        self._cancel_auto()
        self._save_progress_now()
        super().closeEvent(event)

    # ------------------------------------------------------------ 视图切换
    def _ensure_quiz_view(self):
        """强制回到答题页：跳题/上一题/下一题/切题型都不能残留完成页。"""
        if self.session is not None:
            self.session.view_mode = VIEW_QUIZ
        if self.stack.currentWidget() is not self.quiz_view:
            self.stack.setCurrentWidget(self.quiz_view)
        if not self.bottom_bar.isVisible():
            self.bottom_bar.setVisible(True)

    def _show_completion(self):
        """进入完成页：仅当前题型全部已答（自然答完或手动提交）才触发。"""
        if not self.session:
            return
        if not self.session.is_all_answered():
            self._ensure_quiz_view()
            self.quiz_view.load_current()
            self._refresh_chrome()
            return
        self._cancel_auto()
        self.session.show_finish_view()
        stats = self.session.get_finish_stats()
        self.finish_view.set_stats(stats)
        self.stack.setCurrentWidget(self.finish_view)
        self.bottom_bar.setVisible(False)
        self._save_progress_now()
        self._record_history_once()
        self._refresh_chrome()

    def _on_restart_requested(self):
        """重新开始：清空本题型进度并回到第 1 题（不动题库）。"""
        if not self.session:
            return
        self.session.restart_current_session()
        if self.session.mode == MODE_NORMAL:
            try:
                progress_store.delete_progress(*self._session_key)
            except Exception:
                traceback.print_exc()
        self._ensure_quiz_view()
        self.quiz_view.set_session(self.session)
        self._refresh_chrome()

    def _on_review_requested(self):
        """返回第一题：保留答题痕迹，只切回答题页。"""
        self._jump_to(0)

    # ------------------------------------------------------------ 刷新界面
    def _refresh_chrome(self):
        self._update_type_buttons()
        if not self.session:
            self.index_label.setText("")
            self.rate_label.setText("")
            self.stats_label.setText("暂无题目")
            self._update_buttons(True)
            self._force_repaint()
            return
        stats = self.session.get_live_stats()
        total = self.session.count()
        index = self.session.current_index
        all_answered = self.session.is_all_answered()
        prefix = ""
        if self.session.mode == MODE_WRONGBOOK:
            prefix = "错题本练习 · "
        elif self.session.mode == MODE_RANDOM:
            prefix = "随机练习 · "
        if all_answered or self.session.view_mode == VIEW_FINISH:
            self.index_label.setText(f"{prefix}练习完成 · 共 {total} 题")
        else:
            self.index_label.setText(f"{prefix}第 {index + 1} 题 / 共 {total} 题")
        self.rate_label.setText(f"正确率 {stats['accuracy_text']}")
        self.stats_label.setText(
            f"已答 {stats['answered_count']} · 答对 {stats['correct_count']} · "
            f"答错 {stats['wrong_count']}")
        self._update_buttons(all_answered)
        if self.number_panel.isVisible():
            self.number_panel.refresh_states()
        self._force_repaint()

    def _update_type_buttons(self):
        """题型按钮高亮当前题型（随机/错题本练习可能是混合题型，不高亮）。"""
        mixed_mode = bool(self.session and self.session.mode != MODE_NORMAL)
        for qtype, btn in self.type_buttons.items():
            active = (not mixed_mode) and qtype == self.current_type
            btn.setProperty("active", "true" if active else "false")
            style = btn.style()
            style.unpolish(btn)
            style.polish(btn)

    def _repaint_bottom(self):
        """底栏在按钮显隐后必须整块重绘，否则 Android 会残留上一版像素。"""
        self.bottom_bar.update()
        self.bottom_bar.repaint()

    def _force_repaint(self):
        """Android 上局部重绘会让数字缺笔画，这里整窗重绘一次。"""
        self._repaint_bottom()
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
        has_session = self.session is not None
        self.submit_button.setVisible(is_multiple and not all_answered)
        self.submit_button.setEnabled(
            is_multiple and not answered and bool(self.quiz_view.selected_keys()))
        allowed = self._manual_submit_allowed()
        self.manual_button.setVisible(allowed)
        self.manual_button.setEnabled(allowed)
        done = bool(has_session and all_answered)
        self.result_button.setVisible(done)
        self.result_button.setEnabled(done)
        self.prev_button.setEnabled(has_session and not all_answered and index > 0)
        self.next_button.setEnabled(has_session and not all_answered)
        self._repaint_bottom()

    # ------------------------------------------------------------ 手动提交
    def _manual_submit_allowed(self):
        if not self.session:
            return False
        if self.session.mode not in (MODE_NORMAL, MODE_RANDOM):
            return False
        if self.session.manual_submitted:
            return False
        if self.session.is_all_answered():
            return False
        return self.session.count() > 0

    def manual_submit(self):
        """提前交卷：未答题按错误计入成绩，但绝不写错题本。"""
        if not self._manual_submit_allowed():
            return
        self._cancel_auto()
        self.close_number_panel()
        self.confirm_panel.setGeometry(self.rect())
        self._confirm_action = "manual_submit"
        self.confirm_panel.show_confirm("提前交卷", MANUAL_SUBMIT_TIP, "提交", "取消")

    def _on_manual_submit_confirmed(self):
        if not self.session or not self._manual_submit_allowed():
            return
        # 只标记强制判错，不调用任何错题本接口
        self.session.mark_unanswered()
        self._save_progress_now()
        self._refresh_chrome()
        self._show_completion()

    # ------------------------------------------------------------ 判定回调
    def _on_answered(self, correct):
        self._cancel_auto()
        self._update_wrongbook(correct)
        self._save_progress_now()
        self._refresh_chrome()
        if not self.session:
            return
        if self.session.is_all_answered():
            self._auto_action = "finish"
        else:
            question = self.session.current_question()
            self._auto_qid = question["id"] if question else None
            self._auto_action = "next"
        # 答对 0.8 秒后自动下一题；答错留 2 秒看正确答案与解析
        self._auto_timer.start(DELAY_CORRECT_MS if correct else DELAY_WRONG_MS)

    def _cancel_auto(self):
        self._auto_timer.stop()
        self._auto_qid = None
        self._auto_action = None

    def _auto_advance(self):
        action = self._auto_action
        expected_qid = self._auto_qid
        self._auto_action = None
        self._auto_qid = None
        if not self.session:
            return
        if expected_qid is not None:
            question = self.session.current_question()
            if question is None or question["id"] != expected_qid:
                return
        if action == "finish":
            self._show_completion()
            return
        self.goto_next()

    # ------------------------------------------------------------ 导航
    def _jump_to(self, index):
        if not self.session:
            return
        self._cancel_auto()
        self._ensure_quiz_view()
        if self.session.navigate_to_question(index):
            self.quiz_view.load_current()
            self._refresh_chrome()
            self._save_progress_now()

    def goto_next(self):
        if not self.session:
            return
        self._cancel_auto()
        self._ensure_quiz_view()
        if self.session.is_all_answered():
            self._show_completion()
            return
        if self.session.advance_after_answer():
            self.quiz_view.load_current()
            self._refresh_chrome()
            self._save_progress_now()
        else:
            self._show_completion()

    def goto_prev(self):
        if not self.session:
            return
        self._cancel_auto()
        self._ensure_quiz_view()
        if self.session.current_index <= 0:
            self._refresh_chrome()
            return
        self._jump_to(self.session.current_index - 1)

    def submit_multiple(self):
        if not self.session:
            return
        self.quiz_view.submit()

    # ------------------------------------------------------------ 题号导航
    def open_number_panel(self):
        if not self.session:
            return
        self._cancel_auto()
        self.number_panel.set_session(
            self.session, self._number_panel_label())
        self.number_panel.setGeometry(self.rect())
        self.number_panel.raise_()
        self.number_panel.show()

    def _number_panel_label(self):
        mode = self.session.mode if self.session else ""
        if mode == MODE_RANDOM:
            return "随机练习"
        if mode == MODE_WRONGBOOK:
            return "错题本练习"
        return TYPE_LABELS.get(self.current_type, "")

    def close_number_panel(self):
        self.number_panel.hide()

    def _on_number_chosen(self, index):
        self.close_number_panel()
        self._jump_to(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for name in ("number_panel", "confirm_panel", "drawer_panel",
                     "random_panel", "set_panel", "backup_panel",
                     "wrongbook_panel", "history_panel",
                     "history_detail_panel"):
            panel = getattr(self, name, None)
            if panel is not None and panel.isVisible():
                panel.setGeometry(self.rect())

    # ------------------------------------------------------------ 弹层通用
    def _show_overlay(self, panel):
        panel.setGeometry(self.rect())
        panel.raise_()
        panel.show()

    def close_overlays(self):
        for panel in (self.drawer_panel, self.random_panel, self.set_panel,
                      self.backup_panel, self.wrongbook_panel,
                      self.history_panel, self.history_detail_panel):
            panel.hide()

    # ------------------------------------------------------------ 主菜单抽屉
    def open_drawer(self):
        self._cancel_auto()
        self.close_overlays()
        self.drawer_panel.set_context(self._drawer_context())
        self._show_overlay(self.drawer_panel)
        self.drawer_panel.refresh_width()

    def _drawer_context(self):
        """抽屉副标题：当前题库/题型/进度，清空按钮只在有普通练习进度时可用。"""
        parts = []
        parts.append(str(self.set_name) if self.set_name else "全部套题")
        mode = self.session.mode if self.session else ""
        if mode == MODE_RANDOM:
            parts.append(f"随机练习 · {self.session.count()} 题")
        elif mode == MODE_WRONGBOOK:
            parts.append(f"错题本练习 · {self.session.count()} 题")
        else:
            label = TYPE_LABELS.get(self.current_type or "", "")
            if label:
                parts.append(label)
            if self.session:
                stats = self.session.get_live_stats()
                parts.append(f"已答 {stats['answered_count']}/{self.session.count()}")
        return " · ".join(parts)

    def _on_drawer_normal(self):
        """普通练习：关闭抽屉，回到当前题型的普通练习（随机/错题本模式会被丢弃）。"""
        self.close_overlays()
        mode = self.session.mode if self.session else ""
        if mode != MODE_NORMAL:
            self.select_type(self.current_type or "single")
        else:
            self._refresh_chrome()

    def _on_drawer_random(self):
        self.close_overlays()
        self.open_random_panel()

    # ------------------------------------------------------------ 随机练习
    def open_random_panel(self):
        self._cancel_auto()
        self.close_overlays()
        counts = random_picker.count_pool(self.set_name)
        self.random_panel.set_context(self.set_name, counts)
        self._show_overlay(self.random_panel)

    def _on_random_start(self, config):
        self.close_overlays()
        self.start_random_practice(
            config.get("scope", SCOPE_ALL),
            config.get("count"),
            bool(config.get("shuffle", True)))

    def start_random_practice(self, scope=SCOPE_ALL, count=None, shuffle=True):
        """随机练习：按抽题快照出题，绝不写 progress.db（完成时只写 history）。"""
        self._cancel_auto()
        self._save_progress_now()
        self.close_number_panel()
        questions = random_picker.pick_questions(
            scope, count, shuffle, set_name=self.set_name)
        if not questions:
            self.stats_label.setText("随机练习：当前范围没有可用题目")
            return
        self.session = PracticeSession(
            MODE_RANDOM, questions,
            random_config={
                "scope": scope,
                "count": len(questions),
                "shuffle": bool(shuffle),
            })
        self._ensure_quiz_view()
        self.quiz_view.set_session(self.session)
        self._refresh_chrome()

    # ------------------------------------------------------------ 切换套题
    def _set_items(self):
        """[{name, count}]：套题名与题目数量（只读查询题库）。"""
        items = []
        try:
            names = database.list_sets()
        except Exception:
            traceback.print_exc()
            return items
        for name in names:
            count = 0
            try:
                count = int(database.count_questions(set_name=name))
            except TypeError:
                try:
                    count = int(database.count_questions(name))
                except Exception:
                    count = 0
            except Exception:
                count = 0
            items.append({"name": name, "count": count})
        return items

    def open_set_panel(self):
        self._cancel_auto()
        self.close_overlays()
        self.set_panel.set_rows(self._set_items(), current=self.set_name)
        self._show_overlay(self.set_panel)

    def _on_set_chosen(self, name):
        self.close_overlays()
        self.switch_set(name)

    def switch_set(self, name):
        """切换套题：先保存当前套题进度，再用新套题重建题型与会话。

        进度、错题本、答题记录都带套题标记，所以切回来时能恢复到原处。
        """
        target = name or None
        if target == self.set_name:
            return
        self._cancel_auto()
        self._save_progress_now()
        self.close_number_panel()
        self.close_overlays()
        self.set_name = target
        try:
            progress_store.set_setting("last_set", target or "")
        except Exception:
            traceback.print_exc()
        self._question_cache = {}
        self.session = None
        self.current_type = None
        start = None
        for qtype in self.TYPE_ORDER:
            if self._questions_for_type(qtype):
                start = qtype
                break
        if start is None:
            self._ensure_quiz_view()
            self.quiz_view.show_message("该套题没有题目")
            self._refresh_chrome()
            return
        self.select_type(start)

    # ------------------------------------------------------------ 数据备份
    def open_backup_panel(self):
        self._cancel_auto()
        self.close_overlays()
        self._refresh_backup_panel()
        self._show_overlay(self.backup_panel)

    def _refresh_backup_panel(self, message=""):
        directory = ""
        items = []
        try:
            directory = data_backup.backup_dir()
            items = data_backup.list_backups()
        except Exception as exc:
            traceback.print_exc()
            directory = "不可用：%s" % exc
        self.backup_panel.set_backups(directory, items, message)

    def _on_export_requested(self):
        try:
            info = data_backup.export_default()
        except Exception as exc:
            traceback.print_exc()
            self.backup_panel.show_result("导出失败：%s" % exc, False)
            return
        counts = info.get("counts") or {}
        self._refresh_backup_panel()
        self.backup_panel.show_result(
            "已导出 %s（进度 %d · 记录 %d · 错题 %d）" % (
                os.path.basename(info.get("path") or ""),
                counts.get("progress", 0), counts.get("history", 0),
                counts.get("wrongbook", 0)), True)

    def _on_export_as_requested(self):
        """按用户选择的位置导出（系统保存对话框）。"""
        try:
            directory = data_backup.backup_dir()
        except Exception:
            directory = os.path.expanduser("~")
        dialog = QFileDialog(self, "导出数据")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilter("备份文件 (*.json)")
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.selectFile(os.path.join(directory, data_backup.default_filename()))
        # Android 上 Qt 自绘文件对话框可能收不到触摸，20 秒兜底关闭避免卡死
        QTimer.singleShot(20000, dialog.reject)
        if not dialog.exec():
            return
        files = dialog.selectedFiles()
        if not files:
            return
        try:
            info = data_backup.export_to(files[0])
        except Exception as exc:
            traceback.print_exc()
            self.backup_panel.show_result("导出失败：%s" % exc, False)
            return
        self._refresh_backup_panel()
        self.backup_panel.show_result(
            "已导出 %s" % os.path.basename(info.get("path") or ""), True)

    def _on_pick_backup_file(self):
        """从任意位置选一个备份 JSON 导入（系统打开对话框）。"""
        try:
            directory = data_backup.backup_dir()
        except Exception:
            directory = os.path.expanduser("~")
        dialog = QFileDialog(self, "导入数据")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("备份文件 (*.json)")
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.selectFile(directory)
        QTimer.singleShot(20000, dialog.reject)
        if not dialog.exec():
            return
        files = dialog.selectedFiles()
        if files:
            self._on_import_requested(files[0])

    def _on_import_requested(self, path):
        result = data_backup.import_file(path)
        if not result.get("ok"):
            errors = "；".join(result.get("errors") or ["未知错误"])
            self.backup_panel.show_result("导入失败：" + errors, False)
            return
        stats = result.get("stats") or {}
        progress_stats = stats.get("progress") or {}
        history_stats = stats.get("history") or {}
        wrong_stats = stats.get("wrongbook") or {}
        text = "导入完成：进度 %d 条 · 记录 %d 条 · 错题 %d 条" % (
            int(progress_stats.get("changed") or 0),
            int(history_stats.get("added") or 0),
            int(wrong_stats.get("changed") or 0))
        # 进度可能被合并更新，重载当前会话让界面与数据一致
        if self.session is not None and self.session.mode == MODE_NORMAL and self.current_type:
            self._start_normal_session(self.current_type)
        self._refresh_backup_panel()
        self.backup_panel.show_result(text, True)

    # ------------------------------------------------------------ 清空进度
    def _on_clear_progress_requested(self):
        self.close_overlays()
        label = TYPE_LABELS.get(self.current_type or "", "当前题型")
        self._confirm_action = ("clear_progress",)
        self.confirm_panel.show_confirm(
            "清空当前进度",
            f"将清空「{label}」的普通练习进度（作答痕迹与统计），题库与错题本不受影响。是否继续？",
            "清空", "取消")

    def _do_clear_progress(self):
        key = (self._bank_key, self.current_type or "single", self.set_name or "")
        try:
            progress_store.delete_progress(*key)
        except Exception:
            traceback.print_exc()
            self.stats_label.setText("清空进度失败")
        if self.session is not None and self.session.mode == MODE_NORMAL:
            self._start_normal_session(self.current_type or "single")
        self._refresh_chrome()

    # ------------------------------------------------------------ 错题本
    def _wrongbook_rows(self):
        """错题本记录 + 题库只读查询题干（题库里已不存在的题标记失效）。"""
        try:
            records = wrongbook.list_records(set_name=self.set_name)
        except Exception:
            traceback.print_exc()
            return []
        rows = []
        for rec in records:
            qid = int(rec.get("question_id") or 0)
            question = None
            if qid:
                try:
                    question = database.get_question(qid)
                except Exception:
                    traceback.print_exc()
            question = question or {}
            rows.append({
                "question_id": qid,
                "stem": question.get("stem") or "",
                "type": question.get("type") or "",
                "wrong_count": int(rec.get("wrong_count") or 0),
                "missing": not question,
            })
        return rows

    def open_wrongbook_panel(self):
        self._cancel_auto()
        self.close_overlays()
        self.wrongbook_panel.set_rows(self._wrongbook_rows())
        self._show_overlay(self.wrongbook_panel)

    def _update_wrongbook(self, correct):
        """答错自动收录；错题本练习答对自动移除（手动提交的未答不会走到这里）。"""
        if not self.session:
            return
        question = self.session.current_question()
        if not question:
            return
        qid = int(question["id"])
        try:
            if correct:
                if self.session.mode == MODE_WRONGBOOK:
                    wrongbook.remove_wrong(qid)
            else:
                answer = self.session.answers.get(qid) or {}
                wrongbook.record_wrong(
                    qid, answer.get("selected") or [],
                    question.get("answer") or [], source=self.session.mode,
                    set_name=self.set_name or "")
        except Exception as exc:
            traceback.print_exc()
            self.stats_label.setText(f"错题本更新失败：{exc}")

    def _start_wrongbook_practice(self, ids):
        """错题本练习：按快照出题，跳过题库中已不存在的题。"""
        ids = [int(i) for i in (ids or [])]
        if not ids:
            return
        self.close_overlays()
        self._cancel_auto()
        self._save_progress_now()
        questions = []
        for qid in ids:
            question = None
            try:
                question = database.get_question(qid)
            except Exception:
                traceback.print_exc()
            if question:
                questions.append(question)
        if not questions:
            self.wrongbook_panel.set_rows(self._wrongbook_rows())
            self._show_overlay(self.wrongbook_panel)
            return
        self.session = PracticeSession(MODE_WRONGBOOK, questions,
                                      wrongbook_snapshot=ids)
        self._ensure_quiz_view()
        self.quiz_view.set_session(self.session)
        self._refresh_chrome()

    def _on_wrongbook_remove_requested(self, question_id):
        self._confirm_action = ("wrongbook_remove", int(question_id))
        self.confirm_panel.show_confirm(
            "移除错题", "从错题本中移除这道题？题库不受影响。", "移除", "取消")

    def _do_wrongbook_remove(self, question_id):
        try:
            wrongbook.remove_wrong(question_id)
        except Exception as exc:
            traceback.print_exc()
            self.stats_label.setText(f"错题本更新失败：{exc}")
        self.wrongbook_panel.set_rows(self._wrongbook_rows())
        self._show_overlay(self.wrongbook_panel)

    def _on_wrongbook_clear_requested(self):
        self._confirm_action = ("wrongbook_clear",)
        self.confirm_panel.show_confirm(
            "清空错题本", "将清空全部错题记录？此操作不影响题库。", "清空", "取消")

    def _do_wrongbook_clear(self):
        try:
            wrongbook.clear_all(set_name=self.set_name)
        except Exception as exc:
            traceback.print_exc()
            self.stats_label.setText(f"错题本清空失败：{exc}")
        self.wrongbook_panel.set_rows(self._wrongbook_rows())
        self._show_overlay(self.wrongbook_panel)

    # ------------------------------------------------------------ 答题记录
    def open_history_panel(self):
        self._cancel_auto()
        self.close_overlays()
        try:
            rows = progress_store.list_history(set_name=self.set_name)
        except Exception:
            traceback.print_exc()
            rows = []
        self.history_panel.set_rows(rows)
        self._show_overlay(self.history_panel)

    def _on_history_detail_requested(self, record):
        self.history_detail_panel.set_record(record)
        self._show_overlay(self.history_detail_panel)

    def close_history_detail(self):
        self.history_detail_panel.hide()

    def _on_history_delete_requested(self, history_id):
        self._confirm_action = ("history_delete", int(history_id))
        self.confirm_panel.show_confirm(
            "删除记录", "删除这条答题记录？不影响题库、错题本与当前进度。",
            "删除", "取消")

    def _do_history_delete(self, history_id):
        try:
            progress_store.delete_history(history_id)
        except Exception:
            traceback.print_exc()
        self.open_history_panel()

    def _on_history_clear_requested(self):
        self._confirm_action = ("history_clear",)
        self.confirm_panel.show_confirm(
            "清空记录", "将清空全部答题记录？不影响题库、错题本与当前进度。",
            "清空", "取消")

    def _do_history_clear(self):
        try:
            progress_store.clear_history()
        except Exception:
            traceback.print_exc()
        self.open_history_panel()

    def _record_history_once(self):
        """完成页首次出现时写一条历史（session_uuid 唯一，绝不重复）。"""
        if not self.session or self.session.history_recorded:
            return
        if not self.session.is_all_answered():
            return
        if self.session.mode == MODE_WRONGBOOK:
            question_type = ""
        elif self.session.mode == MODE_RANDOM:
            scope = (self.session.random_config or {}).get("scope", SCOPE_ALL)
            question_type = "" if scope == SCOPE_ALL else scope
        else:
            question_type = self.current_type or ""
        try:
            record = self.session.build_history_record(
                self._bank_key, question_type, source=self.session.mode,
                set_name=self.set_name or "")
            progress_store.record_history(record)
            self.session.history_recorded = True
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------ 确认分发
    def _on_confirm_confirmed(self):
        action = self._confirm_action
        self._confirm_action = None
        if not action:
            return
        if action == "manual_submit":
            self._on_manual_submit_confirmed()
            return
        if not isinstance(action, tuple):
            return
        kind = action[0]
        if kind == "wrongbook_remove":
            self._do_wrongbook_remove(action[1])
        elif kind == "wrongbook_clear":
            self._do_wrongbook_clear()
        elif kind == "history_delete":
            self._do_history_delete(action[1])
        elif kind == "history_clear":
            self._do_history_clear()
        elif kind == "clear_progress":
            self._do_clear_progress()
