"""Shared chat/agent logic for dashboard. Runs Woody agent and handles approvals."""

from __future__ import annotations

import os
from pathlib import Path

# Load .env from repo root
_root = Path(__file__).resolve().parent.parent
if (_root / ".env").exists():
    from dotenv import load_dotenv
    load_dotenv(_root / ".env")
from datetime import datetime, timedelta
from typing import Optional

# Woody db path - dashboard uses same DB as Woody for conversation/approvals
def get_woody_db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "woody" / "app.db"
    return Path(os.environ.get("WOODY_DB_PATH", str(default)))


def run_chat(message: str, chat_id: int = 0) -> tuple[str, Optional[str]]:
    """
    Run Woody agent with message. Returns (response, pending_approval_id).
    If response contains approval, pending_approval_id is the ID to approve.
    """
    db_path = get_woody_db_path()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        return "Chat unavailable: OPENAI_API_KEY not set.", None

    # Ensure Woody db exists. Dashboard's 'app' shadows woody's - temporarily clear it.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent
    woody_dir = repo_root / "woody"
    import sys
    for p in (woody_dir, repo_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    import importlib.util
    woody_db_spec = importlib.util.spec_from_file_location(
        "woody_db", str(woody_dir / "app" / "db.py"))
    woody_db = importlib.util.module_from_spec(woody_db_spec)
    woody_db_spec.loader.exec_module(woody_db)
    woody_db.init_db(db_path)

    # Clear dashboard's 'app' and app.* from sys.modules so woody's app gets used
    _saved = {}
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _saved[key] = sys.modules.pop(key)
    try:
        from woody.app.agent import run_agent
        response = run_agent(message, openai_key, db_path, chat_id)
    finally:
        for key, mod in _saved.items():
            sys.modules[key] = mod

    # Check for approval
    approval_id = None
    if "APPROVAL REQUIRED" in response and "APPROVE " in response:
        import re
        m = re.search(r"APPROVE\s+(\w+)", response)
        if m:
            approval_id = m.group(1)

    return response, approval_id


def get_pending_approvals(chat_id: int = 0) -> list:
    """List pending approvals for the given chat. Expires any older than 24 hours."""
    db_path = get_woody_db_path()
    if not db_path.exists():
        return []
    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    import sys
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    _saved = {}
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _saved[key] = sys.modules.pop(key)
    try:
        from woody.app.approvals import list_pending_approvals
        return list_pending_approvals(db_path, chat_id=chat_id)
    finally:
        for key, mod in _saved.items():
            sys.modules[key] = mod


def execute_approval(approval_id: str, chat_id: int = 0) -> tuple[bool, str]:
    """
    Execute a pending approval. Returns (success, message).
    """
    db_path = get_woody_db_path()
    if not db_path.exists():
        return False, "Woody database not found."

    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    import sys
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    _saved = {}
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _saved[key] = sys.modules.pop(key)
    try:
        from woody.app.approvals import approve, get_approval, is_expired
        from woody.app.tools import execute_tool
        from woody.app.agent import _resolve_date_phrases, _ensure_tools_loaded
        from woody.app.conversation import add_message
        _ensure_tools_loaded()  # Register all tools (memory_store, etc.) before execute_tool
        rec = get_approval(db_path, approval_id)
    finally:
        for key, mod in _saved.items():
            sys.modules[key] = mod

    if not rec:
        return False, f"Unknown approval ID: {approval_id}"
    if rec["status"] != "pending":
        return False, f"Approval already {rec['status']}"
    if is_expired(rec.get("created_at", "")):
        return False, "Approval expired (older than 24 hours)."
    if rec["chat_id"] != chat_id:
        return False, "Approval belongs to another chat."

    if not approve(db_path, approval_id):
        return False, "Failed to approve"

    args = dict(rec["tool_args"])
    # Re-resolve date for calendar events
    if rec["tool_name"] == "calendar_create_event":
        orig = (rec.get("original_message") or "").strip()
        if orig:
            tz_name = os.environ.get("CALENDAR_TIMEZONE", "UTC")
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                from datetime import timezone
                tz = timezone.utc
            _, resolved_iso = _resolve_date_phrases(orig, datetime.now(tz))
            if resolved_iso:
                start_d = datetime.strptime(resolved_iso, "%Y-%m-%d").date()
                args["start"] = resolved_iso
                args["end"] = (start_d + timedelta(days=1)).isoformat()
    # Inject chat_id for tools that need it
    if rec["tool_name"] in ("reminder_create", "reminder_cancel", "todo_add", "todo_complete", "todo_remove", "wishlist_add", "wishlist_remove"):
        args["chat_id"] = chat_id

    try:
        result = execute_tool(rec["tool_name"], args)
        success_msg = f"Done. {result}"
        # Record approval in conversation so agent knows it's complete (avoids approval loop)
        _saved2 = {}
        for key in list(sys.modules.keys()):
            if key == "app" or key.startswith("app."):
                _saved2[key] = sys.modules.pop(key)
        try:
            from woody.app.conversation import add_message
            add_message(db_path, chat_id, "user", f"APPROVE {approval_id}")
            add_message(db_path, chat_id, "assistant", success_msg)
        finally:
            for k, mod in _saved2.items():
                sys.modules[k] = mod
        return True, success_msg
    except Exception as e:
        return False, str(e)


def reject_approval(approval_id: str, chat_id: int = 0) -> tuple[bool, str]:
    """Reject a pending approval."""
    db_path = get_woody_db_path()
    if not db_path.exists():
        return False, "Woody database not found."
    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    import sys
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    _saved = {}
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _saved[key] = sys.modules.pop(key)
    try:
        from woody.app.approvals import reject, get_approval, is_expired
        from woody.app.conversation import add_message
        rec = get_approval(db_path, approval_id)
    finally:
        for key, mod in _saved.items():
            sys.modules[key] = mod
    if not rec:
        return False, f"Unknown approval ID: {approval_id}"
    if rec["status"] != "pending":
        return False, f"Approval already {rec['status']}"
    if is_expired(rec.get("created_at", "")):
        return False, "Approval expired (older than 24 hours)."
    if rec["chat_id"] != chat_id:
        return False, "Approval belongs to another chat."
    if reject(db_path, approval_id):
        _saved2 = {}
        for key in list(sys.modules.keys()):
            if key == "app" or key.startswith("app."):
                _saved2[key] = sys.modules.pop(key)
        try:
            from woody.app.conversation import add_message
            add_message(db_path, chat_id, "user", f"REJECT {approval_id}")
            add_message(db_path, chat_id, "assistant", f"Rejected approval {approval_id}.")
        finally:
            for k, mod in _saved2.items():
                sys.modules[k] = mod
        return True, f"Rejected approval {approval_id}."
    return False, "Failed to reject"
