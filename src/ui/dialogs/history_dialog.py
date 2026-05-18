"""同步操作历史对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
)
from PySide6.QtCore import Qt

from src.models.sync_history import SyncHistoryModel


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("操作历史")
        self.setMinimumSize(800, 500)
        self.setStyleSheet(
            "QDialog { background: #252536; border: 1px solid #3a3a55;"
            "border-radius: 8px; }"
        )
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("同步操作历史")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #cdd6f4;")
        layout.addWidget(title)

        # filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel("设备:"))
        self._device_filter = QComboBox()
        self._device_filter.addItem("全部")
        self._device_filter.currentTextChanged.connect(self._load_data)
        filter_row.addWidget(self._device_filter)

        filter_row.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 4px 12px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        refresh_btn.clicked.connect(self._load_data)
        filter_row.addWidget(refresh_btn)

        layout.addLayout(filter_row)

        # table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "时间", "方向", "Skill", "源设备", "目标设备",
            "工具", "状态"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setStyleSheet(
            "QTableWidget { background: #1e1e2e; border: 1px solid #3a3a55;"
            "border-radius: 4px; gridline-color: #3a3a55; color: #cdd6f4; }"
            "QTableWidget::item { padding: 4px 8px; }"
            "QHeaderView::section { background: #2d2d44; border: 1px solid"
            "#3a3a55; padding: 4px 8px; color: #a6adc8; font-weight: 600; }"
        )
        layout.addWidget(self._table, stretch=1)

        # close
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 20px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def _load_data(self):
        device = self._device_filter.currentText()
        if device == "全部":
            device = None

        records = SyncHistoryModel.query(limit=200)

        # update device filter options
        devices = set()
        for r in records:
            devices.add(r.source_device)
            devices.add(r.target_device)
        current = self._device_filter.currentText()
        self._device_filter.blockSignals(True)
        self._device_filter.clear()
        self._device_filter.addItem("全部")
        for d in sorted(devices):
            self._device_filter.addItem(d)
        idx = self._device_filter.findText(current)
        self._device_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._device_filter.blockSignals(False)

        # filter
        if device:
            records = [r for r in records
                       if r.source_device == device or r.target_device == device]

        self._table.setRowCount(len(records))

        dir_map = {"push": "推送", "pull": "拉取"}
        status_map = {"success": "成功", "failed": "失败", "skipped": "跳过"}
        status_colors = {"success": "#a6e3a1", "failed": "#f38ba8",
                         "skipped": "#f9e2af"}

        for i, r in enumerate(records):
            self._table.setItem(i, 0, QTableWidgetItem(r.timestamp))
            self._table.setItem(i, 1, QTableWidgetItem(
                dir_map.get(r.direction, r.direction)))
            self._table.setItem(i, 2, QTableWidgetItem(r.skill_name))
            self._table.setItem(i, 3, QTableWidgetItem(r.source_device))
            self._table.setItem(i, 4, QTableWidgetItem(r.target_device))
            self._table.setItem(i, 5, QTableWidgetItem(r.target_tool))

            status_text = status_map.get(r.status, r.status)
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(
                Qt.GlobalColor.red if r.status == "failed" else
                Qt.GlobalColor.darkYellow if r.status == "skipped" else
                Qt.GlobalColor.green
            )
            self._table.setItem(i, 6, status_item)
