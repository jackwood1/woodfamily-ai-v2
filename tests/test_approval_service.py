"""Tests for shared approval service."""

import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


@pytest.fixture
def woody_db(monkeypatch):
    """Use temp DB for approval service tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    monkeypatch.setenv("WOODY_DB_PATH", str(path))
    # Ensure DB exists
    woody_dir = _root / "woody"
    import importlib.util
    spec = importlib.util.spec_from_file_location("woody_db", str(woody_dir / "app" / "db.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(path)
    yield path
    path.unlink(missing_ok=True)


def test_create(woody_db):
    from shared.approval_service import create
    aid = create(woody_db, chat_id=0, tool_name="test_tool", tool_args={"a": 1}, preview="test")
    assert len(aid) == 8
    import sqlite3
    conn = sqlite3.connect(str(woody_db))
    row = conn.execute("SELECT id, chat_id, tool_name, status FROM approvals WHERE id = ?", (aid,)).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 0
    assert row[2] == "test_tool"
    assert row[3] == "pending"


def test_list_pending(woody_db):
    from shared.approval_service import create, list_pending
    aid1 = create(woody_db, chat_id=0, tool_name="t1", tool_args={}, preview="p1")
    aid2 = create(woody_db, chat_id=0, tool_name="t2", tool_args={}, preview="p2")
    create(woody_db, chat_id=99, tool_name="t3", tool_args={}, preview="p3")  # different chat
    pending = list_pending(chat_id=0, db_path=woody_db)
    ids = [a["id"] for a in pending]
    assert aid1 in ids
    assert aid2 in ids
    assert len([a for a in pending if a["chat_id"] == 0]) >= 2


def test_reject(woody_db):
    from shared.approval_service import create, reject
    aid = create(woody_db, chat_id=0, tool_name="t", tool_args={}, preview="p")
    ok, msg = reject(aid, chat_id=0, db_path=woody_db)
    assert ok is True
    assert "Rejected" in msg
    ok2, _ = reject(aid, chat_id=0, db_path=woody_db)
    assert ok2 is False  # already rejected
    import sqlite3
    conn = sqlite3.connect(str(woody_db))
    row = conn.execute("SELECT status FROM approvals WHERE id = ?", (aid,)).fetchone()
    conn.close()
    assert row[0] == "rejected"


def test_reject_wrong_chat(woody_db):
    from shared.approval_service import create, reject
    aid = create(woody_db, chat_id=0, tool_name="t", tool_args={}, preview="p")
    ok, msg = reject(aid, chat_id=999, db_path=woody_db)
    assert ok is False
    assert "another chat" in msg


def test_execute_unknown_approval(woody_db):
    from shared.approval_service import execute
    ok, msg = execute("nonexistent", chat_id=0, db_path=woody_db)
    assert ok is False
    assert "Unknown" in msg or "expired" in msg


def test_execute_success(woody_db):
    """Execute approval with mocked execute_tool to avoid real tool dependencies."""
    from unittest.mock import patch, MagicMock
    from shared.approval_service import create, execute
    aid = create(woody_db, chat_id=0, tool_name="memory_store", tool_args={"fact": "test fact", "weight": 5}, preview="p")
    with patch("woody.app.tools.execute_tool", MagicMock(return_value="Stored.")):
        with patch("woody.app.conversation.add_message", MagicMock()):
            ok, msg = execute(aid, chat_id=0, db_path=woody_db)
    assert ok is True
    assert "Done" in msg or "Stored" in msg
    import sqlite3
    conn = sqlite3.connect(str(woody_db))
    row = conn.execute("SELECT status FROM approvals WHERE id = ?", (aid,)).fetchone()
    conn.close()
    assert row[0] == "approved"
