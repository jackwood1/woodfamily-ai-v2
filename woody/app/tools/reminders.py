"""Reminders - time-based notifications via Telegram."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import get_db_path
from app.tools.registry import PermissionTier, ToolDef, register


def _get_conn():
    return sqlite3.connect(str(get_db_path()))


def _parse_remind_at(remind_at: str) -> str | None:
    """Parse natural language or ISO datetime to ISO format. Returns None if invalid."""
    s = (remind_at or "").strip()
    if not s:
        return None
    try:
        import parsedatetime
    except ImportError:
        pass
    # Try ISO format first
    if "T" in s and len(s) >= 19:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    # Natural language
    try:
        import parsedatetime
        cal = parsedatetime.Calendar()
        tz_name = os.environ.get("CALENDAR_TIMEZONE", "UTC")
        try:
            from zoneinfo import ZoneInfo
            ref = datetime.now(ZoneInfo(tz_name))
        except Exception:
            ref = datetime.now()
        result, status = cal.parse(s, ref)
        if status:
            dt = datetime(*result[:6])
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass
    return None


def _reminder_create_handler(text: str, remind_at: str, chat_id: int) -> str:
    parsed = _parse_remind_at(remind_at)
    if not parsed:
        return f"Could not parse '{remind_at}'. Use ISO format (e.g. 2026-02-23T17:30:00) or natural language (e.g. tomorrow at 5pm)."
    from datetime import datetime, timezone
    try:
        remind_dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    except ValueError:
        return f"Invalid datetime: {parsed}"
    now = datetime.now(timezone.utc)
    if remind_dt.tzinfo is None:
        remind_dt = remind_dt.replace(tzinfo=timezone.utc)
    if remind_dt < now:
        return f"Remind time {parsed} is in the past. Use a future date/time."
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO reminders (chat_id, text, remind_at, status) VALUES (?, ?, ?, 'pending')",
            (chat_id, text.strip(), parsed),
        )
        conn.commit()
        rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return f"Reminder set for {parsed}: {text[:50]}{'...' if len(text) > 50 else ''}"
    finally:
        conn.close()


def _reminder_list_handler(chat_id: int) -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            SELECT id, text, remind_at
            FROM reminders
            WHERE chat_id = ? AND status = 'pending'
            ORDER BY remind_at
            LIMIT 20
            """,
            (chat_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return "No pending reminders."
    lines = ["⏰ Pending reminders:"]
    for r in rows:
        lines.append(f"  {r[1]} @ {r[2]} (id: {r[0]})")
    return "\n".join(lines)


def _reminder_cancel_handler(reminder_id: int, chat_id: int) -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND chat_id = ? AND status = 'pending'",
            (reminder_id, chat_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            return f"Cancelled reminder {reminder_id}."
        return f"Reminder {reminder_id} not found or already cancelled."
    finally:
        conn.close()


register(
    ToolDef(
        name="reminder_create",
        description="Create a reminder - Woody will send a Telegram message at the specified time. Use natural language (e.g. 'tomorrow at 5pm', 'Monday at 9am') or ISO format.",
        parameters={
            "properties": {
                "text": {"type": "string", "description": "What to remind about"},
                "remind_at": {"type": "string", "description": "When to remind (e.g. 'tomorrow at 5pm', '2026-02-23T17:30:00')"},
            },
            "required": ["text", "remind_at"],
        },
        handler=_reminder_create_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="reminder_list",
        description="List pending reminders for this chat",
        parameters={"properties": {}, "required": []},
        handler=_reminder_list_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="reminder_cancel",
        description="Cancel a reminder by ID (from reminder_list)",
        parameters={
            "properties": {
                "reminder_id": {"type": "integer", "description": "ID of reminder to cancel"},
            },
            "required": ["reminder_id"],
        },
        handler=_reminder_cancel_handler,
        tier=PermissionTier.YELLOW,
    )
)
