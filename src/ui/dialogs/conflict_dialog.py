"""冲突解决对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt


class ConflictDialog(QDialog):
    def __init__(self, skill_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同步冲突")
        self.setMinimumWidth(380)
        self.setModal(True)
        self.setStyleSheet(
            "QDialog { background: #252536; border: 1px solid #3a3a55;"
            "border-radius: 8px; }"
        )
        self._choice = "skip"
        self._apply_all = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        msg = QLabel(f"Skill '{skill_name}' 在目标位置已存在且内容不同。\n请选择处理方式：")
        msg.setStyleSheet("color: #cdd6f4; font-size: 13px;")
        layout.addWidget(msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        overwrite_btn = QPushButton("覆盖")
        overwrite_btn.setStyleSheet(
            "QPushButton { background: #74c7ec; color: #1e1e2e; border: none;"
            "border-radius: 4px; padding: 8px 18px; font-weight: 600; }"
            "QPushButton:hover { background: #89d4f5; }"
        )
        overwrite_btn.clicked.connect(lambda: self._set_choice("overwrite"))
        btn_layout.addWidget(overwrite_btn)

        keep_btn = QPushButton("保留双方")
        keep_btn.setStyleSheet(
            "QPushButton { background: #cba6f7; color: #1e1e2e; border: none;"
            "border-radius: 4px; padding: 8px 18px; font-weight: 600; }"
            "QPushButton:hover { background: #d6baf8; }"
        )
        keep_btn.clicked.connect(lambda: self._set_choice("keep_both"))
        btn_layout.addWidget(keep_btn)

        skip_btn = QPushButton("跳过")
        skip_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 8px 18px; color: #cdd6f4; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        skip_btn.clicked.connect(lambda: self._set_choice("skip"))
        btn_layout.addWidget(skip_btn)

        layout.addLayout(btn_layout)

        self._apply_check = QCheckBox("应用于所有后续冲突")
        self._apply_check.setStyleSheet("color: #6c7086; font-size: 11px;")
        self._apply_check.stateChanged.connect(
            lambda s: setattr(self, '_apply_all', s == Qt.Checked)
        )
        layout.addWidget(self._apply_check)

    def _set_choice(self, choice: str):
        self._choice = choice
        self.accept()

    @property
    def choice(self) -> str:
        return self._choice

    @property
    def apply_all(self) -> bool:
        return self._apply_all
