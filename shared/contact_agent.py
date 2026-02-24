"""
CONTACT Agent - Syncs contacts from Google People API and vCard imports.
Runs regularly to pull in contacts from Gmail/Google Contacts.
Uses emails, events, and other activities to build and update circles.
vCard import (iPhone export) is triggered manually via dashboard.
Note: SMS requires separate integration (e.g. manual export); not implemented.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Set, Tuple

# Paths
def _get_dashboard_db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.db"
    return Path(os.environ.get("DASHBOARD_DB_PATH", str(default)))


def _get_conn(db_path: Path):
    import sqlite3
    return sqlite3.connect(str(db_path))


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _contact_exists_by_email(conn, email: str) -> bool:
    if not email:
        return False
    row = conn.execute(
        "SELECT 1 FROM contacts WHERE LOWER(TRIM(email)) = ?",
        (_normalize_email(email),),
    ).fetchone()
    return row is not None


def _insert_contact(conn, name: str, email: str = "", phone: str = "", notes: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO contacts (name, email, phone, notes) VALUES (?, ?, ?, ?)",
        (name or "", email or "", phone or "", notes or ""),
    )
    conn.commit()
    return cur.lastrowid


# --- Google People API sync ---

def sync_from_google(
    dashboard_db_path: Optional[Path] = None,
    skip_existing: bool = True,
) -> Tuple[int, int]:
    """
    Fetch contacts from Google People API and merge into dashboard contacts.
    Returns (added, skipped).
    """
    creds, err = _get_google_creds()
    if err:
        raise RuntimeError(err)
    people = _fetch_google_connections(creds)
    db = dashboard_db_path or _get_dashboard_db_path()
    if not db.exists():
        return 0, 0
    conn = _get_conn(db)
    added, skipped = 0, 0
    try:
        for p in people:
            name, email, phone = _extract_person_fields(p)
            if not name and not email:
                continue
            name = name or email or "(no name)"
            if skip_existing and email and _contact_exists_by_email(conn, email):
                skipped += 1
                continue
            if skip_existing and not email and _contact_exists_by_name(conn, name):
                skipped += 1
                continue
            _insert_contact(conn, name, email, phone, "")
            added += 1
    finally:
        conn.close()
    return added, skipped


def _get_google_creds():
    try:
        from shared.google_tokens import get_credentials
        return get_credentials()
    except Exception as e:
        return None, str(e)


def _fetch_google_connections(creds) -> List[dict]:
    from googleapiclient.discovery import build
    service = build("people", "v1", credentials=creds)
    person_fields = "names,emailAddresses,phoneNumbers"
    all_people = []
    page_token = None
    while True:
        resp = service.people().connections().list(
            resourceName="people/me",
            pageSize=100,
            personFields=person_fields,
            pageToken=page_token,
        ).execute()
        connections = resp.get("connections", [])
        all_people.extend(connections)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return all_people


def _extract_person_fields(p: dict) -> Tuple[str, str, str]:
    name = ""
    names = p.get("names", [])
    if names:
        n = names[0]
        given = n.get("givenName", "") or ""
        family = n.get("familyName", "") or ""
        name = f"{given} {family}".strip() or n.get("displayName", "")
    email = ""
    emails = p.get("emailAddresses", [])
    if emails:
        email = (emails[0].get("value") or "").strip()
    phone = ""
    phones = p.get("phoneNumbers", [])
    if phones:
        phone = (phones[0].get("value") or "").strip()
    return name, email, phone


def _contact_exists_by_name(conn, name: str) -> bool:
    if not name:
        return False
    row = conn.execute(
        "SELECT 1 FROM contacts WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))",
        (name,),
    ).fetchone()
    return row is not None


# --- vCard import (iPhone export) ---

def import_from_vcard(
    vcard_content: str,
    dashboard_db_path: Optional[Path] = None,
    skip_existing: bool = True,
) -> Tuple[int, int]:
    """
    Parse vCard content and merge into dashboard contacts.
    Returns (added, skipped).
    """
    try:
        import vobject
    except ImportError:
        raise RuntimeError("vobject package required. Run: pip install vobject")
    import io
    db = dashboard_db_path or _get_dashboard_db_path()
    if not db.exists():
        return 0, 0
    conn = _get_conn(db)
    added, skipped = 0, 0
    try:
        stream = io.StringIO(vcard_content)
        for vc in vobject.readComponents(stream):
            if not hasattr(vc, "fn") and not hasattr(vc, "n"):
                continue
            name = _vcard_name(vc)
            email = _vcard_email(vc)
            phone = _vcard_phone(vc)
            notes = _vcard_notes(vc)
            if not name and not email:
                continue
            name = name or email or "(no name)"
            if skip_existing and email and _contact_exists_by_email(conn, email):
                skipped += 1
                continue
            if skip_existing and not email and _contact_exists_by_name(conn, name):
                skipped += 1
                continue
            _insert_contact(conn, name, email, phone, notes)
            added += 1
    finally:
        conn.close()
    return added, skipped


def _vcard_name(vc) -> str:
    if hasattr(vc, "fn") and vc.fn and vc.fn.value:
        return str(vc.fn.value).strip()
    if hasattr(vc, "n") and vc.n and vc.n.value:
        n = vc.n.value
        parts = [n.given or "", n.family or "", n.additional or ""]
        return " ".join(p for p in parts if p).strip()
    return ""


def _vcard_email(vc) -> str:
    if hasattr(vc, "email") and vc.email and vc.email.value:
        return str(vc.email.value).strip()
    return ""


def _vcard_phone(vc) -> str:
    if hasattr(vc, "tel") and vc.tel and vc.tel.value:
        return str(vc.tel.value).strip()
    return ""


def _vcard_notes(vc) -> str:
    if hasattr(vc, "note") and vc.note and vc.note.value:
        return str(vc.note.value).strip()[:500]
    return ""


# --- Activity-based circle building (emails, events) ---

_EMAIL_RE = re.compile(r"<([^>]+)>|^([^\s<]+@[^\s>]+)$")


def _parse_email_from_header(header_value: str) -> Optional[str]:
    """Extract email from 'Name <email@example.com>' or 'email@example.com'."""
    if not header_value or not header_value.strip():
        return None
    s = header_value.strip()
    m = _EMAIL_RE.search(s)
    if m:
        return (m.group(1) or m.group(2) or "").strip().lower()
    if "@" in s:
        return s.lower()
    return None


def _fetch_gmail_activity(days: int = 30, max_messages: int = 200) -> Counter:
    """Count email correspondents from Gmail (From, To). Returns Counter[email]."""
    creds, err = _get_google_creds()
    if err:
        return Counter()
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
        results = service.users().messages().list(
            userId="me",
            q=f"after:{after}",
            maxResults=min(max_messages, 100),
        ).execute()
        msgs = results.get("messages", [])
        counts: Counter = Counter()
        for m in msgs[:max_messages]:
            try:
                msg = service.users().messages().get(userId="me", id=m["id"]).execute()
                payload = msg.get("payload", {})
                headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
                from_ = _parse_email_from_header(headers.get("from", ""))
                to_ = headers.get("to", "")
                for addr in re.split(r"[,;]", to_):
                    e = _parse_email_from_header(addr.strip())
                    if e:
                        counts[e] += 1
                if from_:
                    counts[from_] += 1
            except Exception:
                pass
        return counts
    except Exception:
        return Counter()


def _fetch_calendar_attendees(days: int = 60, max_events: int = 100) -> Counter:
    """Count event attendees from Google Calendar. Returns Counter[email]."""
    creds, err = _get_google_creds()
    if err:
        return Counter()
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days)).isoformat() + "Z"
        time_max = now.isoformat() + "Z"
        events = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            maxResults=max_events,
        ).execute()
        counts: Counter = Counter()
        for e in events.get("items", []):
            for a in e.get("attendees", []):
                email = (a.get("email") or "").strip().lower()
                if email and not a.get("resource"):
                    counts[email] += 1
        return counts
    except Exception:
        return Counter()


def _get_my_email() -> Optional[str]:
    """Get user's primary email (from Gmail profile or tokens)."""
    creds, err = _get_google_creds()
    if err:
        return None
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return (profile.get("emailAddress") or "").strip().lower()
    except Exception:
        return None


