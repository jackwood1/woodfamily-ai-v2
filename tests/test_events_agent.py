"""Tests for EVENTS agent."""

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


@pytest.fixture
def dashboard_db(tmp_path):
    """Create temp dashboard DB with schema."""
    db = tmp_path / "dashboard.db"
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_type TEXT NOT NULL DEFAULT 'event',
            recurrence TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE scheduled_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            recurrence TEXT NOT NULL,
            anchor_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()
    return db


def test_compute_next_due_yearly():
    from shared.events_agent import _compute_next_due
    assert _compute_next_due("2024-06-01", "YEARLY") == "2025-06-01"
    assert _compute_next_due("2024-12-31", "YEARLY") == "2025-12-31"


def test_compute_next_due_monthly():
    from shared.events_agent import _compute_next_due
    assert _compute_next_due("2024-01-15", "MONTHLY") == "2024-02-15"
    assert _compute_next_due("2024-12-15", "MONTHLY") == "2025-01-15"


def test_compute_next_due_weekly():
    from shared.events_agent import _compute_next_due
    assert _compute_next_due("2024-01-15", "WEEKLY") == "2024-01-22"


def test_compute_next_due_invalid():
    from shared.events_agent import _compute_next_due
    assert _compute_next_due("invalid", "YEARLY") is None
    assert _compute_next_due("2024-06-01", "DAILY") is None


def test_create_event(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.events_agent import create_event
    ev_id = create_event("2025-12-25", "Christmas", "Family dinner", "event")
    assert ev_id is not None
    assert ev_id > 0


def test_get_all_events(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    import sqlite3
    conn = sqlite3.connect(str(dashboard_db))
    # Use dates within query range: today to today+365
    d1 = (date.today() + timedelta(days=1)).isoformat()
    d2 = (date.today() + timedelta(days=7)).isoformat()
    conn.execute(
        "INSERT INTO events (date, title, description, event_type) VALUES (?, ?, ?, ?)",
        (d1, "Christmas", "", "event"),
    )
    conn.execute(
        "INSERT INTO events (date, title, description, event_type) VALUES (?, ?, ?, ?)",
        (d2, "Boxing Day", "", "event"),
    )
    conn.commit()
    conn.close()
    from shared.events_agent import get_all_events
    events = get_all_events(days_back=0, days_ahead=365)
    assert len(events) >= 2
    titles = [e["title"] for e in events]
    assert "Christmas" in titles
    assert "Boxing Day" in titles


def test_capture_completed_todo(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.events_agent import capture_completed_todo, get_all_events
    completed_date = (date.today() - timedelta(days=1)).isoformat()  # within days_back=30
    ev_id = capture_completed_todo(1, "Buy groceries", completed_date)
    assert ev_id is not None
    events = get_all_events(days_back=30, days_ahead=0)
    completed = [e for e in events if e.get("event_type") == "completed"]
    assert len(completed) >= 1
    assert "Completed:" in completed[0]["title"]


def test_get_requires_scheduling_empty(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.events_agent import get_requires_scheduling
    items = get_requires_scheduling(dashboard_db_path=dashboard_db)
    assert items == []


def test_get_requires_scheduling_with_template(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    import sqlite3
    conn = sqlite3.connect(str(dashboard_db))
    # anchor 355 days ago -> next_due in ~10 days (within 14)
    conn.execute(
        "INSERT INTO scheduled_templates (title, description, recurrence, anchor_date) VALUES (?, ?, ?, ?)",
        ("Car inspection", "", "YEARLY", (date.today() - timedelta(days=355)).isoformat()),
    )
    conn.commit()
    conn.close()
    from shared.events_agent import get_requires_scheduling
    items = get_requires_scheduling(dashboard_db_path=dashboard_db, days_ahead=14)
    assert len(items) >= 1
    assert items[0]["title"] == "Car inspection"
    assert "next_due" in items[0]


def test_process_scheduled_templates_due(dashboard_db, monkeypatch):
    """Process creates event when template is past due."""
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    import sqlite3
    conn = sqlite3.connect(str(dashboard_db))
    conn.execute(
        "INSERT INTO scheduled_templates (title, description, recurrence, anchor_date) VALUES (?, ?, ?, ?)",
        ("Bill reminder", "", "MONTHLY", (date.today() - timedelta(days=35)).isoformat()),
    )
    conn.commit()
    conn.close()
    from shared.events_agent import process_scheduled_templates, get_all_events
    created, requires = process_scheduled_templates(
        dashboard_db_path=dashboard_db,
    )
    assert created >= 1
    events = get_all_events(days_back=30, days_ahead=0)
    bill_events = [e for e in events if "Bill reminder" in e.get("title", "")]
    assert len(bill_events) >= 1


def test_list_wishlist(woody_db, monkeypatch):
    monkeypatch.setenv("WOODY_DB_PATH", str(woody_db))
    import sqlite3
    conn = sqlite3.connect(str(woody_db))
    conn.execute("INSERT INTO wishlist (chat_id, content) VALUES (0, 'Trip to Japan')")
    conn.commit()
    conn.close()
    from shared.events_agent import list_wishlist
    items = list_wishlist(woody_db_path=woody_db)
    assert len(items) >= 1
    assert any("Japan" in (i.get("content") or "") for i in items)


def test_fulfill_wishlist_item(woody_db, dashboard_db, monkeypatch):
    monkeypatch.setenv("WOODY_DB_PATH", str(woody_db))
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    import sqlite3
    conn = sqlite3.connect(str(woody_db))
    cur = conn.execute("INSERT INTO wishlist (chat_id, content) VALUES (0, 'Learned piano')")
    wid = cur.lastrowid
    conn.commit()
    conn.close()
    from shared.events_agent import fulfill_wishlist_item, get_all_events
    ev_id = fulfill_wishlist_item(wid, woody_db_path=woody_db)
    assert ev_id is not None
    events = get_all_events(days_back=0, days_ahead=0)
    fulfilled = [e for e in events if "Wish fulfilled" in e.get("title", "")]
    assert len(fulfilled) >= 1


@pytest.fixture
def woody_db(tmp_path):
    db = tmp_path / "woody.db"
    from woody.app.db import init_db
    init_db(db)
    return db


