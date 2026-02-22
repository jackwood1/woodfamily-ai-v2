"""Tests for approval workflow."""

import json
import tempfile
from pathlib import Path

import pytest

# Add repo root and woody
import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "woody"))

from woody.app.db import init_db
from woody.app.approvals import create_approval, get_approval, approve, reject


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


def test_create_and_get_approval(db_path):
    init_db(db_path)
    aid = create_approval(db_path, chat_id=123, tool_name="test_tool", tool_args={"a": 1}, preview="test")
    assert len(aid) == 8
    rec = get_approval(db_path, aid)
    assert rec["chat_id"] == 123
    assert rec["tool_name"] == "test_tool"
    assert rec["tool_args"] == {"a": 1}
    assert rec["status"] == "pending"


def test_approve(db_path):
    init_db(db_path)
    aid = create_approval(db_path, 123, "t", {}, "p")
    assert approve(db_path, aid) is True
    assert approve(db_path, aid) is False  # already approved
    rec = get_approval(db_path, aid)
    assert rec["status"] == "approved"


def test_reject(db_path):
    init_db(db_path)
    aid = create_approval(db_path, 123, "t", {}, "p")
    assert reject(db_path, aid) is True
    assert reject(db_path, aid) is False
    rec = get_approval(db_path, aid)
    assert rec["status"] == "rejected"