def _contact_id_by_email(conn, email: str) -> Optional[int]:
    """Get contact id by email. Returns None if not found."""
    if not email:
        return None
    row = conn.execute(
        "SELECT id FROM contacts WHERE LOWER(TRIM(email)) = ?",
        (_normalize_email(email),),
    ).fetchone()
    return row[0] if row else None


def _get_or_create_circle(conn, name: str, description: str = "") -> int:
    """Get circle id by name, or create. Returns circle id."""
    row = conn.execute("SELECT id FROM circles WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO circles (name, description) VALUES (?, ?)",
        (name, description),
    )
    conn.commit()
    return cur.lastrowid


def _is_in_circle(conn, circle_id: int, entity_type: str, entity_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM circle_members WHERE circle_id = ? AND entity_type = ? AND entity_id = ?",
        (circle_id, entity_type, str(entity_id)),
    ).fetchone()
    return row is not None


def process_inbox_messages(
    messages: List[dict],
    woody_db_path: Optional[Path] = None,
    dashboard_db_path: Optional[Path] = None,
    min_count: int = 1,
    max_proposals: int = 15,
) -> int:
    """
    Process inbox messages from COMMUNICATIONS agent. Extract correspondent emails,
    ensure contacts exist, propose circle additions for Frequent correspondents.
    Returns count of proposals created.
    """
    from shared.memory_agent import create_proposal
    woody_db = woody_db_path or _get_woody_db_path()
    dash_db = dashboard_db_path or _get_dashboard_db_path()
    if not woody_db.exists() or not dash_db.exists():
        return 0

    counts: Counter = Counter()
    for m in messages:
        from_ = _parse_email_from_header(m.get("from", ""))
        if from_:
            counts[from_] += 1
        to_raw = m.get("to", "")
        for addr in re.split(r"[,;]", to_raw):
            e = _parse_email_from_header(addr.strip())
            if e:
                counts[e] += 1

    my_email = _get_my_email()
    if my_email:
        counts.pop(my_email, None)

    conn = _get_conn(dash_db)
    proposed = 0
    try:
        circle_corr = _get_or_create_circle(
            conn, "Frequent correspondents",
            "People you email often (from Gmail activity)",
        )
        seen: Set[str] = set()
        for email, count in counts.most_common(max_proposals):
            if count < min_count or email in seen:
                continue
            seen.add(email)
            cid = _contact_id_by_email(conn, email)
            if not cid:
                _insert_contact(conn, email.split("@")[0], email, "", "")
                cid = _contact_id_by_email(conn, email)
            if not cid or _is_in_circle(conn, circle_corr, "contact", str(cid)):
                continue
            create_proposal(
                woody_db,
                "circle_add",
                {
                    "circle_id": circle_corr,
                    "circle_name": "Frequent correspondents",
                    "entity_type": "contact",
                    "entity_id": str(cid),
                    "reason_activity": f"Inbox: {count} message(s)",
                },
                reason=f"Add contact from inbox ({count} emails)",
            )
            proposed += 1
    finally:
        conn.close()
    return proposed


