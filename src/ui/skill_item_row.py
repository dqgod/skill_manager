"""单个 skill 行组件"""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QMenu, QApplication
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication

from src.utils.fs import reveal_in_file_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SkillItemRow(QFrame):
    clicked = Signal()

    def __init__(self, skill_info, parent=None):
        super().__init__(parent)
        self.skill_info = skill_info
        self._selected = False
        self._setup_ui()
        # Right-click context menu (PR-4).
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)

    def _setup_ui(self):
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "SkillItemRow { border-left: 3px solid transparent; }"
            "SkillItemRow:hover { background: #252536; }"
            "SkillItemRow[selected=\"true\"] { background: #2d2d44; border-left-color: #74c7ec; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # checkbox icon
        self._check = QLabel()
        self._check.setFixedSize(14, 14)
        self._check.setStyleSheet(
            "border: 1.5px solid #3a3a55; border-radius: 3px; font-size: 10px;"
            "color: transparent;"
        )
        self._check.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._check)

        # tool icon
        icons = {"codex": "⌚", "claude": "⚙", "cc-switch": "☰"}
        icon = QLabel(icons.get(self.skill_info.tool, "📄"))
        icon.setFixedWidth(20)
        icon.setStyleSheet("font-size: 14px;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        # name + meta
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)

        name_label = QLabel(self.skill_info.name)
        name_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #cdd6f4;")
        name_label.setMaximumHeight(18)
        name_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        info_layout.addWidget(name_label)

        meta_label = QLabel(
            f"{self._format_size(self.skill_info.size)} · {self.skill_info.modified_at}"
        )
        meta_label.setStyleSheet("font-size: 10px; color: #6c7086;")
        meta_label.setMaximumHeight(14)
        meta_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        info_layout.addWidget(meta_label)

        layout.addLayout(info_layout, stretch=1)

        # status tag
        self._tag = QLabel()
        self._update_tag("")  # empty initially, set by parent
        layout.addWidget(self._tag)

    def _update_tag(self, status: str):
        colors = {
            "synced": ("#a6e3a1", "已同步"),
            "local-only": ("#f9e2af", "仅本机"),
            "remote-only": ("#fab387", "仅远程"),
            "conflict": ("#f38ba8", "内容不同"),
        }
        if status in colors:
            color, text = colors[status]
            self._tag.setStyleSheet(
                f"font-size: 9px; padding: 0px 6px; border-radius: 3px;"
                f"background: #2d2d44; color: {color};"
            )
            self._tag.setText(text)
        else:
            self._tag.setText("")

    def set_status_tag(self, status: str):
        self._update_tag(status)

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool):
        self._selected = value
        if value:
            self.setProperty("selected", "true")
            self._check.setStyleSheet(
                "background: #74c7ec; border-color: #74c7ec; border-radius: 3px;"
                "font-size: 10px; color: #1e1e2e;"
            )
            self._check.setText("✓")
        else:
            self.setProperty("selected", "false")
            self._check.setStyleSheet(
                "border: 1.5px solid #3a3a55; border-radius: 3px;"
                "font-size: 10px; color: transparent;"
            )
            self._check.setText("")
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        # Only treat left-click as a selection toggle; right-click should
        # purely open the context menu without flipping selection.
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.0f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"

    # ---- Context menu (PR-4) ----

    def _open_context_menu(self, pos):
        """Build and pop up the per-row context menu.

        Local skills get an extra "Reveal in file manager" entry; remote
        skills only get the copy-* actions because we cannot open a remote
        path locally.
        """
        menu = QMenu(self)
        is_local = getattr(self.skill_info, "device_type", "local") == "local"

        if is_local:
            act_open = QAction("在文件管理器中显示", self)
            act_open.triggered.connect(self._reveal_in_finder)
            menu.addAction(act_open)
            menu.addSeparator()

        act_copy_path = QAction(
            "复制路径" if is_local else "复制远端路径", self,
        )
        act_copy_path.triggered.connect(self._copy_path)
        menu.addAction(act_copy_path)

        act_copy_name = QAction("复制名称", self)
        act_copy_name.triggered.connect(self._copy_name)
        menu.addAction(act_copy_name)

        menu.exec(self.mapToGlobal(pos))

    def _reveal_in_finder(self):
        ok = reveal_in_file_manager(self.skill_info.path)
        if not ok:
            logger.info("reveal failed for %s", self.skill_info.path)

    def _copy_path(self):
        QGuiApplication.clipboard().setText(self.skill_info.path)

    def _copy_name(self):
        QGuiApplication.clipboard().setText(self.skill_info.name)
