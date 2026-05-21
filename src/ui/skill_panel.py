"""单个 Skill 面板：标题栏 + Source 选择器 + 工具 Tab + 图例 + SkillList"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal

from src.models.skill_source import SkillSource, local_global
from src.ui.skill_list_widget import SkillListWidget
from src.ui.widgets.source_selector import SourceSelector
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Connection status colors used by remote source indicator.
STATUS_COLORS = {
    "online": ("#a6e3a1", "在线"),
    "offline": ("#f38ba8", "离线"),
    "checking": ("#f9e2af", "检测中"),
    "unknown": ("#6c7086", "未连接"),
    "local": ("#a6e3a1", "本机"),
}


class SkillPanel(QWidget):
    refresh_requested = Signal()
    tool_changed = Signal(str)
    selection_changed = Signal()
    source_changed = Signal(object)  # emits SkillSource

    def __init__(self, title: str, source: SkillSource | None = None, parent=None):
        super().__init__(parent)
        self._title = title
        self._source: SkillSource = source or local_global()
        self._current_tool = "codex"
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

        # Source selector (replaces the old device combo).
        # Always visible: every panel can be either local or remote.
        self._source_selector = SourceSelector(self._source)
        self._source_selector.source_changed.connect(self._on_source_changed_inner)
        header.addWidget(self._source_selector)

        # Connection status indicator dot + label.
        # For a local source it's just a静态 "本机/已就绪" 标签；
        # for a remote source it轮询健康检查结果。
        self._status_dot = QLabel("●")
        self._status_text = QLabel()
        header.addWidget(self._status_dot)
        header.addWidget(self._status_text)
        # 初始状态：根据 source 类型决定
        self._sync_status_for_source()

        header.addStretch()

        refresh_btn = QPushButton("↻ 刷新")
        refresh_btn.setStyleSheet(
            "background: none; border: 1px solid #3a3a55; color: #a6adc8;"
            "padding: 2px 10px; border-radius: 3px; font-size: 11px;"
        )
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._refresh_btn = refresh_btn
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
            btn.clicked.connect(lambda checked=False, t=tool_id: self._on_tab_changed(t))
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
        logger.info("[TabSwitch] SkillPanel(%s) tab clicked: %s", self._title, tool)
        self._current_tool = tool
        self.tool_changed.emit(tool)
        logger.debug("[TabSwitch] tool_changed signal emitted for: %s", tool)

    @property
    def current_tool(self) -> str:
        return self._current_tool

    def display_skills(self, skills):
        """Display skills filtered by current tool tab."""
        filtered = [s for s in skills if s.tool == self._current_tool]
        logger.info("[DisplaySkills] panel=%s current_tool=%s total_skills=%d filtered=%d",
                     self._title, self._current_tool, len(skills), len(filtered))
        self.skill_list.set_skills(filtered)

    def selected_skills(self):
        return self.skill_list.selected_skills()

    # ---- Source 相关 ----

    @property
    def source(self) -> SkillSource:
        return self._source

    def set_source(self, source: SkillSource):
        """以编程方式更新当前 source（不触发 source_changed 信号）。"""
        self._source = source
        self._source_selector.set_source(source, emit=False)
        self._sync_status_for_source()

    def set_source_options(self, connections, projects):
        """供主窗口调用：把当前 connections/projects 喂给选择器菜单。"""
        self._source_selector.set_options(connections, projects)

    def _on_source_changed_inner(self, src: SkillSource):
        """SourceSelector 用户操作变更 → 同步本地 _source 并对外广播。"""
        self._source = src
        self._sync_status_for_source()
        self.source_changed.emit(src)

    def _sync_status_for_source(self):
        """根据当前 source 重置状态点：本机就直接绿；远程则置 unknown 等待健康检查。"""
        if self._source.is_local:
            self.set_connection_status("local", "本机始终在线")
        else:
            self.set_connection_status("unknown")

    # ---- Connection status indicator ----

    def set_connection_status(self, status: str, detail: str = ""):
        """Update the colored status dot + label.

        status: 'online' | 'offline' | 'checking' | 'unknown' | 'local'
        detail: optional tooltip/extended message (used for tooltip).
        """
        color, text = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        if hasattr(self, "_status_dot"):
            self._status_dot.setStyleSheet(
                f"color: {color}; font-size: 12px; padding: 0px 2px 0px 6px;"
            )
        if hasattr(self, "_status_text"):
            self._status_text.setStyleSheet(
                f"color: {color}; font-size: 11px;"
            )
            self._status_text.setText(text)
            self._status_text.setToolTip(detail or text)
            if hasattr(self, "_status_dot"):
                self._status_dot.setToolTip(detail or text)
        # Disable refresh when offline so users don't queue doomed scans.
        if hasattr(self, "_refresh_btn"):
            self._refresh_btn.setEnabled(status != "offline")
            if status == "offline":
                self._refresh_btn.setToolTip(
                    "远程不可达，请先在「连接管理」中检查这台机器"
                )
            else:
                self._refresh_btn.setToolTip("")
