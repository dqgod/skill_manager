"""Skill 扫描服务：发现本地和远程 skill (F1, F2)"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import GLOBAL_SKILL_PATHS, PROJECT_SKILL_SUBDIRS, ALL_TOOLS
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SkillInfo:
    name: str
    tool: str
    path: str
    level: str  # "global" | "project"
    device: str  # "local" or connection_name
    device_type: str  # "local" | "remote"
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    size: int = 0
    modified_at: str = ""
    is_dir: bool = False
    hash: Optional[str] = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """Unique identifier within a single scan context: (name, tool)."""
        return f"{self.name}|{self.tool}"


class SkillScanner:
    """Discover skills from local and remote filesystems.

    Local scanning is synchronous (fast, sub-3s).
    Remote scanning requires an SSHManager instance (Phase 3).
    """

    def __init__(self, ssh_manager=None):
        self._ssh = ssh_manager

    # ---- Unified entry (PR-1) ----

    def scan(self, source, projects: Optional[list] = None,
             connection=None) -> list[SkillInfo]:
        """单一扫描入口：根据 SkillSource 决定调度本地/远程、全局/项目。

        参数：
          source     —— SkillSource 实例（必填）
          projects   —— 当前已注册项目（解析 source.project_id 用）
          connection —— 当 source.is_remote 时必须给出对应 Connection 实体；
                        通常调用方按 source.connection_name 在 ConnectionModel
                        里查一次再传进来。
        """
        # 延迟导入避免循环依赖
        from src.models.skill_source import SkillSource

        if not isinstance(source, SkillSource):
            raise TypeError(f"scan() requires SkillSource, got {type(source)!r}")
        if not source.is_valid():
            logger.warning("scan() got invalid SkillSource: %r", source)
            return []

        projects = projects or []

        if source.is_local:
            if source.is_global:
                return self.scan_local_global()
            proj = next((p for p in projects if p.id == source.project_id), None)
            if proj is None:
                logger.warning("scan(): local project %s not found", source.project_id)
                return []
            return self.scan_local_project(proj)

        # remote
        if connection is None:
            logger.warning(
                "scan(): remote source requires a Connection but got None "
                "(source=%r)", source,
            )
            return []
        if source.is_global:
            return self.scan_remote_global(connection)
        proj = next((p for p in projects if p.id == source.project_id), None)
        if proj is None:
            logger.warning("scan(): remote project %s not found", source.project_id)
            return []
        return self.scan_remote_project(connection, proj)

    # ---- Local Scanning ----

    def scan_local_global(self, tools: Optional[list[str]] = None) -> list[SkillInfo]:
        """Scan all global skill directories on the local machine."""
        if tools is None:
            tools = [t.value for t in ALL_TOOLS]
        logger.info("Starting local global scan (tools=%s)", tools)
        skills: list[SkillInfo] = []
        for tool_name in tools:
            base = GLOBAL_SKILL_PATHS.get(tool_name)
            logger.info("Local scan path for %s: %s", tool_name, base)
            if not base or not base.exists():
                logger.warning("Local skill path does not exist: %s", base)
                continue
            skills.extend(self._scan_directory(base, tool=tool_name,
                                                level="global", device="local"))
        logger.info("Local global scan done: %d skills found", len(skills))
        return skills

    def scan_local_project(self, project) -> list[SkillInfo]:
        """Scan skill directories within a registered project."""
        proj_path = Path(project.local_path)
        if not proj_path.exists():
            return []
        skills: list[SkillInfo] = []
        for tool_name in project.tool_list():
            subdir = PROJECT_SKILL_SUBDIRS.get(tool_name)
            if not subdir:
                continue
            base = proj_path / subdir
            if base.exists():
                skills.extend(self._scan_directory(
                    base, tool=tool_name, level="project",
                    device="local", project_id=project.id,
                    project_name=project.name,
                ))
        return skills

    # ---- Remote Scanning ----

    def scan_remote_global(self, conn, tools=None) -> list[SkillInfo]:
        if self._ssh is None:
            return []
        if tools is None:
            tools = [t.value for t in ALL_TOOLS]
        remote_home = self._ssh.get_remote_home(conn)
        logger.info("Starting remote global scan on %s@%s (home=%s, tools=%s)",
                     conn.username, conn.host, remote_home, tools)
        # Build remote skill paths — do NOT reuse local GLOBAL_SKILL_PATHS
        remote_skill_paths = {
            "codex": f"{remote_home}/.codex/skills",
            "claude": f"{remote_home}/.claude/skills",
            "cc-switch": f"{remote_home}/.cc-switch/skills",
        }
        skills: list[SkillInfo] = []
        for tool_name in tools:
            base = remote_skill_paths.get(tool_name)
            if not base:
                continue
            logger.info("Remote scan path for %s: %s", tool_name, base)
            skills.extend(self._scan_remote_directory(
                conn, base, tool=tool_name,
                level="global", device=conn.name,
            ))
        logger.info("Remote global scan done on %s@%s: %d skills found",
                     conn.username, conn.host, len(skills))
        return skills

    def scan_remote_project(self, conn, project) -> list[SkillInfo]:
        if self._ssh is None or not project.remote_path:
            return []
        logger.info("Starting remote project scan: %s (remote_path=%s)",
                     project.name, project.remote_path)
        skills: list[SkillInfo] = []
        for tool_name in project.tool_list():
            subdir = PROJECT_SKILL_SUBDIRS.get(tool_name)
            if not subdir:
                continue
            remote_base = f"{project.remote_path}/{subdir}"
            logger.info("Remote project scan path for %s/%s: %s",
                        project.name, tool_name, remote_base)
            skills.extend(self._scan_remote_directory(
                conn, remote_base, tool=tool_name,
                level="project", device=conn.name,
                project_id=project.id, project_name=project.name,
            ))
        return skills

    def _scan_remote_directory(self, conn, remote_path: str, *, tool: str,
                               level: str, device: str,
                               project_id: Optional[str] = None,
                               project_name: Optional[str] = None) -> list[SkillInfo]:
        skills: list[SkillInfo] = []
        logger.debug("Scanning remote path: %s", remote_path)
        entries = self._ssh.list_dir(conn, remote_path)
        if not entries:
            logger.info("Remote path empty or inaccessible: %s", remote_path)
        for entry in sorted(entries, key=lambda e: e.name):
            # Only directories containing SKILL.md are valid skills
            if not entry.is_dir:
                continue
            skill_md = f"{entry.path}/SKILL.md"
            if not self._ssh.file_exists(conn, skill_md):
                continue
            skills.append(SkillInfo(
                name=entry.name,
                tool=tool,
                path=entry.path,
                level=level,
                device=device,
                device_type="remote",
                project_id=project_id,
                project_name=project_name,
                size=entry.size,
                modified_at=datetime.fromtimestamp(
                    entry.modified_at).strftime("%Y-%m-%d %H:%M"),
                is_dir=True,
            ))
        logger.info("Scanned remote %s: %d skills — %s",
                     remote_path, len(skills), [s.name for s in skills])
        return skills

    # ---- Helpers ----

    def _scan_directory(self, base: Path, *, tool: str, level: str,
                        device: str, project_id: Optional[str] = None,
                        project_name: Optional[str] = None) -> list[SkillInfo]:
        skills: list[SkillInfo] = []
        if not base.is_dir():
            return skills
        raw_entries = list(base.iterdir())
        logger.debug("Scanning directory: %s (%d raw entries)", base, len(raw_entries))
        for entry in sorted(raw_entries):
            # Only directories containing SKILL.md are valid skills
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            skills.append(SkillInfo(
                name=entry.name,
                tool=tool,
                path=str(entry.resolve()),
                level=level,
                device=device,
                device_type="local",
                project_id=project_id,
                project_name=project_name,
                size=self._dir_size(entry),
                modified_at=datetime.fromtimestamp(
                    entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                is_dir=True,
            ))
        logger.info("Scanned %s: %d skills — %s",
                     base, len(skills), [s.name for s in skills])
        return skills

    @staticmethod
    def _entry_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except OSError:
            pass
        return total
