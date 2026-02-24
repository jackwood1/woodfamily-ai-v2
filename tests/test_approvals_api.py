"""Tests for approvals API endpoints."""

import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


@pytest.fixture(autouse=True)
def woody_db(monkeypatch):
    """Use temp Woody DB for approval API tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    monkeypatch.setenv("WOODY_DB_PATH", str(path))
    woody_dir = _root / "woody"
    import importlib.util
    spec = importlib.util.spec_from_file_location("woody_db", str(woody_dir / "app" / "db.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(path)
    yield path
    path.unlink(missing_ok=True)


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


def test_approvals_list_empty(client):
    r = client.get("/api/approvals")
    assert r.status_code == 200
    data = r.json()
    assert "approvals" in data
    assert data["approvals"] == []
    assert "db_path" in data


def test_approvals_create_via_service_and_list(client):
    """Create approval via service, then list via API."""
    from shared.approval_service import create
    from shared.db_path import get_woody_db_path
    db_path = get_woody_db_path()
    aid = create(db_path, chat_id=0, tool_name="test_tool", tool_args={"x": 1}, preview="test")
    r = client.get("/api/approvals")
    assert r.status_code == 200
    data = r.json()
    assert len(data["approvals"]) >= 1
    ids = [a["id"] for a in data["approvals"]]
    assert aid in ids


def test_approvals_approve(client):
    """Create approval, then approve via API."""
    from unittest.mock import patch, MagicMock
    from shared.approval_service import create
    from shared.db_path import get_woody_db_path
    db_path = get_woody_db_path()
    aid = create(db_path, chat_id=0, tool_name="memory_store", tool_args={"fact": "test", "weight": 5}, preview="p")
    with patch("woody.app.tools.execute_tool", MagicMock(return_value="Stored.")):
        with patch("woody.app.conversation.add_message", MagicMock()):
            r = client.post("/api/approvals/approve", json={"approval_id": aid})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "Done" in data["message"] or "Stored" in data["message"]


def test_approvals_reject(client):
    from shared.approval_service import create
    from shared.db_path import get_woody_db_path
    db_path = get_woody_db_path()
    aid = create(db_path, chat_id=0, tool_name="t", tool_args={}, preview="p")
    r = client.post("/api/approvals/reject", json={"approval_id": aid})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "Rejected" in data["message"]


def test_approvals_approve_unknown(client):
    r = client.post("/api/approvals/approve", json={"approval_id": "nonexistent"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Unknown" in data["message"] or "expired" in data["message"]


def test_approvals_approve_all_empty(client):
    r = client.post("/api/approvals/approve-all")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["count"] == 0


def test_approvals_reject_all_empty(client):
    r = client.post("/api/approvals/reject-all")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["count"] == 0
