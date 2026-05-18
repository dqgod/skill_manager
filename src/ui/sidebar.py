"""左侧导航栏：全局 + 项目列表"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
)
from PySide6.QtCore import Qt, Signal


class NavItem(QPushButton):
    clicked_with_id = Signal(str)

    def __init__(self, item_id: str, text: str, badge_count: int = 0, parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self._active = False
        self._badge = badge_count
        self._base_text = text
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            "border-left: 3px solid transparent; padding: 6px 12px;"
            "text-align: left; color: #a6adc8; font-size: 12px; }"
            "QPushButton:hover { background-color: #2d2d44; color: #cdd6f4; }"
            "QPushButton[active=\"true\"] {"
            "background-color: #2d2d44; color: #89b4fa;"
            "border-left-color: #89b4fa; }"
        )
        self._build_text(text)
        self.clicked.connect(lambda: self.clicked_with_id.emit(self._item_id))

    def _build_text(self, text: str):
        if self._badge > 0:
            self.setText(f"  {text}  ({self._badge})")
        else:
            self.setText(f"  {text}")

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool):
        self._active = value
        self.setProperty("active", "true" if value else "false")
        self.style().polish(self)


class Sidebar(QWidget):
    view_changed = Signal(str)  # emits "global" or project_id
    add_project_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self._nav_items: dict[str, NavItem] = {}
        self._active_id: str = "global"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # header
        header = QHBoxLayout()
        header.setContentsMargins(12, 10, 12, 10)
        header_label = QLabel("Skill 视图")
        header_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #6c7086;"
            "text-transform: uppercase; letter-spacing: 1px;"
        )
        header.addWidget(header_label)
        header.addStretch()
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #3a3a55;"
            "color: #a6adc8; border-radius: 4px; font-size: 14px;"
            "font-weight: bold; }"
            "QPushButton:hover { background: #2d2d44; color: #cdd6f4; }"
        )
        add_btn.clicked.connect(self.add_project_requested.emit)
        header.addWidget(add_btn)
        layout.addLayout(header)

        # scrollable nav
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._nav_container = QWidget()
        self._nav_container.setStyleSheet("background: transparent;")
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(0)

        # global section
        global_label = QLabel("全局")
        global_label.setStyleSheet(
            "color: #6c7086; font-size: 11px; text-transform: uppercase;"
            "padding: 8px 12px 4px;"
        )
        self._nav_layout.addWidget(global_label)

        global_nav = NavItem("global", "全局 Skill")
        global_nav.active = True
        global_nav.clicked_with_id.connect(self._on_nav_clicked)
        self._nav_items["global"] = global_nav
        self._nav_layout.addWidget(global_nav)

        # projects section
        proj_label = QLabel("项目")
        proj_label.setStyleSheet(
            "color: #6c7086; font-size: 11px; text-transform: uppercase;"
            "padding: 12px 12px 4px; margin-top: 4px;"
        )
        proj_label.setObjectName("project-section-label")
        self._nav_layout.addWidget(proj_label)

        self._projects_start = self._nav_layout.count()
        self._nav_layout.addStretch()

        scroll.setWidget(self._nav_container)
        layout.addWidget(scroll, stretch=1)

        # footer - device status
        footer = QHBoxLayout()
        footer.setContentsMargins(12, 8, 12, 8)
        dot = QLabel("●")
        dot.setStyleSheet("color: #a6e3a1; font-size: 8px;")
        footer.addWidget(dot)

        status_label = QLabel("本机")
        status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        footer.addWidget(status_label)
        footer.addStretch()
        layout.addLayout(footer)

    def add_project_nav(self, project_id: str, name: str):
        """Add a project nav item (safe to call multiple times, deduplicates)."""
        if project_id in self._nav_items:
            return
        nav = NavItem(project_id, name)
        nav.clicked_with_id.connect(self._on_nav_clicked)
        self._nav_items[project_id] = nav
        # Insert before the stretch
        pos = self._nav_layout.count() - 1  # before stretch
        self._nav_layout.insertWidget(pos, nav)

    def remove_project_nav(self, project_id: str):
        if project_id not in self._nav_items:
            return
        nav = self._nav_items.pop(project_id)
        self._nav_layout.removeWidget(nav)
        nav.setParent(None)

    def update_badges(self, global_count: int, project_counts: dict[str, int]):
        """Update skill count badges. project_counts: {project_id: count}."""
        for item_id, count in [("global", global_count)] + list(project_counts.items()):
            nav = self._nav_items.get(item_id)
            if nav:
                nav._badge = count
                nav._build_text(nav._base_text)

    def _on_nav_clicked(self, item_id: str):
        self.set_active(item_id)
        self.view_changed.emit(item_id)

    def set_active(self, item_id: str):
        if self._active_id in self._nav_items:
            self._nav_items[self._active_id].active = False
        if item_id in self._nav_items:
            self._nav_items[item_id].active = True
        self._active_id = item_id

    @property
    def active_view(self) -> str:
        return self._active_id
