"""连接管理对话框：CRUD 列表 + 表单 + 测试"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QWidget, QScrollArea, QFrame,
    QMessageBox, QFormLayout, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from src.models.connection import Connection, ConnectionModel
from src.services.ssh_manager import SSHManager
from src.services.crypto_service import CryptoService


class _TestWorker(QThread):
    result = Signal(bool, str)

    def __init__(self, ssh_mgr: SSHManager, conn: Connection, parent=None):
        super().__init__(parent)
        self._ssh = ssh_mgr
        self._conn = conn

    def run(self):
        ok, msg = self._ssh.test(self._conn)
        self.result.emit(ok, msg)


class ConnectionDialog(QDialog):
    connection_changed = Signal()

    def __init__(self, ssh_manager: SSHManager, crypto: CryptoService,
                 parent=None):
        super().__init__(parent)
        self._ssh = ssh_manager
        self._crypto = crypto
        self._test_worker = None
        self.setWindowTitle("连接管理")
        self.setMinimumSize(500, 420)
        self.setStyleSheet(
            "QDialog { background: #252536; border: 1px solid #3a3a55;"
            "border-radius: 8px; }"
        )
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("SSH 连接管理")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #cdd6f4;")
        layout.addWidget(title)

        # connection list
        self._list_area = QScrollArea()
        self._list_area.setWidgetResizable(True)
        self._list_area.setStyleSheet(
            "QScrollArea { border: 1px solid #3a3a55; border-radius: 4px;"
            "background: #1e1e2e; }"
        )
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        self._list_area.setWidget(self._list_widget)
        self._list_area.setMaximumHeight(200)
        layout.addWidget(self._list_area)

        # form
        form_title = QLabel("新增 / 编辑连接")
        form_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #a6adc8;")
        layout.addWidget(form_title)

        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("连接名称，如 dev-server")
        form.addRow("名称:", self._name)

        self._host = QLineEdit()
        self._host.setPlaceholderText("IP 或主机名")
        form.addRow("主机:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        self._port.setStyleSheet(
            "QSpinBox { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 10px; color: #cdd6f4; }"
        )
        form.addRow("端口:", self._port)

        self._username = QLineEdit()
        self._username.setPlaceholderText("SSH 用户名")
        form.addRow("用户名:", self._username)

        self._auth_type = QComboBox()
        self._auth_type.addItems(["key", "password"])
        self._auth_type.currentTextChanged.connect(self._on_auth_changed)
        form.addRow("认证方式:", self._auth_type)

        self._key_path = QLineEdit()
        self._key_path.setPlaceholderText("私钥路径，留空使用默认")
        form.addRow("私钥路径:", self._key_path)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("SSH 密码（将加密存储）")
        self._password.setVisible(False)
        form.addRow("密码:", self._password)

        layout.addLayout(form)

        # buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        test_btn = QPushButton("测试连接")
        test_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 16px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; color: #cdd6f4; }"
        )
        test_btn.clicked.connect(self._on_test)
        btn_layout.addWidget(test_btn)

        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton { background: #74c7ec; color: #1e1e2e; border: none;"
            "border-radius: 4px; padding: 6px 20px; font-weight: 600; }"
            "QPushButton:hover { background: #89d4f5; }"
        )
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "border-radius: 4px; padding: 6px 16px; color: #a6adc8; }"
            "QPushButton:hover { background: #3a3a55; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _on_auth_changed(self, auth_type: str):
        self._key_path.setVisible(auth_type == "key")
        self._password.setVisible(auth_type == "password")

    def _on_save(self):
        name = self._name.text().strip()
        host = self._host.text().strip()
        if not name or not host:
            QMessageBox.warning(self, "提示", "名称和主机不能为空")
            return

        conn = Connection(
            name=name, host=host, port=self._port.value(),
            username=self._username.text().strip(),
            auth_type=self._auth_type.currentText(),
            key_path=self._key_path.text().strip() or None,
        )
        if conn.auth_type == "password":
            pw = self._password.text()
            if pw:
                conn.password_enc = self._crypto.encrypt(pw)

        ConnectionModel.save(conn)
        self._clear_form()
        self._refresh_list()
        self.connection_changed.emit()

    def _on_test(self):
        name = self._name.text().strip()
        host = self._host.text().strip()
        if not host:
            QMessageBox.warning(self, "提示", "请先输入主机地址")
            return

        conn = Connection(
            name=name or "test", host=host, port=self._port.value(),
            username=self._username.text().strip(),
            auth_type=self._auth_type.currentText(),
            key_path=self._key_path.text().strip() or None,
        )
        if conn.auth_type == "password":
            pw = self._password.text()
            if pw:
                conn.password_enc = self._crypto.encrypt(pw)

        self._test_worker = _TestWorker(self._ssh, conn)
        self._test_worker.result.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, ok: bool, msg: str):
        if ok:
            QMessageBox.information(self, "测试结果", "连接成功！")
        else:
            QMessageBox.critical(self, "测试失败", msg)

    def _refresh_list(self):
        # clear existing items
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        connections = ConnectionModel.get_all()
        for conn in connections:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background: #2d2d44; border-radius: 4px; padding: 6px; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)

            info = QLabel(
                f"{conn.name}  |  {conn.username}@{conn.host}:{conn.port}"
                f"  |  {'密钥认证' if conn.auth_type == 'key' else '密码认证'}"
            )
            info.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: 500;")
            row_layout.addWidget(info, stretch=1)

            test_btn = QPushButton("测试")
            test_btn.setFixedWidth(50)
            test_btn.setStyleSheet(
                "QPushButton { background: none; border: 1px solid #3a3a55;"
                "color: #74c7ec; border-radius: 3px; padding: 2px 8px;"
                "font-size: 11px; }"
                "QPushButton:hover { background: #74c7ec; color: #1e1e2e; }"
                "QPushButton:disabled { color: #6c7086; border-color: #3a3a55; }"
            )
            test_btn.clicked.connect(
                lambda checked=False, c=conn, b=test_btn: self._test_existing(c, b)
            )
            row_layout.addWidget(test_btn)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(50)
            del_btn.setStyleSheet(
                "QPushButton { background: none; border: 1px solid #3a3a55;"
                "color: #f38ba8; border-radius: 3px; padding: 2px 8px;"
                "font-size: 11px; }"
                "QPushButton:hover { background: #f38ba8; color: #1e1e2e; }"
            )
            del_btn.clicked.connect(
                lambda checked=False, cid=conn.id: self._delete_conn(cid)
            )
            row_layout.addWidget(del_btn)

            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _test_existing(self, conn: Connection, btn: QPushButton):
        """Test an already-saved connection from the list row."""
        self._stop_test_worker()
        original = btn.text()
        btn.setEnabled(False)
        btn.setText("测试中...")

        worker = _TestWorker(self._ssh, conn, parent=self)
        self._test_worker = worker

        def _done(ok: bool, msg: str, b=btn, t=original):
            try:
                b.setEnabled(True)
                b.setText(t)
            except RuntimeError:
                pass
            if ok:
                QMessageBox.information(
                    self, "测试结果",
                    f"连接 {conn.name} ({conn.username}@{conn.host}:{conn.port}) 成功！",
                )
            else:
                QMessageBox.critical(
                    self, "测试失败",
                    f"连接 {conn.name} 失败：\n{msg}",
                )

        worker.result.connect(_done)
        worker.start()

    def _delete_conn(self, conn_id: str):
        ConnectionModel.delete(conn_id)
        self._refresh_list()
        self.connection_changed.emit()

    def _clear_form(self):
        self._name.clear()
        self._host.clear()
        self._port.setValue(22)
        self._username.clear()
        self._auth_type.setCurrentIndex(0)
        self._key_path.clear()
        self._password.clear()

    def closeEvent(self, event):
        self._stop_test_worker()
        super().closeEvent(event)

    def reject(self):
        self._stop_test_worker()
        super().reject()

    def _stop_test_worker(self):
        if self._test_worker is not None:
            try:
                self._test_worker.result.disconnect(self._on_test_result)
            except (TypeError, RuntimeError):
                pass
            if self._test_worker.isRunning():
                self._test_worker.quit()
                self._test_worker.wait(2000)
            self._test_worker = None
