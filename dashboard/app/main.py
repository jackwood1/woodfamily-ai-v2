"""Dashboard API."""

import logging
import sys
from pathlib import Path
from typing import Optional

# Add repo root for otel_setup and shared
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

# Configure logging to file + console
from shared.logging_config import setup_logging
setup_logging(service="dashboard", log_dir=_root / "logs")

# Load .env from repo root
from dotenv import load_dotenv
load_dotenv(_root / ".env")

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from otel_setup import init_tracing
from otel_setup.span_buffer import get_span_buffer

import base64
import os
import secrets
from typing import Callable

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .db import get_conn, init_db

app = FastAPI(title="Woody Dashboard")

# Auth: Basic (DASHBOARD_USER/PASSWORD) and/or Google OAuth (GOOGLE_CLIENT_ID + SESSION_SECRET)
_dash_user = os.environ.get("DASHBOARD_USER", "").strip()
_dash_pass = os.environ.get("DASHBOARD_PASSWORD", "").strip()
_google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
_google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
_session_secret = os.environ.get("SESSION_SECRET", "").strip()
_google_auth_enabled = bool(_google_client_id and _google_client_secret and _session_secret)
_basic_auth_enabled = bool(_dash_user and _dash_pass)
_auth_enabled = _basic_auth_enabled or _google_auth_enabled

# Optional: restrict Google login to specific domains (comma-separated, e.g. gmail.com,woodfamily.ai)
_allowed_domains = [d.strip().lower() for d in os.environ.get("GOOGLE_AUTH_ALLOWED_DOMAINS", "").split(",") if d.strip()]

DEFAULT_DISPLAY_NAME = os.environ.get("DASHBOARD_DISPLAY_NAME", "Jack Wood").strip() or "Jack Wood"


def _get_auth_redirect_uri() -> str:
    base = os.environ.get("DASHBOARD_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/auth/google/callback"


def _is_public_path(path: str) -> bool:
    return path in ("/", "/login", "/health") or path.startswith(("/static/", "/api/auth/"))


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.user = DEFAULT_DISPLAY_NAME
        if not _auth_enabled:
            return await call_next(request)
        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)
        # Check session (Google login)
        if _google_auth_enabled:
            session = getattr(request, "session", None) or {}
            if session.get("user"):
                request.state.user = session["user"].get("name") or session["user"].get("email") or DEFAULT_DISPLAY_NAME
                return await call_next(request)
        # Check Basic auth
        if _basic_auth_enabled:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Basic "):
                try:
                    decoded = base64.b64decode(auth[6:]).decode()
                    user, _, passwd = decoded.partition(":")
                    if secrets.compare_digest(user, _dash_user) and secrets.compare_digest(passwd, _dash_pass):
                        request.state.user = user
                        return await call_next(request)
                except Exception:
                    pass
        # Unauthorized: redirect HTML requests to login, 401 for API
        if "text/html" in request.headers.get("Accept", "") and path == "/":
            return RedirectResponse(url="/login", status_code=302)
        return Response(content="Unauthorized", status_code=401, headers={"WWW-Authenticate": "Basic realm=Dashboard"})


# Session must run before AuthMiddleware so request.session is available
app.add_middleware(AuthMiddleware)
if _google_auth_enabled:
    from starlette.middleware.sessions import SessionMiddleware  # requires itsdangerous
    app.add_middleware(SessionMiddleware, secret_key=_session_secret, max_age=14 * 24 * 3600)  # 14 days

# OpenTelemetry (with span buffer for dashboard widget)
init_tracing(service_name="dashboard", buffer_spans=True, buffer_size=50)
FastAPIInstrumentor.instrument_app(app)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Schemas ---


class EventCreate(BaseModel):
    date: str
    title: str
    description: str = ""
    event_type: str = "event"
    recurrence: str = ""  # e.g. RRULE:FREQ=WEEKLY;BYDAY=MO or empty


class EventMergeBody(BaseModel):
    keep_id: int
    delete_ids: list[int]


class DecisionCreate(BaseModel):
    date: str
    decision: str
    context: str = ""
    outcome: str = ""


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    tags: str = ""


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None


class DecisionOutcomeUpdate(BaseModel):
    outcome: str


class AboutMeUpdate(BaseModel):
    content: str = ""


class MemoryCreate(BaseModel):
    fact: str
    weight: int = 5
    memory_type: str = "long"


