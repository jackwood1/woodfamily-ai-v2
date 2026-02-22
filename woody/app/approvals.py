"""Approval workflow for write actions."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from app.db import execute, get_conn


def create_approval(
    db_path: Path,
    chat_id: int,
    tool_name: str,
    tool_args: dict[str, Any],
    preview: str,
    original_message: str = "",
) -> str:
    """Persist approval record and return approval ID."""
    approval_id = str(uuid.uuid4())[:8]
    execute(
        db_path,
        """
        INSERT INTO approvals (id, chat_id, tool_name, tool_args, preview, status, original_message)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (approval_id, chat_id, tool_name, json.dumps(tool_args), preview, original_message),
    )
    return approval_id


def get_approval(db_path: Path, approval_id: str) -> Optional[dict[str, Any]]:
    """Fetch approval by ID (case-insensitive lookup)."""
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT id, chat_id, tool_name, tool_args, preview, status, original_message, created_at FROM approvals WHERE LOWER(id) = LOWER(?)",
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


def approve(db_path: Path, approval_id: str) -> bool:
    """Mark approval as approved. Returns True if found and was pending."""
    cur = execute(
        db_path,
        "UPDATE approvals SET status = 'approved' WHERE LOWER(id) = LOWER(?) AND status = 'pending'",
        (approval_id.strip(),),
    )
    return cur.rowcount > 0


def reject(db_path: Path, approval_id: str) -> bool:
    """Mark approval as rejected. Returns True if found and was pending."""
    cur = execute(
        db_path,
        "UPDATE approvals SET status = 'rejected' WHERE LOWER(id) = LOWER(?) AND status = 'pending'",
        (approval_id.strip(),),
    )
    return cur.rowcount > 0


def expire_old_approvals(db_path: Path) -> int:
    """Mark pending approvals older than 24 hours as expired. Returns count expired."""
    cur = execute(
        db_path,
        "UPDATE approvals SET status = 'expired' WHERE status = 'pending' AND created_at < datetime('now', '-24 hours')",
        (),
    )
    return cur.rowcount


def list_pending_approvals(db_path: Path, chat_id: Optional[int] = None) -> list:
    """List pending approvals, expiring any older than 24 hours. Optionally filter by chat_id."""
    expire_old_approvals(db_path)
    conn = get_conn(db_path)
    try:
        if chat_id is not None:
            cur = conn.execute(
                """SELECT id, chat_id, tool_name, tool_args, preview, status, original_message, created_at
                   FROM approvals WHERE status = 'pending' AND chat_id = ? ORDER BY created_at DESC""",
                (chat_id,),
            )
        else:
            cur = conn.execute(
                """SELECT id, chat_id, tool_name, tool_args, preview, status, original_message, created_at
                   FROM approvals WHERE status = 'pending' ORDER BY created_at DESC""",
                (),
            )
        rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        out.append({
            "id": row[0],
            "chat_id": row[1],
            "tool_name": row[2],
            "tool_args": json.loads(row[3]),
            "preview": row[4],
            "status": row[5],
            "original_message": row[6] if len(row) > 6 else "",
            "created_at": row[7] if len(row) > 7 else "",
        })
    return out


def is_expired(created_at: str) -> bool:
    """Check if approval is older than 24 hours."""
    if not created_at:
        return False
    from datetime import datetime, timedelta, timezone
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > timedelta(hours=24)
    except (ValueError, TypeError):
        return False
