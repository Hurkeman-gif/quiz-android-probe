#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 第二步：移动端最小答题界面入口。

启动流程：
1. ensure_bank_from_assets() 把打包资产里的 quiz.db 复制到应用私有目录并校验；
2. MobileMainWindow 只读打开题库，取出第一个套题的题目；
3. 答题判定与统计调用现有 app.session，不保存进度、不写错题本。
异常时显示具体原因与堆栈，不静默退出。
"""
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ErrorWindow(QWidget):
    """启动失败兜底窗口：显示原因与堆栈，方便真机排查。"""

    def __init__(self, title: str, detail: str):
        super().__init__()
        self.setWindowTitle("启动失败")
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        box = QVBoxLayout(body)
        head = QLabel(title)
        head.setWordWrap(True)
        head.setStyleSheet("color: #B91C1C; font-size: 16pt; font-weight: 700;")
        box.addWidget(head)
        text = QLabel(detail)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(text)
        box.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)


APP_DISPLAY_NAME = "答题练习软件"


def keep_screen_on():
    """Android：答题过程中保持屏幕常亮，避免自动息屏打断练习。

    非 Android 平台（或 jnius 不可用）时静默跳过。
    """
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        layout_params = autoclass("android.view.WindowManager$LayoutParams")
        activity.getWindow().addFlags(layout_params.FLAG_KEEP_SCREEN_ON)
    except Exception:
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName("AnswerTraining")
    app.setOrganizationDomain("answertraining.com")
    keep_screen_on()
    try:
        from app.mobile.main_window import MobileMainWindow

        window = MobileMainWindow()
    except Exception:
        window = ErrorWindow("启动失败", traceback.format_exc())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
