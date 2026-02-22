"""Conversation memory - persist chat history per chat_id."""

from pathlib import Path
from typing import Any, List

from app.db import get_conn


def get_messages(db_path: Path, chat_id: int, limit: int = 20) -> List[dict]:
    """Load recent messages for chat_id."""
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT role, content FROM conversation_messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    # Reverse to chronological order
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def add_message(db_path: Path, chat_id: int, role: str, content: str) -> None:
    """Append a message to conversation history."""
    conn = get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO conversation_messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        conn.commit()
    finally:
        conn.close()
