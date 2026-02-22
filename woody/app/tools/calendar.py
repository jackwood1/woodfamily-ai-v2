"""Google Calendar tools - requires Google OAuth via dashboard."""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from app.tools.registry import PermissionTier, ToolDef, register

try:
    from googleapiclient.discovery import build
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# Default timezone for events (IANA e.g. America/Los_Angeles). Use UTC if unset.
DEFAULT_TZ = os.environ.get("CALENDAR_TIMEZONE", "UTC")


def _get_creds():
    from shared.google_tokens import get_credentials
    return get_credentials()


def _calendar_today_handler() -> str:
    creds, err = _get_creds()
    if err:
        return err
    try:
        from datetime import datetime
        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        end = datetime.utcnow().replace(hour=23, minute=59, second=59).isoformat() + "Z"
        events = service.events().list(calendarId="primary", timeMin=now, timeMax=end, singleEvents=True).execute()
        items = events.get("items", [])
        if not items:
            return "No events today"
        lines = []
        for e in items:
            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
            lines.append(f"- {e.get('summary', '(no title)')} @ {start}")
        return "\n".join(lines)
    except Exception as e:
        err = str(e).lower()
        if "credentials" in err or "token" in err or "invalid_grant" in err:
            return "Calendar: Token expired or invalid. Reconnect Google in the dashboard."
        if "quota" in err or "rate" in err:
            return "Calendar: Rate limit exceeded. Try again later."
        if "timeout" in err or "connection" in err:
            return "Calendar: Connection failed. Check your network."
        return f"Calendar error: {e}"


def _normalize_datetime(dt_str: str) -> str:
    """Normalize datetime: strip whitespace, ensure basic format."""
    s = (dt_str or "").strip()
    return s


def _is_date_only(s: str) -> bool:
    """True if string is yyyy-mm-dd only."""
    return bool(s and len(s) <= 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", s))


def _parse_start_date(start_norm: str) -> "datetime | None":
    """Parse start to get date for past-date check. Returns None if unparseable."""
    from datetime import datetime
    if _is_date_only(start_norm):
        try:
            return datetime.strptime(start_norm, "%Y-%m-%d")
        except ValueError:
            return None
    if "T" in start_norm:
        try:
            return datetime.fromisoformat(start_norm.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(start_norm[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return None
    return None


def _calendar_create_event_handler(
    summary: str, start: str, end: str, description: str = "", recurrence: str = ""
) -> str:
    creds, err = _get_creds()
    if err:
        return err
    try:
        service = build("calendar", "v3", credentials=creds)
        start_norm = _normalize_datetime(start)
        end_norm = _normalize_datetime(end)
        # Reject past dates
        from datetime import datetime, timezone
        parsed = _parse_start_date(start_norm)
        if parsed:
            now = datetime.now(timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed < now:
                today = datetime.now().strftime("%Y-%m-%d")
                return f"Calendar create: Start date {start_norm} is in the past. Use today ({today}) or a future date."
        # Date-only = all-day event (Google expects end = day after for single-day)
        if _is_date_only(start_norm) and _is_date_only(end_norm):
            if start_norm == end_norm:
                from datetime import datetime, timedelta
                d = datetime.strptime(start_norm, "%Y-%m-%d").date()
                end_norm = (d + timedelta(days=1)).isoformat()
            body = {"summary": summary, "start": {"date": start_norm}, "end": {"date": end_norm}}
        else:
            # Timed event: use timeZone so API accepts datetime without offset
            body = {
                "summary": summary,
                "start": {"dateTime": start_norm, "timeZone": DEFAULT_TZ},
                "end": {"dateTime": end_norm, "timeZone": DEFAULT_TZ},
            }
        if description:
            body["description"] = description
        if recurrence and recurrence.strip():
            rrule = recurrence.strip()
            if not rrule.upper().startswith("RRULE:"):
                rrule = "RRULE:" + rrule
            body["recurrence"] = [rrule]
        event = service.events().insert(calendarId="primary", body=body).execute()
        link = event.get("htmlLink", "")
        start_info = event.get("start", {})
        when = start_info.get("dateTime") or start_info.get("date", "")
        if when:
            return f"Created: {summary} at {when}. {link}\n(Set CALENDAR_TIMEZONE in .env if the time looks wrong)"
        return f"Created event: {link}"
    except Exception as e:
        err = str(e).lower()
        if "credentials" in err or "token" in err or "invalid_grant" in err:
            return "Calendar create: Token expired or invalid. Reconnect Google in the dashboard."
        if "quota" in err or "rate" in err:
            return "Calendar create: Rate limit exceeded. Try again later."
        if "timeout" in err or "connection" in err:
            return "Calendar create: Connection failed. Check your network."
        if "time" in err and ("zone" in err or "rfc" in err or "format" in err):
            return "Calendar create: Invalid datetime format. Use ISO format like 2025-02-22T14:00:00 or 2025-02-22 for all-day."
        return f"Calendar error: {e}"


register(
    ToolDef(
        name="calendar_today",
        description="List today's calendar events",
        parameters={"properties": {}, "required": []},
        handler=_calendar_today_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="calendar_create_event",
        description="Create a calendar event",
        parameters={
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO datetime—MUST be today or future (e.g. 2025-02-22T14:00:00). Never use past dates."},
                "end": {"type": "string", "description": "ISO datetime—MUST be today or future, after start"},
                "description": {"type": "string"},
                "recurrence": {"type": "string", "description": "Optional RRULE e.g. FREQ=WEEKLY;BYDAY=MO"},
            },
            "required": ["summary", "start", "end"],
        },
        handler=_calendar_create_event_handler,
        tier=PermissionTier.YELLOW,
    )
)
