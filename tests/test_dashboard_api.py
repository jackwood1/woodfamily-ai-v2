"""Tests for dashboard API endpoints."""

import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


@pytest.fixture(autouse=True)
def dashboard_db(monkeypatch):
    """Use temp DB for dashboard tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    monkeypatch.setattr("dashboard.app.db.DB_PATH", path)
    from dashboard.app.db import init_db
    init_db()
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from dashboard.app.main import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_events_calendar_no_tokens(client):
    """Calendar endpoint returns [] when Google not connected."""
    r = client.get("/api/events/calendar")
    assert r.status_code == 200
    assert r.json() == []


def test_memories_list(client):
    r = client.get("/api/memories")
    assert r.status_code == 200
    data = r.json()
    assert "memories" in data
    assert isinstance(data["memories"], list)


def test_memories_search(client):
    r = client.get("/api/memories?q=test")
    assert r.status_code == 200
    data = r.json()
    assert "memories" in data
    assert isinstance(data["memories"], list)


def test_events_coming(client):
    r = client.get("/api/events?coming=1")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_events_create(client):
    r = client.post(
        "/api/events",
        json={"date": "2025-12-25", "title": "Christmas", "description": "", "event_type": "event"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Christmas"
    assert data["date"] == "2025-12-25"
    assert "id" in data
