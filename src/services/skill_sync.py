"""Skill 同步引擎：备份、原子复制、校验、回滚 (F4)"""

import io
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from src.config import (
    BACKUP_DIR, BACKUP_RETENTION_DAYS,
    SYNC_DIRECTION_PUSH, SYNC_DIRECTION_PULL,
)
from src.services.skill_scanner import SkillInfo
from src.services.skill_hasher import SkillHasher
from src.services.ssh_manager import SSHManager
from src.models.connection import Connection
from src.models.project import Project
from src.models.sync_history import SyncRecord, SyncHistoryModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SyncTask:
    skill_name: str
    source_path: str
    target_path: str
    source_device: str
    target_device: str
    source_tool: str
    target_tool: str
    is_dir: bool
    expected_hash: str
    source_level: str = "global"
    target_level: str = "global"
    source_project_id: Optional[str] = None
    target_project_id: Optional[str] = None


@dataclass
class SyncResult:
    task: SyncTask
    status: str  # "success" | "failed" | "skipped"
    detail: str = ""


class SkillSyncService:
    """Orchestrate sync operations with backup, atomic copy, and rollback."""

    def __init__(self, ssh_manager: SSHManager, hasher: SkillHasher):
        self._ssh = ssh_manager
        self._hasher = hasher

    # ---- Task Preparation ----

    def prepare_tasks(
        self,
        skills: list[SkillInfo],
        direction: str,
        sync_level: str,
        target_tools: list[str],
        source_project: Optional[Project] = None,
        target_project: Optional[Project] = None,
        source_connection: Optional[Connection] = None,
        target_connection: Optional[Connection] = None,
    ) -> list[SyncTask]:
        """Map selected skills to sync tasks based on direction and level."""
        tasks: list[SyncTask] = []
        for skill in skills:
            for tool in target_tools:
                task = self._make_task(
                    skill, tool, direction, sync_level,
                    source_project, target_project,
                    source_connection, target_connection,
                )
                if task:
                    tasks.append(task)
        return tasks

    def _make_task(self, skill, target_tool, direction, sync_level,
                   source_project, target_project,
                   source_conn, target_conn) -> Optional[SyncTask]:
        """Create a single sync task. Returns None if the mapping is N/A."""
        source_level, target_level = self._resolve_levels(sync_level)
        # resolve source and target paths
        if direction == SYNC_DIRECTION_PUSH:
            source_path = skill.path
            source_device = "local" if skill.device_type == "local" else skill.device
            target_device = target_conn.name if target_conn else "local"
            target_path = self._resolve_target_path(
                skill.name, target_tool, sync_level, target_project, target_conn
            )
        else:  # pull
            source_path = skill.path
            source_device = skill.device
            target_device = "local"
            target_path = self._resolve_target_path(
                skill.name, target_tool, sync_level, target_project, target_conn
            )

        if not target_path:
            return None

        return SyncTask(
            skill_name=skill.name,
            source_path=source_path,
            target_path=target_path,
            source_device=source_device,
            target_device=target_device,
            source_tool=skill.tool,
            target_tool=target_tool,
            is_dir=skill.is_dir,
            expected_hash=skill.hash or "",
            source_level=source_level,
            target_level=target_level,
            source_project_id=skill.project_id if source_level == "project" else None,
            target_project_id=target_project.id if target_level == "project" and target_project else None,
        )

    def _resolve_target_path(self, skill_name: str, target_tool: str,
                             sync_level: str,
                             target_project: Optional[Project],
                             target_conn: Optional[Connection]) -> str:
        """Resolve target filesystem path for a skill."""
        from src.config import GLOBAL_SKILL_PATHS, PROJECT_SKILL_SUBDIRS

        if sync_level in ("global_to_global", "project_to_global"):
            # target is global
            if target_conn:
                remote_home = self._ssh.get_remote_home(target_conn)
                base = Path(remote_home) / f".{target_tool}" / "skills"
                if target_tool == "cc-switch":
                    base = Path(remote_home) / ".cc-switch" / "skills"
            else:
                base = GLOBAL_SKILL_PATHS.get(target_tool)
            return str(base / skill_name) if base else ""

        if sync_level in ("global_to_project", "project_to_project"):
            if not target_project:
                return ""
            subdir = PROJECT_SKILL_SUBDIRS.get(target_tool, "")
            if target_conn:
                if not target_project.remote_path:
                    return ""
                base = Path(target_project.remote_path) / subdir
            else:
                base = Path(target_project.local_path) / subdir
            return str(base / skill_name)

        return ""

    @staticmethod
    def _resolve_levels(sync_level: str) -> tuple[str, str]:
        mapping = {
            "global_to_global": ("global", "global"),
            "global_to_project": ("global", "project"),
            "project_to_global": ("project", "global"),
            "project_to_project": ("project", "project"),
        }
        return mapping.get(sync_level, ("global", "global"))

    # ---- Execution ----

    def execute(
        self,
        tasks: list[SyncTask],
        source_connection: Optional[Connection] = None,
        target_connection: Optional[Connection] = None,
        conflict_strategy: str = "ask",
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
        on_conflict: Optional[Callable[[SyncTask], str]] = None,
    ) -> list[SyncResult]:
        """Execute sync tasks sequentially. Emits progress and conflict callbacks."""
        results: list[SyncResult] = []
        total = len(tasks)

        for i, task in enumerate(tasks):
            backup_path = ""
            # check conflict
            if self._target_exists(task, target_connection):
                if conflict_strategy == "skip":
                    results.append(SyncResult(task, "skipped", "目标已存在，策略为跳过"))
                    if on_progress:
                        on_progress(i, total, task.skill_name, "skipped")
                    continue
                elif conflict_strategy == "ask" and on_conflict:
                    choice = on_conflict(task)
                    if choice == "skip":
                        results.append(SyncResult(task, "skipped", "用户跳过"))
                        if on_progress:
                            on_progress(i, total, task.skill_name, "skipped")
                        continue
                    elif choice == "keep_both":
                        task.target_path = self._rename_for_keep(task.target_path)

            if on_progress:
                on_progress(i, total, task.skill_name, "copying")

            try:
                # backup existing target
                backup_path = self._backup_target(task, target_connection)
                # copy
                self._copy_skill(task, source_connection, target_connection)
                # verify
                if not self._verify(task, target_connection):
                    self._restore_backup(backup_path, task.target_path, target_connection)
                    results.append(SyncResult(task, "failed", "校验失败，已回滚"))
                    if on_progress:
                        on_progress(i, total, task.skill_name, "failed")
                    continue

                # record
                self._record(task, "success")
                results.append(SyncResult(task, "success"))
                if on_progress:
                    on_progress(i, total, task.skill_name, "success")

            except Exception as e:
                logger.error(f"Sync failed for {task.skill_name}: {e}")
                self._restore_backup(backup_path, task.target_path, target_connection)
                self._record(task, "failed", str(e))
                results.append(SyncResult(task, "failed", str(e)))
                if on_progress:
                    on_progress(i, total, task.skill_name, "failed")

        return results

    # ---- Internal ----

    def _target_exists(self, task: SyncTask,
                       target_conn: Optional[Connection]) -> bool:
        if target_conn:
            return self._ssh.file_exists(target_conn, task.target_path)
        return Path(task.target_path).exists()

    def _backup_target(self, task: SyncTask,
                       target_conn: Optional[Connection]) -> str:
        """Create backup of existing target. Returns backup path or empty string."""
        if not self._target_exists(task, target_conn):
            return ""

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUP_DIR / ts
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = str(backup_dir / task.skill_name)
        if task.is_dir:
            backup_path = f"{backup_path}.tar.gz"

        try:
            if task.is_dir:
                if target_conn:
                    data = self._ssh.download_directory(target_conn, task.target_path)
                else:
                    data = self._archive_local_dir(task.target_path)
                Path(backup_path).write_bytes(data)
            elif target_conn:
                data = self._ssh.read_file(target_conn, task.target_path)
                Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
                Path(backup_path).write_bytes(data)
            else:
                shutil.copy2(task.target_path, backup_path)
        except Exception as e:
            logger.warning(f"Backup failed for {task.skill_name}: {e}")
            return ""

        return backup_path

    def _restore_backup(self, backup_path: str, target_path: str,
                        target_conn: Optional[Connection]):
        if not backup_path or not Path(backup_path).exists():
            return
        try:
            self._delete_target(target_path, target_conn)
            if target_conn and backup_path.endswith(".tar.gz"):
                self._ssh.extract_archive(target_conn, Path(backup_path).read_bytes(), target_path)
            elif target_conn:
                data = Path(backup_path).read_bytes()
                self._ssh.mkdir_p(target_conn, str(Path(target_path).parent))
                self._ssh.write_file(target_conn, target_path, data)
            elif backup_path.endswith(".tar.gz"):
                self._extract_local_archive(Path(backup_path).read_bytes(), target_path)
            else:
                shutil.copy2(backup_path, target_path)
        except Exception as e:
            logger.error(f"Rollback failed for {target_path}: {e}")

    def _copy_skill(self, task: SyncTask,
                    source_conn: Optional[Connection],
                    target_conn: Optional[Connection]):
        """Atomic copy: write to temp, verify, rename."""
        tmp_target = f"{task.target_path}.tmp-{uuid.uuid4().hex[:8]}"
        target_dir = str(Path(task.target_path).parent)

        # ensure target dir
        if target_conn:
            self._ssh.mkdir_p(target_conn, target_dir)
        else:
            Path(target_dir).mkdir(parents=True, exist_ok=True)

        # copy via appropriate method
        if source_conn and target_conn:
            # remote → remote (two-hop via local)
            if task.is_dir:
                data = self._ssh.download_directory(source_conn, task.source_path)
                self._ssh.extract_archive(target_conn, data, tmp_target)
            else:
                data = self._ssh.read_file(source_conn, task.source_path)
                self._ssh.write_file(target_conn, tmp_target, data)
        elif source_conn:
            # remote → local
            if task.is_dir:
                data = self._ssh.download_directory(source_conn, task.source_path)
                self._extract_local_archive(data, tmp_target)
            else:
                data = self._ssh.read_file(source_conn, task.source_path)
                Path(tmp_target).write_bytes(data)
        elif target_conn:
            # local → remote
            if task.is_dir:
                data = self._archive_local_dir(task.source_path)
                self._ssh.extract_archive(target_conn, data, tmp_target)
            else:
                data = Path(task.source_path).read_bytes()
                self._ssh.write_file(target_conn, tmp_target, data)
        else:
            # local → local
            if task.is_dir:
                shutil.copytree(task.source_path, tmp_target)
            else:
                shutil.copy2(task.source_path, tmp_target)

        # hash verification on temp (compare against real SHA-256 only)
        if task.expected_hash and len(task.expected_hash) == 64 and all(
            c in '0123456789abcdef' for c in task.expected_hash
        ):
            if target_conn:
                actual = self._ssh.compute_remote_hash(target_conn, tmp_target)
            else:
                actual = SkillHasher.compute_local_hash(tmp_target)
            if actual and actual != task.expected_hash:
                raise ValueError(
                    f"Hash mismatch for {task.skill_name}: "
                    f"expected {task.expected_hash[:8]}..., got {actual[:8]}..."
                )

        # rename temp → actual (atomic)
        if target_conn:
            self._delete_target(task.target_path, target_conn)
            self._ssh.rename(target_conn, tmp_target, task.target_path)
        else:
            # remove existing first
            self._delete_target(task.target_path, None)
            os.replace(tmp_target, task.target_path)

    def _verify(self, task: SyncTask,
                target_conn: Optional[Connection]) -> bool:
        """Verify target hash matches expected.

        Note: expected_hash may be a status tag (set by UI classification)
        rather than a real SHA-256 hash. In that case verification is skipped.
        """
        if not task.expected_hash:
            return True
        if task.expected_hash in (
            "synced", "conflict", "local-only", "remote-only", "unknown", "",
        ):
            logger.debug(
                "Skipping hash verify for %s: expected_hash is a status tag '%s'",
                task.skill_name, task.expected_hash,
            )
            return True
        if target_conn:
            actual = self._ssh.compute_remote_hash(target_conn, task.target_path)
        else:
            actual = SkillHasher.compute_local_hash(task.target_path)
        return actual == task.expected_hash

    def _record(self, task: SyncTask, status: str, detail: str = ""):
        rec = SyncRecord(
            direction=SYNC_DIRECTION_PUSH if task.source_device == "local"
                      else SYNC_DIRECTION_PULL,
            source_device=task.source_device,
            source_level=task.source_level,
            source_project_id=task.source_project_id,
            source_tool=task.source_tool,
            target_device=task.target_device,
            target_level=task.target_level,
            target_project_id=task.target_project_id,
            target_tool=task.target_tool,
            skill_name=task.skill_name,
            status=status,
            detail=detail,
        )
        SyncHistoryModel.add(rec)

    def _delete_target(self, target_path: str,
                       target_conn: Optional[Connection]):
        try:
            if target_conn:
                self._ssh.delete(target_conn, target_path)
            elif Path(target_path).is_dir():
                shutil.rmtree(target_path, ignore_errors=True)
            elif Path(target_path).exists():
                Path(target_path).unlink()
        except Exception:
            pass

    @staticmethod
    def _archive_local_dir(path: str) -> bytes:
        """Tar.gz a local directory, applying the same SKILL_IGNORE_* filters
        as the hashers so two sides agree on byte content after sync."""
        from src.services.skill_hasher import should_ignore_file
        buffer = io.BytesIO()
        root = Path(path)
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for entry in sorted(root.rglob("*")):
                if entry.is_file():
                    rel = entry.relative_to(root).as_posix()
                    if should_ignore_file(rel):
                        continue
                tar.add(entry, arcname=entry.relative_to(root))
        return buffer.getvalue()

    @staticmethod
    def _extract_local_archive(data: bytes, target_path: str):
        target = Path(target_path)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(target)

    @staticmethod
    def _rename_for_keep(target_path: str) -> str:
        p = Path(target_path)
        stem = p.stem
        suffix = p.suffix
        return str(p.parent / f"{stem}_from_sync{suffix}")

    @staticmethod
    def cleanup_old_backups(retention_days: int = BACKUP_RETENTION_DAYS):
        if not BACKUP_DIR.exists():
            return
        cutoff = datetime.now().timestamp() - retention_days * 86400
        for d in BACKUP_DIR.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                logger.info(f"Cleaned up old backup: {d}")
