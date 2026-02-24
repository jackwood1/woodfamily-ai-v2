"""
Approval service: create, list, execute, and reject approvals.
Single source of truth for approval workflow. Used by dashboard API and chat.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from shared.db_path import get_woody_db_path

log = logging.getLogger(__name__)

# Cache: approval_id -> db_path (for typed "APPROVE X" when db_path unknown)
_approval_db_paths: dict[str, str] = {}
_MAX_CACHE = 500


def get_approval_cache_keys() -> list[str]:
    """Return recent cache keys for debug."""
    return list(_approval_db_paths.keys())[-10:]


def _cache_register(approval_id: str, db_path: Path) -> None:
    if len(_approval_db_paths) >= _MAX_CACHE:
        for k in list(_approval_db_paths.keys())[:100]:
            del _approval_db_paths[k]
    _approval_db_paths[approval_id] = str(db_path)


def _get_db_candidates() -> list[Path]:
    repo = Path(__file__).resolve().parent.parent
    return [
        repo / "woody" / "app.db",
        repo / "dashboard" / "app.db",
        repo / "app.db",
        get_woody_db_path().resolve(),
    ]


def _ensure_db(db_path: Path) -> None:
    if db_path.exists():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    import importlib.util
    spec = importlib.util.spec_from_file_location("woody_db", str(woody_dir / "app" / "db.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(db_path)


def _get_approval_raw(db_path: Path, approval_id: str) -> Optional[dict[str, Any]]:
    import sqlite3
    conn = sqlite3.connect(str(db_path.resolve()))
    try:
        cur = conn.execute(
            "SELECT id, chat_id, tool_name, tool_args, preview, status, original_message, created_at "
            "FROM approvals WHERE LOWER(id) = LOWER(?)",
            (approval_id.strip(),),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "chat_id": row[1],
        "tool_name": row[2],
        "tool_args": json.loads(row[3]),
        "preview": row[4],
        "status": row[5],
        "original_message": row[6] if len(row) > 6 else "",
        "created_at": row[7] if len(row) > 7 else "",
    }


def _is_expired(created_at: str) -> bool:
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > timedelta(hours=24)
    except (ValueError, TypeError):
        return False


# --- Public API ---


def create(
    db_path: Path,
    chat_id: int,
    tool_name: str,
    tool_args: dict,
    preview: str,
    original_message: str = "",
) -> str:
    """Create a pending approval. Returns approval_id (8-char)."""
    import sqlite3
    approval_id = str(uuid.uuid4())[:8]
    resolved = db_path.resolve()
    log.info("[APPROVAL] create: id=%s db_path=%s", approval_id, resolved)
    import sys
    sys.stderr.write(f"[APPROVAL] create: id={approval_id} db_path={resolved}\n")
    sys.stderr.flush()
    _ensure_db(resolved)
    conn = sqlite3.connect(str(resolved))
    try:
        conn.execute(
            """INSERT INTO approvals (id, chat_id, tool_name, tool_args, preview, status, original_message)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (approval_id, chat_id, tool_name, json.dumps(tool_args), preview, original_message),
        )
        conn.commit()
    finally:
        conn.close()
    _cache_register(approval_id, resolved)
    return approval_id


