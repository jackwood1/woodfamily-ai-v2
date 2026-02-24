"""
COMMUNICATIONS Agent - Unified interface for email, SMS, and other channels.
Send, read, and manage communications across channels.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths - use shared module so Woody and dashboard always use same DB
from shared.db_path import get_woody_db_path as _get_woody_db_path


def _get_google_creds():
    try:
        from shared.google_tokens import get_credentials
        return get_credentials()
    except Exception as e:
        return None, str(e)


def _yahoo_available() -> bool:
    try:
        from shared.yahoo_tokens import has_valid_tokens
        return has_valid_tokens()
    except Exception:
        return False


# --- Email (Gmail + Yahoo) ---

def send_email(to: str, subject: str, body: str, cc: str = "", provider: Optional[str] = None) -> Dict[str, Any]:
    """Send email via Gmail or Yahoo. provider: 'gmail'|'yahoo'|None (auto: Gmail first, then Yahoo). Returns {ok, message_id, error}."""
    if provider == "yahoo" or (provider is None and not _get_google_creds()[0] and _yahoo_available()):
        from shared.yahoo_mail import send_email_yahoo
        return send_email_yahoo(to, subject, body, cc)
    creds, err = _get_google_creds()
    if err:
        if _yahoo_available():
            from shared.yahoo_mail import send_email_yahoo
            return send_email_yahoo(to, subject, body, cc)
        return {"ok": False, "error": err}
    try:
        from email.mime.text import MIMEText
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"ok": True, "message_id": result.get("id"), "thread_id": result.get("threadId")}
    except Exception as e:
        err = str(e).lower()
        if "credentials" in err or "token" in err or "invalid_grant" in err:
            return {"ok": False, "error": "Gmail: Token expired. Reconnect Google in dashboard."}
        if "quota" in err or "rate" in err:
            return {"ok": False, "error": "Gmail: Rate limit exceeded."}
        return {"ok": False, "error": str(e)}


def read_emails(query: str = "in:inbox", max_results: int = 10, providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Read emails from Gmail and/or Yahoo.
    providers: ['gmail','yahoo'] or None (both if connected). Returns {ok, messages, error}.
    """
    if providers is None:
        providers = []
        if _get_google_creds()[0]:
            providers.append("gmail")
        if _yahoo_available():
            providers.append("yahoo")
    if not providers:
        creds, err = _get_google_creds()
        return {"ok": False, "messages": [], "error": err or "No email provider connected. Connect Google or Yahoo in dashboard."}
    all_messages: List[dict] = []
    last_error: Optional[str] = None
    for p in providers:
        if p == "gmail":
            creds, err = _get_google_creds()
            if err:
                last_error = err
                continue
            try:
                from googleapiclient.discovery import build
                service = build("gmail", "v1", credentials=creds)
                results = service.users().messages().list(
                    userId="me", q=query, maxResults=min(max_results, 50),
                ).execute()
                msgs = results.get("messages", [])
                for m in msgs[:max_results]:
                    msg = service.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
                    payload = msg.get("payload", {})
                    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
                    all_messages.append({
                        "id": f"gmail:{msg['id']}",
                        "thread_id": msg.get("threadId"),
                        "subject": headers.get("subject", "(no subject)"),
                        "from": headers.get("from", ""),
                        "to": headers.get("to", ""),
                        "date": headers.get("date", ""),
                        "snippet": msg.get("snippet", ""),
                        "provider": "gmail",
                    })
            except Exception as e:
                last_error = str(e)
        elif p == "yahoo":
            from shared.yahoo_mail import read_emails_yahoo
            r = read_emails_yahoo(max_results=max_results)
            if r.get("ok") and r.get("messages"):
                for m in r["messages"]:
                    m["id"] = f"yahoo:{m['id']}"
                    m["provider"] = "yahoo"
                    all_messages.append(m)
            elif r.get("error"):
                last_error = r["error"]
    # Dedupe by subject+from+date, sort by date desc
    seen = set()
    unique = []
    for m in all_messages:
        key = (m.get("subject", ""), m.get("from", ""), m.get("date", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(m)
    unique.sort(key=lambda x: x.get("date", ""), reverse=True)
    return {"ok": True, "messages": unique[:max_results], "error": last_error if not unique else None}


def get_email(message_id: str) -> Dict[str, Any]:
    """Get full email by id. Returns {ok, subject, from, to, body, error}. Yahoo: prefix 'yahoo:' not yet supported for full fetch."""
    if message_id.startswith("yahoo:"):
        return {"ok": False, "error": "Yahoo: Full email fetch not yet implemented. Use communications_read for Yahoo."}
    creds, err = _get_google_creds()
    if err:
        return {"ok": False, "error": err}
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        body = ""
        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        return {
            "ok": True,
            "id": msg["id"],
            "subject": headers.get("subject", "(no subject)"),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "body": body,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def archive_email(message_id: str) -> Dict[str, Any]:
    """Archive email (remove from inbox). Returns {ok, error}. Gmail only; Yahoo not supported."""
    if message_id.startswith("yahoo:"):
        return {"ok": False, "error": "Yahoo: Archive not yet implemented."}
    creds, err = _get_google_creds()
    if err:
        return {"ok": False, "error": err}
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def trash_email(message_id: str) -> Dict[str, Any]:
    """Move email to trash. Returns {ok, error}. Gmail only; Yahoo not supported."""
    if message_id.startswith("yahoo:"):
        return {"ok": False, "error": "Yahoo: Trash not yet implemented."}
    creds, err = _get_google_creds()
    if err:
        return {"ok": False, "error": err}
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().trash(userId="me", id=message_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- SMS (Twilio) ---

def send_sms(to: str, body: str) -> Dict[str, Any]:
    """Send SMS via Twilio. Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()
    if not sid or not token or not from_num:
        return {"ok": False, "error": "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER."}
    to_clean = to.strip()
    if not to_clean.startswith("+"):
        to_clean = "+1" + to_clean.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    try:
        import logging
        import sys
        logging.getLogger(__name__).info("[SMS] Sending to %s via Twilio", to_clean)
        sys.stderr.write(f"[SMS] Sending to {to_clean} via Twilio\n")
        sys.stderr.flush()
        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(body=body[:1600], from_=from_num, to=to_clean)
        return {"ok": True, "sid": msg.sid, "status": msg.status}
    except ImportError:
        return {"ok": False, "error": "Twilio library not installed. Run: pip install twilio"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def sms_available() -> bool:
    """Check if SMS (Twilio) is configured."""
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        and os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        and os.environ.get("TWILIO_PHONE_NUMBER", "").strip()
    )


# --- Unified send ---

def send(channel: str, to: str, subject_or_body: str, body: str = "") -> Dict[str, Any]:
    """
    Send via channel. channel: 'email' | 'sms'.
    For email: subject_or_body=subject, body=body.
    For sms: subject_or_body=body (body ignored).
    """
    if channel == "email":
        return send_email(to, subject_or_body, body or subject_or_body)
    if channel == "sms":
        return send_sms(to, subject_or_body)
    return {"ok": False, "error": f"Unknown channel: {channel}. Use 'email' or 'sms'."}


# --- Agent run (inbox scan → contacts + events) ---

def run_communications_agent() -> Dict[str, Any]:
    """
    Run COMMUNICATIONS agent: read inbox, pass to CONTACT agent for
    circle inference, pass to EVENTS agent for potential events (TODOs, meetings).
    Returns summary of proposals created.
    """
    result: Dict[str, Any] = {"ok": True, "channels": {"email": True, "sms": sms_available()}}
    result["circle_proposals"] = 0
    result["event_proposals"] = 0

    # Read inbox
    inbox = read_emails(query="in:inbox", max_results=30)
    if not inbox.get("ok") or not inbox.get("messages"):
        if inbox.get("error"):
            result["error"] = inbox["error"]
        return result

    messages = inbox["messages"]

    # Pass to CONTACT agent for circle inference
    try:
        from shared.contact_agent import process_inbox_messages
        count = process_inbox_messages(messages, min_count=1, max_proposals=15)
        result["circle_proposals"] = count
    except Exception as e:
        result["contact_error"] = str(e)

    # Pass to EVENTS agent for potential events (TODOs, meetings, dates)
    try:
        from shared.events_agent import propose_events_from_emails
        count = propose_events_from_emails(messages, max_proposals=10)
        result["event_proposals"] = count
    except Exception as e:
        result["events_error"] = str(e)

    return result
