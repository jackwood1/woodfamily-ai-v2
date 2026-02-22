"""TODOs - tasks with optional due dates and completion status."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from app.config import get_db_path
from app.tools.registry import PermissionTier, ToolDef, register


def _get_conn():
    return sqlite3.connect(str(get_db_path()))


def _parse_due_date(due_date: str) -> str | None:
    """Parse natural language or YYYY-MM-DD to ISO date. Returns None if empty/invalid."""
    s = (due_date or "").strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        import parsedatetime
        cal = parsedatetime.Calendar()
        import os
        tz_name = os.environ.get("CALENDAR_TIMEZONE", "UTC")
        try:
            from zoneinfo import ZoneInfo
            ref = datetime.now(ZoneInfo(tz_name))
        except Exception:
            ref = datetime.now()
        result, status = cal.parse(s, ref)
        if status:
            dt = datetime(*result[:6])
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _todo_add_handler(content: str, chat_id: int, due_date: str = "") -> str:
    conn = _get_conn()
    try:
        due = _parse_due_date(due_date) if due_date else None
        conn.execute(
            "INSERT INTO todos (chat_id, content, status, due_date) VALUES (?, ?, 'pending', ?)",
            (chat_id, content.strip(), due),
        )
        conn.commit()
        return f"Added TODO: {content[:60]}{'...' if len(content) > 60 else ''}"
    finally:
        conn.close()


def _todo_list_handler(chat_id: int, include_done: bool = False) -> str:
    conn = _get_conn()
    try:
        if include_done:
            cur = conn.execute(
                """
                SELECT id, content, status, due_date
                FROM todos
                WHERE chat_id = ?
                ORDER BY status ASC, due_date IS NULL, due_date ASC, created_at
                LIMIT 30
                """,
                (chat_id,),
            )
        else:
            cur = conn.execute(
                """
                SELECT id, content, status, due_date
                FROM todos
                WHERE chat_id = ? AND status = 'pending'
                ORDER BY due_date IS NULL, due_date ASC, created_at
                LIMIT 30
                """,
                (chat_id,),
            )
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return "No TODOs." if not include_done else "No TODOs (pending or done)."
    lines = ["📋 TODOs:"]
    for r in rows:
        rid, content, status, due = r
        mark = "✅" if status == "done" else "⬜"
        due_str = f" (due: {due})" if due else ""
        lines.append(f"  {mark} [{rid}] {content}{due_str}")
    return "\n".join(lines)


def _todo_complete_handler(todo_id: int, chat_id: int) -> str:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT content FROM todos WHERE id = ? AND chat_id = ? AND status = 'pending'",
            (todo_id, chat_id),
        ).fetchone()
        if not row:
            return f"TODO {todo_id} not found or already done."
        content = row[0]
        conn.execute(
            "UPDATE todos SET status = 'done' WHERE id = ? AND chat_id = ? AND status = 'pending'",
            (todo_id, chat_id),
        )
        conn.commit()
        try:
            from shared.events_agent import capture_completed_todo
            capture_completed_todo(todo_id, content)
        except Exception:
            pass
        return f"Marked TODO {todo_id} as done."
    finally:
        conn.close()


def _todo_remove_handler(todo_id: int, chat_id: int) -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM todos WHERE id = ? AND chat_id = ?",
            (todo_id, chat_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            return f"Removed TODO {todo_id}."
        return f"TODO {todo_id} not found."
    finally:
        conn.close()


register(
    ToolDef(
        name="todo_add",
        description="Add a TODO. Use due_date for optional due date (e.g. 2026-02-23 or 'tomorrow').",
        parameters={
            "properties": {
                "content": {"type": "string", "description": "The TODO text"},
                "due_date": {"type": "string", "description": "Optional due date (YYYY-MM-DD or natural language)"},
            },
            "required": ["content"],
        },
        handler=_todo_add_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="todo_list",
        description="List TODOs. By default shows only pending. Set include_done=true to see completed.",
        parameters={
            "properties": {
                "include_done": {"type": "boolean", "description": "Include completed TODOs"},
            },
            "required": [],
        },
        handler=_todo_list_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="todo_complete",
        description="Mark a TODO as done by ID (from todo_list)",
        parameters={
            "properties": {
                "todo_id": {"type": "integer", "description": "ID of TODO to complete"},
            },
            "required": ["todo_id"],
        },
        handler=_todo_complete_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="todo_remove",
        description="Remove a TODO by ID (from todo_list)",
        parameters={
            "properties": {
                "todo_id": {"type": "integer", "description": "ID of TODO to remove"},
            },
            "required": ["todo_id"],
        },
        handler=_todo_remove_handler,
        tier=PermissionTier.YELLOW,
    )
)
