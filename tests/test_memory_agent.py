"""Tests for Memory agent."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


@pytest.fixture
def woody_db(tmp_path):
    """Create temp Woody DB with memory_agent tables."""
    db = tmp_path / "woody.db"
    from woody.app.db import init_db
    init_db(db)
    return db


def test_create_proposal(woody_db):
    from shared.memory_agent import create_proposal, list_pending_proposals
    pid = create_proposal(woody_db, "add", {"fact": "Test fact"}, "test reason")
    assert len(pid) == 12
    proposals = list_pending_proposals(woody_db)
    assert len(proposals) == 1
    assert proposals[0]["action_type"] == "add"
    assert proposals[0]["payload"]["fact"] == "Test fact"
    assert proposals[0]["reason"] == "test reason"


def test_resolve_proposal(woody_db):
    from shared.memory_agent import create_proposal, resolve_proposal, get_proposal
    pid = create_proposal(woody_db, "add", {"fact": "x"}, "")
    assert resolve_proposal(woody_db, pid, "approved") is True
    assert resolve_proposal(woody_db, pid, "approved") is False  # already resolved
    prop = get_proposal(woody_db, pid)
    assert prop["status"] == "approved"


def test_resolve_proposal_reject(woody_db):
    from shared.memory_agent import create_proposal, resolve_proposal, get_proposal
    pid = create_proposal(woody_db, "remove", {"query": "x"}, "")
    assert resolve_proposal(woody_db, pid, "rejected") is True
    prop = get_proposal(woody_db, pid)
    assert prop["status"] == "rejected"


def test_get_proposal_not_found(woody_db):
    from shared.memory_agent import get_proposal
    assert get_proposal(woody_db, "nonexistent") is None


def test_commit_proposal_circle_add(woody_db, dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.memory_agent import create_proposal, resolve_proposal, commit_proposal
    import sqlite3
    conn = sqlite3.connect(str(dashboard_db))
    conn.execute(
        "INSERT INTO circles (name, description) VALUES ('Test Circle', '')"
    )
    conn.commit()
    circle_id = conn.execute("SELECT id FROM circles WHERE name = 'Test Circle'").fetchone()[0]
    conn.execute(
        "INSERT INTO contacts (name, email, phone, notes) VALUES ('Test', 'test@x.com', '', '')"
    )
    conn.commit()
    contact_id = conn.execute("SELECT id FROM contacts WHERE email = 'test@x.com'").fetchone()[0]
    conn.close()
    pid = create_proposal(
        woody_db,
        "circle_add",
        {"circle_id": circle_id, "circle_name": "Test Circle", "entity_type": "contact", "entity_id": str(contact_id)},
        "test",
    )
    resolve_proposal(woody_db, pid, "approved")
    ok, msg = commit_proposal(woody_db, pid)
    assert ok is True
    conn = sqlite3.connect(str(dashboard_db))
    row = conn.execute(
        "SELECT 1 FROM circle_members WHERE circle_id = ? AND entity_type = 'contact' AND entity_id = ?",
        (circle_id, str(contact_id)),
    ).fetchone()
    conn.close()
    assert row is not None


@pytest.fixture
def dashboard_db(tmp_path):
    """Create temp dashboard DB."""
    db = tmp_path / "dashboard.db"
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE circles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE circle_members (
            circle_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (circle_id, entity_type, entity_id)
        );
        CREATE TABLE contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()
    return db
