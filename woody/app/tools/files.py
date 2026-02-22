"""Sandboxed file tools. Paths relative to sandbox root."""

from pathlib import Path

from app.config import get_sandbox_dir
from app.tools.registry import PermissionTier, ToolDef, register


def _resolve_safe(path_str: str) -> Path:
    """Resolve path within sandbox. Reject traversal and absolute paths."""
    if not path_str or path_str.strip() != path_str:
        raise ValueError("Invalid path")
    if path_str.startswith("/") or "\\" in path_str:
        raise ValueError("Absolute paths not allowed")
    parts = Path(path_str).parts
    for p in parts:
        if p in (".", ".."):
            raise ValueError("Path traversal not allowed")
    root = get_sandbox_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    resolved = (root / path_str).resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError("Path outside sandbox")
    return resolved


def _file_read_handler(path: str) -> str:
    p = _resolve_safe(path)
    if not p.exists():
        return f"File not found: {path}"
    if p.is_dir():
        return f"Not a file: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"Permission denied reading {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def _file_write_handler(path: str, content: str) -> str:
    try:
        p = _resolve_safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except PermissionError:
        return f"Permission denied writing to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _file_list_handler(path: str = ".") -> str:
    p = _resolve_safe(path)
    if not p.exists():
        return f"Path not found: {path}"
    if not p.is_dir():
        return f"Not a directory: {path}"
    items = sorted(p.iterdir())
    lines = []
    for i in items:
        kind = "d" if i.is_dir() else "f"
        lines.append(f"  {kind}  {i.name}")
    return "\n".join(lines) if lines else "(empty)"


register(
    ToolDef(
        name="file_read",
        description="Read contents of a file from the sandbox",
        parameters={
            "properties": {"path": {"type": "string", "description": "Relative path to file"}},
            "required": ["path"],
        },
        handler=_file_read_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="file_write",
        description="Write content to a file in the sandbox",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "Relative path to file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        handler=_file_write_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="file_list",
        description="List files in a sandbox directory",
        parameters={
            "properties": {"path": {"type": "string", "description": "Relative path to directory (default: .)"}},
            "required": [],
        },
        handler=_file_list_handler,
        tier=PermissionTier.GREEN,
    )
)
