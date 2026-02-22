"""COMMUNICATIONS tools - send, read, manage email and SMS via communications agent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from app.tools.registry import PermissionTier, ToolDef, register


def _comms_send_handler(channel: str, to: str, body: str, subject: str = "") -> str:
    from shared.communications_agent import send, sms_available
    if channel == "sms":
        if not sms_available():
            return "SMS not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER in .env"
        result = send("sms", to, body or subject)
    else:
        result = send("email", to, subject or "(no subject)", body or "")
    if result.get("ok"):
        if channel == "sms":
            return f"Sent SMS to {to}."
        return f"Sent email to {to}: {subject[:50]}..."
    return result.get("error", "Send failed")


def _comms_read_handler(query: str = "in:inbox", max_results: int = 10) -> str:
    from shared.communications_agent import read_emails
    result = read_emails(query=query, max_results=max_results)
    if not result.get("ok"):
        return result.get("error", "Read failed")
    msgs = result.get("messages", [])
    if not msgs:
        return "No emails found."
    lines = []
    for m in msgs:
        lines.append(f"- [{m['id']}] {m['subject'][:50]} (from {m['from'][:40]})")
    return "\n".join(lines)


def _comms_get_email_handler(message_id: str) -> str:
    from shared.communications_agent import get_email
    result = get_email(message_id)
    if not result.get("ok"):
        return result.get("error", "Get failed")
    return f"Subject: {result['subject']}\nFrom: {result['from']}\nTo: {result['to']}\nDate: {result['date']}\n\n{result['body'][:2000]}"


def _comms_archive_handler(message_id: str) -> str:
    from shared.communications_agent import archive_email
    result = archive_email(message_id)
    if result.get("ok"):
        return f"Archived email {message_id}."
    return result.get("error", "Archive failed")


def _comms_trash_handler(message_id: str) -> str:
    from shared.communications_agent import trash_email
    result = trash_email(message_id)
    if result.get("ok"):
        return f"Moved email {message_id} to trash."
    return result.get("error", "Trash failed")


register(
    ToolDef(
        name="communications_send",
        description="Send email or SMS. Use channel 'email' or 'sms'. For email: provide to, subject, body. For SMS: provide to and body (subject ignored).",
        parameters={
            "properties": {
                "channel": {"type": "string", "description": "email or sms"},
                "to": {"type": "string", "description": "Email address or phone number (e.g. +1234567890)"},
                "subject": {"type": "string", "description": "Subject (email only)"},
                "body": {"type": "string", "description": "Message body"},
            },
            "required": ["channel", "to", "body"],
        },
        handler=_comms_send_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="communications_read",
        description="Read/search emails from Gmail. Use Gmail search syntax (e.g. 'in:inbox', 'from:someone@example.com', 'subject:meeting').",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "Gmail search query", "default": "in:inbox"},
                "max_results": {"type": "integer", "description": "Max emails to return", "default": 10},
            },
            "required": [],
        },
        handler=_comms_read_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="communications_get_email",
        description="Get full email content by message ID (from communications_read).",
        parameters={
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
        handler=_comms_get_email_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="communications_archive_email",
        description="Archive an email (remove from inbox, keep in All Mail).",
        parameters={
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
        handler=_comms_archive_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="communications_trash_email",
        description="Move an email to trash.",
        parameters={
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
        handler=_comms_trash_handler,
        tier=PermissionTier.YELLOW,
    )
)
