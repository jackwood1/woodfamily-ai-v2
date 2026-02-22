"""Background reminder loop - sends daily digest of upcoming events and end-of-day summary via Telegram."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _get_todays_approved_actions(db_path: Path) -> list[dict]:
    """Fetch approvals that were approved today (by created_at date in UTC)."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            SELECT tool_name, tool_args, created_at
            FROM approvals
            WHERE status = 'approved'
            AND date(created_at) = date('now')
            ORDER BY created_at
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [{"tool_name": r[0], "tool_args": json.loads(r[1]), "created_at": r[2]} for r in rows]


def _format_action(action: dict) -> str:
    """Format a single approved action for the summary."""
    name = action.get("tool_name", "")
    args = action.get("tool_args", {})
    if name == "calendar_create_event":
        return f"• Created event: {args.get('summary', '(no title)')} on {args.get('start', '?')}"
    if name == "gmail_send":
        return f"• Sent email to {args.get('to', '?')}: {args.get('subject', '(no subject)')}"
    if name == "communications_send":
        ch = args.get("channel", "?")
        if ch == "sms":
            return f"• Sent SMS to {args.get('to', '?')}"
        return f"• Sent email to {args.get('to', '?')}: {args.get('subject', '(no subject)')}"
    if name == "memory_store":
        content = (args.get("fact") or args.get("content") or args.get("text") or "")[:60]
        full = str(args.get("fact", args.get("content", args.get("text", ""))))
        if len(full) > 60:
            content += "..."
        return f"• Stored memory: {content}"
    if name == "file_write":
        return f"• Wrote to {args.get('path', '?')}"
    return f"• {name}: {json.dumps(args)[:80]}"


def _format_summary(actions: list[dict]) -> str:
    """Format end-of-day summary of what Woody did."""
    if not actions:
        return "📋 Daily summary\n\nNothing to report today."
    lines = ["📋 Daily summary", ""]
    for a in actions:
        lines.append(_format_action(a))
    return "\n".join(lines)


def _run_summary_once(token: str, chat_id: int, db_path: Path) -> bool:
    """Send end-of-day summary if not already sent today. Returns True if sent."""
    today = date.today().isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT 1 FROM daily_summary_sent WHERE sent_date = ?", (today,)).fetchone()
        if row:
            return False
    finally:
        conn.close()

    actions = _get_todays_approved_actions(db_path)
    text = _format_summary(actions)
    if not _send_reminder(token, chat_id, text):
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("INSERT OR IGNORE INTO daily_summary_sent (sent_date) VALUES (?)", (today,))
        conn.commit()
    finally:
        conn.close()
    return True


def _send_reminder(token: str, chat_id: int, text: str) -> bool:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{TELEGRAM_API.format(token=token)}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            return r.status_code == 200
    except Exception:
        return False


def _format_digest(events: list, requires_scheduling: list | None = None) -> str:
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    today_events = [e for e in events if e.get("date") == today]
    tomorrow_events = [e for e in events if e.get("date") == tomorrow]
    lines = ["📅 Coming up"]
    if today_events:
        lines.append("Today: " + ", ".join(e.get("title", "(no title)") for e in today_events))
    else:
        lines.append("Today: nothing")
    if tomorrow_events:
        lines.append("Tomorrow: " + ", ".join(e.get("title", "(no title)") for e in tomorrow_events))
    else:
        lines.append("Tomorrow: nothing")
    if requires_scheduling:
        lines.append("")
        lines.append("⚠️ Requires scheduling:")
        for r in requires_scheduling[:5]:
            due = r.get("next_due", "")
            lines.append(f"  • {r.get('title', '(no title)')} (due {due})")
    return "\n".join(lines)


