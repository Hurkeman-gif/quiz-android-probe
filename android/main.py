#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 第一步：题库加载验证（最小 Android 入口）。

只验证数据层：
1. 从打包资产复制 quiz.db 到 Android 私有目录并做 SHA256 校验；
2. 用现有 database 模块以只读方式打开；
3. 读出第一种题型的前 3 道题并显示。
不做答题交互、不做颜色判定、不改移动端 UI。
"""
import os
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

from app import database, models, platform


class VerifyWindow(QWidget):
    """极简验证窗口：显示题库路径、总数、前 3 题题干与选项数。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("题库加载验证")
        self.resize(500, 760)
        self._build_ui()
        self._run_verification()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body = QWidget()
        self.box = QVBoxLayout(body)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll)

    def _add(self, text, bold=False, color=None):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        if color:
            label.setStyleSheet(f"color: {color};")
        self.box.addWidget(label)

    def _run_verification(self):
        try:
            bank_path = platform.ensure_bank_from_assets()
            info = database.open_bank(bank_path)
            total = database.count_questions()
            size = os.path.getsize(bank_path)
            sha = platform.sha256_file(bank_path)

            self._add("题库加载成功", bold=True, color="#2e7d32")
            self._add(f"题库路径：{bank_path}")
            self._add(f"题库字节数：{size}")
            self._add(f"题库 SHA256：{sha}")
            self._add(f"题目总数：{total}")
            self._add("")

            questions = database.list_questions()
            first_type = questions[0]["type"] if questions else "single"
            show = questions[:3]
            self._add(
                f"第一种题型：{models.TYPE_LABELS.get(first_type, first_type)}，"
                f"前 {len(show)} 题：", bold=True)
            for q in show:
                label = models.TYPE_LABELS.get(q["type"], q["type"])
                n_opts = len(q.get("options") or [])
                self._add(f"[{q['id']}]（{label}）{q['stem']}")
                self._add(
                    f"    选项数：{n_opts}，答案：{'、'.join(q.get('answer') or [])}")
        except Exception as exc:
            self._add("题库加载失败", bold=True, color="#c62828")
            self._add(str(exc))
            self._add(traceback.format_exc())


def main():
    app = QApplication(sys.argv)
    window = VerifyWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
