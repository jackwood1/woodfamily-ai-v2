"""Gmail tools - requires Google OAuth via dashboard."""

import sys
from pathlib import Path

# Add repo root for shared
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from app.tools.registry import PermissionTier, ToolDef, register

try:
    from googleapiclient.discovery import build
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def _get_creds():
    from shared.google_tokens import get_credentials
    return get_credentials()


def _gmail_search_handler(query: str, max_results: int = 10) -> str:
    creds, err = _get_creds()
    if err:
        return err
    try:
        service = build("gmail", "v1", credentials=creds)
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        msgs = results.get("messages", [])
        if not msgs:
            return "No messages found"
        lines = []
        for m in msgs[:5]:
            msg = service.users().messages().get(userId="me", id=m["id"]).execute()
            payload = msg.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            subj = headers.get("Subject", "(no subject)")
            from_ = headers.get("From", "")
            lines.append(f"- {subj} (from {from_})")
        return "\n".join(lines)
    except Exception as e:
        err = str(e).lower()
        if "credentials" in err or "token" in err or "invalid_grant" in err:
            return "Gmail: Token expired or invalid. Reconnect Google in the dashboard."
        if "quota" in err or "rate" in err:
            return "Gmail: Rate limit exceeded. Try again later."
        if "timeout" in err or "connection" in err:
            return "Gmail: Connection failed. Check your network."
        return f"Gmail error: {e}"


def _gmail_send_handler(to: str, subject: str, body: str) -> str:
    creds, err = _get_creds()
    if err:
        return err
    try:
        import base64
        from email.mime.text import MIMEText
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Sent email to {to}"
    except Exception as e:
        err = str(e).lower()
        if "credentials" in err or "token" in err or "invalid_grant" in err:
            return "Gmail send: Token expired or invalid. Reconnect Google in the dashboard."
        if "quota" in err or "rate" in err:
            return "Gmail send: Rate limit exceeded. Try again later."
        if "timeout" in err or "connection" in err:
            return "Gmail send: Connection failed. Check your network."
        return f"Gmail send error: {e}"


register(
    ToolDef(
        name="gmail_search",
        description="Search Gmail inbox",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "Gmail search query"},
                "max_results": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        },
        handler=_gmail_search_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="gmail_send",
        description="Send an email via Gmail",
        parameters={
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        handler=_gmail_send_handler,
        tier=PermissionTier.YELLOW,
    )
)
