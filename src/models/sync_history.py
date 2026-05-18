"""同步历史数据类与写入"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.models.db import get_connection


@dataclass
class SyncRecord:
    direction: str
    source_device: str
    source_level: str
    source_tool: str
    target_device: str
    target_level: str
    target_tool: str
    skill_name: str
    status: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = ""
    source_project_id: Optional[str] = None
    target_project_id: Optional[str] = None
    detail: str = ""


class SyncHistoryModel:
    @staticmethod
    def add(record: SyncRecord) -> None:
        db = get_connection()
        if not record.timestamp:
            record.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO sync_history
               (id, timestamp, direction, source_device, source_level,
                source_project_id, source_tool, target_device, target_level,
                target_project_id, target_tool, skill_name, status, detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record.id, record.timestamp, record.direction,
             record.source_device, record.source_level,
             record.source_project_id, record.source_tool,
             record.target_device, record.target_level,
             record.target_project_id, record.target_tool,
             record.skill_name, record.status, record.detail),
        )
        db.commit()

    @staticmethod
    def add_bulk(records: list[SyncRecord]) -> None:
        db = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for r in records:
            if not r.timestamp:
                r.timestamp = now
            rows.append((
                r.id, r.timestamp, r.direction,
                r.source_device, r.source_level, r.source_project_id,
                r.source_tool, r.target_device, r.target_level,
                r.target_project_id, r.target_tool,
                r.skill_name, r.status, r.detail,
            ))
        db.executemany(
            """INSERT INTO sync_history
               (id, timestamp, direction, source_device, source_level,
                source_project_id, source_tool, target_device, target_level,
                target_project_id, target_tool, skill_name, status, detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        db.commit()

    @staticmethod
    def query(
        project_id: Optional[str] = None,
        device: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SyncRecord]:
        db = get_connection()
        conditions = []
        params = []
        if project_id:
            conditions.append(
                "(source_project_id=? OR target_project_id=?)"
            )
            params.extend([project_id, project_id])
        if device:
            conditions.append(
                "(source_device=? OR target_device=?)"
            )
            params.extend([device, device])
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = db.execute(
            f"SELECT * FROM sync_history{where} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [SyncHistoryModel._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row) -> SyncRecord:
        return SyncRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            direction=row["direction"],
            source_device=row["source_device"],
            source_level=row["source_level"],
            source_project_id=row["source_project_id"],
            source_tool=row["source_tool"],
            target_device=row["target_device"],
            target_level=row["target_level"],
            target_project_id=row["target_project_id"],
            target_tool=row["target_tool"],
            skill_name=row["skill_name"],
            status=row["status"],
            detail=row["detail"] or "",
        )
