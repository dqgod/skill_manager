"""Skill 列表滚动区域"""

from PySide6.QtWidgets import (
    QScrollArea, QVBoxLayout, QWidget, QLabel, QMenu, QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication

from src.ui.skill_item_row import SkillItemRow
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SkillListWidget(QScrollArea):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._rows: list[SkillItemRow] = []

        # Blank-area context menu: only "Copy" + "Select all".
        # Hovering on a row hits SkillItemRow's own menu first because the
        # row's customContextMenuRequested fires before this one bubbles.
        self._container.setContextMenuPolicy(Qt.CustomContextMenu)
        self._container.customContextMenuRequested.connect(
            self._on_blank_context_menu
        )

    def set_skills(self, skills):
        """Replace all rows with new skill list."""
        logger.info("[SetSkills] rendering %d rows", len(skills))
        # clear existing
        for row in self._rows:
            row.setParent(None)
        self._rows.clear()

        # remove all items from layout
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not skills:
            empty = QLabel("暂无 skill")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #6c7086; font-size: 12px; padding: 40px;")
            self._layout.addWidget(empty)
        else:
            for s in skills:
                row = SkillItemRow(s)
                row.clicked.connect(self._on_row_clicked)
                # apply status tag from hash
                status = self._hash_to_status(s.hash or "")
                if status:
                    row.set_status_tag(status)
                self._rows.append(row)
                self._layout.addWidget(row)

        self._layout.addStretch()

    def selected_skills(self) -> list:
        return [row.skill_info for row in self._rows if row.selected]

    def clear_selection(self):
        for row in self._rows:
            row.selected = False
        self.selection_changed.emit()

    @staticmethod
    def _hash_to_status(h: str) -> str:
        if h in ("synced", "conflict", "local-only", "remote-only",
                 "loading", "off"):
            return h
        return ""

    def _on_row_clicked(self):
        row = self.sender()
        row.selected = not row.selected
        self.selection_changed.emit()

    # ---- Blank-area context menu ----

    def _row_at(self, container_pos):
        """Return the SkillItemRow at container coordinates, or None."""
        child = self._container.childAt(container_pos)
        while child is not None and child is not self._container:
            if isinstance(child, SkillItemRow):
                return child
            child = child.parentWidget()
        return None

    def _on_blank_context_menu(self, pos):
        """Right-click on the blank area: only copy / select-all.

        If the click landed on a row, do nothing — the row owns its own menu
        (in-finder reveal, copy path, copy name).
        """
        if self._row_at(pos) is not None:
            return  # row's own menu will handle it

        menu = QMenu(self)

        copy_act = QAction("复制选中文本", self)
        copy_act.triggered.connect(self._copy_focused_text)
        menu.addAction(copy_act)

        copy_names_act = QAction("复制已选 skill 名称", self)
        copy_names_act.triggered.connect(self._copy_selected_skill_names)
        copy_names_act.setEnabled(any(r.selected for r in self._rows))
        menu.addAction(copy_names_act)

        menu.addSeparator()

        select_all_act = QAction("全选", self)
        select_all_act.triggered.connect(self._select_all)
        select_all_act.setEnabled(bool(self._rows))
        menu.addAction(select_all_act)

        clear_sel_act = QAction("取消全选", self)
        clear_sel_act.triggered.connect(self.clear_selection)
        clear_sel_act.setEnabled(any(r.selected for r in self._rows))
        menu.addAction(clear_sel_act)

        menu.exec(self._container.mapToGlobal(pos))

    @staticmethod
    def _copy_focused_text():
        """Copy whatever text is currently selected in the focused widget.

        Falls back to a no-op if the focus widget doesn't expose text.
        """
        w = QApplication.focusWidget()
        text = ""
        try:
            sel = getattr(w, "selectedText", None)
            if callable(sel):
                text = sel() or ""
        except Exception:
            text = ""
        if text:
            QGuiApplication.clipboard().setText(text)

    def _copy_selected_skill_names(self):
        names = [r.skill_info.name for r in self._rows if r.selected]
        if names:
            QGuiApplication.clipboard().setText("\n".join(names))

    def _select_all(self):
        for row in self._rows:
            row.selected = True
        self.selection_changed.emit()
