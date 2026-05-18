"""项目注册与管理服务 (F6)"""

from pathlib import Path
from typing import Optional

from src.config import PROJECT_SKILL_SUBDIRS
from src.models.project import Project, ProjectModel


class ProjectService:
    @staticmethod
    def register(
        name: str,
        local_path: str,
        remote_connection_id: Optional[str] = None,
        remote_path: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ) -> Project:
        """Validate and register a project. Raises ValueError on bad input."""
        name = name.strip()
        if not name:
            raise ValueError("项目名称不能为空")

        local = Path(local_path).resolve()
        if not local.exists():
            raise ValueError(f"项目路径不存在: {local_path}")
        if not local.is_dir():
            raise ValueError(f"项目路径不是目录: {local_path}")

        # check duplicate
        existing = ProjectModel.get_by_local_path(str(local))
        if existing:
            raise ValueError(f"该路径已注册为项目: {existing.name}")

        proj = Project(
            name=name,
            local_path=str(local),
            remote_connection_id=remote_connection_id or None,
            remote_path=remote_path or None,
            tools=",".join(tools) if tools else "codex,claude",
        )
        ProjectModel.save(proj)
        return proj

    @staticmethod
    def auto_detect_skill_dirs(project: Project) -> dict[str, bool]:
        """Check which skill subdirs exist for the project."""
        base = Path(project.local_path)
        result: dict[str, bool] = {}
        for tool in project.tool_list():
            subdir = PROJECT_SKILL_SUBDIRS.get(tool)
            if subdir:
                result[tool] = (base / subdir).is_dir()
        return result

    @staticmethod
    def ensure_skill_dirs(project: Project, tools: Optional[list[str]] = None):
        """Create missing skill directories for the project."""
        base = Path(project.local_path)
        tlist = tools or project.tool_list()
        for tool in tlist:
            subdir = PROJECT_SKILL_SUBDIRS.get(tool)
            if subdir:
                (base / subdir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def update(
        project: Project,
        name: Optional[str] = None,
        remote_connection_id: Optional[str] = None,
        remote_path: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ):
        if name is not None:
            project.name = name.strip()
        if remote_connection_id is not None:
            project.remote_connection_id = remote_connection_id or None
        if remote_path is not None:
            project.remote_path = remote_path or None
        if tools is not None:
            project.tools = ",".join(tools)
        ProjectModel.save(project)

    @staticmethod
    def delete(project_id: str):
        ProjectModel.delete(project_id)
