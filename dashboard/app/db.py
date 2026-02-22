"""Dashboard database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "dashboard.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL DEFAULT 'event',
    recurrence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    decision TEXT NOT NULL,
    context TEXT,
    outcome TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS circles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS circle_members (
    circle_id INTEGER NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    PRIMARY KEY (circle_id, entity_type, entity_id),
    CHECK (entity_type IN ('contact', 'place', 'memory'))
);

CREATE TABLE IF NOT EXISTS scheduled_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    recurrence TEXT NOT NULL,
    anchor_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_decisions_date ON decisions(date);
CREATE INDEX IF NOT EXISTS idx_scheduled_templates_anchor ON scheduled_templates(anchor_date);
CREATE INDEX IF NOT EXISTS idx_circle_members_circle ON circle_members(circle_id);
CREATE INDEX IF NOT EXISTS idx_circle_members_entity ON circle_members(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS about_me (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _migrate_add_recurrence(conn: sqlite3.Connection) -> None:
    """Add recurrence column if missing."""
    try:
        conn.execute("ALTER TABLE events ADD COLUMN recurrence TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_about_me(conn: sqlite3.Connection) -> None:
    """Add about_me table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS about_me (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            content TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("INSERT OR IGNORE INTO about_me (id, content) VALUES (1, '')")
    conn.commit()


def _migrate_scheduled_templates(conn: sqlite3.Connection) -> None:
    """Add scheduled_templates table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            recurrence TEXT NOT NULL,
            anchor_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_templates_anchor ON scheduled_templates(anchor_date)")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def init_db() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA)
    _migrate_add_recurrence(conn)
    _migrate_scheduled_templates(conn)
    _migrate_about_me(conn)
    conn.close()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