def _run_once(token: str, chat_id: int, db_path: Path) -> bool:
    """Check if we should send, fetch events, send digest. Returns True if sent."""
    today = date.today().isoformat()
    conn = __import__("sqlite3").connect(str(db_path))
    try:
        row = conn.execute("SELECT 1 FROM reminder_digest_sent WHERE sent_date = ?", (today,)).fetchone()
        if row:
            return False
    finally:
        conn.close()

    events = []
    requires_scheduling = []
    try:
        from shared.reminders import get_upcoming_events_from_api, get_upcoming_events_from_db, get_requires_scheduling_from_api
        events = get_upcoming_events_from_api()
        if not events:
            events = get_upcoming_events_from_db()
        requires_scheduling = get_requires_scheduling_from_api(days=14)
    except Exception:
        pass

    if not events and not requires_scheduling:
        return False

    text = _format_digest(events, requires_scheduling)
    if not _send_reminder(token, chat_id, text):
        return False

    conn = __import__("sqlite3").connect(str(db_path))
    try:
        conn.execute("INSERT OR IGNORE INTO reminder_digest_sent (sent_date) VALUES (?)", (today,))
        conn.commit()
    finally:
        conn.close()
    return True


def _run_user_reminders(token: str, db_path: Path) -> None:
    """Check for due user-created reminders and send them."""
    conn = sqlite3.connect(str(db_path))
    try:
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        cur = conn.execute(
            """
            SELECT id, chat_id, text
            FROM reminders
            WHERE status = 'pending' AND remind_at <= ?
            """,
            (now_str,),
        )
        rows = cur.fetchall()
        for rid, rchat_id, text in rows:
            msg = f"⏰ Reminder: {text}"
            if _send_reminder(token, int(rchat_id), msg):
                conn.execute("UPDATE reminders SET status = 'sent' WHERE id = ?", (rid,))
                conn.commit()
    except Exception as e:
        print(f"User reminder error: {e}")
    finally:
        conn.close()


def _reminder_loop(
    token: str,
    chat_id: int,
    db_path: Path,
    interval_minutes: int = 30,
    hour_utc: int = 8,
    summary_hour_utc: Optional[int] = 5,
) -> None:
    """Run reminder check every interval_minutes. Send digest at hour_utc, summary at summary_hour_utc."""
    user_reminder_interval = 2 * 60  # Check user reminders every 2 min
    last_user_check = 0.0
    while True:
        try:
            now = datetime.utcnow()
            if chat_id is not None:
                if now.hour == hour_utc:
                    _run_once(token, chat_id, db_path)
                if summary_hour_utc is not None and now.hour == summary_hour_utc:
                    _run_summary_once(token, chat_id, db_path)
            # User reminders: check every 2 min
            t = time.time()
            if t - last_user_check >= user_reminder_interval:
                _run_user_reminders(token, db_path)
                last_user_check = t
        except Exception as e:
            print(f"Reminder error: {e}")
        time.sleep(min(user_reminder_interval, interval_minutes * 60))


def start_reminder_loop(
    token: str,
    db_path: Path,
    interval_minutes: int = 30,
    hour_utc: Optional[int] = None,
    summary_hour_utc: Optional[int] = None,
) -> None:
    """Start reminder loop in a daemon thread. User reminders work without TELEGRAM_REMINDER_CHAT_ID."""
    chat_id: Optional[int] = None
    chat_id_str = os.environ.get("TELEGRAM_REMINDER_CHAT_ID", "").strip()
    if chat_id_str:
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            pass
    if hour_utc is None:
        try:
            hour_utc = int(os.environ.get("REMINDER_HOUR_UTC", "8"))
        except ValueError:
            hour_utc = 8
    if summary_hour_utc is None:
        try:
            val = os.environ.get("SUMMARY_HOUR_UTC", "5")
            summary_hour_utc = int(val) if val else None
        except ValueError:
            summary_hour_utc = 5
    thread = threading.Thread(
        target=_reminder_loop,
        args=(token, chat_id, db_path),
        kwargs={
            "interval_minutes": interval_minutes,
            "hour_utc": hour_utc,
            "summary_hour_utc": summary_hour_utc,
        },
        daemon=True,
    )
    thread.start()
