"""Telegram polling loop and message handling."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from app.agent import _resolve_date_phrases, run_agent
from app.approvals import approve, get_approval, reject, is_expired
from app.tools import execute_tool

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _send_message(token: str, chat_id: int, text: str) -> None:
    with httpx.Client() as client:
        client.post(
            f"{TELEGRAM_API.format(token=token)}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30.0,
        )


def _process_approval_command(
    text: str,
    chat_id: int,
    token: str,
    db_path: Path,
) -> bool:
    """Handle APPROVE <ID> or REJECT <ID>. Returns True if handled."""
    text = text.strip()
    approve_match = re.match(r"approve\s+(\w+)", text, re.IGNORECASE)
    reject_match = re.match(r"reject\s+(\w+)", text, re.IGNORECASE)

    if approve_match:
        approval_id = approve_match.group(1)
        rec = get_approval(db_path, approval_id)
        if not rec:
            _send_message(token, chat_id, f"Unknown approval ID: {approval_id}")
            return True
        if rec["status"] != "pending":
            _send_message(token, chat_id, f"Approval {approval_id} already {rec['status']}")
            return True
        if rec["chat_id"] != chat_id:
            _send_message(token, chat_id, "Approval belongs to another chat.")
            return True
        if is_expired(rec.get("created_at", "")):
            _send_message(token, chat_id, "Approval expired (older than 24 hours).")
            return True
        if approve(db_path, approval_id):
            args = dict(rec["tool_args"])
            # Re-resolve date from original message when executing calendar event
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
            result = execute_tool(rec["tool_name"], args)
            _send_message(token, chat_id, f"Done. Result: {result}")
        return True

    if reject_match:
        approval_id = reject_match.group(1)
        if reject(db_path, approval_id):
            _send_message(token, chat_id, f"Rejected approval {approval_id}.")
        else:
            _send_message(token, chat_id, f"Unknown or already processed: {approval_id}")
        return True

    return False


def _ensure_tools_loaded() -> None:
    import app.tools.calendar  # noqa: F401
    import app.tools.files  # noqa: F401
    import app.tools.gmail  # noqa: F401
    import app.tools.communications  # noqa: F401
    import app.tools.github  # noqa: F401
    import app.tools.home_ops  # noqa: F401
    import app.tools.memory_tools  # noqa: F401
    import app.tools.reminders  # noqa: F401
    import app.tools.todos  # noqa: F401
    import app.tools.wishlist  # noqa: F401
    import app.tools.circles  # noqa: F401
    import app.tools.web_research  # noqa: F401


def process_message(
    token: str,
    db_path: Path,
    openai_key: str,
    chat_id: int,
    text: str,
) -> None:
    """Process one inbound message and send response."""
    _ensure_tools_loaded()

    if _process_approval_command(text, chat_id, token, db_path):
        return

    if text.strip().lower() == "/chatid":
        _send_message(token, chat_id, f"Your chat ID: {chat_id}\nAdd TELEGRAM_REMINDER_CHAT_ID={chat_id} to .env for daily event reminders.")
        return

    try:
        response = run_agent(text, openai_key, db_path, chat_id)
        _send_message(token, chat_id, response or "(No response)")
    except Exception as e:
        _send_message(token, chat_id, f"Error: {e}")


def run_polling_loop(token: str, db_path: Path, openai_key: str) -> None:
    """Long-poll Telegram for messages and process them."""
    url = f"{TELEGRAM_API.format(token=token)}/getUpdates"
    offset = 0

    try:
        while True:
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.get(url, params={"offset": offset, "timeout": 30})
                    data = resp.json()
            except Exception as e:
                print(f"Poll error: {e}")
                continue

            if not data.get("ok"):
                print(f"API error: {data}")
                continue

            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")
                if not text or chat_id is None:
                    continue
                process_message(token, db_path, openai_key, chat_id, text)
    except KeyboardInterrupt:
        print("\nStopping woody.")
