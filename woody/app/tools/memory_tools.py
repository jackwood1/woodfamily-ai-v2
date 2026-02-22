"""Tools for long-term memory (vector store)."""

from app.memory import memory_add, memory_search
from shared.memory import memory_refresh, memory_delete
from app.tools.registry import PermissionTier, ToolDef, register


def _memory_store_handler(
    fact: str,
    weight: int = 5,
    memory_type: str = "long",
) -> str:
    try:
        ok = memory_add(fact, weight=weight, memory_type=memory_type)
        return "Stored in memory." if ok else "Memory not available (chromadb not installed)."
    except Exception as e:
        return f"Memory store failed: {e}. Chromadb may not be installed or the DB may be corrupted."


def _memory_search_handler(
    query: str,
    n: int = 5,
    memory_type: str = "",
) -> str:
    try:
        mtype = memory_type.strip() or None
        if mtype and mtype not in ("short", "long"):
            mtype = None
        results = memory_search(query, n=n, memory_type=mtype)
    except Exception as e:
        return f"Memory search failed: {e}. Chromadb may not be installed or the DB may be corrupted."
    if not results:
        return "No relevant memories found."
    return "\n".join(f"- {r}" for r in results)


register(
    ToolDef(
        name="memory_store",
        description="Store a fact in memory. Use weight 1-10 for importance (default 5). Use memory_type 'short' for temporary or 'long' for permanent.",
        parameters={
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember"},
                "weight": {"type": "integer", "description": "Importance 1-10 (default 5). Higher = more likely to surface in search."},
                "memory_type": {"type": "string", "description": "short = temporary, long = permanent (default)"},
            },
            "required": ["fact"],
        },
        handler=_memory_store_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="memory_search",
        description="Search memory for relevant facts. Optionally filter by memory_type (short/long).",
        parameters={
            "properties": {
                "query": {"type": "string"},
                "n": {"type": "integer", "description": "Max results"},
                "memory_type": {"type": "string", "description": "Filter: 'short' or 'long' (optional)"},
            },
            "required": ["query"],
        },
        handler=_memory_search_handler,
        tier=PermissionTier.GREEN,
    )
)

def _memory_remove_handler(query: str) -> str:
    """Remove a memory by searching for it. Deletes the best match."""
    try:
        results = memory_search(query, n=1, with_ids=True)
    except Exception as e:
        return f"Memory search failed: {e}."
    if not results:
        return "No matching memory found to remove."
    mem = results[0]
    mem_id = mem.get("id")
    if not mem_id:
        return "Could not identify memory to remove."
    ok = memory_delete(mem_id)
    if not ok:
        return "Failed to remove memory."
    txt = mem.get("text", "")
    return f"Removed: {txt[:80]}{'...' if len(txt) > 80 else ''}" if txt else "Removed."


register(
    ToolDef(
        name="memory_remove",
        description="Remove/forget a memory. Use a search query to find the memory to delete (e.g. 'son 8th grade', 'Quinn birthday'). Deletes the best match.",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "Search query to find the memory to remove"},
            },
            "required": ["query"],
        },
        handler=_memory_remove_handler,
        tier=PermissionTier.YELLOW,
    )
)


def _memory_refresh_handler(query: str, bump_weight: bool = False) -> str:
    result = memory_refresh(query, bump_weight=bump_weight)
    return "Refreshed." if result else "No matching memory found."


register(
    ToolDef(
        name="memory_refresh",
        description="Refresh a memory to make it more relevant in future searches. Finds memory by query (e.g. 'Quinn birthday'), updates last_touched. Use when the user wants to 'exercise' or reinforce a memory.",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "Search query to find the memory (e.g. 'Quinn birthday', 'Jacob allergy')"},
                "bump_weight": {"type": "boolean", "description": "Also increase importance by 1 (default false)"},
            },
            "required": ["query"],
        },
        handler=_memory_refresh_handler,
        tier=PermissionTier.GREEN,
    )
)
