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
from src.models.skill_source import (
    SkillSource, local_global, remote_global,
)
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


class _SourceScanWorker(QThread):
    """通用 SkillSource 扫描 worker。

    取代以前的 _LocalScanWorker / _RemoteScanWorker —— 只要给定一个
    SkillSource 和（如果 remote 的话）对应 Connection，本 worker 就能
    跑出该侧的 skill 列表，UI 一侧无需关心是本机还是远程。
    """

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, scanner: SkillScanner, source: SkillSource,
                 projects: list, connection=None, parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._source = source
        self._projects = projects
        self._connection = connection

    def run(self):
        try:
            skills = self._scanner.scan(
                self._source,
                projects=self._projects,
                connection=self._connection,
            )
        except Exception as e:
            logger.warning(
                "[SourceScan] failed source=%r conn=%r err=%s",
                self._source, getattr(self._connection, "name", None), e,
            )
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
        return f"扫描失败：{msg}"


# 兼容别名：旧测试 / 旧代码仍可能 import 这两个名字
_LocalScanWorker = _SourceScanWorker
_RemoteScanWorker = _SourceScanWorker


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

    Returns the *tagged* left + right lists; emits failure as empty results.
    The terms "left/right" intentionally replace "local/remote" because the
    new model lets either side be local or remote.
    """
    finished = Signal(list, list)  # tagged_left, tagged_right
    failed = Signal(str)

    def __init__(self, hasher: SkillHasher, left: list, right: list,
                 left_connection=None, right_connection=None, parent=None):
        super().__init__(parent)
        self._hasher = hasher
        self._left = left
        self._right = right
        self._left_conn = left_connection
        self._right_conn = right_connection

    def run(self):
        try:
            diff = self._hasher.compare(
                self._left, self._right,
                left_connection=self._left_conn,
                right_connection=self._right_conn,
            )
            synced = {(s.name, s.tool) for s in diff.synced}
            left_only = {(s.name, s.tool) for s in diff.local_only}
            right_only = {(s.name, s.tool) for s in diff.remote_only}
            conflict = {(p[0].name, p[0].tool) for p in diff.conflict}

            for s in self._left:
                key = (s.name, s.tool)
                if key in synced:
                    s.hash = "synced"
                elif key in conflict:
                    s.hash = "conflict"
                elif key in left_only:
                    s.hash = "local-only"
                else:
                    s.hash = "unknown"
            for s in self._right:
                key = (s.name, s.tool)
                if key in synced:
                    s.hash = "synced"
                elif key in conflict:
                    s.hash = "conflict"
                elif key in right_only:
                    s.hash = "remote-only"
                else:
                    s.hash = "unknown"
            self.finished.emit(self._left, self._right)
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
        # Refresh every 60s while a remote source is selected.
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_health_for_remote_panels)
        self._health_timer.start(60_000)

        self._projects: list = []
        self._connections: list = []
        self._sync_conflict_strategy = "ask"

        # Settings & persisted preferences
        self._settings = QSettings("skill_manager", "skill_manager")

        # ---- Dual-source state (PR-2) ----
        # Each panel has its own independent SkillSource.
        # Default: 左=本机/全局，右=远程[<first connection>]/全局 if available else local/global.
        self._left_source: SkillSource = SkillSource.from_json(
            self._settings.value("ui/left_source", "", type=str)
        ) or local_global()
        self._right_source: SkillSource = SkillSource.from_json(
            self._settings.value("ui/right_source", "", type=str)
        ) or local_global()
        self._left_skills: list = []
        self._right_skills: list = []
        self._left_scan_seq = 0
        self._right_scan_seq = 0

        # Hash-compare master switch (PR-Switch).
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
        # 自动选择默认 right_source = 第一个 remote（如还是 local_global 默认）
        self._maybe_pick_default_right_source()
        # Push current source options to selectors and trigger initial scans.
        self._push_source_options()
        self._refresh_side("left")
        self._refresh_side("right")

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

        # Sidebar 退出主流程：保留实例（PR-4 会演化为"预设/项目快捷"区），
        # 但当前不放进可见布局；project_changed 信号仍能在内存中维持其状态。
        self._sidebar = Sidebar()
        self._sidebar.view_changed.connect(self._on_legacy_view_changed)
        self._sidebar.add_project_requested.connect(self._on_add_project)
        self._sidebar.setVisible(False)
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
            "打开后会计算并比较两侧 skill 的内容哈希；\n"
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

        self._panels = SkillPanels(
            left_source=self._left_source, right_source=self._right_source,
        )
        left_panel = self._panels.left_panel
        left_panel.refresh_requested.connect(lambda: self._refresh_side("left"))
        left_panel.tool_changed.connect(lambda t: self._on_tool_changed("left", t))
        left_panel.selection_changed.connect(self._on_selection_changed)
        left_panel.source_changed.connect(
            lambda src: self._on_source_changed("left", src)
        )

        right_panel = self._panels.right_panel
        right_panel.refresh_requested.connect(lambda: self._refresh_side("right"))
        right_panel.tool_changed.connect(lambda t: self._on_tool_changed("right", t))
        right_panel.selection_changed.connect(self._on_selection_changed)
        right_panel.source_changed.connect(
            lambda src: self._on_source_changed("right", src)
        )

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

    def _on_legacy_view_changed(self, view_id: str):
        """旧 sidebar 仍可能发信号（隐藏后理论不再触发，但保险一下）。

        把全局/项目切换映射到 left 面板，与历史行为保持一致。
        """
        if view_id == "global":
            self._on_source_changed("left", local_global())
        else:
            proj = next((p for p in self._projects if p.id == view_id), None)
            if proj:
                from src.models.skill_source import local_project
                self._on_source_changed("left", local_project(proj.id, proj.name))

    def _on_tool_changed(self, side: str, tool: str):
        skills = self._left_skills if side == "left" else self._right_skills
        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        logger.info("[TabSwitch] _on_tool_changed side=%s tool=%s skills=%d",
                     side, tool, len(skills))
        panel.display_skills(skills)
        self._on_selection_changed()

    def _on_selection_changed(self):
        left_sel = self._panels.left_panel.selected_skills()
        right_sel = self._panels.right_panel.selected_skills()
        self._bottom_bar.update_selection_count(len(left_sel) + len(right_sel))

    def _on_source_changed(self, side: str, src: SkillSource):
        """用户在面板上挑了新 source —— 持久化、重置列表、触发刷新。"""
        logger.info("[Source] _on_source_changed side=%s -> %r", side, src)
        if side == "left":
            self._left_source = src
            self._settings.setValue("ui/left_source", src.to_json())
        else:
            self._right_source = src
            self._settings.setValue("ui/right_source", src.to_json())
        # 同步面板显示标签 + 状态
        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        panel.set_source(src)
        # 远程 source 立即触发健康检查
        if src.is_remote:
            self._check_health_for_side(side)
        self._refresh_side(side)

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
        # 把新项目列表灌给两侧的 source selector
        self._push_source_options()
        self._toast.show_message("项目列表已更新")

    # ---- Sync ----

    def _on_sync_requested(self):
        """根据 BottomBar 的 push/pull 方向决定 source/target side：

        push: 左 → 右，左侧勾选的 skill 同步到右侧目标
        pull: 右 → 左，右侧勾选的 skill 同步到左侧目标
        """
        direction = self._bottom_bar.sync_direction
        sync_level = self._bottom_bar.sync_level
        target_tools = self._bottom_bar.selected_tools

        if direction == SYNC_DIRECTION_PUSH:
            source_side, target_side = "left", "right"
        else:
            source_side, target_side = "right", "left"

        source_src = self._left_source if source_side == "left" else self._right_source
        target_src = self._left_source if target_side == "left" else self._right_source
        source_panel = (self._panels.left_panel if source_side == "left"
                        else self._panels.right_panel)

        selected = source_panel.selected_skills()
        if not selected:
            self._toast.show_message("请先在源侧选择要同步的 skill", success=False)
            return
        if not target_tools:
            self._toast.show_message("请先选择目标工具", success=False)
            return

        source_conn = self._resolve_connection(source_src) if source_src.is_remote else None
        target_conn = self._resolve_connection(target_src) if target_src.is_remote else None

        # 项目解析：源侧/目标侧各自的项目
        source_project = self._resolve_project(source_src)
        target_project = self._resolve_project(target_src)

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

        self._sync_dialog = SyncProgressDialog(len(tasks), self)
        for task in tasks:
            self._sync_dialog.add_item(task.skill_name)

        self._sync_worker = _SyncWorker(
            self._sync_svc, tasks, source_conn, target_conn,
            self._sync_conflict_strategy
        )
        self._sync_worker.progress.connect(self._on_sync_progress)
        self._sync_worker.conflict.connect(self._on_sync_conflict)
        self._sync_worker.finished.connect(self._on_sync_finished)
        self._sync_worker.start()
        self._sync_dialog.show()

    def _resolve_connection(self, src: SkillSource):
        if not src.is_remote:
            return None
        return ConnectionModel.get_by_name(src.connection_name)

    def _resolve_project(self, src: SkillSource):
        if not src.is_project:
            return None
        return next((p for p in self._projects if p.id == src.project_id), None)

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
        # 同步完两侧都刷一遍
        self._refresh_side("left")
        self._refresh_side("right")

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
        """读取所有连接 → 喂给两侧 source selector。

        新模型下这里不再"选中"任何一个连接（活跃连接的概念不存在了），
        因为左右两侧各有自己的 SkillSource。
        """
        self._connections = ConnectionModel.get_all()
        self._push_source_options()
        # 校验当前 source 是否仍然有效（连接被删除等情况）
        self._validate_sources_after_options_change()

    def _push_source_options(self):
        """把 connections + projects 推送到两侧 selector 菜单。"""
        self._panels.left_panel.set_source_options(self._connections, self._projects)
        self._panels.right_panel.set_source_options(self._connections, self._projects)

    def _validate_sources_after_options_change(self):
        """SourceSelector.set_options 已经会回退失效 source 并发 source_changed
        信号；这里只需要做最后兜底的状态同步。"""
        self._panels.left_panel.set_source(self._panels.left_panel.source)
        self._panels.right_panel.set_source(self._panels.right_panel.source)

    def _maybe_pick_default_right_source(self):
        """初始默认右侧 = 远程[第一个连接]/全局，前提是用户没有持久化偏好且有连接。"""
        if self._right_source.is_local and self._right_source.is_global:
            # 这就是 SkillSource 的"零值"——表示用户从没动过
            if self._connections:
                self._right_source = remote_global(self._connections[0].name)
                self._panels.right_panel.set_source(self._right_source)
                self._settings.setValue("ui/right_source", self._right_source.to_json())

    def _refresh_side(self, side: str):
        """统一刷新入口：根据 side 的 SkillSource 决定走 local / remote 扫描。"""
        assert side in ("left", "right")
        src = self._left_source if side == "left" else self._right_source
        worker_attr = "_left_worker" if side == "left" else "_right_worker"
        seq_attr = "_left_scan_seq" if side == "left" else "_right_scan_seq"

        logger.info("[Refresh] _refresh_side side=%s source=%r", side, src)

        # Stop any previous worker on this side
        prev = getattr(self, worker_attr, None)
        if prev is not None:
            try:
                prev.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                prev.failed.disconnect()
            except (TypeError, RuntimeError, AttributeError):
                pass
            if prev.isRunning():
                prev.quit()
                prev.wait(5000)

        seq = getattr(self, seq_attr) + 1
        setattr(self, seq_attr, seq)

        # Status chip + status bar
        self.statusBar().showMessage(f"正在扫描{side}侧...")
        self._set_status_chip(
            "scanning_remote" if src.is_remote else "scanning_local"
        )

        connection = self._resolve_connection(src) if src.is_remote else None
        worker = _SourceScanWorker(
            self._scanner, src, self._projects,
            connection=connection, parent=self,
        )
        worker.finished.connect(
            lambda skills, s=seq, sd=side:
                self._on_scan_done_guarded(sd, skills, s)
        )
        worker.failed.connect(
            lambda msg, s=seq, sd=side:
                self._on_scan_failed_guarded(sd, msg, s)
        )
        setattr(self, worker_attr, worker)
        worker.start()

    def _on_scan_done_guarded(self, side: str, skills: list, seq: int):
        cur = self._left_scan_seq if side == "left" else self._right_scan_seq
        if seq != cur:
            return
        self._finalize_worker("_left_worker" if side == "left" else "_right_worker")
        self._on_scan_side_done(side, skills)

    def _on_scan_failed_guarded(self, side: str, msg: str, seq: int):
        cur = self._left_scan_seq if side == "left" else self._right_scan_seq
        if seq != cur:
            return
        self._finalize_worker("_left_worker" if side == "left" else "_right_worker")
        if side == "left":
            self._left_skills = []
        else:
            self._right_skills = []
        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        panel.display_skills([])
        self.statusBar().showMessage(f"{side}侧扫描失败：{msg}")
        self._set_status_chip("error", f"{side}侧扫描失败")
        # 远程时把状态点改为 offline，附带原因
        src = self._left_source if side == "left" else self._right_source
        if src.is_remote:
            conn = self._resolve_connection(src)
            host = conn.host if conn else "?"
            user = conn.username if conn else "?"
            port = conn.port if conn else 22
            panel.set_connection_status(
                "offline",
                f"无法连接 {user}@{host}:{port}\n{msg}",
            )
        try:
            Toast(self).show_message(msg, duration=4000, success=False)
        except Exception:
            pass
        logger.warning("[Scan] side=%s failed: %s", side, msg)

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

    def _on_scan_side_done(self, side: str, skills: list):
        if side == "left":
            self._left_skills = skills
        else:
            self._right_skills = skills

        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        src = self._left_source if side == "left" else self._right_source

        # 远程扫描成功 = 这台远端可达（更新连接状态点为绿）
        if src.is_remote:
            conn = self._resolve_connection(src)
            if conn:
                panel.set_connection_status(
                    "online",
                    f"已连接 {conn.username}@{conn.host}:{conn.port}",
                )

        # 立即渲染（先打 loading / off 标签，再去比对）
        if self._hash_compare_enabled:
            for s in skills:
                if s.hash is None:
                    s.hash = "loading"
        else:
            for s in skills:
                s.hash = "off"
        panel.display_skills(skills)
        self.statusBar().showMessage(f"{side}侧扫描完成，{len(skills)} 个 skill")
        self._on_selection_changed()
        logger.info("[Scan] side=%s completed: %d skills", side, len(skills))

        # 两侧都扫完才比对
        other = self._right_skills if side == "left" else self._left_skills
        if self._hash_compare_enabled and skills and other:
            self._auto_compare()
        elif self._hash_compare_enabled:
            for s in skills:
                s.hash = "local-only" if side == "left" else "remote-only"
            panel.display_skills(skills)
            self._set_status_chip("done", f"✓ {side}侧 {len(skills)}")
        else:
            self._set_status_chip("done", f"✓ {side}侧 {len(skills)}（未校验）")

    def _auto_compare(self):
        """Compare left/right skills off the UI thread.

        New model: either side may be local or remote, so we resolve each
        side's connection independently before handing off to SkillHasher.
        """
        if not self._hash_compare_enabled:
            for s in self._left_skills:
                s.hash = "off"
            for s in self._right_skills:
                s.hash = "off"
            self._panels.left_panel.display_skills(self._left_skills)
            self._panels.right_panel.display_skills(self._right_skills)
            self._set_status_chip("done", "校验已关闭")
            return
        self._finalize_worker("_compare_worker")
        self.statusBar().showMessage("正在比对两侧 skill ...")
        self._set_status_chip("comparing")
        left_conn = self._resolve_connection(self._left_source)
        right_conn = self._resolve_connection(self._right_source)
        self._compare_worker = _AutoCompareWorker(
            self._hasher,
            self._left_skills,
            self._right_skills,
            left_connection=left_conn,
            right_connection=right_conn,
            parent=self,
        )
        self._compare_worker.finished.connect(self._on_compare_done)
        self._compare_worker.failed.connect(self._on_compare_failed)
        self._compare_worker.start()

    def _on_compare_done(self, tagged_left: list, tagged_right: list):
        self._finalize_worker("_compare_worker")
        self._left_skills = tagged_left
        self._right_skills = tagged_right
        self._panels.left_panel.display_skills(self._left_skills)
        self._panels.right_panel.display_skills(self._right_skills)
        synced = sum(1 for s in self._left_skills if s.hash == "synced")
        self.statusBar().showMessage(
            f"比对完成：{synced} 已同步 / {len(self._left_skills)} 左 / "
            f"{len(self._right_skills)} 右"
        )
        self._set_status_chip("done", f"✓ 已同步 {synced}/{len(self._left_skills)}")

    def _on_compare_failed(self, msg: str):
        self._finalize_worker("_compare_worker")
        # 退化为按 name/tool 是否两侧都存在来打标签，至少让用户能看清。
        left_keys = {(s.name, s.tool) for s in self._left_skills}
        right_keys = {(s.name, s.tool) for s in self._right_skills}
        for s in self._left_skills:
            s.hash = "synced" if (s.name, s.tool) in right_keys else "local-only"
        for s in self._right_skills:
            s.hash = "synced" if (s.name, s.tool) in left_keys else "remote-only"
        self._panels.left_panel.display_skills(self._left_skills)
        self._panels.right_panel.display_skills(self._right_skills)
        self.statusBar().showMessage(f"比对失败：{msg}")
        self._set_status_chip("error", "比对失败")
        try:
            self._toast.show_message(f"比对失败：{msg}", success=False, duration=3000)
        except Exception:
            pass

    # ---- Connection health check (per-side) ----

    def _refresh_health_for_remote_panels(self):
        """Periodic timer entry: probe each side that currently is remote."""
        if self._left_source.is_remote:
            self._check_health_for_side("left")
        if self._right_source.is_remote:
            self._check_health_for_side("right")

    def _check_health_for_side(self, side: str):
        """Probe SSH for the given side's source. No-op if side is local."""
        assert side in ("left", "right")
        src = self._left_source if side == "left" else self._right_source
        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        if not src.is_remote:
            return
        conn = self._resolve_connection(src)
        if not conn:
            panel.set_connection_status("unknown")
            return
        worker_attr = "_left_health_worker" if side == "left" else "_right_health_worker"
        self._finalize_worker(worker_attr)
        panel.set_connection_status("checking", f"正在检测 {conn.host} ...")
        worker = _HealthCheckWorker(self._ssh, conn, parent=self)
        worker.finished.connect(
            lambda status, detail, sd=side: self._on_health_done(sd, status, detail)
        )
        setattr(self, worker_attr, worker)
        worker.start()

    def _on_health_done(self, side: str, status: str, detail: str):
        worker_attr = "_left_health_worker" if side == "left" else "_right_health_worker"
        self._finalize_worker(worker_attr)
        src = self._left_source if side == "left" else self._right_source
        panel = self._panels.left_panel if side == "left" else self._panels.right_panel
        if not src.is_remote:
            return
        conn = self._resolve_connection(src)
        if not conn:
            return
        if status == "online":
            tip = f"已连接 {conn.username}@{conn.host}:{conn.port}"
        else:
            tip = f"无法连接 {conn.username}@{conn.host}:{conn.port}\n{detail}"
        panel.set_connection_status(status, tip)
        # 如果之前空列表是因为离线，现在恢复，自动补一次刷新。
        cur_skills = self._left_skills if side == "left" else self._right_skills
        if status == "online" and not cur_skills:
            self._refresh_side(side)

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
        # Sidebar 已退出主流程；保留 no-op 以兼容潜在外部调用。
        return

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
        prev = self._status_chip.text() if hasattr(self, "_status_chip") else "<n/a>"
        logger.info(
            "[Chip] _set_status_chip state=%s text=%r => label=%r fg=%s bg=%s "
            "(prev=%r)",
            state, text, label, fg, bg, prev,
        )
        try:
            self._status_chip.setText(label)
            self._status_chip.setStyleSheet(
                f"QLabel {{ font-size: 11px; padding: 2px 8px; border-radius: 8px;"
                f"color: {fg}; background: {bg}; }}"
            )
        except RuntimeError as e:
            # _status_chip's underlying C++ object was deleted (e.g. window
            # is being torn down). Log and bail; nothing else can recover.
            logger.warning("[Chip] setText failed (object deleted?): %s", e)
            return
        # auto-fade "done" back to idle after 3s; cancel any pending fade
        was_active = self._chip_clear_timer.isActive()
        self._chip_clear_timer.stop()
        if state == "done":
            self._chip_clear_timer.start(3000)
            logger.debug("[Chip] auto-fade timer (3s) armed; was_active=%s", was_active)
        elif was_active:
            logger.debug("[Chip] auto-fade timer cancelled by new state=%s", state)

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
            if self._left_skills or self._right_skills:
                # Show loading tags during the upcoming compare
                for s in self._left_skills:
                    s.hash = "loading"
                for s in self._right_skills:
                    s.hash = "loading"
                self._panels.left_panel.display_skills(self._left_skills)
                self._panels.right_panel.display_skills(self._right_skills)
            self._auto_compare()
        else:
            # Stop any in-flight comparator and clear hash status.
            self._finalize_worker("_compare_worker")
            for s in self._left_skills:
                s.hash = "off"
            for s in self._right_skills:
                s.hash = "off"
            self._panels.left_panel.display_skills(self._left_skills)
            self._panels.right_panel.display_skills(self._right_skills)
            self._set_status_chip("done", "校验已关闭")
            self.statusBar().showMessage("内容一致性校验已关闭")

    def closeEvent(self, event):
        logger.info("Application shutting down")
        self._ssh.close_all()
        super().closeEvent(event)
