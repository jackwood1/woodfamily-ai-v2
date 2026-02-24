"""
EVENTS Agent - Manages calendar events, TODOs, wishlists.
- Interface to calendars (dashboard events + Google Calendar)
- When TODOs complete: capture as events
- Events passed to memories (track when and what was done)
- Recurring templates (bills, inspections, birthdays): surface "Requires Scheduling"
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Paths
def _get_dashboard_db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.db"
    return Path(os.environ.get("DASHBOARD_DB_PATH", str(default)))


def _get_woody_db_path() -> Path:
    from shared.db_path import get_woody_db_path
    return get_woody_db_path()


def _get_conn(db_path: Path):
    import sqlite3
    return sqlite3.connect(str(db_path))


# --- Calendar interface ---

def get_all_events(
    days_back: int = 7,
    days_ahead: int = 14,
) -> List[dict]:
    """Unified calendar: dashboard events + Google Calendar (if available)."""
    events = []
    dashboard_db = _get_dashboard_db_path()
    if dashboard_db.exists():
        try:
            conn = _get_conn(dashboard_db)
            try:
                since = (date.today() - timedelta(days=days_back)).isoformat()
                until = (date.today() + timedelta(days=days_ahead)).isoformat()
                rows = conn.execute(
                    """SELECT id, date, title, description, event_type FROM events
                       WHERE date >= ? AND date <= ?
                       ORDER BY date ASC""",
                    (since, until),
                ).fetchall()
                for r in rows:
                    events.append({
                        "id": r[0],
                        "date": r[1],
                        "title": r[2],
                        "description": r[3] or "",
                        "event_type": r[4],
                        "source": "dashboard",
                    })
            finally:
                conn.close()
        except Exception:
            pass

    # Add Google Calendar events if available (skip if duplicate of dashboard event)
    dashboard_keys: set = set()
    for ev in events:
        d, t = ev.get("date", "")[:10], _normalize_title_for_match(ev.get("title", ""))
        if d and t:
            dashboard_keys.add((d, t))
    try:
        from shared.google_tokens import get_credentials
        from shared.reminders import get_upcoming_events_from_api
        creds, err = get_credentials()
        if not err:
            api_events = get_upcoming_events_from_api()
            for e in api_events:
                if e.get("source") == "google" or "date" in e:
                    ev_date = e.get("date", "")[:10]
                    ev_title = e.get("title", e.get("summary", "(no title)"))
                    key = (ev_date, _normalize_title_for_match(ev_title))
                    if key in dashboard_keys:
                        continue
                    dashboard_keys.add(key)
                    events.append({
                        "id": e.get("id"),
                        "date": ev_date,
                        "title": ev_title,
                        "description": e.get("description", ""),
                        "event_type": "calendar",
                        "source": "google",
                    })
    except Exception:
        pass

    events.sort(key=lambda x: (x.get("date", ""), x.get("title", "")))
    return events


def create_event(
    date_str: str,
    title: str,
    description: str = "",
    event_type: str = "event",
) -> Optional[int]:
    """Create event in dashboard. Returns event id or None."""
    dashboard_db = _get_dashboard_db_path()
    if not dashboard_db.exists():
        return None
    try:
        conn = _get_conn(dashboard_db)
        try:
            cur = conn.execute(
                "INSERT INTO events (date, title, description, event_type) VALUES (?, ?, ?, ?)",
                (date_str, title, description, event_type),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
    except Exception:
        return None


# --- TODO completion → event ---

def capture_completed_todo(
    todo_id: int,
    content: str,
    completed_date: Optional[str] = None,
) -> Optional[int]:
    """When a TODO is completed, capture it as an event. Returns event id."""
    date_str = completed_date or date.today().isoformat()
    title = f"Completed: {content[:60]}{'...' if len(content) > 60 else ''}"
    return create_event(
        date_str=date_str,
        title=title,
        description=f"TODO #{todo_id} completed",
        event_type="completed",
    )


# --- Duplicate detection helpers ---

def _normalize_title_for_match(title: str) -> str:
    """Normalize title for duplicate matching: lowercase, strip, collapse spaces."""
    if not title:
        return ""
    return " ".join((title or "").lower().strip().split())[:80]


def _event_suggestion_already_proposed(db_path: Path, title: str, ev_date: str) -> bool:
    """Check if we already have a pending event_suggestion with same/similar title and date."""
    conn = _get_conn(db_path)
    try:
        import json
        cur = conn.execute(
            "SELECT payload FROM memory_agent_proposals WHERE status = 'pending' AND action_type = 'event_suggestion'",
            (),
        )
        norm = _normalize_title_for_match(title)
        for row in cur.fetchall():
            try:
                p = json.loads(row[0])
                if p.get("date", "")[:10] == ev_date[:10]:
                    p_title = _normalize_title_for_match(p.get("title", ""))
                    if p_title and norm and (p_title == norm or p_title in norm or norm in p_title):
                        return True
            except Exception:
                pass
        return False
    finally:
        conn.close()


def _event_exists_in_dashboard(title: str, ev_date: str, dashboard_db_path: Optional[Path] = None) -> bool:
    """Check if an event with same/similar title and date already exists in dashboard."""
    db = dashboard_db_path or _get_dashboard_db_path()
    if not db.exists():
        return False
    conn = _get_conn(db)
    try:
        norm = _normalize_title_for_match(title)
        date_str = ev_date[:10]
        rows = conn.execute(
            "SELECT title FROM events WHERE date >= ? AND date <= ?",
            (date_str, date_str),
        ).fetchall()
        for r in rows:
            existing = _normalize_title_for_match(r[0])
            if existing and norm and (existing == norm or existing in norm or norm in existing):
                return True
        return False
    finally:
        conn.close()


# --- Email → event suggestions ---

_EMAIL_EVENT_PATTERNS = [
    re.compile(r"\b(remind|reminder)\b", re.I),
    re.compile(r"\b(todo|to-do|to do)\b", re.I),
    re.compile(r"\b(meeting|call|call with)\b", re.I),
    re.compile(r"\b(appointment|schedule)\b", re.I),
    re.compile(r"\b(follow.?up|followup)\b", re.I),
    re.compile(r"\b(deadline|due)\b", re.I),
    re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}", re.I),
    re.compile(r"\d{1,2}/\d{1,2}(/\d{2,4})?", re.I),
    re.compile(r"\d{4}-\d{2}-\d{2}", re.I),
]


def propose_events_from_emails(
    messages: List[dict],
    woody_db_path: Optional[Path] = None,
    max_proposals: int = 10,
) -> int:
    """
    Scan inbox messages for potential events (reminders, TODOs, meetings, dates).
    Creates event_suggestion proposals for user to approve. Skips duplicates.
    Returns count created.
    """
    from shared.memory_agent import create_proposal
    db_path = woody_db_path or _get_woody_db_path()
    if not db_path.exists():
        return 0

    proposed = 0
    seen_texts: set = set()
    ev_date = date.today().isoformat()
    for m in messages[:50]:
        subject = (m.get("subject") or "").strip()
        snippet = (m.get("snippet") or "").strip()
        from_ = m.get("from", "")
        combined = f"{subject} {snippet}"[:300]
        if not combined or len(combined) < 10:
            continue
        for pat in _EMAIL_EVENT_PATTERNS:
            if pat.search(combined):
                text = f"{subject}" if subject else snippet[:100]
                if not text:
                    continue
                key = text[:80].lower()
                if key in seen_texts:
                    break
                seen_texts.add(key)
                title = subject or "(From email)"
                if _event_suggestion_already_proposed(db_path, title, ev_date):
                    break
                if _event_exists_in_dashboard(title, ev_date):
                    break
                from shared.user_actions import was_rejected_recently, get_action_counts
                source_hint = f"From: {from_}" if from_ else ""
                if was_rejected_recently(title, ev_date, source_hint, db_path=db_path, days=14):
                    break
                counts = get_action_counts(db_path=db_path, days=30)
                cal = counts.get("calendar_added", 0)
                todo = counts.get("todo_added", 0)
                approved = counts.get("event_approved", 0)
                suggested = "calendar" if cal >= todo and cal > 0 else ("todo" if todo > cal and todo > 0 else "")
                create_proposal(
                    db_path,
                    "event_suggestion",
                    {
                        "title": title,
                        "description": f"From: {from_}\n{snippet[:200]}",
                        "source": "email",
                        "date": ev_date,
                        "suggested_action": suggested,
                    },
                    reason=f"Potential event from email: {text[:60]}...",
                )
                proposed += 1
                if proposed >= max_proposals:
                    return proposed
                break
    return proposed


# --- Events → memories ---

def _event_already_proposed(db_path: Path, event_id: Any, ev_date: str, text: str) -> bool:
    """Check if we already have a pending event_memory proposal for this event."""
    conn = _get_conn(db_path)
    try:
        import json
        cur = conn.execute(
            "SELECT payload FROM memory_agent_proposals WHERE status = 'pending' AND action_type = 'event_memory'",
            (),
        )
        for row in cur.fetchall():
            try:
                p = json.loads(row[0])
                if p.get("date") == ev_date and (p.get("event_id") == event_id or p.get("text", "").startswith(text[:50])):
                    return True
            except Exception:
                pass
        return False
    finally:
        conn.close()


def propose_events_for_memory(
    woody_db_path: Optional[Path] = None,
    days_back: int = 7,
    max_proposals: int = 15,
) -> int:
    """
    Create memory proposals for recent events (including completed TODOs).
    Skips events already proposed. Returns count of proposals created.
    """
    from shared.memory_agent import create_proposal
    db_path = woody_db_path or _get_woody_db_path()
    if not db_path.exists():
        return 0

    events = get_all_events(days_back=days_back, days_ahead=0)
    count = 0
    since = (date.today() - timedelta(days=days_back)).isoformat()

    for ev in events:
        if count >= max_proposals:
            break
        ev_date = ev.get("date", "")[:10]
        if ev_date < since:
            continue
        title = ev.get("title", "")
        if not title:
            continue
        ev_type = ev.get("event_type", "event")
        if ev_type == "reminder":
            continue
        text = title
        if ev.get("description"):
            text += f": {ev['description'][:80]}"
        if _event_already_proposed(db_path, ev.get("id"), ev_date, text):
            continue
        create_proposal(
            db_path,
            "event_memory",
            {
                "event_id": ev.get("id"),
                "date": ev_date,
                "text": text[:500],
                "weight": 5 if ev_type == "completed" else 4,
                "memory_type": "long",
            },
            reason=f"Event on {ev_date}",
        )
        count += 1

    return count


# --- Wishlist interface ---

DASHBOARD_CHAT_ID = 0


def list_wishlist(woody_db_path: Optional[Path] = None, limit: int = 50) -> List[dict]:
    """List wishlist items (dashboard chat_id=0). Used by EVENTS agent for context."""
    db_path = woody_db_path or _get_woody_db_path()
    if not db_path.exists():
        return []
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, content, created_at FROM wishlist WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (DASHBOARD_CHAT_ID, limit),
        ).fetchall()
        return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
    finally:
        conn.close()


def fulfill_wishlist_item(
    wishlist_id: int,
    woody_db_path: Optional[Path] = None,
    completed_date: Optional[str] = None,
) -> Optional[int]:
    """
    Mark a wishlist item as fulfilled: create a completed event and remove from wishlist.
    Returns event id or None.
    """
    db_path = woody_db_path or _get_woody_db_path()
    if not db_path.exists():
        return None
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT content FROM wishlist WHERE id = ? AND chat_id = ?",
            (wishlist_id, DASHBOARD_CHAT_ID),
        ).fetchone()
        if not row:
            return None
        content = row[0]
        conn.execute("DELETE FROM wishlist WHERE id = ? AND chat_id = ?", (wishlist_id, DASHBOARD_CHAT_ID))
        conn.commit()
    finally:
        conn.close()
    date_str = completed_date or date.today().isoformat()
    title = f"Wish fulfilled: {content[:60]}{'...' if len(content) > 60 else ''}"
    return create_event(
        date_str=date_str,
        title=title,
        description=f"Wishlist #{wishlist_id} fulfilled",
        event_type="completed",
    )


# --- Scheduled templates (recurring: bills, inspections, birthdays) ---

def _compute_next_due(anchor_date: str, recurrence: str) -> Optional[str]:
    """Compute next due date from anchor_date + recurrence. Returns yyyy-mm-dd or None."""
    try:
        d = datetime.strptime(anchor_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    r = (recurrence or "").upper().strip()
    if r == "YEARLY":
        return (d.replace(year=d.year + 1)).isoformat()
    if r == "MONTHLY":
        if d.month == 12:
            return d.replace(year=d.year + 1, month=1).isoformat()
        return d.replace(month=d.month + 1).isoformat()
    if r == "WEEKLY":
        return (d + timedelta(days=7)).isoformat()
    return None


def get_requires_scheduling(
    days_ahead: int = 14,
    dashboard_db_path: Optional[Path] = None,
) -> List[dict]:
    """
    Return scheduled templates due within days_ahead that need attention.
    Each item has: id, title, description, next_due, recurrence.
    """
    db = dashboard_db_path or _get_dashboard_db_path()
    if not db.exists():
        return []
    today = date.today()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    out = []
    conn = _get_conn(db)
    try:
        rows = conn.execute(
            "SELECT id, title, description, recurrence, anchor_date FROM scheduled_templates",
            (),
        ).fetchall()
        for r in rows:
            next_due = _compute_next_due(r[4], r[3])
            if next_due and next_due <= cutoff:
                out.append({
                    "id": r[0],
                    "title": r[1],
                    "description": r[2] or "",
                    "recurrence": r[3],
                    "anchor_date": r[4],
                    "next_due": next_due,
                })
        out.sort(key=lambda x: x.get("next_due", ""))
    finally:
        conn.close()
    return out


def process_scheduled_templates(
    dashboard_db_path: Optional[Path] = None,
    woody_db_path: Optional[Path] = None,
) -> Tuple[int, List[dict]]:
    """
    Process scheduled templates: create events when due, update anchor_date.
    Returns (events_created, requires_scheduling_list).
    """
    db = dashboard_db_path or _get_dashboard_db_path()
    if not db.exists():
        return 0, []
    today = date.today().isoformat()
    created = 0
    conn = _get_conn(db)
    try:
        rows = conn.execute(
            "SELECT id, title, description, recurrence, anchor_date FROM scheduled_templates",
            (),
        ).fetchall()
        for r in rows:
            tid, title, desc, recurrence, anchor = r[0], r[1], r[2], r[3], r[4]
            next_due = _compute_next_due(anchor, recurrence)
            if not next_due or next_due > today:
                continue
            if _event_exists_in_dashboard(title, next_due, dashboard_db_path=db):
                conn.execute(
                    "UPDATE scheduled_templates SET anchor_date = ? WHERE id = ?",
                    (next_due, tid),
                )
                conn.commit()
                continue
            ev_id = create_event(
                date_str=next_due,
                title=title,
                description=(desc or "") + f" [scheduled template #{tid}]",
                event_type="reminder",
            )
            if ev_id:
                conn.execute(
                    "UPDATE scheduled_templates SET anchor_date = ? WHERE id = ?",
                    (next_due, tid),
                )
                conn.commit()
                created += 1
    finally:
        conn.close()
    requires = get_requires_scheduling(days_ahead=14, dashboard_db_path=db)
    return created, requires


# --- Agent run ---

def run_events_agent(woody_db_path: Optional[Path] = None) -> dict:
    """
    Run EVENTS agent: process scheduled templates (create events when due),
    then propose events for memory.
    Returns summary. Does not commit - user approves via Memory Agent UI.
    """
    created, _ = process_scheduled_templates()
    count = propose_events_for_memory(woody_db_path)
    return {"event_memory": count, "scheduled_created": created}
