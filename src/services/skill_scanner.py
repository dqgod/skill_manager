"""Skill 扫描服务：发现本地和远程 skill (F1, F2)"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import GLOBAL_SKILL_PATHS, PROJECT_SKILL_SUBDIRS, ALL_TOOLS


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

    # ---- Local Scanning ----

    def scan_local_global(self, tools: Optional[list[str]] = None) -> list[SkillInfo]:
        """Scan all global skill directories on the local machine."""
        if tools is None:
            tools = [t.value for t in ALL_TOOLS]
        skills: list[SkillInfo] = []
        for tool_name in tools:
            base = GLOBAL_SKILL_PATHS.get(tool_name)
            if not base or not base.exists():
                continue
            skills.extend(self._scan_directory(base, tool=tool_name,
                                                level="global", device="local"))
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
        skills: list[SkillInfo] = []
        for tool_name in tools:
            base = GLOBAL_SKILL_PATHS.get(tool_name)
            if not base:
                continue
            skills.extend(self._scan_remote_directory(
                conn, str(base), tool=tool_name,
                level="global", device=conn.name,
            ))
        return skills

    def scan_remote_project(self, conn, project) -> list[SkillInfo]:
        if self._ssh is None or not project.remote_path:
            return []
        skills: list[SkillInfo] = []
        for tool_name in project.tool_list():
            subdir = PROJECT_SKILL_SUBDIRS.get(tool_name)
            if not subdir:
                continue
            remote_base = f"{project.remote_path}/{subdir}"
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
        entries = self._ssh.list_dir(conn, remote_path)
        for entry in sorted(entries, key=lambda e: e.name):
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
                is_dir=entry.is_dir,
            ))
        return skills

    # ---- Helpers ----

    def _scan_directory(self, base: Path, *, tool: str, level: str,
                        device: str, project_id: Optional[str] = None,
                        project_name: Optional[str] = None) -> list[SkillInfo]:
        skills: list[SkillInfo] = []
        if not base.is_dir():
            return skills
        for entry in sorted(base.iterdir()):
            is_dir = entry.is_dir()
            skills.append(SkillInfo(
                name=entry.name,
                tool=tool,
                path=str(entry.resolve()),
                level=level,
                device=device,
                device_type="local",
                project_id=project_id,
                project_name=project_name,
                size=self._entry_size(entry) if not is_dir else self._dir_size(entry),
                modified_at=datetime.fromtimestamp(
                    entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                is_dir=is_dir,
            ))
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