class ContactCreate(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    notes: str = ""


class PlaceCreate(BaseModel):
    name: str
    address: str = ""
    notes: str = ""


class CircleCreate(BaseModel):
    name: str
    description: str = ""


class CircleMemberAdd(BaseModel):
    entity_type: str  # contact, place, memory
    entity_id: str


class WishlistCreate(BaseModel):
    content: str


class TodoCreate(BaseModel):
    content: str
    due_date: str = ""  # yyyy-mm-dd or empty
    event_id: Optional[int] = None  # when adding from event, for action logging


class ScheduledTemplateCreate(BaseModel):
    title: str
    description: str = ""
    recurrence: str  # YEARLY, MONTHLY, or WEEKLY
    anchor_date: str  # yyyy-mm-dd (last occurrence or base date)


# --- Events ---


@app.get("/api/events")
def list_events(limit: int = 50, coming: bool = False):
    """List events. If coming=True, only events in the next 2 days (today + tomorrow), ordered soonest first."""
    from datetime import date, timedelta
    conn = get_conn()
    today = date.today().isoformat()
    if coming:
        end = (date.today() + timedelta(days=1)).isoformat()  # today + tomorrow
        rows = conn.execute(
            "SELECT id, date, title, description, event_type, recurrence, created_at FROM events WHERE date >= ? AND date <= ? ORDER BY date ASC LIMIT ?",
            (today, end, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, date, title, description, event_type, recurrence, created_at FROM events ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/events")
def create_event(e: EventCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO events (date, title, description, event_type, recurrence) VALUES (?, ?, ?, ?, ?)",
        (e.date, e.title, e.description, e.event_type, e.recurrence or ""),
    )
    conn.commit()
    row = conn.execute("SELECT id, date, title, description, event_type, recurrence, created_at FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/events/duplicates")
def list_event_duplicates():
    """Find dashboard events that are likely duplicates (same date + similar title)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, date, title, description, event_type FROM events ORDER BY date ASC, id ASC"
    ).fetchall()
    conn.close()
    # Normalize title for grouping: lowercase, collapse whitespace
    def _norm(t):
        return " ".join((t or "").lower().split()).strip()[:100]

    by_key = {}  # (date[:10], normalized_title) -> [events]
    for r in rows:
        ev = {"id": r[0], "date": r[1], "title": r[2], "description": r[3], "event_type": r[4]}
        key = (str(ev["date"] or "")[:10], _norm(ev["title"]))
        if not key[0] or not key[1]:
            continue
        by_key.setdefault(key, []).append(ev)
    # Only groups with 2+ events
    duplicates = [v for v in by_key.values() if len(v) >= 2]
    return {"duplicates": duplicates}


@app.post("/api/events/merge")
def merge_event_duplicates(body: EventMergeBody):
    """Merge duplicate events: keep the first id, delete the rest."""
    keep_id = body.keep_id
    delete_ids = body.delete_ids or []
    if not keep_id or not delete_ids:
        return {"ok": False, "message": "keep_id and delete_ids required."}
    conn = get_conn()
    try:
        for did in delete_ids:
            if int(did) != int(keep_id):
                conn.execute("DELETE FROM events WHERE id = ?", (int(did),))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "message": f"Merged: kept {keep_id}, removed {len(delete_ids)}."}


@app.delete("/api/events/{id}")
def delete_event(id: int):
    conn = get_conn()
    row = conn.execute("SELECT id, title, date FROM events WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM events WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    if row:
        try:
            from shared.user_actions import log_action
            from shared.chat import get_woody_db_path
            if get_woody_db_path().exists():
                log_action("event_deleted", event_id=id, title=row[1], event_date=(row[2] or "")[:10])
        except Exception:
            pass
    return {"ok": True}


@app.post("/api/events/{id}/create-in-calendar")
def create_event_in_calendar(id: int):
    """Create a dashboard event in Google Calendar (all-day event)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, date, title, description, recurrence FROM events WHERE id = ?", (id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "message": "Event not found"}
    ev = dict(row)
    from datetime import datetime
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {"ok": False, "message": "Google API libraries not installed"}
    from shared.google_tokens import get_credentials
    creds, err = get_credentials()
    if err:
        return {"ok": False, "message": err}
    try:
        service = build("calendar", "v3", credentials=creds)
        date_str = ev["date"]
        body = {
            "summary": ev["title"],
            "start": {"date": date_str},
            "end": {"date": _next_day(date_str)},
        }
        if ev.get("description"):
            body["description"] = ev["description"]
        if ev.get("recurrence") and str(ev["recurrence"]).strip():
            rrule = ev["recurrence"].strip()
            if not rrule.upper().startswith("RRULE:"):
                rrule = "RRULE:" + rrule
            body["recurrence"] = [rrule]
        event = service.events().insert(calendarId="primary", body=body).execute()
        try:
            from shared.user_actions import log_action
            from shared.chat import get_woody_db_path
            if get_woody_db_path().exists():
                log_action("calendar_added", event_id=id, title=ev.get("title"), event_date=ev.get("date"))
        except Exception:
            pass
        return {"ok": True, "message": "Created in Google Calendar", "link": event.get("htmlLink", "")}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def _next_day(date_str: str) -> str:
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d + timedelta(days=1)).isoformat()


@app.get("/api/events/requires-scheduling")
def list_requires_scheduling(days: int = 14):
    """List recurring items due within days that need scheduling (bills, inspections, birthdays)."""
    try:
        from shared.events_agent import get_requires_scheduling
        items = get_requires_scheduling(days_ahead=days)
        return items
    except Exception as e:
        return []


@app.get("/api/events/calendar")
def list_calendar_events():
    """Fetch Google Calendar events for the next 2 days (today + tomorrow)."""
    from datetime import datetime, timedelta
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return []
    from shared.google_tokens import get_credentials
    creds, err = get_credentials()
    if err:
        return []
    try:
        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end = now + timedelta(days=2)
        time_min = now.isoformat() + "Z"
        time_max = end.isoformat() + "Z"
        events = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        items = events.get("items", [])
        out = []
        for e in items:
            start = e.get("start", {})
            dt = start.get("dateTime") or start.get("date", "")
            date_str = dt[:10] if len(dt) >= 10 else ""
            if not date_str:
                continue
            out.append({
                "id": None,
                "date": date_str,
                "title": e.get("summary", "(no title)"),
                "description": e.get("description", "") or "",
                "event_type": "calendar",
                "source": "google",
            })
        return out
    except Exception:
        return []


# --- Scheduled templates (recurring: bills, inspections, birthdays) ---

@app.get("/api/scheduled-templates")
def list_scheduled_templates():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, description, recurrence, anchor_date, created_at FROM scheduled_templates ORDER BY anchor_date ASC",
        (),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/scheduled-templates")
def create_scheduled_template(t: ScheduledTemplateCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO scheduled_templates (title, description, recurrence, anchor_date) VALUES (?, ?, ?, ?)",
        (t.title, t.description, t.recurrence.upper(), t.anchor_date[:10]),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, title, description, recurrence, anchor_date, created_at FROM scheduled_templates WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return dict(row)


@app.delete("/api/scheduled-templates/{id}")
def delete_scheduled_template(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM scheduled_templates WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/scheduled-templates/{id}/schedule-now")
def schedule_template_now(id: int, date_str: Optional[str] = None):
    """Create event for this template now (or on date_str) and advance anchor_date."""
    from shared.events_agent import create_event
    from datetime import date
    conn = get_conn()
    row = conn.execute(
        "SELECT id, title, description, recurrence, anchor_date FROM scheduled_templates WHERE id = ?",
        (id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "error": "Template not found"}
    tid, title, desc, recurrence, anchor = row[0], row[1], row[2], row[3], row[4]
    schedule_date = (date_str or date.today().isoformat())[:10]
    ev_id = create_event(
        date_str=schedule_date,
        title=title,
        description=(desc or "") + f" [scheduled template #{tid}]",
        event_type="reminder",
    )
    if not ev_id:
        return {"ok": False, "error": "Failed to create event"}
    conn = get_conn()
    conn.execute("UPDATE scheduled_templates SET anchor_date = ? WHERE id = ?", (schedule_date, id))
    conn.commit()
    conn.close()
    return {"ok": True, "event_id": ev_id}


# --- Decisions ---


@app.get("/api/decisions")
def list_decisions(limit: int = 50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, date, decision, context, outcome, created_at FROM decisions ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/decisions")
def create_decision(d: DecisionCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO decisions (date, decision, context, outcome) VALUES (?, ?, ?, ?)",
        (d.date, d.decision, d.context, d.outcome),
    )
    conn.commit()
    row = conn.execute("SELECT id, date, decision, context, outcome, created_at FROM decisions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.patch("/api/decisions/{id}")
def update_decision(id: int, body: DecisionOutcomeUpdate):
    conn = get_conn()
    conn.execute("UPDATE decisions SET outcome = ? WHERE id = ?", (body.outcome, id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/decisions/{id}")
def delete_decision(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM decisions WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# --- About Me ---


@app.get("/api/about-me")
def get_about_me():
    conn = get_conn()
    row = conn.execute("SELECT content, updated_at FROM about_me WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {"content": "", "updated_at": None}
    return {"content": row["content"] or "", "updated_at": row["updated_at"]}


@app.put("/api/about-me")
def update_about_me(body: AboutMeUpdate):
    content = body.content or ""
    conn = get_conn()
    conn.execute(
        "INSERT INTO about_me (id, content, updated_at) VALUES (1, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET content = excluded.content, updated_at = datetime('now')",
        (content,),
    )
    conn.commit()
    row = conn.execute("SELECT content, updated_at FROM about_me WHERE id = 1").fetchone()
    conn.close()
    return {"content": row["content"] or "", "updated_at": row["updated_at"]}


@app.post("/api/about-me/import/linkedin")
async def import_about_me_linkedin(file: UploadFile = File(...)):
    """Import work/education from LinkedIn data export ZIP. Request at Settings & Privacy → Data Privacy → Get a copy of your data."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return {"ok": False, "message": "Please upload a ZIP file from LinkedIn's data export."}
    try:
        zip_bytes = await file.read()
        if len(zip_bytes) > 50 * 1024 * 1024:  # 50 MB limit
            return {"ok": False, "message": "File too large (max 50 MB)."}
        from shared.import_archives import parse_linkedin_archive
        extracted = parse_linkedin_archive(zip_bytes)
        if not extracted.strip():
            return {"ok": False, "message": "No profile data found in archive. Ensure you requested Profile, Positions, and Education."}
        conn = get_conn()
        row = conn.execute("SELECT content FROM about_me WHERE id = 1").fetchone()
        existing = (row["content"] or "").strip() if row else ""
        separator = "\n\n--- Imported from LinkedIn ---\n\n" if existing else ""
        new_content = existing + separator + extracted.strip()
        conn.execute(
            "INSERT INTO about_me (id, content, updated_at) VALUES (1, ?, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET content = excluded.content, updated_at = datetime('now')",
            (new_content,),
        )
        conn.commit()
        row = conn.execute("SELECT content, updated_at FROM about_me WHERE id = 1").fetchone()
        conn.close()
        return {"ok": True, "content": row["content"] or "", "updated_at": row["updated_at"], "imported": len(extracted)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/about-me/import/facebook")
async def import_about_me_facebook(file: UploadFile = File(...)):
    """Import profile from Facebook data export ZIP. Request at Settings → Your Facebook Information → Download your information."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return {"ok": False, "message": "Please upload a ZIP file from Facebook's data export."}
    try:
        zip_bytes = await file.read()
        if len(zip_bytes) > 50 * 1024 * 1024:  # 50 MB limit
            return {"ok": False, "message": "File too large (max 50 MB)."}
        from shared.import_archives import parse_facebook_archive
        extracted = parse_facebook_archive(zip_bytes)
        if not extracted.strip():
            return {"ok": False, "message": "No profile data found. Ensure you selected 'Profile information' when requesting your data."}
        conn = get_conn()
        row = conn.execute("SELECT content FROM about_me WHERE id = 1").fetchone()
        existing = (row["content"] or "").strip() if row else ""
        separator = "\n\n--- Imported from Facebook ---\n\n" if existing else ""
        new_content = existing + separator + extracted.strip()
        conn.execute(
            "INSERT INTO about_me (id, content, updated_at) VALUES (1, ?, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET content = excluded.content, updated_at = datetime('now')",
            (new_content,),
        )
        conn.commit()
        row = conn.execute("SELECT content, updated_at FROM about_me WHERE id = 1").fetchone()
        conn.close()
        return {"ok": True, "content": row["content"] or "", "updated_at": row["updated_at"], "imported": len(extracted)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# --- Notes ---


@app.get("/api/notes")
def list_notes(limit: int = 50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, content, tags, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/notes")
def create_note(n: NoteCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
        (n.title, n.content, n.tags),
    )
    conn.commit()
    row = conn.execute("SELECT id, title, content, tags, created_at, updated_at FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.patch("/api/notes/{id}")
def update_note(id: int, n: NoteUpdate):
    conn = get_conn()
    updates = []
    params = []
    if n.title is not None:
        updates.append("title = ?")
        params.append(n.title)
    if n.content is not None:
        updates.append("content = ?")
        params.append(n.content)
    if n.tags is not None:
        updates.append("tags = ?")
        params.append(n.tags)
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(id)
        conn.execute(f"UPDATE notes SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/notes/{id}")
def delete_note(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# --- Integrations ---


@app.get("/api/integrations/google/status")
def google_status():
    """Return whether Google is connected and its capabilities."""
    try:
        from shared.google_tokens import has_valid_tokens
        connected = has_valid_tokens()
        return {
            "connected": connected,
            "capabilities": ["Gmail", "Calendar", "Contacts"] if connected else [],
        }
    except Exception:
        return {"connected": False, "capabilities": []}


@app.delete("/api/integrations/google")
def google_disconnect():
    """Disconnect Google (remove stored tokens)."""
    try:
        from shared.google_tokens import clear_tokens
        ok = clear_tokens()
        return {"ok": ok, "message": "Google disconnected." if ok else "Already disconnected."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.get("/api/integrations/google/authorize")
def google_authorize():
    """Redirect to Google OAuth."""
    import os
    from google_auth_oauthlib.flow import Flow
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/integrations/google/callback")
    if not client_id or not client_secret:
        return HTMLResponse("<p>GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required.</p>", status_code=500)
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/contacts.readonly",
        ],
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return RedirectResponse(auth_url)


@app.get("/api/integrations/google/callback")
def google_callback(code: str = ""):
    """Handle Google OAuth callback."""
    import os
    from google_auth_oauthlib.flow import Flow
    from shared.google_tokens import save_tokens
    if not code:
        return HTMLResponse("<p>No code received.</p>", status_code=400)
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/integrations/google/callback")
    flow = Flow.from_client_config(
        {"web": {"client_id": client_id, "client_secret": client_secret, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": [redirect_uri]}},
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/contacts.readonly",
        ],
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    tokens = {"token": creds.token, "refresh_token": creds.refresh_token, "client_id": client_id, "client_secret": client_secret}
    save_tokens(tokens)
    return HTMLResponse("<p>Google connected. You can close this tab.</p>")


# --- Yahoo Mail ---

@app.get("/api/integrations/yahoo/status")
def yahoo_status():
    """Return whether Yahoo is connected and its capabilities."""
    try:
        from shared.yahoo_tokens import has_valid_tokens
        connected = has_valid_tokens()
        return {
            "connected": connected,
            "capabilities": ["Mail"] if connected else [],
        }
    except Exception:
        return {"connected": False, "capabilities": []}


@app.delete("/api/integrations/yahoo")
def yahoo_disconnect():
    """Disconnect Yahoo (remove stored tokens)."""
    try:
        from shared.yahoo_tokens import clear_tokens
        ok = clear_tokens()
        return {"ok": ok, "message": "Yahoo disconnected." if ok else "Already disconnected."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.get("/api/integrations/yahoo/authorize")
def yahoo_authorize():
    """Redirect to Yahoo OAuth."""
    from urllib.parse import urlencode
    client_id = os.environ.get("YAHOO_CLIENT_ID", "").strip()
    redirect_uri = os.environ.get("YAHOO_REDIRECT_URI", "http://localhost:8000/api/integrations/yahoo/callback")
    if not client_id:
        return HTMLResponse("<p>YAHOO_CLIENT_ID required. Create an app at developer.yahoo.com.</p>", status_code=500)
    # Yahoo Mail scopes: openid (required for userinfo), mail-r (read), mail-w (read/write)
    # Use only openid to test OAuth flow; add mail-r mail-w once Mail API is approved
    scopes = os.environ.get("YAHOO_SCOPES", "openid mail-r mail-w")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
    }
    auth_url = "https://api.login.yahoo.com/oauth2/request_auth?" + urlencode(params)
    return RedirectResponse(auth_url)


@app.get("/api/integrations/yahoo/callback")
def yahoo_callback(code: str = ""):
    """Handle Yahoo OAuth callback."""
    import time
    if not code:
        return HTMLResponse("<p>No code received.</p>", status_code=400)
    client_id = os.environ.get("YAHOO_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YAHOO_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("YAHOO_REDIRECT_URI", "http://localhost:8000/api/integrations/yahoo/callback")
    if not client_id or not client_secret:
        return HTMLResponse("<p>YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET required.</p>", status_code=500)
    try:
        import httpx
        resp = httpx.post(
            "https://api.login.yahoo.com/oauth2/get_token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token or not refresh_token:
            return HTMLResponse("<p>Yahoo did not return access_token or refresh_token.</p>", status_code=400)
        expires_in = int(data.get("expires_in", 3600))
        tokens = {
            "token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "expires_at": time.time() + expires_in,
        }
        # Fetch user email from Yahoo userinfo for IMAP
        try:
            uresp = httpx.get(
                "https://api.login.yahoo.com/openid/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if uresp.status_code == 200:
                uinfo = uresp.json()
                tokens["email"] = uinfo.get("email") or uinfo.get("sub", "")
        except Exception:
            pass
        from shared.yahoo_tokens import save_tokens
        save_tokens(tokens)
        return HTMLResponse("<p>Yahoo connected. You can close this tab.</p>")
    except httpx.HTTPStatusError as e:
        return HTMLResponse(f"<p>Yahoo token exchange failed: {e.response.text}</p>", status_code=400)
    except Exception as e:
        return HTMLResponse(f"<p>Error: {e}</p>", status_code=500)


# --- Twilio (SMS) ---

@app.get("/api/integrations/twilio/status")
def twilio_status():
    """Return whether Twilio SMS is configured (via env vars)."""
    try:
        from shared.communications_agent import sms_available
        connected = sms_available()
        phone = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()
        # Mask for display: +1555***4567
        masked = f"{phone[:4]}***{phone[-4:]}" if len(phone) >= 8 else ""
        return {
            "connected": connected,
            "phone_masked": masked if connected else None,
        }
    except Exception:
        return {"connected": False, "phone_masked": None}


# --- Communications ---

@app.get("/api/communications/status")
def communications_status():
    """Return status of communication channels (email via Gmail/Yahoo, SMS via Twilio)."""
    try:
        from shared.google_tokens import has_valid_tokens
        from shared.yahoo_tokens import has_valid_tokens as yahoo_connected
        from shared.communications_agent import sms_available
        return {
            "email": has_valid_tokens() or yahoo_connected(),
            "gmail": has_valid_tokens(),
            "yahoo": yahoo_connected(),
            "sms": sms_available(),
        }
    except Exception:
        return {"email": False, "gmail": False, "yahoo": False, "sms": False}


@app.post("/api/communications/run")
def communications_run_now():
    """Manually trigger COMMUNICATIONS agent: scan inbox, feed contacts + events agents."""
    try:
        from shared.communications_agent import run_communications_agent
        result = run_communications_agent()
        if result.get("error"):
            return {"ok": False, "message": result["error"]}
        circle = result.get("circle_proposals", 0)
        events = result.get("event_proposals", 0)
        parts = []
        if circle:
            parts.append(f"{circle} circle proposal(s)")
        if events:
            parts.append(f"{events} event suggestion(s)")
        return {
            "ok": True,
            "circle_proposals": circle,
            "event_proposals": events,
            "message": f"Scanned inbox. Proposed: {', '.join(parts)}" if parts else "Nothing to propose.",
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}


# --- Health ---


@app.get("/health")
def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}


# --- Google Auth (login) ---

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in – Woody Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    body { font-family: 'DM Sans', sans-serif; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f0f0f; color: #e0e0e0; }
    .card { background: #1a1a1a; padding: 2.5rem; border-radius: 12px; text-align: center; max-width: 360px; }
    h1 { margin: 0 0 0.5rem; font-size: 1.5rem; }
    p { margin: 0 0 1.5rem; color: #888; font-size: 0.95rem; }
    a { display: inline-flex; align-items: center; gap: 0.5rem; background: #4285f4; color: white; text-decoration: none; padding: 0.75rem 1.25rem; border-radius: 8px; font-weight: 500; transition: background 0.2s; }
    a:hover { background: #3367d6; }
    svg { width: 20px; height: 20px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Woody Dashboard</h1>
    <p>Sign in with your Google account</p>
    <a href="/api/auth/google/authorize">
      <svg viewBox="0 0 24 24"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
      Sign in with Google
    </a>
  </div>
</body>
</html>
"""


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login page with Sign in with Google."""
    if not _google_auth_enabled:
        return HTMLResponse("<p>Google Auth not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_SECRET.</p>", status_code=500)
    # Redirect to dashboard if already logged in
    session = getattr(request, "session", None) or {}
    if session.get("user"):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(LOGIN_HTML)


@app.get("/api/auth/google/authorize")
def auth_google_authorize(request: Request):
    """Redirect to Google OAuth for login."""
    if not _google_auth_enabled:
        return HTMLResponse("<p>Google Auth not configured.</p>", status_code=500)
    from google_auth_oauthlib.flow import Flow
    redirect_uri = _get_auth_redirect_uri()
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": _google_client_id,
                "client_secret": _google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="select_account")
    return RedirectResponse(auth_url)


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request, code: str = ""):
    """Handle Google OAuth callback, set session, redirect to dashboard."""
    if not _google_auth_enabled:
        return RedirectResponse(url="/login", status_code=302)
    if not code:
        return RedirectResponse(url="/login?error=no_code", status_code=302)
    try:
        from google_auth_oauthlib.flow import Flow
        import httpx
        redirect_uri = _get_auth_redirect_uri()
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": _google_client_id,
                    "client_secret": _google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
        if r.status_code != 200:
            return RedirectResponse(url="/login?error=userinfo_failed", status_code=302)
        info = r.json()
        email = (info.get("email") or "").strip().lower()
        if _allowed_domains and email:
            domain = email.split("@")[-1] if "@" in email else ""
            if domain not in _allowed_domains:
                return RedirectResponse(url="/login?error=domain_not_allowed", status_code=302)
        request.session["user"] = {
            "email": email,
            "name": (info.get("name") or info.get("email") or "User").strip(),
            "picture": info.get("picture"),
        }
        return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        logging.getLogger(__name__).exception("Google auth callback failed")
        return RedirectResponse(url=f"/login?error={type(e).__name__}", status_code=302)


@app.get("/api/auth/logout")
async def auth_logout(request: Request):
    """Clear session and redirect to login."""
    if hasattr(request, "session"):
        request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/api/auth/me")
def auth_me(request: Request):
    """Return current user from session (for frontend)."""
    session = getattr(request, "session", None) or {}
    user = session.get("user")
    if not user:
        return {"logged_in": False, "user": None}
    return {"logged_in": True, "user": {"email": user.get("email"), "name": user.get("name"), "picture": user.get("picture")}}


@app.get("/api/me")
def get_current_user(request: Request):
    """Return the current user display name (logged-in user or default Jack Wood)."""
    return {"user": getattr(request.state, "user", DEFAULT_DISPLAY_NAME)}


# --- Serve dashboard ---


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/memories")
def list_memories(limit: int = 50, q: str = ""):
    """List memories. If q is provided, search by keyword. Returns memories with id for delete."""
    try:
        from shared.memory import memory_list, memory_search
        if q and q.strip():
            results = memory_search(q.strip(), n=limit, with_ids=True)
            return {"memories": results}
        return {"memories": memory_list(limit=limit)}
    except Exception as e:
        return {"memories": [], "error": str(e)}


@app.post("/api/memories")
def create_memory(m: MemoryCreate):
    """Add a memory manually."""
    try:
        from shared.memory import memory_add
        ok = memory_add(
            m.fact.strip(),
            weight=m.weight,
            memory_type=m.memory_type,
        )
        return {"ok": ok, "message": "Memory stored." if ok else "Chromadb not available."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    """Delete a memory by id."""
    try:
        from shared.memory import memory_delete
        ok = memory_delete(memory_id)
        return {"ok": ok, "message": "Memory deleted." if ok else "Failed to delete."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/memories/refresh")
def refresh_memory(query: str, bump_weight: bool = False):
    """Refresh a memory by query to make it more relevant."""
    try:
        from shared.memory import memory_refresh
        result = memory_refresh(query.strip(), bump_weight=bump_weight)
        return {"ok": result is not None, "memory": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- Memory Agent (nightly proposals, user approval before commit) ---

def _ensure_woody_db(db_path: Path) -> Path:
    """Ensure Woody DB exists; create if missing. Returns resolved path."""
    db_path = db_path.resolve()
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        woody_dir = Path(__file__).resolve().parent.parent.parent / "woody"
        import importlib.util
        spec = importlib.util.spec_from_file_location("woody_db", str(woody_dir / "app" / "db.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.init_db(db_path)
    return db_path


@app.get("/api/memory-agent/proposals")
def memory_agent_proposals():
    """List pending memory agent proposals. User must approve before changes are committed."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import list_pending_proposals
        db_path = _ensure_woody_db(get_woody_db_path())
        return {"proposals": list_pending_proposals(db_path)}
    except Exception as e:
        return {"proposals": [], "error": str(e)}


@app.post("/api/memory-agent/proposals/{proposal_id}/approve")
def memory_agent_approve(proposal_id: str):
    """Approve a proposal and commit the change. Trains the agent by confirming the action."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import resolve_proposal, commit_proposal
        db_path = _ensure_woody_db(get_woody_db_path())
        if not resolve_proposal(db_path, proposal_id, "approved"):
            return {"ok": False, "message": "Proposal not found or already resolved."}
        ok, msg = commit_proposal(db_path, proposal_id)
        return {"ok": ok, "message": msg}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/memory-agent/proposals/{proposal_id}/reject")
def memory_agent_reject(proposal_id: str):
    """Reject a proposal. Trains the agent by indicating the action is not desired."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import resolve_proposal, get_proposal
        from shared.user_actions import log_action
        db_path = _ensure_woody_db(get_woody_db_path())
        prop = get_proposal(db_path, proposal_id)
        ok = resolve_proposal(db_path, proposal_id, "rejected")
        if ok and prop and prop.get("action_type") == "event_suggestion":
            payload = prop.get("payload", {})
            log_action("event_rejected", proposal_id=proposal_id, title=payload.get("title"), event_date=(payload.get("date") or "")[:10], source=payload.get("description", "")[:100], db_path=db_path)
        return {"ok": ok, "message": "Rejected." if ok else "Proposal not found or already resolved."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/memory-agent/proposals/approve-all")
def memory_agent_approve_all():
    """Approve all pending memory agent proposals."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import list_pending_proposals, resolve_proposal, commit_proposal
        db_path = _ensure_woody_db(get_woody_db_path())
        proposals = list_pending_proposals(db_path)
        results = []
        for p in proposals:
            pid = p.get("id")
            if not pid:
                continue
            if resolve_proposal(db_path, pid, "approved"):
                ok, msg = commit_proposal(db_path, pid)
                results.append({"id": pid, "ok": ok, "message": msg})
            else:
                results.append({"id": pid, "ok": False, "message": "Already resolved."})
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/memory-agent/proposals/reject-all")
def memory_agent_reject_all():
    """Reject all pending memory agent proposals."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import list_pending_proposals, resolve_proposal, get_proposal
        from shared.user_actions import log_action
        db_path = _ensure_woody_db(get_woody_db_path())
        proposals = list_pending_proposals(db_path)
        results = []
        for p in proposals:
            pid = p.get("id")
            if not pid:
                continue
            prop = get_proposal(db_path, pid)
            ok = resolve_proposal(db_path, pid, "rejected")
            if ok and prop and prop.get("action_type") == "event_suggestion":
                payload = prop.get("payload", {})
                log_action("event_rejected", proposal_id=pid, title=payload.get("title"), event_date=(payload.get("date") or "")[:10], source=payload.get("description", "")[:100], db_path=db_path)
            results.append({"id": pid, "ok": ok})
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/memory-agent/run")
def memory_agent_run_now():
    """Manually trigger the memory agent to propose changes (normally runs nightly)."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.memory_agent import run_memory_agent
        db_path = _ensure_woody_db(get_woody_db_path())
        summary = run_memory_agent(db_path)
        return {"ok": True, "summary": summary}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/events-agent/run")
def events_agent_run_now():
    """Manually trigger the EVENTS agent to propose event→memory changes (also runs as part of Memory Agent)."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.events_agent import run_events_agent
        db_path = _ensure_woody_db(get_woody_db_path())
        summary = run_events_agent(db_path)
        return {"ok": True, "summary": summary}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# --- Contacts ---


@app.get("/api/contacts")
def list_contacts(limit: int = 100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, email, phone, notes, created_at FROM contacts ORDER BY name LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/contacts")
def create_contact(c: ContactCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO contacts (name, email, phone, notes) VALUES (?, ?, ?, ?)",
        (c.name, c.email, c.phone, c.notes),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, name, email, phone, notes, created_at FROM contacts WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return dict(row)


@app.patch("/api/contacts/{id}")
def update_contact(id: int, c: ContactCreate):
    conn = get_conn()
    conn.execute(
        "UPDATE contacts SET name=?, email=?, phone=?, notes=? WHERE id=?",
        (c.name, c.email, c.phone, c.notes, id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/contacts/{id}")
def delete_contact(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM contacts WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/contacts/import/google")
def import_contacts_from_google():
    """Manually trigger CONTACT agent to sync from Google and build circles from activity."""
    try:
        from shared.contact_agent import run_contact_agent
        result = run_contact_agent()
        if result.get("error"):
            return {"ok": False, "message": result["error"]}
        return {
            "ok": True,
            "added": result.get("added", 0),
            "skipped": result.get("skipped", 0),
            "circle_proposals": result.get("circle_proposals", 0),
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/contacts/import/vcard")
async def import_contacts_from_vcard(file: UploadFile = File(...)):
    """Import contacts from vCard file (e.g. iPhone export from iCloud)."""
    try:
        content = (await file.read()).decode("utf-8", errors="replace")
        from shared.contact_agent import import_from_vcard
        added, skipped = import_from_vcard(content)
        return {"ok": True, "added": added, "skipped": skipped}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# --- Places ---


@app.get("/api/places")
def list_places(limit: int = 100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, address, notes, created_at FROM places ORDER BY name LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/places")
def create_place(p: PlaceCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO places (name, address, notes) VALUES (?, ?, ?)",
        (p.name, p.address, p.notes),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, name, address, notes, created_at FROM places WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return dict(row)


@app.delete("/api/places/{id}")
def delete_place(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM places WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# --- Circles ---


@app.get("/api/circles")
def list_circles(limit: int = 100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, description, created_at FROM circles ORDER BY name LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/circles")
def create_circle(c: CircleCreate):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO circles (name, description) VALUES (?, ?)",
            (c.name, c.description),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, description, created_at FROM circles WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return dict(row)
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.get("/api/circles/{id}")
def get_circle(id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, description, created_at FROM circles WHERE id = ?",
        (id,),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Not found"}
    circle = dict(row)
    members = conn.execute(
        "SELECT entity_type, entity_id FROM circle_members WHERE circle_id = ?",
        (id,),
    ).fetchall()
    conn.close()
    circle["members"] = [{"entity_type": r[0], "entity_id": r[1]} for r in members]
    return circle


@app.post("/api/circles/{id}/members")
def add_circle_member(id: int, m: CircleMemberAdd):
    if m.entity_type not in ("contact", "place", "memory"):
        return {"ok": False, "error": "entity_type must be contact, place, or memory"}
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO circle_members (circle_id, entity_type, entity_id) VALUES (?, ?, ?)",
            (id, m.entity_type, str(m.entity_id)),
        )
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


@app.delete("/api/circles/{id}/members")
def remove_circle_member(id: int, entity_type: str, entity_id: str):
    conn = get_conn()
    conn.execute(
        "DELETE FROM circle_members WHERE circle_id = ? AND entity_type = ? AND entity_id = ?",
        (id, entity_type, entity_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/circles/{id}")
def delete_circle(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM circles WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# --- Wishlist, TODOs (Woody DB) ---
# Use TELEGRAM_REMINDER_CHAT_ID when set so items added via Telegram appear in dashboard
def _get_dashboard_chat_id() -> int:
    try:
        cid = os.environ.get("TELEGRAM_REMINDER_CHAT_ID", "").strip()
        if cid and cid.lstrip("-").isdigit():
            return int(cid)
    except (ValueError, TypeError):
        pass
    return 0


DASHBOARD_CHAT_ID = _get_dashboard_chat_id()


def _get_woody_conn():
    from pathlib import Path
    from shared.db_path import get_woody_db_path
    import sqlite3
    db_path = get_woody_db_path().resolve()
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        woody_dir = Path(__file__).resolve().parent.parent.parent / "woody"
        import importlib.util
        spec = importlib.util.spec_from_file_location("woody_db", str(woody_dir / "app" / "db.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/wishlist")
def list_wishlist(limit: int = 50):
    """List wishlist items (dashboard chat_id=0)."""
    try:
        conn = _get_woody_conn()
        rows = conn.execute(
            "SELECT id, content, created_at FROM wishlist WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (DASHBOARD_CHAT_ID, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except (FileNotFoundError, Exception):
        return []


@app.post("/api/wishlist")
def create_wishlist_item(w: WishlistCreate):
    """Add wishlist item."""
    try:
        conn = _get_woody_conn()
        cur = conn.execute(
            "INSERT INTO wishlist (chat_id, content) VALUES (?, ?)",
            (DASHBOARD_CHAT_ID, w.content.strip()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, content, created_at FROM wishlist WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        conn.close()
        return dict(row)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/wishlist/{id}")
def delete_wishlist_item(id: int):
    """Remove wishlist item."""
    try:
        conn = _get_woody_conn()
        conn.execute("DELETE FROM wishlist WHERE id = ? AND chat_id = ?", (id, DASHBOARD_CHAT_ID))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/todos")
def list_todos(limit: int = 100, include_done: bool = True):
    """List TODOs from Woody DB (dashboard chat_id)."""
    try:
        conn = _get_woody_conn()
        if include_done:
            rows = conn.execute(
                "SELECT id, content, status, due_date, created_at FROM todos WHERE chat_id = ? ORDER BY status ASC, due_date IS NULL, due_date ASC, created_at DESC LIMIT ?",
                (DASHBOARD_CHAT_ID, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, content, status, due_date, created_at FROM todos WHERE chat_id = ? AND status = 'pending' ORDER BY due_date IS NULL, due_date ASC, created_at DESC LIMIT ?",
                (DASHBOARD_CHAT_ID, limit),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except (FileNotFoundError, Exception):
        return []


@app.post("/api/todos/{id}/complete")
def complete_todo(id: int):
    """Mark a TODO as done."""
    try:
        conn = _get_woody_conn()
        cur = conn.execute(
            "UPDATE todos SET status = 'done' WHERE id = ? AND chat_id = ? AND status = 'pending'",
            (id, DASHBOARD_CHAT_ID),
        )
        conn.commit()
        conn.close()
        if cur.rowcount > 0:
            return {"ok": True}
        return {"ok": False, "error": "TODO not found or already done"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.delete("/api/todos/{id}")
def delete_todo(id: int):
    """Remove a TODO."""
    try:
        conn = _get_woody_conn()
        cur = conn.execute("DELETE FROM todos WHERE id = ? AND chat_id = ?", (id, DASHBOARD_CHAT_ID))
        conn.commit()
        conn.close()
        if cur.rowcount > 0:
            return {"ok": True}
        return {"ok": False, "error": "TODO not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/todos")
def create_todo(t: TodoCreate):
    """Add a TODO to Woody (dashboard chat_id=0). Used when adding event to TODO list."""
    try:
        conn = _get_woody_conn()
        due = (t.due_date or "").strip()[:10] or None
        cur = conn.execute(
            "INSERT INTO todos (chat_id, content, status, due_date) VALUES (?, ?, 'pending', ?)",
            (DASHBOARD_CHAT_ID, t.content.strip(), due),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, content, status, due_date, created_at FROM todos WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        conn.close()
        if t.event_id is not None:
            try:
                from shared.user_actions import log_action
                log_action("todo_added", event_id=t.event_id, title=t.content.strip(), event_date=due)
            except Exception:
                pass
        return {"ok": True, "id": row["id"]}
    except FileNotFoundError:
        return {"ok": False, "error": "Woody database not found. Run Woody once."}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wishlist/{id}/fulfill")
def fulfill_wishlist_item(id: int):
    """Mark wishlist item as fulfilled: creates a completed event and removes from wishlist."""
    try:
        from shared.db_path import get_woody_db_path
        from shared.events_agent import fulfill_wishlist_item as do_fulfill
        db_path = get_woody_db_path()
        event_id = do_fulfill(id, woody_db_path=db_path)
        if event_id is None:
            return {"ok": False, "error": "Wishlist item not found"}
        return {"ok": True, "event_id": event_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- Chat (Woody from dashboard) ---


class ChatMessage(BaseModel):
    message: str


@app.get("/api/chat/history")
def chat_history(limit: int = 20):
    """Get recent chat messages for dashboard."""
    try:
        from shared.chat import get_woody_db_path
        db_path = get_woody_db_path()
        if not db_path.exists():
            return {"messages": []}
        woody_dir = Path(__file__).resolve().parent.parent.parent / "woody"
        import sys
        if str(woody_dir) not in sys.path:
            sys.path.insert(0, str(woody_dir))
        from app.conversation import get_messages
        msgs = get_messages(db_path, DASHBOARD_CHAT_ID, limit=limit)
        return {"messages": msgs}
    except Exception:
        return {"messages": []}


@app.post("/api/chat")
def chat_send(m: ChatMessage):
    """Send a message to Woody. Returns response."""
    msg = m.message.strip()
    try:
        from shared.chat import run_chat
        response, _db_path = run_chat(msg, chat_id=DASHBOARD_CHAT_ID)
        return {"response": response}
    except Exception as e:
        return {"response": f"Error: {e}"}


@app.get("/api/debug/woody-db")
def debug_woody_db(approval_id: Optional[str] = None):
    """Return Woody DB path, scan ALL app.db locations, and optionally search for approval_id."""
    import sqlite3
    from shared.db_path import get_woody_db_path

    woody_path = get_woody_db_path().resolve()
    repo = Path(__file__).resolve().parent.parent.parent
    # Canonical path first (what create/list/approve actually use)
    candidates = [
        ("canonical (get_woody_db_path)", woody_path),
        ("woody/app.db", repo / "woody" / "app.db"),
        ("dashboard/app.db", repo / "dashboard" / "app.db"),
        ("app.db", repo / "app.db"),
    ]
    # Dedupe by path
    seen = set()
    unique = []
    for label, p in candidates:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, Path(key)))

    dbs = []
    for label, p in unique:
        info = {"path": str(p), "exists": p.exists(), "approvals": [], "pending_count": 0, "wishlist_count": 0}
        if p.exists():
            try:
                conn = sqlite3.connect(str(p))
                info["pending_count"] = conn.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending'").fetchone()[0]
                cur = conn.execute(
                    "SELECT id, chat_id, tool_name, status, created_at FROM approvals ORDER BY created_at DESC LIMIT 20"
                )
                info["approvals"] = [{"id": r[0], "chat_id": r[1], "tool_name": r[2], "status": r[3], "created_at": r[4]} for r in cur.fetchall()]
                try:
                    info["wishlist_count"] = conn.execute("SELECT COUNT(*) FROM wishlist").fetchone()[0]
                except Exception:
                    pass
                if approval_id:
                    row = conn.execute("SELECT id, status, created_at FROM approvals WHERE LOWER(id) = LOWER(?)", (approval_id.strip(),)).fetchone()
                    info["search_result"] = {"found": bool(row), "row": list(row) if row else None}
                conn.close()
            except Exception as e:
                info["error"] = str(e)
        dbs.append({"label": label, **info})

    return {
        "woody_db_path": str(woody_path),
        "all_dbs": dbs,
        "search_approval_id": approval_id,
    }


@app.get("/api/otel/traces")
def get_otel_traces(limit: int = 30):
    """Return recent OpenTelemetry spans for the dashboard widget."""
    buffer = get_span_buffer()
    if not buffer:
        return {"spans": []}
    return {"spans": buffer.get_spans(limit=limit)}


@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<p>Dashboard API. Add static/index.html for UI.</p>")
