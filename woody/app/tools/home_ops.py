"""Home ops tools (lists/tasks) with SQLite storage."""

from app.config import get_db_path
from app.tools.registry import PermissionTier, ToolDef, register


def _get_conn():
    path = get_db_path()
    return __import__("sqlite3").connect(str(path))


def _list_items_handler(list_name: str = "default") -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            SELECT i.item FROM home_ops_items i
            JOIN home_ops_lists l ON i.list_id = l.id
            WHERE l.name = ?
            ORDER BY i.created_at
            """,
            (list_name,),
        )
        rows = cur.fetchall()
        if not rows:
            return f"List '{list_name}' is empty."
        return "\n".join(f"- {r[0]}" for r in rows)
    finally:
        conn.close()


def _add_item_handler(list_name: str = "default", item: str = "") -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO home_ops_lists (name) VALUES (?)",
            (list_name,),
        )
        conn.commit()
        cur = conn.execute("SELECT id FROM home_ops_lists WHERE name = ?", (list_name,))
        row = cur.fetchone()
        list_id = row[0]
        conn.execute(
            "INSERT INTO home_ops_items (list_id, item) VALUES (?, ?)",
            (list_id, item),
        )
        conn.commit()
        return f"Added '{item}' to list '{list_name}'."
    finally:
        conn.close()


def _remove_item_handler(list_name: str = "default", item: str = "") -> str:
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            DELETE FROM home_ops_items WHERE list_id = (SELECT id FROM home_ops_lists WHERE name = ?)
            AND item = ?
            """,
            (list_name, item),
        )
        conn.commit()
        if cur.rowcount > 0:
            return f"Removed '{item}' from list '{list_name}'."
        return f"Item '{item}' not found in list '{list_name}'."
    finally:
        conn.close()


register(
    ToolDef(
        name="home_ops_list",
        description="List items in a home ops list (e.g. shopping, tasks)",
        parameters={
            "properties": {"list_name": {"type": "string", "description": "Name of the list"}},
            "required": [],
        },
        handler=_list_items_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="home_ops_add",
        description="Add an item to a home ops list",
        parameters={
            "properties": {
                "list_name": {"type": "string", "description": "Name of the list"},
                "item": {"type": "string", "description": "Item to add"},
            },
            "required": ["item"],
        },
        handler=_add_item_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="home_ops_remove",
        description="Remove an item from a home ops list",
        parameters={
            "properties": {
                "list_name": {"type": "string", "description": "Name of the list"},
                "item": {"type": "string", "description": "Item to remove"},
            },
            "required": ["item"],
        },
        handler=_remove_item_handler,
        tier=PermissionTier.GREEN,
    )
)
