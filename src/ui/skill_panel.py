"""单个 Skill 面板：标题栏 + 工具 Tab + 图例 + SkillList"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal

from src.ui.skill_list_widget import SkillListWidget


class SkillPanel(QWidget):
    refresh_requested = Signal()
    tool_changed = Signal(str)
    selection_changed = Signal()
    device_changed = Signal(str)

    def __init__(self, title: str, show_device_selector: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._show_device_selector = show_device_selector
        self._current_tool = "codex"
        self._device_combo = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # header
        header = QHBoxLayout()
        header.setContentsMargins(12, 8, 12, 8)

        title_label = QLabel(self._title)
        title_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #cdd6f4;")
        header.addWidget(title_label)

        if self._show_device_selector:
            from PySide6.QtWidgets import QComboBox
            self._device_combo = QComboBox()
            self._device_combo.setFixedWidth(160)
            self._device_combo.addItem("未选择远程设备")
            self._device_combo.currentTextChanged.connect(
                self._on_device_selected
            )
            header.addWidget(self._device_combo)

        header.addStretch()

        refresh_btn = QPushButton("↻ 刷新")
        refresh_btn.setStyleSheet(
            "background: none; border: 1px solid #3a3a55; color: #a6adc8;"
            "padding: 2px 10px; border-radius: 3px; font-size: 11px;"
        )
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # tool tabs
        tab_layout = QHBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)

        tools = [("codex", "Codex"), ("claude", "Claude Code"), ("cc-switch", "CC-Switch")]
        self._tabs = {}
        for i, (tool_id, label) in enumerate(tools):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none;"
                "border-bottom: 2px solid transparent; padding: 6px 12px;"
                "font-size: 12px; color: #6c7086; }"
                "QPushButton:hover { color: #a6adc8; }"
                "QPushButton:checked { color: #89b4fa; border-bottom-color: #89b4fa; }"
            )
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tab_changed(t))
            self._tab_group.addButton(btn, i)
            self._tabs[tool_id] = btn
            tab_layout.addWidget(btn)
            if i == 0:
                btn.setChecked(True)

        tab_layout.addStretch()
        layout.addLayout(tab_layout)

        # tag legend
        legend = QHBoxLayout()
        legend.setContentsMargins(12, 4, 12, 4)
        legend.setSpacing(12)

        for color, text in [("#a6e3a1", "已同步"), ("#f9e2af", "仅本机"),
                             ("#fab387", "仅远程"), ("#f38ba8", "内容不同")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 8px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 10px; color: #6c7086;")
            legend.addWidget(dot)
            lbl.setContentsMargins(0, 0, 0, 0)
            legend.addWidget(lbl)

        legend.addStretch()
        layout.addLayout(legend)

        # skill list
        self.skill_list = SkillListWidget()
        self.skill_list.selection_changed.connect(self.selection_changed.emit)
        layout.addWidget(self.skill_list, stretch=1)

    def _on_tab_changed(self, tool: str):
        self._current_tool = tool
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._current_tool

    def display_skills(self, skills):
        """Display skills filtered by current tool tab."""
        filtered = [s for s in skills if s.tool == self._current_tool]
        self.skill_list.set_skills(filtered)

    def selected_skills(self):
        return self.skill_list.selected_skills()

    def set_devices(self, connections: list):
        """Populate device selector with connection names."""
        if not self._device_combo:
            return
        current = self._device_combo.currentText()
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        if not connections:
            self._device_combo.addItem("未选择远程设备")
        else:
            for conn in connections:
                self._device_combo.addItem(conn.name)
        # restore selection
        idx = self._device_combo.findText(current)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        self._device_combo.blockSignals(False)

    def select_device(self, name: str):
        """Select a device by name."""
        if not self._device_combo:
            return
        idx = self._device_combo.findText(name)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)

    def _on_device_selected(self, text: str):
        if text != "未选择远程设备":
            self.device_changed.emit(text)
