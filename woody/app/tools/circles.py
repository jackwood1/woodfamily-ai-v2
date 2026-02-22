"""Circle and contact tools - connect people, places, memories via dashboard API."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from app.tools.registry import PermissionTier, ToolDef, register
from shared.dashboard_client import dashboard_request


def _circle_list_handler() -> str:
    data, err = dashboard_request("GET", "/api/circles")
    if err:
        return f"Circles: {err}"
    circles = data if isinstance(data, list) else []
    if not circles:
        return "No circles yet. Create one in the dashboard or say 'create a circle called Family'."
    lines = ["Circles:"]
    for c in circles:
        lines.append(f"  • {c.get('name', '?')} (id: {c.get('id')})")
    return "\n".join(lines)


def _circle_create_handler(name: str, description: str = "") -> str:
    data, err = dashboard_request("POST", "/api/circles", json={"name": name, "description": description})
    if err:
        return f"Circle create: {err}"
    return f"Created circle '{name}'."


def _circle_add_member_handler(circle_id: int, entity_type: str, entity_id: str) -> str:
    if entity_type not in ("contact", "place", "memory"):
        return "entity_type must be contact, place, or memory"
    data, err = dashboard_request(
        "POST", f"/api/circles/{circle_id}/members",
        json={"entity_type": entity_type, "entity_id": str(entity_id)},
    )
    if err:
        return f"Add member: {err}"
    return f"Added {entity_type} {entity_id} to circle."


def _contact_list_handler() -> str:
    data, err = dashboard_request("GET", "/api/contacts")
    if err:
        return f"Contacts: {err}"
    contacts = data if isinstance(data, list) else []
    if not contacts:
        return "No contacts yet. Add them in the dashboard."
    lines = ["Contacts:"]
    for c in contacts:
        lines.append(f"  • {c.get('name', '?')} (id: {c.get('id')})")
    return "\n".join(lines)


def _contact_add_handler(name: str, email: str = "", phone: str = "", notes: str = "") -> str:
    data, err = dashboard_request(
        "POST", "/api/contacts",
        json={"name": name, "email": email, "phone": phone, "notes": notes},
    )
    if err:
        return f"Contact add: {err}"
    return f"Added contact '{name}'."


def _place_list_handler() -> str:
    data, err = dashboard_request("GET", "/api/places")
    if err:
        return f"Places: {err}"
    places = data if isinstance(data, list) else []
    if not places:
        return "No places yet. Add them in the dashboard."
    lines = ["Places:"]
    for p in places:
        lines.append(f"  • {p.get('name', '?')} (id: {p.get('id')})")
    return "\n".join(lines)


def _place_add_handler(name: str, address: str = "", notes: str = "") -> str:
    data, err = dashboard_request(
        "POST", "/api/places",
        json={"name": name, "address": address, "notes": notes},
    )
    if err:
        return f"Place add: {err}"
    return f"Added place '{name}'."


register(ToolDef(
    name="circle_list",
    description="List circles (groups of people, places, memories)",
    parameters={"properties": {}, "required": []},
    handler=_circle_list_handler,
    tier=PermissionTier.GREEN,
))

register(ToolDef(
    name="circle_create",
    description="Create a circle to connect people, places, and memories",
    parameters={
        "properties": {
            "name": {"type": "string", "description": "Circle name (e.g. Family, Work)"},
            "description": {"type": "string", "description": "Optional description"},
        },
        "required": ["name"],
    },
    handler=_circle_create_handler,
    tier=PermissionTier.YELLOW,
))

register(ToolDef(
    name="circle_add_member",
    description="Add a contact, place, or memory to a circle. Use IDs from circle_list, contact_list, place_list, or memory id.",
    parameters={
        "properties": {
            "circle_id": {"type": "integer", "description": "Circle ID"},
            "entity_type": {"type": "string", "description": "contact, place, or memory"},
            "entity_id": {"type": "string", "description": "ID of the contact, place, or memory"},
        },
        "required": ["circle_id", "entity_type", "entity_id"],
    },
    handler=_circle_add_member_handler,
    tier=PermissionTier.YELLOW,
))

register(ToolDef(
    name="contact_list",
    description="List contacts from the dashboard",
    parameters={"properties": {}, "required": []},
    handler=_contact_list_handler,
    tier=PermissionTier.GREEN,
))

register(ToolDef(
    name="contact_add",
    description="Add a contact to the dashboard",
    parameters={
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
    },
    handler=_contact_add_handler,
    tier=PermissionTier.YELLOW,
))

register(ToolDef(
    name="place_list",
    description="List places from the dashboard",
    parameters={"properties": {}, "required": []},
    handler=_place_list_handler,
    tier=PermissionTier.GREEN,
))

register(ToolDef(
    name="place_add",
    description="Add a place to the dashboard",
    parameters={
        "properties": {
            "name": {"type": "string"},
            "address": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
    },
    handler=_place_add_handler,
    tier=PermissionTier.YELLOW,
))
