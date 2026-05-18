"""主窗口：菜单栏 + 侧边栏 + 双面板 + 底部栏"""

import copy

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStatusBar,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QThread, QTimer, Signal

from src.config import (
    ALL_TOOLS_STR, SYNC_DIRECTION_PUSH, SYNC_DIRECTION_PULL,
    SYNC_LEVEL_GLOBAL, SYNC_LEVEL_TO_PROJECT,
    SYNC_LEVEL_TO_GLOBAL, SYNC_LEVEL_PROJECT,
)
from src.services.skill_scanner import SkillScanner, SkillInfo
from src.services.skill_hasher import SkillHasher
from src.services.skill_sync import SkillSyncService, SyncTask
from src.services.ssh_manager import SSHManager
from src.services.crypto_service import CryptoService
from src.models.connection import Connection, ConnectionModel
from src.models.project import Project, ProjectModel
from src.ui.sidebar import Sidebar
from src.ui.skill_panels import SkillPanels
from src.ui.bottom_bar import BottomBar
from src.ui.dialogs.connection_dialog import ConnectionDialog
from src.ui.dialogs.project_dialog import ProjectDialog
from src.ui.dialogs.sync_progress_dialog import SyncProgressDialog
from src.ui.dialogs.conflict_dialog import ConflictDialog
from src.ui.dialogs.history_dialog import HistoryDialog
from src.ui.widgets.toast import Toast
from src.utils.logger import get_logger

logger = get_logger(__name__)


