"""
User action logging for preference learning.
Tracks: calendar_added, todo_added, event_deleted, event_approved, event_rejected.
Used by events agent to influence future recommendations.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.chat import get_woody_db_path


def _get_conn(db_path: Optional[Path] = None):
    path = db_path or get_woody_db_path()
    return sqlite3.connect(str(path))


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create user_actions table if missing (lazy migration for dashboard-only usage)."""
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


def log_action(
    action: str,
    event_id: Optional[int] = None,
    proposal_id: Optional[str] = None,
    title: Optional[str] = None,
    event_date: Optional[str] = None,
    source: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """
    Log a user action. Actions: calendar_added, todo_added, event_deleted,
    event_approved, event_rejected.
    """
    path = db_path or get_woody_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn(path)
    try:
        conn.execute(
            """INSERT INTO user_actions (action, event_id, proposal_id, title, event_date, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (action, event_id, proposal_id, (title or "")[:200], (event_date or "")[:10], source or ""),
        )
        conn.commit()
    except sqlite3.OperationalError:
        try:
            _ensure_table(conn)
            conn.execute(
                """INSERT INTO user_actions (action, event_id, proposal_id, title, event_date, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                (action, event_id, proposal_id, (title or "")[:200], (event_date or "")[:10], source or ""),
            )
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


def get_recent_rejections(
    db_path: Optional[Path] = None,
    days: int = 30,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get event_suggestion proposals user rejected. Used to avoid re-proposing similar."""
    path = db_path or get_woody_db_path()
    if not path.exists():
        return []
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = _get_conn(path)
    try:
        cur = conn.execute(
            """SELECT title, event_date, source, created_at FROM user_actions
               WHERE action = 'event_rejected' AND created_at >= ?
               ORDER BY created_at DESC LIMIT ?""",
            (since, limit),
        )
        return [
            {"title": r[0], "event_date": r[1], "source": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_action_counts(
    db_path: Optional[Path] = None,
    days: int = 30,
) -> Dict[str, int]:
    """Get counts per action type. Used to infer preferences (e.g. user prefers calendar)."""
    path = db_path or get_woody_db_path()
    if not path.exists():
        return {}
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = _get_conn(path)
    try:
        cur = conn.execute(
            """SELECT action, COUNT(*) FROM user_actions
               WHERE created_at >= ? AND action IN ('calendar_added', 'todo_added', 'event_deleted', 'event_approved', 'event_rejected')
               GROUP BY action""",
            (since,),
        )
        return dict(cur.fetchall())
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def was_rejected_recently(
    title: str,
    event_date: str,
    source_hint: str,
    db_path: Optional[Path] = None,
    days: int = 14,
) -> bool:
    """
    Check if user rejected a similar event recently.
    title: normalized to first 60 chars for matching.
    source_hint: e.g. "From: x@yahoo.com" - we match if rejection had same sender.
    """
    rejections = get_recent_rejections(db_path, days=days, limit=50)
    title_key = (title or "").strip().lower()[:60]
    if not title_key:
        return False
    for r in rejections:
        r_title = (r.get("title") or "").strip().lower()[:60]
        if r_title and (title_key in r_title or r_title in title_key):
            if source_hint and r.get("source"):
                if source_hint.lower() in str(r.get("source", "")).lower():
                    return True
            else:
                return True
    return False
