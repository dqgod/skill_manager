"""SQLite 数据库初始化与连接管理"""

import sqlite3
import threading
from pathlib import Path

from src.config import APP_DATA_DIR, DB_FILENAME

_local = threading.local()


def get_db_path() -> Path:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DATA_DIR / DB_FILENAME


def get_connection() -> sqlite3.Connection:
    """线程安全的数据库连接，每线程一个连接，开启 WAL 模式和外键约束。"""
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(str(get_db_path()))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.connection = conn
    return conn


def init_db() -> None:
    """幂等建表。"""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 22,
            username TEXT NOT NULL,
            auth_type TEXT NOT NULL CHECK(auth_type IN ('key', 'password')),
            key_path TEXT,
            password_enc BLOB,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            local_path TEXT NOT NULL UNIQUE,
            remote_connection_id TEXT,
            remote_path TEXT,
            tools TEXT NOT NULL DEFAULT 'codex,claude',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (remote_connection_id) REFERENCES connections(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sync_history (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            direction TEXT NOT NULL CHECK(direction IN ('push', 'pull')),
            source_device TEXT NOT NULL,
            source_level TEXT NOT NULL CHECK(source_level IN ('global', 'project')),
            source_project_id TEXT,
            source_tool TEXT NOT NULL,
            target_device TEXT NOT NULL,
            target_level TEXT NOT NULL CHECK(target_level IN ('global', 'project')),
            target_project_id TEXT,
            target_tool TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'skipped')),
            detail TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sync_history_time
            ON sync_history(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_sync_history_project
            ON sync_history(source_project_id);
    """)
    conn.commit()


def close_db() -> None:
    conn = getattr(_local, "connection", None)
    if conn:
        conn.close()
        _local.connection = None
