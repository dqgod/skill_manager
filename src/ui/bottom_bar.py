"""底部操作栏：同步方向、层级、工具复选框、同步按钮"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QCheckBox, QLabel, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, Signal

from src.config import (
    SYNC_DIRECTION_PUSH, SYNC_DIRECTION_PULL,
    SYNC_LEVEL_GLOBAL, SYNC_LEVEL_TO_PROJECT,
    SYNC_LEVEL_TO_GLOBAL, SYNC_LEVEL_PROJECT,
    ALL_TOOLS_STR,
)


class BottomBar(QWidget):
    sync_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self._sync_direction = SYNC_DIRECTION_PUSH
        self._sync_level = SYNC_LEVEL_GLOBAL
        self._selected_tools: set[str] = set(ALL_TOOLS_STR)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # direction
        dir_group = QButtonGroup(self)
        dir_group.setExclusive(True)
        for i, (key, label) in enumerate([
            (SYNC_DIRECTION_PUSH, "→ 推送选中"),
            (SYNC_DIRECTION_PULL, "← 拉取选中"),
        ]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._btn_style("sync-dir", "#89b4fa"))
            btn.clicked.connect(lambda checked, k=key: setattr(self, '_sync_direction', k))
            dir_group.addButton(btn, i)
            if i == 0:
                btn.setChecked(True)
            layout.addWidget(btn)

        layout.addWidget(self._divider())

        # sync level
        lvl_group = QButtonGroup(self)
        lvl_group.setExclusive(True)
        levels = [
            (SYNC_LEVEL_GLOBAL, "全局↔全局"),
            (SYNC_LEVEL_TO_PROJECT, "全局→项目"),
            (SYNC_LEVEL_TO_GLOBAL, "项目→全局"),
            (SYNC_LEVEL_PROJECT, "项目↔项目"),
        ]
        for i, (key, label) in enumerate(levels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._btn_style("sync-level", "#cba6f7", 10))
            btn.clicked.connect(lambda checked, k=key: setattr(self, '_sync_level', k))
            lvl_group.addButton(btn, i)
            if i == 0:
                btn.setChecked(True)
            layout.addWidget(btn)

        layout.addWidget(self._divider())

        # tool checkboxes
        self._tool_checks: dict[str, QCheckBox] = {}
        for tool in ALL_TOOLS_STR:
            cb = QCheckBox(tool.capitalize() if tool != "cc-switch" else "CC-Switch")
            cb.setChecked(True)
            cb.setStyleSheet("color: #a6adc8; font-size: 11px; spacing: 4px;")
            cb.stateChanged.connect(self._on_tool_changed)
            self._tool_checks[tool] = cb
            layout.addWidget(cb)

        layout.addStretch()

        # selection count
        self._count_label = QLabel("已选择 0 个 skill")
        self._count_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(self._count_label)

        # sync button
        sync_btn = QPushButton("★ 开始同步")
        sync_btn.setStyleSheet(
            "QPushButton { background: #74c7ec; color: #1e1e2e; border: none;"
            "border-radius: 4px; padding: 7px 20px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #89d4f5; }"
        )
        sync_btn.clicked.connect(self.sync_requested.emit)
        layout.addWidget(sync_btn)

    @staticmethod
    def _btn_style(cls: str, active_color: str, font_size: int = 12) -> str:
        return (
            f"QPushButton {{ background: #2d2d44; border: 1px solid #3a3a55;"
            f"border-radius: 4px; padding: 6px 12px; color: #cdd6f4; font-size: {font_size}px; }}"
            f"QPushButton:hover {{ background: #3a3a55; }}"
            f"QPushButton:checked {{ background: {active_color}; color: #1e1e2e;"
            f"border-color: {active_color}; }}"
        )

    @staticmethod
    def _divider() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("background: #3a3a55; max-width: 1px; min-height: 24px;")
        return f

    def _on_tool_changed(self):
        self._selected_tools = {
            t for t, cb in self._tool_checks.items() if cb.isChecked()
        }

    def update_selection_count(self, count: int):
        self._count_label.setText(f"已选择 {count} 个 skill")

    @property
    def sync_direction(self) -> str:
        return self._sync_direction

    @property
    def sync_level(self) -> str:
        return self._sync_level

    @property
    def selected_tools(self) -> list[str]:
        return [t for t in ALL_TOOLS_STR if self._tool_checks[t].isChecked()]
