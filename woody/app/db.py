"""SQLite database initialization and helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional


def init_db(db_path: Path) -> None:
    """Create database and tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        # Migration: add original_message to approvals if missing
        try:
            conn.execute("ALTER TABLE approvals ADD COLUMN original_message TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memory_agent_run (run_date TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    event_id INTEGER,
                    proposal_id TEXT,
                    title TEXT,
                    event_date TEXT,
                    source TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_actions_action ON user_actions(action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_actions_created ON user_actions(created_at)")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    tool_args TEXT NOT NULL,
    preview TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    original_message TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS home_ops_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS home_ops_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES home_ops_lists(id),
    item TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reminder_digest_sent (
    sent_date TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS daily_summary_sent (
    sent_date TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wishlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_agent_proposals (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_agent_run (
    run_date TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_agent_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_approvals_chat_status ON approvals(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_memory_agent_status ON memory_agent_proposals(status);
CREATE INDEX IF NOT EXISTS idx_reminders_chat_status ON reminders(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at);
CREATE INDEX IF NOT EXISTS idx_todos_chat_status ON todos(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_wishlist_chat ON wishlist(chat_id);
CREATE INDEX IF NOT EXISTS idx_home_ops_items_list ON home_ops_items(list_id);
CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversation_messages(chat_id);
"""


def get_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def execute(
    db_path: Path,
    sql: str,
    params: Optional[tuple] = None,
) -> sqlite3.Cursor:
    conn = get_conn(db_path)
    try:
        cur = conn.execute(sql, params or ())
        conn.commit()
        return cur
    finally:
        conn.close()
