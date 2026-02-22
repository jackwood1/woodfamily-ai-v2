"""Wishlist - things you want, may never complete. Like TODOs but without completion."""

from __future__ import annotations

import sqlite3

from app.config import get_db_path
from app.tools.registry import PermissionTier, ToolDef, register


def _get_conn():
    return sqlite3.connect(str(get_db_path()))


def _wishlist_add_handler(content: str, chat_id: int) -> str:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO wishlist (chat_id, content) VALUES (?, ?)",
            (chat_id, content.strip()),
        )
        conn.commit()
        return f"Added to wishlist: {content[:60]}{'...' if len(content) > 60 else ''}"
    finally:
        conn.close()


def _wishlist_list_handler(chat_id: int) -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT id, content FROM wishlist WHERE chat_id = ? ORDER BY created_at DESC LIMIT 50",
            (chat_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return "Wishlist is empty."
    lines = ["✨ Wishlist:"]
    for r in rows:
        rid, content = r
        lines.append(f"  [{rid}] {content}")
    return "\n".join(lines)


def _wishlist_remove_handler(wishlist_id: int, chat_id: int) -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM wishlist WHERE id = ? AND chat_id = ?",
            (wishlist_id, chat_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            return f"Removed from wishlist."
        return f"Wishlist item {wishlist_id} not found."
    finally:
        conn.close()


register(
    ToolDef(
        name="wishlist_add",
        description="Add an item to the wishlist. Use for things you want but may never get (e.g. 'Trip to Japan', 'Learn piano'). Unlike TODOs, these are aspirational.",
        parameters={
            "properties": {
                "content": {"type": "string", "description": "The wishlist item"},
            },
            "required": ["content"],
        },
        handler=_wishlist_add_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="wishlist_list",
        description="List wishlist items.",
        parameters={"properties": {}, "required": []},
        handler=_wishlist_list_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="wishlist_remove",
        description="Remove an item from the wishlist by ID (from wishlist_list).",
        parameters={
            "properties": {
                "wishlist_id": {"type": "integer", "description": "ID of wishlist item to remove"},
            },
            "required": ["wishlist_id"],
        },
        handler=_wishlist_remove_handler,
        tier=PermissionTier.YELLOW,
    )
)