class _LocalScanWorker(QThread):
    finished = Signal(list)

    def __init__(self, scanner: SkillScanner, view_id: str, projects: list,
                 parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._view_id = view_id
        self._projects = projects

    def run(self):
        skills = []
        if self._view_id == "global":
            skills = self._scanner.scan_local_global()
        else:
            proj = next((p for p in self._projects if p.id == self._view_id), None)
            if proj:
                skills = self._scanner.scan_local_project(proj)
        self.finished.emit(skills)


class _RemoteScanWorker(QThread):
    finished = Signal(list)

    def __init__(self, scanner: SkillScanner, connection: Connection,
                 view_id: str, projects: list, parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._conn = connection
        self._view_id = view_id
        self._projects = projects

    def run(self):
        skills = []
        if self._view_id == "global":
            skills = self._scanner.scan_remote_global(self._conn)
        else:
            proj = next((p for p in self._projects if p.id == self._view_id), None)
            if proj:
                skills = self._scanner.scan_remote_project(self._conn, proj)
        self.finished.emit(skills)


class _SyncWorker(QThread):
    progress = Signal(int, int, str, str)  # current, total, skill_name, status
    conflict = Signal(object)  # SyncTask
    finished = Signal(list)  # list[SyncResult]

    def __init__(self, sync_svc: SkillSyncService, tasks: list,
                 source_conn, target_conn, conflict_strategy: str,
                 parent=None):
        super().__init__(parent)
        self._sync_svc = sync_svc
        self._tasks = tasks
        self._source_conn = source_conn
        self._target_conn = target_conn
        self._conflict_strategy = conflict_strategy
        self._conflict_response: str | None = None
        self._apply_all = False

    def run(self):
        results = self._sync_svc.execute(
            self._tasks,
            source_connection=self._source_conn,
            target_connection=self._target_conn,
            conflict_strategy=self._conflict_strategy,
            on_progress=lambda cur, tot, name, st: self.progress.emit(cur, tot, name, st),
            on_conflict=self._handle_conflict if self._conflict_strategy == "ask" else None,
        )
        self.finished.emit(results)

    def _handle_conflict(self, task) -> str:
        if self._apply_all:
            return self._conflict_response or "skip"
        self.conflict.emit(task)
        # wait for response via set_conflict_response
        self._conflict_response = None
        while self._conflict_response is None:
            self.msleep(50)
        return self._conflict_response

    def set_conflict_response(self, response: str, apply_all: bool = False):
        self._conflict_response = response
        self._apply_all = apply_all


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Skill Manager — 跨设备 Skill 管理")
        self.resize(1200, 750)

        self._crypto = CryptoService()
        self._ssh = SSHManager(self._crypto)
        self._scanner = SkillScanner(self._ssh)
        self._hasher = SkillHasher(self._ssh)
        self._sync_svc = SkillSyncService(self._ssh, self._hasher)

        # Periodic idle connection cleanup
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._ssh.cleanup_idle)
        self._idle_timer.start(60_000)  # every 60 seconds
        self._projects: list = []
        self._sync_conflict_strategy = "ask"
        self._local_skills: list = []
        self._remote_skills: list = []
        self._active_connection: Connection | None = None
        self._local_scan_seq = 0   # guard against stale local scan results
        self._remote_scan_seq = 0  # guard against stale remote scan results

        self._setup_ui()
        self._ensure_default_connection()
        self._load_projects()
        self._load_connections()
        # cleanup old backups on startup
        SkillSyncService.cleanup_old_backups()
        # auto-refresh local on startup
        self._refresh_local("global")

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # menu bar
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background: #252536; border-bottom: 1px solid #3a3a55;"
            "padding: 4px 0; }"
            "QMenuBar::item { padding: 4px 10px; color: #a6adc8; font-size: 12px; }"
            "QMenuBar::item:selected { background: #2d2d44; color: #cdd6f4; }"
        )
        conn_menu = menubar.addMenu("连接管理")
        conn_action = conn_menu.addAction("管理连接...")
        conn_action.triggered.connect(self._open_connection_dialog)

        proj_menu = menubar.addMenu("项目管理")
        proj_action = proj_menu.addAction("注册项目...")
        proj_action.triggered.connect(self._on_add_project)

        hist_menu = menubar.addMenu("操作历史")
        hist_action = hist_menu.addAction("查看历史...")
        hist_action.triggered.connect(self._open_history_dialog)

        # main content
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.view_changed.connect(self._on_view_changed)
        self._sidebar.add_project_requested.connect(self._on_add_project)
        content.addWidget(self._sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._panels = SkillPanels()
        local = self._panels.local_panel
        local.refresh_requested.connect(self._on_refresh_local)
        local.tool_changed.connect(lambda t: self._on_tool_changed("local", t))
        local.selection_changed.connect(self._on_selection_changed)

        remote = self._panels.remote_panel
        remote.refresh_requested.connect(self._on_refresh_remote)
        remote.tool_changed.connect(lambda t: self._on_tool_changed("remote", t))
        remote.selection_changed.connect(self._on_selection_changed)
        remote.device_changed.connect(self._on_remote_device_changed)

        right.addWidget(self._panels, stretch=1)

        self._bottom_bar = BottomBar()
        self._bottom_bar.sync_requested.connect(self._on_sync_requested)
        right.addWidget(self._bottom_bar)

        content.addLayout(right, stretch=1)
        root.addLayout(content)

        # status bar
        status = QStatusBar()
        status.setStyleSheet(
            "QStatusBar { background: #1e1e2e; border-top: 1px solid #3a3a55;"
            "color: #6c7086; font-size: 11px; padding: 2px 12px; }"
        )
        status.showMessage("就绪")
        self.setStatusBar(status)

        # toast
        self._toast = Toast(self)

    # ---- Events ----

    def _on_view_changed(self, view_id: str):
        self._refresh_local(view_id)

    def _on_refresh_local(self):
        self._refresh_local(self._sidebar.active_view)

    def _on_refresh_remote(self):
        if not self._active_connection:
            self._toast.show_message("请先选择远程设备", success=False)
            return
        self._refresh_remote(self._sidebar.active_view)

    def _on_tool_changed(self, side: str, tool: str):
        skills = self._local_skills if side == "local" else self._remote_skills
        panel = self._panels.local_panel if side == "local" else self._panels.remote_panel
        logger.info("[TabSwitch] MainWindow._on_tool_changed side=%s tool=%s skills_count=%d",
                     side, tool, len(skills))
        panel.display_skills(skills)
        self._on_selection_changed()

    def _on_selection_changed(self):
        local_sel = self._panels.local_panel.selected_skills()
        remote_sel = self._panels.remote_panel.selected_skills()
        self._bottom_bar.update_selection_count(len(local_sel) + len(remote_sel))

    def _on_remote_device_changed(self, conn_name: str):
        if not conn_name:
            self._active_connection = None
            return
        self._active_connection = ConnectionModel.get_by_name(conn_name)
        if self._active_connection:
            self._refresh_remote(self._sidebar.active_view)

    def _on_add_project(self):
        dlg = ProjectDialog(self)
        dlg.project_changed.connect(self._on_project_changed)
        dlg.exec()

    def _open_history_dialog(self):
        dlg = HistoryDialog(self)
        dlg.exec()

    def _on_project_changed(self):
        self._projects = ProjectModel.get_all()
        # clear existing project nav items
        for proj in ProjectModel.get_all():
            self._sidebar.remove_project_nav(proj.id)
        # re-add
        for proj in self._projects:
            self._sidebar.add_project_nav(proj.id, proj.name)
        self._toast.show_message("项目列表已更新")

    def _on_sync_requested(self):
        # gather selected skills from both panels (prefer local for push, remote for pull)
        direction = self._bottom_bar.sync_direction
        sync_level = self._bottom_bar.sync_level
        target_tools = self._bottom_bar.selected_tools

        if direction == SYNC_DIRECTION_PUSH:
            selected = self._panels.local_panel.selected_skills()
            if not selected:
                self._toast.show_message("请先选择要推送的 skill", success=False)
                return
        else:
            selected = self._panels.remote_panel.selected_skills()
            if not selected:
                self._toast.show_message("请先选择要拉取的 skill", success=False)
                return

        if not target_tools:
            self._toast.show_message("请先选择目标工具", success=False)
            return

        # resolve connections
        source_conn = None
        target_conn = None
        if direction == SYNC_DIRECTION_PUSH:
            target_conn = self._active_connection
        else:
            source_conn = self._active_connection

        # prepare tasks
        tasks = self._sync_svc.prepare_tasks(
            selected, direction, sync_level, target_tools,
            source_connection=source_conn,
            target_connection=target_conn,
        )
        if not tasks:
            self._toast.show_message("没有可执行的任务", success=False)
            return

        # progress dialog
        self._sync_dialog = SyncProgressDialog(len(tasks), self)
        for task in tasks:
            self._sync_dialog.add_item(task.skill_name)

        # worker
        self._sync_worker = _SyncWorker(
            self._sync_svc, tasks, source_conn, target_conn,
            self._sync_conflict_strategy
        )
        self._sync_worker.progress.connect(self._on_sync_progress)
        self._sync_worker.conflict.connect(self._on_sync_conflict)
        self._sync_worker.finished.connect(self._on_sync_finished)
        self._sync_worker.start()
        self._sync_dialog.show()

    def _on_sync_progress(self, cur: int, total: int, name: str, status: str):
        if hasattr(self, '_sync_dialog'):
            self._sync_dialog.update_item(name, status)
            self._sync_dialog.set_progress(cur + 1 if status == "success" else cur)

    def _on_sync_conflict(self, task):
        dlg = ConflictDialog(task.skill_name, self._sync_dialog)
        if dlg.exec() == dlg.Accepted:
            self._sync_worker.set_conflict_response(dlg.choice, dlg.apply_all)

    def _on_sync_finished(self, results):
        success_count = sum(1 for r in results if r.status == "success")
        fail_count = sum(1 for r in results if r.status == "failed")
        self._sync_dialog.set_progress(len(results))
        self._sync_dialog.accept()
        self._toast.show_message(
            f"同步完成：{success_count}/{len(results)} 成功"
        )
        logger.info(
            "Sync finished: %d success, %d failed, %d total",
            success_count, fail_count, len(results),
        )
        # refresh both panels
        self._refresh_local(self._sidebar.active_view)
        if self._active_connection:
            self._refresh_remote(self._sidebar.active_view)

    def _open_connection_dialog(self):
        dlg = ConnectionDialog(self._ssh, self._crypto, self)
        dlg.connection_changed.connect(self._load_connections)
        dlg.exec()

    # ---- Internal ----

    def _ensure_default_connection(self):
        """Create default connection for the user's server if none exist."""
        existing = ConnectionModel.get_all()
        if existing:
            return
        conn = Connection(
            name="dev-server",
            host="192.168.124.241",
            port=22,
            username="root",
            auth_type="key",
        )
        ConnectionModel.save(conn)

    def _load_projects(self):
        self._projects = ProjectModel.get_all()
        for proj in self._projects:
            self._sidebar.add_project_nav(proj.id, proj.name)

    def _load_connections(self):
        connections = ConnectionModel.get_all()
        remote_panel = self._panels.remote_panel
        remote_panel.set_devices(connections)
        # auto-select first if none active
        if not self._active_connection and connections:
            remote_panel.select_device(connections[0].name)
            self._active_connection = connections[0]

    def _refresh_local(self, view_id: str):
        # Disconnect and stop any previous worker
        if hasattr(self, '_local_worker') and self._local_worker is not None:
            try:
                self._local_worker.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self._local_worker.isRunning():
                self._local_worker.quit()
                self._local_worker.wait(5000)

        self._local_scan_seq += 1
        seq = self._local_scan_seq
        self.statusBar().showMessage("正在扫描本机...")
        self.setCursor(Qt.BusyCursor)
        self._local_worker = _LocalScanWorker(
            self._scanner, view_id, self._projects
        )
        self._local_worker.finished.connect(
            lambda skills, s=seq: self._on_scan_local_done_guarded(skills, s)
        )
        self._local_worker.start()

    def _refresh_remote(self, view_id: str):
        if not self._active_connection:
            return
        # Disconnect and stop any previous worker
        if hasattr(self, '_remote_worker') and self._remote_worker is not None:
            try:
                self._remote_worker.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self._remote_worker.isRunning():
                self._remote_worker.quit()
                self._remote_worker.wait(5000)

        self._remote_scan_seq += 1
        seq = self._remote_scan_seq
        self.statusBar().showMessage("正在扫描远程...")
        self.setCursor(Qt.BusyCursor)
        self._remote_worker = _RemoteScanWorker(
            self._scanner, self._active_connection, view_id, self._projects
        )
        self._remote_worker.finished.connect(
            lambda skills, s=seq: self._on_scan_remote_done_guarded(skills, s)
        )
        self._remote_worker.start()

    def _on_scan_local_done_guarded(self, skills: list, seq: int):
        if seq != self._local_scan_seq:
            return  # stale result
        self._on_scan_local_done(skills)

    def _on_scan_remote_done_guarded(self, skills: list, seq: int):
        if seq != self._remote_scan_seq:
            return  # stale result
        self._on_scan_remote_done(skills)

    def _on_scan_local_done(self, skills: list):
        self.setCursor(Qt.ArrowCursor)
        self._local_skills = skills
        self._update_badges("local", skills)
        if self._remote_skills:
            self._auto_compare()
        else:
            # No remote data yet — mark all as local-only
            for s in self._local_skills:
                s.hash = "local-only"
        self._panels.local_panel.display_skills(self._local_skills)
        self.statusBar().showMessage(f"本机扫描完成，{len(skills)} 个 skill")
        self._on_selection_changed()
        logger.info("Local scan completed: %d skills", len(skills))

    def _on_scan_remote_done(self, skills: list):
        self.setCursor(Qt.ArrowCursor)
        self._remote_skills = skills
        self._update_badges("remote", skills)
        if self._local_skills:
            self._auto_compare()
        else:
            for s in self._remote_skills:
                s.hash = "remote-only"
        self._panels.remote_panel.display_skills(self._remote_skills)
        self.statusBar().showMessage(f"远程扫描完成，{len(skills)} 个 skill")
        self._on_selection_changed()
        logger.info("Remote scan completed: %d skills", len(skills))

    def _auto_compare(self):
        """Auto-compare local and remote skills, apply status tags."""
        # Preserve original local skills before classify_skills mutates their
        # hash fields (Bug 4). classify_remote_skills needs unmodified hashes.
        original_local = copy.deepcopy(self._local_skills)

        self._local_skills = self._hasher.classify_skills(
            self._local_skills, self._remote_skills,
            remote_connection=self._active_connection,
        )
        self._remote_skills = self._hasher.classify_remote_skills(
            original_local, self._remote_skills,
            remote_connection=self._active_connection,
        )

    def _tag_to_status(self, skill_info) -> str:
        """Map skill_info hash field to a display status tag."""
        h = skill_info.hash or ""
        if h == "synced":
            return "synced"
        elif h == "conflict":
            return "conflict"
        elif h == "local-only":
            return "local-only"
        elif h == "remote-only":
            return "remote-only"
        return ""

    def _update_badges(self, side: str, skills: list):
        if side == "local":
            global_count = sum(1 for s in skills if s.level == "global")
            pc: dict[str, int] = {}
            for s in skills:
                if s.project_id:
                    pc[s.project_id] = pc.get(s.project_id, 0) + 1
            self._sidebar.update_badges(global_count, pc)

    def closeEvent(self, event):
        logger.info("Application shutting down")
        self._ssh.close_all()
        super().closeEvent(event)
