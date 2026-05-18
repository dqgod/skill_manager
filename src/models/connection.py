"""连接配置数据类与 CRUD"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.models.db import get_connection


@dataclass
class Connection:
    name: str
    host: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    port: int = 22
    username: str = ""
    auth_type: str = "key"
    key_path: Optional[str] = None
    password_enc: Optional[bytes] = None
    created_at: str = ""
    updated_at: str = ""


class ConnectionModel:
    @staticmethod
    def save(conn: Connection) -> None:
        db = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not conn.created_at:
            conn.created_at = now
        conn.updated_at = now
        db.execute(
            """INSERT OR REPLACE INTO connections
               (id, name, host, port, username, auth_type,
                key_path, password_enc, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (conn.id, conn.name, conn.host, conn.port,
             conn.username, conn.auth_type, conn.key_path,
             conn.password_enc, conn.created_at, conn.updated_at),
        )
        db.commit()

    @staticmethod
    def get(conn_id: str) -> Optional[Connection]:
        db = get_connection()
        row = db.execute(
            "SELECT * FROM connections WHERE id=?", (conn_id,)
        ).fetchone()
        return ConnectionModel._row_to_conn(row) if row else None

    @staticmethod
    def get_all() -> list[Connection]:
        db = get_connection()
        rows = db.execute("SELECT * FROM connections ORDER BY created_at DESC").fetchall()
        return [ConnectionModel._row_to_conn(r) for r in rows]

    @staticmethod
    def delete(conn_id: str) -> None:
        db = get_connection()
        db.execute("DELETE FROM connections WHERE id=?", (conn_id,))
        db.commit()

    @staticmethod
    def get_by_name(name: str) -> Optional[Connection]:
        db = get_connection()
        row = db.execute(
            "SELECT * FROM connections WHERE name=?", (name,)
        ).fetchone()
        return ConnectionModel._row_to_conn(row) if row else None

    @staticmethod
    def _row_to_conn(row) -> Connection:
        return Connection(
            id=row["id"],
            name=row["name"],
            host=row["host"],
            port=row["port"],
            username=row["username"],
            auth_type=row["auth_type"],
            key_path=row["key_path"],
            password_enc=row["password_enc"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
