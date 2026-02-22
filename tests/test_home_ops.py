"""Tests for home_ops tools."""

import tempfile
from pathlib import Path

import pytest

import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "woody"))

import os
os.environ["APP_DB_PATH"] = ""  # Set in fixture


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    os.environ["APP_DB_PATH"] = str(path)
    from woody.app.db import init_db
    init_db(path)
    yield path
    path.unlink(missing_ok=True)


def test_home_ops_list_empty(db_path):
    from woody.app.tools.home_ops import _list_items_handler
    assert "empty" in _list_items_handler("shopping").lower()


def test_home_ops_add_and_list(db_path):
    from woody.app.tools.home_ops import _add_item_handler, _list_items_handler
    _add_item_handler("shopping", "milk")
    _add_item_handler("shopping", "eggs")
    result = _list_items_handler("shopping")
    assert "milk" in result
    assert "eggs" in result
