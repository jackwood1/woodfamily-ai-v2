"""Shared reminder logic - fetches upcoming events for Telegram reminders."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import httpx


def get_dashboard_db_path() -> Path:
    """Path to dashboard SQLite DB."""
    default = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.db"
    return Path(os.environ.get("DASHBOARD_DB_PATH", str(default)))


def get_upcoming_events_from_db(limit: int = 20) -> List[dict]:
    """Read upcoming events from dashboard DB (today + tomorrow)."""
    db_path = get_dashboard_db_path()
    if not db_path.exists():
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        rows = conn.execute(
            """SELECT id, date, title, description, event_type FROM events
               WHERE date >= ? AND date <= ?
               ORDER BY date ASC LIMIT ?""",
            (today, tomorrow, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_upcoming_events_from_api(base_url: str = "") -> List[dict]:
    """Fetch upcoming events from dashboard API (includes Google Calendar)."""
    url = base_url or os.environ.get("DASHBOARD_URL", "http://localhost:8000")
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{url.rstrip('/')}/api/events?coming=1")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return []


def get_requires_scheduling_from_api(base_url: str = "", days: int = 14) -> List[dict]:
    """Fetch items requiring scheduling (bills, inspections, birthdays) from dashboard API."""
    url = base_url or os.environ.get("DASHBOARD_URL", "http://localhost:8000")
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{url.rstrip('/')}/api/events/requires-scheduling?days={days}")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return get_requires_scheduling_from_db(days=days)


def get_requires_scheduling_from_db(days: int = 14) -> List[dict]:
    """Read requires-scheduling from dashboard DB (fallback when API unavailable)."""
    try:
        from shared.events_agent import get_requires_scheduling
        return get_requires_scheduling(days_ahead=days)
    except Exception:
        return []
