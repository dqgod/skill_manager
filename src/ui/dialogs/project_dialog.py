"""项目注册与管理对话框"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QCheckBox, QWidget, QFormLayout, QFileDialog,
    QMessageBox, QFrame, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from src.models.connection import ConnectionModel
from src.models.project import Project, ProjectModel
from src.services.project_service import ProjectService


class ProjectDialog(QDialog):
    project_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("项目管理")
        self.setMinimumSize(480, 500)
        self.setStyleSheet(
            "QDialog { background: #252536; border: 1px solid #3a3a55;"
            "border-radius: 8px; }"
        )
        self._setup_ui()
        self._refresh_list()
        self._load_connections()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("注册项目")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #cdd6f4;")
        layout.addWidget(title)

        # form
        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("例如：开发任务A")
        form.addRow("项目名称:", self._name)

        path_row = QHBoxLayout()
        self._local_path = QLineEdit()
        self._local_path.setPlaceholderText("例如：D:\\projects\\task-a")
        path_row.addWidget(self._local_path, stretch=1)
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 12px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        form.addRow("本机路径:", path_row)

        self._remote_check = QCheckBox("关联远程机器")
        self._remote_check.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._remote_check.stateChanged.connect(self._on_remote_toggle)
        form.addRow("", self._remote_check)

        self._remote_device = QComboBox()
        self._remote_device.setVisible(False)
        form.addRow("远程设备:", self._remote_device)

        self._remote_path = QLineEdit()
        self._remote_path.setPlaceholderText("/home/user/project")
        self._remote_path.setVisible(False)
        form.addRow("远程路径:", self._remote_path)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(12)
        self._tool_codex = QCheckBox("Codex")
        self._tool_codex.setChecked(True)
        self._tool_codex.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self._tool_claude = QCheckBox("Claude Code")
        self._tool_claude.setChecked(True)
        self._tool_claude.setStyleSheet("color: #a6adc8; font-size: 12px;")
        tool_row.addWidget(self._tool_codex)
        tool_row.addWidget(self._tool_claude)
        tool_row.addStretch()
        form.addRow("支持工具:", tool_row)

        layout.addLayout(form)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("注册")
        save_btn.setStyleSheet(
            "QPushButton { background: #74c7ec; color: #1e1e2e; border: none;"
            "border-radius: 4px; padding: 6px 20px; font-weight: 600; }"
            "QPushButton:hover { background: #89d4f5; }"
        )
        save_btn.clicked.connect(self._on_register)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 16px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        # existing projects
        layout.addWidget(QLabel("已注册项目"))
        self._proj_container = QVBoxLayout()
        self._proj_container.setSpacing(4)
        layout.addLayout(self._proj_container)
        layout.addStretch()

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if path:
            self._local_path.setText(path)

    def _on_remote_toggle(self, state):
        visible = state == Qt.Checked
        self._remote_device.setVisible(visible)
        self._remote_path.setVisible(visible)

    def _load_connections(self):
        connections = ConnectionModel.get_all()
        self._remote_device.clear()
        self._remote_device.addItem("")
        for conn in connections:
            self._remote_device.addItem(conn.name, conn.id)

    def _on_register(self):
        name = self._name.text().strip()
        local_path = self._local_path.text().strip()
        if not name or not local_path:
            QMessageBox.warning(self, "提示", "项目名称和路径不能为空")
            return

        tools = []
        if self._tool_codex.isChecked():
            tools.append("codex")
        if self._tool_claude.isChecked():
            tools.append("claude")

        remote_conn_id = None
        remote_path = None
        if self._remote_check.isChecked():
            idx = self._remote_device.currentIndex()
            if idx > 0:
                remote_conn_id = self._remote_device.currentData()
            remote_path = self._remote_path.text().strip() or None

        try:
            ProjectService.register(
                name=name, local_path=local_path,
                remote_connection_id=remote_conn_id,
                remote_path=remote_path, tools=tools,
            )
            self._clear_form()
            self._refresh_list()
            self.project_changed.emit()
        except ValueError as e:
            QMessageBox.warning(self, "无法注册", str(e))

    def _refresh_list(self):
        # clear
        while self._proj_container.count():
            item = self._proj_container.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        projects = ProjectModel.get_all()
        for proj in projects:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background: #2d2d44; border-radius: 4px; padding: 6px; }"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)

            info = QLabel(f"📁 {proj.name}  |  {proj.local_path}")
            info.setStyleSheet("color: #cdd6f4; font-size: 12px;")
            rl.addWidget(info, stretch=1)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(50)
            del_btn.setStyleSheet(
                "QPushButton { background: none; border: 1px solid #3a3a55;"
                "color: #f38ba8; border-radius: 3px; padding: 2px 8px;"
                "font-size: 11px; }"
                "QPushButton:hover { background: #f38ba8; color: #1e1e2e; }"
            )
            del_btn.clicked.connect(
                lambda checked=False, pid=proj.id: self._delete_project(pid)
            )
            rl.addWidget(del_btn)

            self._proj_container.addWidget(row)

    def _delete_project(self, proj_id: str):
        ProjectService.delete(proj_id)
        self._refresh_list()
        self.project_changed.emit()

    def _clear_form(self):
        self._name.clear()
        self._local_path.clear()
        self._remote_check.setChecked(False)
        self._remote_path.clear()
