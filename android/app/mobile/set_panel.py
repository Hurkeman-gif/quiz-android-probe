# -*- coding: utf-8 -*-
"""切换套题 / 数据备份 两个弹层。

套题（set_name）是桌面版已有的字段：练习进度按 (题库, 题型, 套题) 保存，
错题本与答题记录同样带套题标记，所以切换套题后彼此互不影响。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .overlay import BACKDROP, OverlayCard
from .record_list import RecordList


class SetPickerPanel(QWidget):
    """套题列表弹层。setChosen 传套题名，空字符串表示「全部套题」。"""

    setChosen = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 96, 14, 52)
        outer.setSpacing(0)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("切换套题")
        title.setObjectName("panelTitle")
        self.count_label = QLabel("")
        self.count_label.setObjectName("panelSub")
        header.addWidget(title)
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelClose")
        self.close_button.setMinimumHeight(36)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_button)
        lay.addLayout(header)

        hint = QLabel("点选要练习的套题；进度、错题与记录按套题分开保存。")
        hint.setObjectName("panelSub")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.list = RecordList(self.card)
        self.list.itemActivated.connect(self._on_row_activated)
        lay.addWidget(self.list, 1)

        outer.addWidget(self.card)

    # ------------------------------------------------------------------ API
    def set_rows(self, items, current=None):
        """items: [{"name": str, "count": int}]；current 为当前套题名（None/""=全部）。"""
        self._rows = list(items or [])
        total = sum(int(it.get("count") or 0) for it in self._rows)
        self.count_label.setText("共 %d 套" % len(self._rows))
        current_key = current or ""
        rows = [{
            "lines": [
                "全部套题" + ("（当前）" if not current_key else ""),
                "混合全部套题 · %d 题" % total,
            ],
            "payload": "",
        }]
        for item in self._rows:
            name = str(item.get("name") or "")
            if not name:
                continue
            active = name == current_key
            rows.append({
                "lines": [
                    name + ("（当前）" if active else ""),
                    "%d 题 · 单击切换" % int(item.get("count") or 0),
                ],
                "payload": name,
            })
        self.list.set_rows(rows)

    def selected_set(self):
        payload = self.list.selected_payload()
        return "" if payload is None else str(payload)

    # ------------------------------------------------------------- 事件处理
    def _on_row_activated(self, index):
        payload = self.list.selected_payload()
        if payload is None:
            return
        self.setChosen.emit(str(payload))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)


class BackupPanel(QWidget):
    """数据备份弹层：导出 JSON 到固定目录 / 从备份列表导入 / 刷新列表。

    不使用系统文件选择器（Qt for Android 上会导致主线程死锁、界面假死），
    备份文件统一放在 Android/data/<包名>/files/backup/ 下。
    """

    exportRequested = Signal()
    importRequested = Signal(str)
    refreshRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMinimumSize(1, 1)
        self.hide()
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 96, 14, 52)
        outer.setSpacing(0)

        self.card = OverlayCard(self)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("数据备份")
        title.setObjectName("panelTitle")
        self.count_label = QLabel("")
        self.count_label.setObjectName("panelSub")
        header.addWidget(title)
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("panelClose")
        self.close_button.setMinimumHeight(36)
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_button)
        lay.addLayout(header)

        self.dir_label = QLabel("")
        self.dir_label.setObjectName("panelSub")
        self.dir_label.setWordWrap(True)
        lay.addWidget(self.dir_label)

        self.list = RecordList(self.card)
        lay.addWidget(self.list, 1)

        self.empty_label = QLabel("暂无备份文件\n点「导出数据」生成一个 JSON 备份")
        self.empty_label.setObjectName("panelEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        lay.addWidget(self.empty_label, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("backupStatus")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)

        self.hint_label = QLabel(
            "导入其它备份：先把 .json 文件拷贝到上面的备份目录，再点「刷新」")
        self.hint_label.setObjectName("panelSub")
        self.hint_label.setWordWrap(True)
        lay.addWidget(self.hint_label)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.export_button = QPushButton("导出数据")
        self.export_button.setObjectName("panelPrimary")
        self.export_button.setMinimumHeight(48)
        self.export_button.setFocusPolicy(Qt.NoFocus)
        self.export_button.clicked.connect(self.exportRequested.emit)
        self.import_button = QPushButton("导入选中")
        self.import_button.setObjectName("panelGhost")
        self.import_button.setMinimumHeight(48)
        self.import_button.setFocusPolicy(Qt.NoFocus)
        self.import_button.clicked.connect(self._on_import)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("panelGhost")
        self.refresh_button.setMinimumHeight(48)
        self.refresh_button.setFocusPolicy(Qt.NoFocus)
        self.refresh_button.clicked.connect(self._on_refresh)
        row1.addWidget(self.export_button, 2)
        row1.addWidget(self.import_button, 1)
        row1.addWidget(self.refresh_button, 1)
        lay.addLayout(row1)

        outer.addWidget(self.card)

    # ------------------------------------------------------------------ API
    def set_backups(self, directory, items, message=""):
        self._rows = list(items or [])
        self.dir_label.setText("备份目录：" + (directory or "（不可用）"))
        self.count_label.setText("共 %d 个备份" % len(self._rows))
        rows = []
        for item in self._rows:
            size_kb = max(1, int(round(int(item.get("size") or 0) / 1024.0)))
            rows.append({
                "lines": [
                    str(item.get("name") or ""),
                    "%s · %d KB" % (item.get("mtime_text") or "", size_kb),
                ],
                "payload": str(item.get("path") or ""),
            })
        has_rows = bool(rows)
        self.list.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.list.set_rows(rows)
        self.import_button.setEnabled(has_rows)
        if message:
            self.show_result(message)

    def selected_path(self):
        payload = self.list.selected_payload()
        return "" if payload is None else str(payload)

    def show_result(self, text, ok=True):
        self.status_label.setProperty("state", "ok" if ok else "error")
        self.status_label.setText(text)
        style = self.status_label.style()
        if style is not None:
            style.unpolish(self.status_label)
            style.polish(self.status_label)

    # ------------------------------------------------------------- 事件处理
    def _on_import(self):
        path = self.selected_path()
        if path:
            self.importRequested.emit(path)

    def _on_refresh(self):
        self.refreshRequested.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKDROP)
        painter.end()

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.closeRequested.emit()
        super().mousePressEvent(event)
