"""项目配置数据类与 CRUD"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.models.db import get_connection


@dataclass
class Project:
    name: str
    local_path: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    remote_connection_id: Optional[str] = None
    remote_path: Optional[str] = None
    tools: str = "codex,claude"
    created_at: str = ""
    updated_at: str = ""

    def tool_list(self) -> list[str]:
        return [t.strip() for t in self.tools.split(",") if t.strip()]


class ProjectModel:
    @staticmethod
    def save(proj: Project) -> None:
        db = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not proj.created_at:
            proj.created_at = now
        proj.updated_at = now
        db.execute(
            """INSERT OR REPLACE INTO projects
               (id, name, local_path, remote_connection_id,
                remote_path, tools, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (proj.id, proj.name, proj.local_path, proj.remote_connection_id,
             proj.remote_path, proj.tools, proj.created_at, proj.updated_at),
        )
        db.commit()

    @staticmethod
    def get(proj_id: str) -> Optional[Project]:
        db = get_connection()
        row = db.execute("SELECT * FROM projects WHERE id=?", (proj_id,)).fetchone()
        return ProjectModel._row_to_proj(row) if row else None

    @staticmethod
    def get_all() -> list[Project]:
        db = get_connection()
        rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [ProjectModel._row_to_proj(r) for r in rows]

    @staticmethod
    def delete(proj_id: str) -> None:
        db = get_connection()
        db.execute("DELETE FROM projects WHERE id=?", (proj_id,))
        db.commit()

    @staticmethod
    def get_by_local_path(path: str) -> Optional[Project]:
        db = get_connection()
        row = db.execute(
            "SELECT * FROM projects WHERE local_path=?", (path,)
        ).fetchone()
        return ProjectModel._row_to_proj(row) if row else None

    @staticmethod
    def _row_to_proj(row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            local_path=row["local_path"],
            remote_connection_id=row["remote_connection_id"],
            remote_path=row["remote_path"],
            tools=row["tools"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
