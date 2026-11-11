# -*- coding: utf-8 -*-
"""全屏弹层公共部件：遮罩 + 白色圆角卡片 + 可滚动列表。

Android 上 QMessageBox / QDialog 会另开窗口，触摸事件投递不到按钮上，
所以错题本、历史记录这些界面全部改成画在同一个 QWidget 里的弹层。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QListWidget, QWidget

BACKDROP = QColor(17, 24, 39, 140)
CARD_BG = QColor("#FFFFFF")
CARD_RADIUS = 16


class OverlayCard(QWidget):
    """白色圆角卡片背景（四角透出遮罩，视觉上就是圆角）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), CARD_RADIUS, CARD_RADIUS)
        painter.fillPath(path, CARD_BG)
        painter.end()
        super().paintEvent(event)


def make_record_list(parent=None) -> QListWidget:
    """统一样式的记录列表。

    滚动时整列表重绘（repaint）：Android 上只提交局部脏区会让行文字叠影。
    """
    lst = QListWidget(parent)
    lst.setObjectName("recordList")
    lst.setWordWrap(True)
    lst.setUniformItemSizes(False)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    lst.setSelectionMode(QListWidget.SingleSelection)
    lst.setFocusPolicy(Qt.NoFocus)
    lst.verticalScrollBar().valueChanged.connect(
        lambda _value, widget=lst: widget.viewport().repaint())
    return lst
