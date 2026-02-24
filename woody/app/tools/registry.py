"""Tool registry and policy engine."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict


class PermissionTier(str, Enum):
    GREEN = "green"   # Safe read-only
    YELLOW = "yellow"  # Write tools (execute directly)
    RED = "red"       # Disabled


class ToolDef(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    tier: PermissionTier


_registry: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> None:
    _registry[tool.name] = tool


def get(name: str) -> ToolDef | None:
    return _registry.get(name)


def get_all() -> list[ToolDef]:
    return list(_registry.values())


def get_openai_tools() -> list[dict[str, Any]]:
    """Return tools in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": t.parameters.get("properties", {}),
                    "required": t.parameters.get("required", []),
                },
            },
        }
        for t in _registry.values()
        if t.tier != PermissionTier.RED
    ]


def is_write_tool(name: str) -> bool:
    tool = get(name)
    return tool is not None and tool.tier == PermissionTier.YELLOW


def execute_tool(name: str, args: dict[str, Any], **kwargs: Any) -> Any:
    """Execute tool after policy check."""
    tool = get(name)
    if not tool:
        raise ValueError(f"Unknown tool: {name}")
    if tool.tier == PermissionTier.RED:
        raise ValueError(f"Tool {name} is disabled")
    return tool.handler(**args, **kwargs)
