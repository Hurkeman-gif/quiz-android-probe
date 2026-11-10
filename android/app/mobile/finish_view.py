# -*- coding: utf-8 -*-
"""答题完成页：显示总题数/已答数/答对数/答错数/正确率，提供两个出口按钮。

与 Windows 版完成页口径一致：
- 正确率 = 答对数 / 总题数（手动提交时未答题按错误计入分母）；
- 答错数含「未答按错误计入」的部分，并单独注明数量。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

TITLE_TEXT = "练习完成！"


class FinishView(QWidget):
    """完成页（只读展示 + 两个按钮信号）。"""

    restartRequested = Signal()   # 重新开始：清空本题型进度
    reviewRequested = Signal()    # 返回第一题：保留答题痕迹

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("finishView")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)
        root.addStretch(1)

        self.title_label = QLabel(TITLE_TEXT)
        self.title_label.setObjectName("finishTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title_label)
        root.addSpacing(18)

        self.total_label = self._make_stat()
        self.answered_label = self._make_stat()
        self.correct_label = self._make_stat()
        self.wrong_label = self._make_stat()
        self.accuracy_label = self._make_stat(strong=True)
        for label in (self.total_label, self.answered_label,
                      self.correct_label, self.wrong_label):
            root.addWidget(label)
            root.addSpacing(6)
        root.addSpacing(4)
        root.addWidget(self.accuracy_label)
        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.restart_button = QPushButton("重新开始")
        self.restart_button.setObjectName("restartBtn")
        self.restart_button.setMinimumHeight(50)
        self.restart_button.setFocusPolicy(Qt.NoFocus)
        self.restart_button.setCursor(Qt.PointingHandCursor)
        self.restart_button.clicked.connect(self.restartRequested.emit)
        self.review_button = QPushButton("返回第一题")
        self.review_button.setObjectName("reviewBtn")
        self.review_button.setMinimumHeight(50)
        self.review_button.setFocusPolicy(Qt.NoFocus)
        self.review_button.setCursor(Qt.PointingHandCursor)
        self.review_button.clicked.connect(self.reviewRequested.emit)
        buttons.addWidget(self.restart_button, 1)
        buttons.addWidget(self.review_button, 1)
        root.addLayout(buttons)

    def _make_stat(self, strong=False):
        label = QLabel("")
        label.setObjectName("finishStatStrong" if strong else "finishStat")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Minimum)
        return label

    def set_stats(self, stats):
        """按 session.get_finish_stats() 的结果刷新文案。"""
        total = int(stats.get("total_count") or 0)
        answered = int(stats.get("answered_count") or 0)
        correct = int(stats.get("correct_count") or 0)
        wrong = int(stats.get("wrong_display_count") or 0)
        forced = int(stats.get("forced_unanswered_count") or 0)
        self.total_label.setText(f"总题数：{total} 题")
        self.answered_label.setText(f"已答数：{answered} 题")
        self.correct_label.setText(f"答对：{correct} 题")
        if forced:
            self.wrong_label.setText(
                f"答错：{wrong} 题（未答按错误计入 {forced} 题）")
        else:
            self.wrong_label.setText(f"答错：{wrong} 题")
        self.accuracy_label.setText(
            f"正确率：{stats.get('accuracy_text') or '--'}")
