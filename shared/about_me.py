"""About Me - user-provided context for agent decisions."""

from __future__ import annotations

import os
from pathlib import Path


def _get_dashboard_db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.db"
    return Path(os.environ.get("DASHBOARD_DB_PATH", str(default)))


def get_about_me() -> str:
    """Read About Me content from dashboard DB. Returns empty string if none or on error."""
    db_path = _get_dashboard_db_path()
    if not db_path.exists():
        return ""
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT content FROM about_me WHERE id = 1"
        ).fetchone()
        conn.close()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""
