"""Shared chat/agent logic for dashboard. Runs Woody agent."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Load .env from repo root
_root = Path(__file__).resolve().parent.parent
if (_root / ".env").exists():
    from dotenv import load_dotenv
    load_dotenv(_root / ".env")

from shared.db_path import get_woody_db_path


def run_chat(message: str, chat_id: int = 0) -> tuple[str, Path]:
    """Run Woody agent with message. Returns (response, db_path). Write tools execute directly."""
    db_path = get_woody_db_path().resolve()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        return "Chat unavailable: OPENAI_API_KEY not set.", db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent
    woody_dir = repo_root / "woody"

    # Ensure Woody db and tables exist
    import importlib.util
    woody_db_spec = importlib.util.spec_from_file_location(
        "woody_db", str(woody_dir / "app" / "db.py"))
    woody_db = importlib.util.module_from_spec(woody_db_spec)
    woody_db_spec.loader.exec_module(woody_db)
    woody_db.init_db(db_path)

    # Run agent in-process (app=woody.app)
    _saved = {}
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _saved[key] = sys.modules.pop(key)
        if key.startswith("woody.app"):
            sys.modules.pop(key, None)
    sys.path.insert(0, str(woody_dir))
    sys.path.insert(0, str(repo_root))
    try:
        import woody.app as _woody_app
        sys.modules["app"] = _woody_app
        from woody.app.agent import run_agent
        response = run_agent(message, openai_key, db_path, chat_id)
    finally:
        for key, mod in _saved.items():
            sys.modules[key] = mod

    return response, db_path
