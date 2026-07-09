"""SQLite database layer for persistent storage.

References:
- Sakura: app/agent/memory.py — multi-layer memory with SQLite + mem0 vectors
- KillClawd: simple JSON file on Desktop for XP persistence

We use sqlite3 (Python built-in) for zero-dependency local storage.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Any


CREATE_TABLES_SQL = """
-- TODO items
CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority    INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'pending',
    due_date    TEXT,
    source      TEXT DEFAULT 'manual',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at TEXT,
    tags        TEXT DEFAULT '[]'
);

-- Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    trigger_at  TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    repeat_rule TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Tool execution history
CREATE TABLE IF NOT EXISTS tool_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT NOT NULL,
    intent      TEXT,
    params      TEXT,
    success     INTEGER,
    message     TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Pet state (position, mood, stats)
CREATE TABLE IF NOT EXISTS pet_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Notes / knowledge snippets
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT,
    content     TEXT NOT NULL,
    source      TEXT DEFAULT 'selection',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- General key-value store for extensibility
CREATE TABLE IF NOT EXISTS kv_store (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


class Database:
    """Thin wrapper around sqlite3 for HaChiCat data storage."""

    def __init__(self, db_path: Path):
        self._path = db_path
        self._conn: sqlite3.Connection | None = None
        # Serializes access across the main thread and background worker
        # threads (LLM todo/tool execution) sharing one connection.
        self._lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get (or open) the database connection."""
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_tables(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript(CREATE_TABLES_SQL)
        self.conn.commit()

    def execute(self, sql: str, params: tuple | dict | None = None) -> sqlite3.Cursor:
        """Execute a SQL statement."""
        with self._lock:
            return self.conn.execute(sql, params or ())

    def fetch_one(self, sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
        """Fetch a single row as dict."""
        with self._lock:
            row = self.conn.execute(sql, params or ()).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
        """Fetch all rows as list of dicts."""
        with self._lock:
            return [dict(row) for row in self.conn.execute(sql, params or ()).fetchall()]

    def insert(self, sql: str, params: tuple | dict | None = None) -> int:
        """Execute insert and return lastrowid."""
        with self._lock:
            cur = self.conn.execute(sql, params or ())
            self.conn.commit()
            return cur.lastrowid

    def update(self, sql: str, params: tuple | dict | None = None) -> int:
        """Execute update/delete and return rowcount."""
        with self._lock:
            cur = self.conn.execute(sql, params or ())
            self.conn.commit()
            return cur.rowcount

    def get_pet_state(self, key: str, default: str | None = None) -> str | None:
        """Get a pet state value by key."""
        row = self.fetch_one("SELECT value FROM pet_state WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_pet_state(self, key: str, value: str) -> None:
        """Set a pet state key-value pair (upsert)."""
        self.update(
            "INSERT OR REPLACE INTO pet_state (key, value) VALUES (?, ?)",
            (key, value),
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
