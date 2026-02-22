"""
Yahoo Mail via IMAP/SMTP with XOAUTH2.
Uses OAuth tokens from yahoo_tokens to authenticate.
"""

import base64
import imaplib
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from shared.yahoo_tokens import get_access_token, load_tokens


IMAP_HOST = "imap.mail.yahoo.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 465


def _get_email() -> Optional[str]:
    """Get stored Yahoo email from tokens."""
    t = load_tokens()
    return (t or {}).get("email", "").strip() or None


def _xoauth2_string(email: str, access_token: str) -> str:
    """Build XOAUTH2 auth string for IMAP: user=<email>^Aauth=Bearer <token>^A^A"""
    raw = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode()).decode()


def read_emails_yahoo(
    folder: str = "INBOX",
    max_results: int = 10,
    since_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Read emails from Yahoo Mail via IMAP.
    Returns {ok, messages, error}. messages have id, subject, from, to, date, snippet.
    """
    access_token, err = get_access_token()
    if err:
        return {"ok": False, "messages": [], "error": err}
    email = _get_email()
    if not email:
        return {"ok": False, "messages": [], "error": "Yahoo email not stored. Reconnect Yahoo."}
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        auth_str = _xoauth2_string(email, access_token)
        imap.authenticate("XOAUTH2", lambda x: auth_str)
        imap.select(folder, readonly=True)
        # Search: ALL or UNSEEN
        if since_days:
            from datetime import datetime, timedelta
            since = (datetime.utcnow() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            status, data = imap.search(None, f"SINCE {since}")
        else:
            status, data = imap.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            imap.logout()
            return {"ok": True, "messages": []}
        msg_ids = data[0].split()
        msg_ids = msg_ids[-max_results:] if len(msg_ids) > max_results else msg_ids
        msg_ids.reverse()  # newest first
        out = []
        for mid in msg_ids:
            try:
                status, msg_data = imap.fetch(mid, "(RFC822.HEADER)")
                if status != "OK" or not msg_data:
                    continue
                from email import message_from_bytes
                raw = msg_data[0][1]
                msg = message_from_bytes(raw)
                subject = msg.get("Subject", "(no subject)")
                if isinstance(subject, bytes):
                    from email.header import decode_header
                    decoded = decode_header(subject)
                    subject = "".join(
                        (t.decode(c or "utf-8") if isinstance(t, bytes) else t)
                        for t, c in decoded
                    )
                from_addr = msg.get("From", "")
                to_addr = msg.get("To", "")
                date_str = msg.get("Date", "")
                # Get snippet from first 200 chars of body if available
                status2, body_data = imap.fetch(mid, "(RFC822)")
                snippet = ""
                if status2 == "OK" and body_data:
                    full_msg = message_from_bytes(body_data[0][1])
                    if full_msg.is_multipart():
                        for part in full_msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        snippet = payload.decode("utf-8", errors="replace")[:200]
                                except Exception:
                                    pass
                                break
                    else:
                        try:
                            payload = full_msg.get_payload(decode=True)
                            if payload:
                                snippet = payload.decode("utf-8", errors="replace")[:200]
                        except Exception:
                            pass
                out.append({
                    "id": mid.decode() if isinstance(mid, bytes) else str(mid),
                    "subject": subject,
                    "from": from_addr,
                    "to": to_addr,
                    "date": date_str,
                    "snippet": snippet,
                })
            except Exception:
                continue
        imap.logout()
        return {"ok": True, "messages": out}
    except imaplib.IMAP4.error as e:
        err = str(e).lower()
        if "authentication" in err or "invalid credentials" in err:
            return {"ok": False, "messages": [], "error": "Yahoo: IMAP auth failed. Your token may lack mail-r scope. Enable Mail API in your Yahoo app, then reconnect with YAHOO_SCOPES=openid mail-r mail-w."}
        return {"ok": False, "messages": [], "error": str(e)}
    except Exception as e:
        return {"ok": False, "messages": [], "error": str(e)}


def send_email_yahoo(to: str, subject: str, body: str, cc: str = "") -> Dict[str, Any]:
    """Send email via Yahoo SMTP with XOAUTH2. Returns {ok, message_id, error}."""
    access_token, err = get_access_token()
    if err:
        return {"ok": False, "error": err}
    email = _get_email()
    if not email:
        return {"ok": False, "error": "Yahoo email not stored. Reconnect Yahoo."}
    try:
        msg = MIMEText(body)
        msg["From"] = email
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        smtp.ehlo()
        auth_str = _xoauth2_string(email, access_token)
        code, resp = smtp.docmd("AUTH", "XOAUTH2 " + auth_str)
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, resp)
        recipients = [r.strip() for r in to.split(",")]
        if cc:
            recipients.extend([r.strip() for r in cc.split(",")])
        smtp.sendmail(email, recipients, msg.as_string())
        smtp.quit()
        return {"ok": True, "message_id": None}  # SMTP doesn't return message_id
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "error": "Yahoo: SMTP auth failed. Your token may lack mail-w scope. Enable Mail API in your Yahoo app, then reconnect."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
