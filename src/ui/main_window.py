"""主窗口：菜单栏 + 侧边栏 + 双面板 + 底部栏"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStatusBar,
    QCheckBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QSettings

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
    failed = Signal(str)

    def __init__(self, scanner: SkillScanner, connection: Connection,
                 view_id: str, projects: list, parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._conn = connection
        self._view_id = view_id
        self._projects = projects

    def run(self):
        skills = []
        try:
            if self._view_id == "global":
                skills = self._scanner.scan_remote_global(self._conn)
            else:
                proj = next((p for p in self._projects if p.id == self._view_id), None)
                if proj:
                    skills = self._scanner.scan_remote_project(self._conn, proj)
        except Exception as e:
            logger.warning("Remote scan failed: %s", e)
            self.failed.emit(self._format_error(e))
            return
        self.finished.emit(skills)

    @staticmethod
    def _format_error(e: Exception) -> str:
        msg = str(e) or e.__class__.__name__
        low = msg.lower()
        if isinstance(e, TimeoutError) or "timed out" in low or "timeout" in low:
            return "连接超时：远程主机无响应，请检查网络/IP 或 VPN"
        if "authentication" in low:
            return "认证失败：用户名或密钥错误"
        if "name or service not known" in low or "nodename" in low:
            return "无法解析主机名，请检查 host 是否正确"
        return f"远程扫描失败：{msg}"


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


class _AutoCompareWorker(QThread):
    """Run SkillHasher.compare off the UI thread.

    Returns the *tagged* local + remote lists; emits failure as empty results.
    """
    finished = Signal(list, list)  # tagged_local, tagged_remote
    failed = Signal(str)

    def __init__(self, hasher: SkillHasher, local: list, remote: list,
                 connection, parent=None):
        super().__init__(parent)
        self._hasher = hasher
        self._local = local
        self._remote = remote
        self._connection = connection

    def run(self):
        try:
            diff = self._hasher.compare(
                self._local, self._remote,
                remote_connection=self._connection,
            )
            synced = {(s.name, s.tool) for s in diff.synced}
            local_only = {(s.name, s.tool) for s in diff.local_only}
            remote_only = {(s.name, s.tool) for s in diff.remote_only}
            conflict = {(p[0].name, p[0].tool) for p in diff.conflict}

            for s in self._local:
                key = (s.name, s.tool)
                if key in synced:
                    s.hash = "synced"
                elif key in conflict:
                    s.hash = "conflict"
                elif key in local_only:
                    s.hash = "local-only"
                else:
                    s.hash = "unknown"
            for s in self._remote:
                key = (s.name, s.tool)
                if key in synced:
                    s.hash = "synced"
                elif key in conflict:
                    s.hash = "conflict"
                elif key in remote_only:
                    s.hash = "remote-only"
                else:
                    s.hash = "unknown"
            self.finished.emit(self._local, self._remote)
        except Exception as e:
            logger.warning("Auto-compare failed: %s", e)
            self.failed.emit(str(e))


class _HealthCheckWorker(QThread):
    """Test reachability of a remote connection off the UI thread.

    Emits status:
      'online'  — TCP + auth OK (echo round-trip succeeded)
      'offline' — any failure; detail carries the human-readable cause
    """
    finished = Signal(str, str)  # status, detail

    def __init__(self, ssh: SSHManager, connection, parent=None):
        super().__init__(parent)
        self._ssh = ssh
        self._connection = connection

    def run(self):
        try:
            ok, msg = self._ssh.test(self._connection)
            if ok:
                self.finished.emit("online", "在线")
            else:
                self.finished.emit("offline", msg or "连接失败")
        except Exception as e:
            self.finished.emit("offline", str(e))


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

        # Periodic remote-connection health check (PR-3 status indicator).
        # Refresh every 60s while a device is selected.
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._check_remote_health)
        self._health_timer.start(60_000)

        self._projects: list = []
        self._sync_conflict_strategy = "ask"
        self._local_skills: list = []
        self._remote_skills: list = []
        self._active_connection: Connection | None = None
        self._local_scan_seq = 0   # guard against stale local scan results
        self._remote_scan_seq = 0  # guard against stale remote scan results

        # Hash-compare master switch (PR-Switch).
        # Persisted across launches via QSettings.
        self._settings = QSettings("skill_manager", "skill_manager")
        self._hash_compare_enabled: bool = bool(
            self._settings.value("ui/hash_compare_enabled", False, type=bool)
        )

        # Auto-fade timer for the status chip ("✓ 完成" reverts to idle).
        self._chip_clear_timer = QTimer(self)
        self._chip_clear_timer.setSingleShot(True)
        self._chip_clear_timer.timeout.connect(
            lambda: self._set_status_chip("idle")
        )

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

        # ----- top bar above panels: hash-compare toggle + status chip -----
        # Lives inside the main window (not the menubar) because macOS
        # QMenuBar.setCornerWidget interacts poorly with the native menu
        # and ends up deleting the corner widget at runtime.
        top_bar = QWidget()
        top_bar.setStyleSheet(
            "QWidget { background: #1e1e2e; border-bottom: 1px solid #3a3a55; }"
        )
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(12, 6, 12, 6)
        top_bar_layout.setSpacing(10)
        top_bar_layout.addStretch()

        self._hash_compare_check = QCheckBox("校验内容一致性")
        self._hash_compare_check.setStyleSheet(
            "QCheckBox { color: #a6adc8; font-size: 11px; spacing: 4px; }"
            "QCheckBox::indicator { width: 13px; height: 13px; }"
        )
        self._hash_compare_check.setToolTip(
            "打开后会计算并比较本机与远端 skill 的内容哈希；\n"
            "关闭则跳过哈希计算，只展示列表，启动/刷新更快。"
        )
        self._hash_compare_check.setChecked(self._hash_compare_enabled)
        self._hash_compare_check.toggled.connect(self._on_hash_compare_toggled)
        top_bar_layout.addWidget(self._hash_compare_check)

        self._status_chip = QLabel("")
        self._status_chip.setStyleSheet(
            "QLabel { font-size: 11px; padding: 2px 8px; border-radius: 8px;"
            "color: #6c7086; background: transparent; }"
        )
        top_bar_layout.addWidget(self._status_chip)

        right.addWidget(top_bar)
        self._set_status_chip("idle")
        # -------------------------------------------------------------------

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
            self._panels.remote_panel.set_connection_status("unknown")
            return
        self._active_connection = ConnectionModel.get_by_name(conn_name)
        if self._active_connection:
            self._check_remote_health()
            self._refresh_remote(self._sidebar.active_view)

    def _on_add_project(self):
        dlg = ProjectDialog(self)
        dlg.project_changed.connect(self._on_project_changed)
        dlg.exec()

    def _open_history_dialog(self):
        dlg = HistoryDialog(self)
        dlg.exec()

    def _on_project_changed(self):
        for item_id in list(self._sidebar._nav_items.keys()):
            if item_id != "global":
                self._sidebar.remove_project_nav(item_id)
        self._projects = ProjectModel.get_all()
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

        active_project = next(
            (p for p in self._projects if p.id == self._sidebar.active_view),
            None,
        )
        source_project = None
        target_project = None
        if sync_level == SYNC_LEVEL_TO_PROJECT:
            target_project = active_project
        elif sync_level == SYNC_LEVEL_TO_GLOBAL:
            source_project = active_project
        elif sync_level == SYNC_LEVEL_PROJECT:
            source_project = active_project
            target_project = active_project

        # prepare tasks
        tasks = self._sync_svc.prepare_tasks(
            selected, direction, sync_level, target_tools,
            source_project=source_project,
            target_project=target_project,
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
            if status in ("success", "failed", "skipped"):
                self._sync_dialog.set_progress(cur + 1)

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
            # Probe health right away so user sees green/red within seconds.
            self._check_remote_health()

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
        self._set_status_chip("scanning_local")
        self._local_worker = _LocalScanWorker(
            self._scanner, view_id, self._projects, parent=self,
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
            try:
                self._remote_worker.failed.disconnect()
            except (TypeError, RuntimeError, AttributeError):
                pass
            if self._remote_worker.isRunning():
                self._remote_worker.quit()
                self._remote_worker.wait(5000)

        self._remote_scan_seq += 1
        seq = self._remote_scan_seq
        self.statusBar().showMessage("正在扫描远程...")
        self._set_status_chip("scanning_remote")
        self._remote_worker = _RemoteScanWorker(
            self._scanner, self._active_connection, view_id, self._projects,
            parent=self,
        )
        self._remote_worker.finished.connect(
            lambda skills, s=seq: self._on_scan_remote_done_guarded(skills, s)
        )
        self._remote_worker.failed.connect(
            lambda msg, s=seq: self._on_scan_remote_failed_guarded(msg, s)
        )
        self._remote_worker.start()

    def _on_scan_local_done_guarded(self, skills: list, seq: int):
        if seq != self._local_scan_seq:
            return  # stale result
        self._finalize_worker("_local_worker")
        self._on_scan_local_done(skills)

    def _on_scan_remote_done_guarded(self, skills: list, seq: int):
        if seq != self._remote_scan_seq:
            return  # stale result
        self._finalize_worker("_remote_worker")
        self._on_scan_remote_done(skills)

    def _on_scan_remote_failed_guarded(self, msg: str, seq: int):
        if seq != self._remote_scan_seq:
            return  # stale result
        self._finalize_worker("_remote_worker")
        self._remote_skills = []
        self._panels.remote_panel.display_skills([])
        self._update_badges("remote", [])
        self.statusBar().showMessage(f"远程扫描失败：{msg}")
        self._set_status_chip("error", "远程扫描失败")
        # Mark the panel offline with the actual error reason.
        if self._active_connection:
            conn = self._active_connection
            self._panels.remote_panel.set_connection_status(
                "offline",
                f"无法连接 {conn.username}@{conn.host}:{conn.port}\n{msg}",
            )
        try:
            toast = Toast(self)
            toast.show_message(msg, duration=4000, success=False)
        except Exception:
            pass
        logger.warning("Remote scan failed: %s", msg)

    def _finalize_worker(self, attr: str):
        """Quit + wait + deleteLater the QThread referenced by self.<attr>.

        Why: Qt aborts the process with `QThread: Destroyed while thread is
        still running` if the QThread Python object goes out of scope before
        the underlying thread fully exits. We make sure the thread has
        finished (event loop exited) before letting GC near it.
        """
        worker = getattr(self, attr, None)
        if worker is None:
            return
        try:
            if worker.isRunning():
                worker.quit()
                worker.wait(3000)
        except RuntimeError:
            pass
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        setattr(self, attr, None)

    def _on_scan_local_done(self, skills: list):
        self._local_skills = skills
        self._update_badges("local", skills)
        # Always render local list immediately so the UI doesn't look frozen.
        if self._hash_compare_enabled:
            # Show "loading" tag until _auto_compare finishes.
            for s in self._local_skills:
                if s.hash is None:
                    s.hash = "loading"
        else:
            for s in self._local_skills:
                s.hash = "off"
        self._panels.local_panel.display_skills(self._local_skills)
        self.statusBar().showMessage(f"本机扫描完成，{len(skills)} 个 skill")
        self._on_selection_changed()
        logger.info("Local scan completed: %d skills", len(skills))

        if self._hash_compare_enabled and self._remote_skills:
            self._auto_compare()
        elif self._hash_compare_enabled:
            # No remote yet — temporarily mark as local-only
            for s in self._local_skills:
                s.hash = "local-only"
            self._panels.local_panel.display_skills(self._local_skills)
            self._set_status_chip("done", f"✓ 本机 {len(skills)}")
        else:
            self._set_status_chip("done", f"✓ 本机 {len(skills)}（未校验）")

    def _on_scan_remote_done(self, skills: list):
        self._remote_skills = skills
        self._update_badges("remote", skills)
        # A successful scan implies the remote is reachable.
        if self._active_connection:
            conn = self._active_connection
            self._panels.remote_panel.set_connection_status(
                "online",
                f"已连接 {conn.username}@{conn.host}:{conn.port}",
            )
        # Render immediately so users can interact while we crunch hashes.
        if self._hash_compare_enabled:
            for s in self._remote_skills:
                if s.hash is None:
                    s.hash = "loading"
        else:
            for s in self._remote_skills:
                s.hash = "off"
        self._panels.remote_panel.display_skills(self._remote_skills)
        self.statusBar().showMessage(f"远程扫描完成，{len(skills)} 个 skill")
        self._on_selection_changed()
        logger.info("Remote scan completed: %d skills", len(skills))

        if self._hash_compare_enabled and self._local_skills:
            self._auto_compare()
        elif self._hash_compare_enabled:
            for s in self._remote_skills:
                s.hash = "remote-only"
            self._panels.remote_panel.display_skills(self._remote_skills)
            self._set_status_chip("done", f"✓ 远程 {len(skills)}")
        else:
            self._set_status_chip("done", f"✓ 远程 {len(skills)}（未校验）")

    def _auto_compare(self):
        """Auto-compare local and remote skills off the UI thread.

        Why: the comparator must hash every shared skill on the *remote* side,
        which historically blocked the GUI for several seconds on large
        inventories. Pushing it into a worker keeps the window responsive
        and lets users keep scrolling/clicking while we crunch.
        """
        # Master switch: skip hashing entirely when disabled.
        if not self._hash_compare_enabled:
            for s in self._local_skills:
                s.hash = "off"
            for s in self._remote_skills:
                s.hash = "off"
            self._panels.local_panel.display_skills(self._local_skills)
            self._panels.remote_panel.display_skills(self._remote_skills)
            self._set_status_chip("done", "校验已关闭")
            return
        # Cancel any in-flight comparison
        self._finalize_worker("_compare_worker")
        self.statusBar().showMessage("正在比对本机/远程 skill ...")
        self._set_status_chip("comparing")
        self._compare_worker = _AutoCompareWorker(
            self._hasher,
            self._local_skills,
            self._remote_skills,
            self._active_connection,
            parent=self,
        )
        self._compare_worker.finished.connect(self._on_compare_done)
        self._compare_worker.failed.connect(self._on_compare_failed)
        self._compare_worker.start()

    def _on_compare_done(self, tagged_local: list, tagged_remote: list):
        self._finalize_worker("_compare_worker")
        self._local_skills = tagged_local
        self._remote_skills = tagged_remote
        self._panels.local_panel.display_skills(self._local_skills)
        self._panels.remote_panel.display_skills(self._remote_skills)
        synced = sum(1 for s in self._local_skills if s.hash == "synced")
        self.statusBar().showMessage(
            f"比对完成：{synced} 已同步 / {len(self._local_skills)} 本机 / "
            f"{len(self._remote_skills)} 远程"
        )
        self._set_status_chip("done", f"✓ 已同步 {synced}/{len(self._local_skills)}")

    def _on_compare_failed(self, msg: str):
        self._finalize_worker("_compare_worker")
        # Fall back to direction-only tagging so user still sees the lists
        local_keys = {(s.name, s.tool) for s in self._local_skills}
        remote_keys = {(s.name, s.tool) for s in self._remote_skills}
        for s in self._local_skills:
            s.hash = "synced" if (s.name, s.tool) in remote_keys else "local-only"
        for s in self._remote_skills:
            s.hash = "synced" if (s.name, s.tool) in local_keys else "remote-only"
        self._panels.local_panel.display_skills(self._local_skills)
        self._panels.remote_panel.display_skills(self._remote_skills)
        self.statusBar().showMessage(f"比对失败：{msg}")
        self._set_status_chip("error", "比对失败")
        try:
            self._toast.show_message(f"比对失败：{msg}", success=False, duration=3000)
        except Exception:
            pass

    # ---- Connection health check (PR-3) ----

    def _check_remote_health(self):
        """Run an SSH health probe for the current active connection.

        Result is rendered as the colored status dot in the remote panel.
        Safe to call repeatedly: in-flight worker is replaced.
        """
        if not self._active_connection:
            self._panels.remote_panel.set_connection_status("unknown")
            return
        # Replace any in-flight worker
        self._finalize_worker("_health_worker")
        # Yellow "checking" while we probe
        host = self._active_connection.host
        self._panels.remote_panel.set_connection_status(
            "checking", f"正在检测 {host} ..."
        )
        self._health_worker = _HealthCheckWorker(
            self._ssh, self._active_connection, parent=self,
        )
        self._health_worker.finished.connect(self._on_health_done)
        self._health_worker.start()

    def _on_health_done(self, status: str, detail: str):
        self._finalize_worker("_health_worker")
        if not self._active_connection:
            return
        conn = self._active_connection
        if status == "online":
            tip = f"已连接 {conn.username}@{conn.host}:{conn.port}"
        else:
            tip = f"无法连接 {conn.username}@{conn.host}:{conn.port}\n{detail}"
        self._panels.remote_panel.set_connection_status(status, tip)
        # If a refresh was queued while we were unknown, kick it now.
        if status == "online" and not self._remote_skills:
            self._refresh_remote(self._sidebar.active_view)

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

    # ---- Status chip + hash-compare toggle ----

    def _set_status_chip(self, state: str, text: str = ""):
        """Top-right corner chip — single source of truth for "what's busy now".

        We removed the old window-wide BusyCursor (which made the whole UI
        feel frozen) and surface progress here instead.

        state ∈ {idle, scanning_local, scanning_remote, comparing, done, error}
        """
        styles = {
            "idle": ("#6c7086", "transparent", text or "就绪"),
            "scanning_local": ("#1e1e2e", "#f9e2af", text or "⟳ 扫描本机…"),
            "scanning_remote": ("#1e1e2e", "#f9e2af", text or "⟳ 扫描远程…"),
            "comparing": ("#1e1e2e", "#89dceb", text or "⟳ 比对哈希…"),
            "done": ("#1e1e2e", "#a6e3a1", text or "✓ 完成"),
            "error": ("#1e1e2e", "#f38ba8", text or "✗ 失败"),
        }
        fg, bg, label = styles.get(state, styles["idle"])
        self._status_chip.setText(label)
        self._status_chip.setStyleSheet(
            f"QLabel {{ font-size: 11px; padding: 2px 8px; border-radius: 8px;"
            f"color: {fg}; background: {bg}; }}"
        )
        # auto-fade "done" back to idle after 3s; cancel any pending fade
        self._chip_clear_timer.stop()
        if state == "done":
            self._chip_clear_timer.start(3000)

    def _on_hash_compare_toggled(self, checked: bool):
        """User flipped the master switch; persist + re-render.

        - ON  : trigger a fresh compare if both sides already loaded.
        - OFF : cancel any in-flight comparator, mark all skills "off".
        """
        self._hash_compare_enabled = bool(checked)
        try:
            self._settings.setValue(
                "ui/hash_compare_enabled", self._hash_compare_enabled
            )
        except Exception as e:  # pragma: no cover
            logger.warning("Failed to persist hash_compare_enabled: %s", e)

        if self._hash_compare_enabled:
            if self._local_skills or self._remote_skills:
                # Show loading tags during the upcoming compare
                for s in self._local_skills:
                    s.hash = "loading"
                for s in self._remote_skills:
                    s.hash = "loading"
                self._panels.local_panel.display_skills(self._local_skills)
                self._panels.remote_panel.display_skills(self._remote_skills)
            self._auto_compare()
        else:
            # Stop any in-flight comparator and clear hash status.
            self._finalize_worker("_compare_worker")
            for s in self._local_skills:
                s.hash = "off"
            for s in self._remote_skills:
                s.hash = "off"
            self._panels.local_panel.display_skills(self._local_skills)
            self._panels.remote_panel.display_skills(self._remote_skills)
            self._set_status_chip("done", "校验已关闭")
            self.statusBar().showMessage("内容一致性校验已关闭")

    def closeEvent(self, event):
        logger.info("Application shutting down")
        self._ssh.close_all()
        super().closeEvent(event)
