"""Skill 列表滚动区域"""

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt, Signal

from src.ui.skill_item_row import SkillItemRow


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

    def set_skills(self, skills):
        """Replace all rows with new skill list."""
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
        if h == "synced":
            return "synced"
        elif h == "conflict":
            return "conflict"
        elif h == "local-only":
            return "local-only"
        elif h == "remote-only":
            return "remote-only"
        return ""

    def _on_row_clicked(self):
        row = self.sender()
        row.selected = not row.selected
        self.selection_changed.emit()
