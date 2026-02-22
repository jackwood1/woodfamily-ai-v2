# Agent Guidance – Woodfamily AI v2

## Project Overview

- **Woody** – Telegram bot (OpenAI, tools, approval flow). Runs from `woody/` with `python run.py`.
- **Dashboard** – FastAPI web app for events, decisions, notes, memories, integrations. Runs with `uvicorn dashboard.app.main:app`.
- **Shared** – `shared/` holds `google_tokens`, `memory`, `reminders`, `events_agent`, `memory_agent`, `contact_agent`, `communications_agent` used by both.

## COMMUNICATIONS Agent (`shared/communications_agent.py`)

Unified interface for email and SMS. **Runs regularly** (every 60 min) to scan inbox and feed other agents:

- **Email (Gmail)** – send_email, read_emails, get_email, archive_email, trash_email. Requires gmail.modify scope for archive/trash; reconnect Google after adding.
- **SMS (Twilio)** – send_sms when TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER are set.
- **Woody tools** – communications_send (email|sms), communications_read, communications_get_email, communications_archive_email, communications_trash_email.
- **Inbox scan loop** – Reads inbox, passes correspondent emails to CONTACT agent (circle inference), passes potential events (reminders, TODOs, meetings, dates) to EVENTS agent. Proposals appear in Memory Agent panel; user approves.

## CONTACT Agent (`shared/contact_agent.py`)

Syncs contacts from Google and vCard (iPhone):

- **Google People API** – `sync_from_google()` fetches contacts; CONTACT agent loop runs every 24h (configurable via `CONTACT_AGENT_INTERVAL_MINUTES`). Requires `contacts.readonly` scope; reconnect Google after adding.
- **vCard import** – `import_from_vcard()` parses .vcf files. Use for iPhone exports (iCloud.com → Export vCard). Dashboard "Import vCard" button.
- **Merge** – Skips contacts that already exist (by email or name). Dashboard "Import Google" for manual sync.
- **Activity-based circles** – Analyzes Gmail (last 30 days) and Calendar attendees (last 60 days) to propose adding contacts to "Frequent correspondents" and "Event attendees" circles. Proposals appear in Memory Agent panel; user approves. SMS requires separate integration (not implemented).

## EVENTS Agent (`shared/events_agent.py`)

Manages calendar events, TODOs, and wishlists:

- **Calendar interface** – `get_all_events()` merges dashboard events + Google Calendar. `create_event()` writes to dashboard.
- **TODO completion** – When Woody marks a TODO done, `capture_completed_todo()` creates a dashboard event (`event_type="completed"`).
- **Wishlist** – `list_wishlist()`, `fulfill_wishlist_item()` (creates completed event, removes from wishlist).
- **Events → memories** – `propose_events_for_memory()` creates memory proposals for recent events; user approves via Memory Agent UI.
- **Nightly** – Runs as part of Memory Agent (which calls `propose_events_for_memory()`). Dashboard "Run EVENTS" triggers events→memory only.
- **Scheduled templates** – Recurring items (bills, car inspections, birthdays). EVENTS agent loop runs every 6h (configurable via `EVENTS_AGENT_INTERVAL_MINUTES`), creates events when due, surfaces "Requires Scheduling" for items due within 14 days. Included in daily reminder digest.

## About Me

- **Storage**: Dashboard DB `about_me` table. Injected into Woody system prompt.
- **Import**: Settings → About Me. Upload LinkedIn or Facebook data export ZIP (request at each platform's Settings → Data Privacy → Get a copy of your data). Parsers in `shared/import_archives.py`.

## Key Paths

- `woody/` – Bot, tools, agent, Telegram loop
- `dashboard/` – Web UI, API, static assets
- `shared/` – Google OAuth, Chromadb memory, reminder helpers
- `otel_setup/` – OpenTelemetry
- `tests/` – pytest, run with `PYTHONPATH=. pytest tests/`

## Conventions

1. **Python 3.9+** – Use `Optional[X]` and `from __future__ import annotations` for compatibility.
2. **Tools** – Woody tools live in `woody/app/tools/`. Register via `ToolDef` with `PermissionTier` (GREEN=read, YELLOW=approval, RED=disabled).
3. **Approvals** – Write tools require user to reply `APPROVE <id>`. See `woody/app/approvals.py`.
4. **Google** – Use `shared.google_tokens.get_credentials()` for Gmail/Calendar; it persists refreshed tokens.
5. **State** – See `STATE.md` for where data lives.

## Adding Features

- **New Woody tool** – Add handler in `woody/app/tools/`, register with `register(ToolDef(...))`, import in `agent.py` and `telegram_loop.py`.
- **New dashboard endpoint** – Add in `dashboard/app/main.py`.
- **New integration** – OAuth tokens go in `.google_tokens.json`; add Connect/Disconnect in Integrations panel.

## Testing

```bash
python -m pytest tests/ -v
```

Tests use temp DBs (via `tmp_path`). Set `DASHBOARD_DB_PATH` in tests to point at temp dashboard DB.

### Test Coverage

| File | Coverage |
|------|----------|
| `test_events_agent.py` | `_compute_next_due` (YEARLY/MONTHLY/WEEKLY), `create_event`, `get_all_events`, `capture_completed_todo`, `get_requires_scheduling`, `process_scheduled_templates_due`, `list_wishlist`, `fulfill_wishlist_item` |
| `test_contact_agent.py` | `_normalize_email`, `_parse_email_from_header`, `_extract_person_fields`, `import_from_vcard` (single import, skip-existing) |
| `test_communications_agent.py` | `sms_available`, `send` (unknown channel), `send_sms` (not configured), `run_communications_agent` |
| `test_memory_agent.py` | `create_proposal`, `list_pending_proposals`, `resolve_proposal`, `get_proposal`, `commit_proposal` (circle_add) |
| `test_approvals.py` | Create, approve, reject approval flow |

## Env Vars (see README)

- Required: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`
- Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- Optional: `GITHUB_TOKEN`, `TELEGRAM_REMINDER_CHAT_ID`, `DASHBOARD_URL`, `DASHBOARD_USER`/`DASHBOARD_PASSWORD`
