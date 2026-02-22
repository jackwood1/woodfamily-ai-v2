"""Tests for sandboxed file tools."""

import tempfile
from pathlib import Path

import pytest

import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "woody"))

import os


@pytest.fixture
def sandbox_dir():
    d = tempfile.mkdtemp()
    os.environ["FILES_SANDBOX_DIR"] = d
    yield Path(d)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_file_write_read(sandbox_dir):
    from woody.app.tools.files import _file_write_handler, _file_read_handler
    _file_write_handler("test.txt", "hello world")
    assert _file_read_handler("test.txt") == "hello world"


def test_file_reject_traversal(sandbox_dir):
    from woody.app.tools.files import _file_read_handler
    with pytest.raises(ValueError, match="traversal"):
        _file_read_handler("../../../etc/passwd")
