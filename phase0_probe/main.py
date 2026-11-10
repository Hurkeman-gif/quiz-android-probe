#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 0 探针：验证 PySide6 Qt Widgets 在 Android 上能渲染与交互。

不含数据库、网络、资源文件、第三方依赖；硬编码一道 "1+1=?" 的假题。
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CORRECT_KEY = "B"  # 正确答案硬编码为 B（1+1=2）

OPTION_LABELS = [
    ("A", "A. 1"),
    ("B", "B. 2"),
    ("C", "C. 3"),
    ("D", "D. 4"),
]

_GREEN = "QPushButton { background-color: #2e7d32; color: white; }"
_RED = "QPushButton { background-color: #c62828; color: white; }"
_NEUTRAL = "QPushButton { background-color: #eeeeee; color: black; }"


class ProbeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase0 Probe")
        self.question_no = 1
        self.answered = False
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.no_label = QLabel()
        self.no_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.no_label)

        self.stem_label = QLabel("题干：1+1=？")
        self.stem_label.setWordWrap(True)
        self.stem_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(self.stem_label)

        self.option_buttons = []
        for key, text in OPTION_LABELS:
            btn = QPushButton(text)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda checked=False, k=key: self._on_option(k))
            layout.addWidget(btn)
            self.option_buttons.append((key, btn))

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.next_button = QPushButton("下一题")
        self.next_button.clicked.connect(self._on_next)
        layout.addWidget(self.next_button)

    def _refresh(self):
        self.no_label.setText("第 %d 题" % self.question_no)

    def _on_option(self, key):
        if self.answered:
            return
        self.answered = True

        for k, btn in self.option_buttons:
            btn.setEnabled(False)
            if k == CORRECT_KEY:
                btn.setStyleSheet(_GREEN)   # 正确答案恒显示绿色
            elif k == key:
                btn.setStyleSheet(_RED)     # 用户选中的错误选项显示红色
            else:
                btn.setStyleSheet(_NEUTRAL)

        if key == CORRECT_KEY:
            self.result_label.setText("回答正确")
        else:
            self.result_label.setText("回答错误")

    def _on_next(self):
        for _, btn in self.option_buttons:
            btn.setEnabled(True)
            btn.setStyleSheet("")
        self.result_label.setText("")
        self.answered = False
        self.question_no += 1
        self._refresh()


def main():
    app = QApplication(sys.argv)
    window = ProbeWindow()
    window.resize(360, 640)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
