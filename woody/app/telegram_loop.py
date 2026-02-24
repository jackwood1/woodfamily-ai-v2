"""Telegram polling loop and message handling."""

from pathlib import Path

import httpx

from app.agent import run_agent

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _send_message(token: str, chat_id: int, text: str) -> None:
    with httpx.Client() as client:
        client.post(
            f"{TELEGRAM_API.format(token=token)}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30.0,
        )


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