def build_circles_from_activity(
    woody_db_path: Optional[Path] = None,
    dashboard_db_path: Optional[Path] = None,
    email_min_count: int = 3,
    attendee_min_count: int = 2,
    max_proposals: int = 20,
) -> int:
    """
    Analyze Gmail and Calendar activity, propose adding contacts to circles.
    Creates "Frequent correspondents" and "Event attendees" circles if needed.
    Returns count of proposals created.
    """
    from shared.memory_agent import create_proposal
    woody_db = woody_db_path or _get_woody_db_path()
    dash_db = dashboard_db_path or _get_dashboard_db_path()
    if not woody_db.exists() or not dash_db.exists():
        return 0
    my_email = _get_my_email()
    email_counts = _fetch_gmail_activity(days=30)
    attendee_counts = _fetch_calendar_attendees(days=60)
    if my_email:
        email_counts.pop(my_email, None)
        attendee_counts.pop(my_email, None)
    conn = _get_conn(dash_db)
    try:
        circle_corr = _get_or_create_circle(
            conn, "Frequent correspondents",
            "People you email often (from Gmail activity)",
        )
        circle_attend = _get_or_create_circle(
            conn, "Event attendees",
            "People at your calendar events",
        )
        proposed = 0
        seen_emails: Set[str] = set()
        for email, count in email_counts.most_common(max_proposals):
            if count < email_min_count or email in seen_emails:
                continue
            seen_emails.add(email)
            cid = _contact_id_by_email(conn, email)
            if not cid:
                _insert_contact(conn, email.split("@")[0], email, "", "")
                cid = _contact_id_by_email(conn, email)
            if not cid:
                continue
            if _is_in_circle(conn, circle_corr, "contact", str(cid)):
                continue
            create_proposal(
                woody_db,
                "circle_add",
                {
                    "circle_id": circle_corr,
                    "circle_name": "Frequent correspondents",
                    "entity_type": "contact",
                    "entity_id": str(cid),
                    "reason_activity": f"Email: {count} messages",
                },
                reason=f"Add contact {cid} to Frequent correspondents ({count} emails)",
            )
            proposed += 1
            if proposed >= max_proposals:
                break
        for email, count in attendee_counts.most_common(max_proposals):
            if count < attendee_min_count or email in seen_emails:
                continue
            seen_emails.add(email)
            cid = _contact_id_by_email(conn, email)
            if not cid:
                _insert_contact(conn, email.split("@")[0], email, "", "")
                cid = _contact_id_by_email(conn, email)
            if not cid:
                continue
            if _is_in_circle(conn, circle_attend, "contact", str(cid)):
                continue
            create_proposal(
                woody_db,
                "circle_add",
                {
                    "circle_id": circle_attend,
                    "circle_name": "Event attendees",
                    "entity_type": "contact",
                    "entity_id": str(cid),
                    "reason_activity": f"Events: {count}",
                },
                reason=f"Add contact {cid} to Event attendees ({count} events)",
            )
            proposed += 1
            if proposed >= max_proposals:
                break
    finally:
        conn.close()
    return proposed


def _get_woody_db_path() -> Path:
    from shared.db_path import get_woody_db_path
    return get_woody_db_path()


# --- Agent run ---

def run_contact_agent(
    woody_db_path: Optional[Path] = None,
    dashboard_db_path: Optional[Path] = None,
) -> dict:
    """
    Run CONTACT agent: sync from Google People API, then build circles from activity.
    Returns summary {added, skipped, circle_proposals, error}.
    """
    result = {"added": 0, "skipped": 0, "circle_proposals": 0}
    try:
        added, skipped = sync_from_google(dashboard_db_path)
        result["added"] = added
        result["skipped"] = skipped
    except Exception as e:
        result["error"] = str(e)
        return result
    try:
        proposals = build_circles_from_activity(
            woody_db_path=woody_db_path,
            dashboard_db_path=dashboard_db_path,
        )
        result["circle_proposals"] = proposals
    except Exception as e:
        result["circle_error"] = str(e)
    return result
