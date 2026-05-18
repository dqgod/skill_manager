"""同步进度对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal


class SyncProgressDialog(QDialog):
    cancelled = Signal()
    conflict_response = Signal(str)  # "overwrite" | "skip" | "keep_both"

    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在同步...")
        self.setMinimumSize(440, 300)
        self.setModal(True)
        self.setStyleSheet(
            "QDialog { background: #252536; border: 1px solid #3a3a55;"
            "border-radius: 8px; }"
        )
        self._total = total
        self._cancelled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel(f"正在同步...  共 {self._total} 个任务")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #cdd6f4;")
        layout.addWidget(title)

        # progress items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._item_container = QWidget()
        self._item_layout = QVBoxLayout(self._item_container)
        self._item_layout.setSpacing(4)
        self._item_layout.addStretch()
        scroll.setWidget(self._item_container)
        layout.addWidget(scroll, stretch=1)

        # progress bar
        self._bar = QProgressBar()
        self._bar.setMaximum(self._total)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._status_label = QLabel(f"进度: 0/{self._total}")
        self._status_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        # cancel button
        cancel = QPushButton("取消")
        cancel.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 20px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        cancel.clicked.connect(self._on_cancel)
        layout.addWidget(cancel, alignment=Qt.AlignCenter)

    def add_item(self, skill_name: str):
        """Add a progress row. Returns index."""
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)

        icon = QLabel("⬤")
        icon.setStyleSheet("color: #6c7086; font-size: 10px;")
        icon.setObjectName(f"icon-{skill_name}")
        rl.addWidget(icon)

        name = QLabel(skill_name)
        name.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        rl.addWidget(name, stretch=1)

        status = QLabel("等待")
        status.setStyleSheet("color: #6c7086; font-size: 10px;")
        status.setObjectName(f"status-{skill_name}")
        rl.addWidget(status)

        idx = self._item_layout.count() - 1  # before stretch
        self._item_layout.insertWidget(idx, row)

    def update_item(self, skill_name: str, status: str):
        """Update status: copying, success, failed, skipped."""
        icon = self.findChild(QLabel, f"icon-{skill_name}")
        st = self.findChild(QLabel, f"status-{skill_name}")
        if st:
            st.setText({"copying": "传输中...", "success": "完成",
                        "failed": "失败", "skipped": "跳过"}.get(status, status))
        colors = {"copying": "#74c7ec", "success": "#a6e3a1",
                  "failed": "#f38ba8", "skipped": "#f9e2af"}
        if icon:
            icon.setStyleSheet(f"color: {colors.get(status, '#6c7086')}; font-size: 10px;")
        if st:
            st.setStyleSheet(f"color: {colors.get(status, '#6c7086')}; font-size: 10px;")

    def set_progress(self, current: int):
        self._bar.setValue(current)
        self._status_label.setText(f"进度: {current}/{self._total}")

    def _on_cancel(self):
        self._cancelled = True
        self.cancelled.emit()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