def list_pending(chat_id: int, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """List pending approvals for chat. Expires any older than 24 hours."""
    if db_path is None:
        db_path = get_woody_db_path()
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        return []
    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    _saved = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")}
    try:
        import woody.app as _wa
        sys.modules["app"] = _wa
        from woody.app.approvals import list_pending_approvals
        approvals = list_pending_approvals(db_path, chat_id=chat_id)
        for a in approvals:
            _cache_register(a.get("id", ""), db_path)
        return approvals
    finally:
        for k, mod in _saved.items():
            sys.modules[k] = mod


def execute(
    approval_id: str,
    chat_id: int,
    db_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """Execute a pending approval. Returns (success, message)."""
    aid = approval_id.strip()
    if db_path is None:
        db_path = Path(_approval_db_paths.get(aid) or str(get_woody_db_path()))
    else:
        db_path = Path(db_path)
    db_path = db_path.resolve()
    woody_dir = Path(__file__).resolve().parent.parent / "woody"

    _ensure_db(db_path)
    rec = _get_approval_raw(db_path, approval_id)

    if not rec:
        import sqlite3
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT id, status, created_at FROM approvals WHERE LOWER(id) = LOWER(?)",
                (aid,),
            ).fetchone()
            conn.close()
            if row:
                return False, f"Approval {approval_id} exists but status is '{row[1]}'. It may have been expired or already processed."
        except Exception:
            pass
        for candidate in _get_db_candidates():
            try:
                cand = candidate.resolve()
            except Exception:
                continue
            if cand == db_path or not candidate.exists():
                continue
            try:
                rec = _get_approval_raw(candidate, approval_id)
                if rec:
                    db_path = cand
                    log.info("[APPROVAL] Found %s in fallback DB: %s", approval_id, db_path)
                    _cache_register(aid, db_path)
                    break
            except Exception:
                pass
        if not rec:
            return False, f"Unknown approval ID: {approval_id}. It may have expired. Try the action again."

    if rec["status"] != "pending":
        return False, f"Approval already {rec['status']}"
    if _is_expired(rec.get("created_at", "")):
        return False, "Approval expired (older than 24 hours)."
    if rec["chat_id"] != chat_id:
        return False, "Approval belongs to another chat."

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "UPDATE approvals SET status = 'approved' WHERE LOWER(id) = LOWER(?) AND status = 'pending'",
            (aid,),
        )
        conn.commit()
        if cur.rowcount == 0:
            return False, "Failed to approve"
    finally:
        conn.close()

    args = dict(rec["tool_args"])
    if rec["tool_name"] == "calendar_create_event":
        orig = (rec.get("original_message") or "").strip()
        if orig:
            tz_name = os.environ.get("CALENDAR_TIMEZONE", "UTC")
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc
            _saved = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")}
            try:
                import woody.app as _wa
                sys.modules["app"] = _wa
                from woody.app.agent import _resolve_date_phrases
                _, resolved_iso = _resolve_date_phrases(orig, datetime.now(tz))
                if resolved_iso:
                    start_d = datetime.strptime(resolved_iso, "%Y-%m-%d").date()
                    args["start"] = resolved_iso
                    args["end"] = (start_d + timedelta(days=1)).isoformat()
            finally:
                for k, mod in _saved.items():
                    sys.modules[k] = mod
    if rec["tool_name"] in ("reminder_create", "reminder_cancel", "todo_add", "todo_complete", "todo_remove", "wishlist_add", "wishlist_remove"):
        args["chat_id"] = chat_id

    _saved = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")}
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        import woody.app as _wa
        sys.modules["app"] = _wa
        from woody.app.tools import execute_tool
        from woody.app.conversation import add_message
        log.info("[APPROVAL] execute: running tool %s", rec["tool_name"])
        import sys
        sys.stderr.write(f"[APPROVAL] execute: running tool {rec['tool_name']}\n")
        sys.stderr.flush()
        result = execute_tool(rec["tool_name"], args)
        success_msg = f"Done. {result}"
        add_message(db_path, chat_id, "user", f"APPROVE {approval_id}")
        add_message(db_path, chat_id, "assistant", success_msg)
        return True, success_msg
    except Exception as e:
        return False, str(e)
    finally:
        for k, mod in _saved.items():
            sys.modules[k] = mod


def reject(
    approval_id: str,
    chat_id: int,
    db_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """Reject a pending approval. Returns (success, message)."""
    aid = approval_id.strip()
    if db_path is None:
        db_path = Path(_approval_db_paths.get(aid) or str(get_woody_db_path()))
    else:
        db_path = Path(db_path)
    db_path = db_path.resolve()
    woody_dir = Path(__file__).resolve().parent.parent / "woody"
    _ensure_db(db_path)

    _saved = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")}
    for p in (woody_dir, Path(__file__).resolve().parent.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        import woody.app as _wa
        sys.modules["app"] = _wa
        from woody.app.approvals import reject as woody_reject, get_approval, is_expired
        from woody.app.conversation import add_message
        rec = get_approval(db_path, approval_id)
    finally:
        for k, mod in _saved.items():
            sys.modules[k] = mod

    if not rec:
        return False, f"Unknown approval ID: {approval_id} (DB: {db_path})"
    if rec["status"] != "pending":
        return False, f"Approval already {rec['status']}"
    if is_expired(rec.get("created_at", "")):
        return False, "Approval expired (older than 24 hours)."
    if rec["chat_id"] != chat_id:
        return False, "Approval belongs to another chat."
    if woody_reject(db_path, approval_id):
        _saved2 = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k == "app" or k.startswith("app.")}
        try:
            import woody.app as _wa
            sys.modules["app"] = _wa
            from woody.app.conversation import add_message
            add_message(db_path, chat_id, "user", f"REJECT {approval_id}")
            add_message(db_path, chat_id, "assistant", f"Rejected approval {approval_id}.")
        finally:
            for k, mod in _saved2.items():
                sys.modules[k] = mod
        return True, f"Rejected approval {approval_id}."
    return False, "Failed to reject"
