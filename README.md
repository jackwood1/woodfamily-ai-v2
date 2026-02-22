# Woodfamily AI v2

Version 2 - fresh start.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Projects

- **woody** – Telegram bot with OpenAI, approval workflow, tools (home_ops, files, web, Gmail, Calendar, GitHub, memory, reminders, TODOs)
- **dashboard** – Track events, decisions, notes, Otel traces, Google OAuth, **chat with Woody**

## Run

```bash
# Woody (Telegram bot)
cd woody && python run.py

# Dashboard
cd dashboard && uvicorn app.main:app --reload
```

## Testing

```bash
python -m pytest tests/ -v
```

Tests cover the shared agents (events, contact, communications, memory), approvals, and dashboard API. Agent tests use temp SQLite DBs; set `DASHBOARD_DB_PATH` via `monkeypatch` to point at temp dashboard DB.

## Docker

```bash
docker-compose up
```

## Integrations

- **Google (Gmail, Calendar, Contacts)**: Visit `http://localhost:8000/api/integrations/google/authorize` to connect. Enable **People API** for contact sync. Reconnect after adding to grant gmail.modify (archive/trash).
- **GitHub**: Set `GITHUB_TOKEN` in `.env`

## Optional env vars

- `OTEL_EXPORTER_OTLP_ENDPOINT` – OTLP collector URL
- `OTEL_CONSOLE_EXPORT=true` – Print traces to stdout
- `DASHBOARD_USER` / `DASHBOARD_PASSWORD` – Basic auth for dashboard
- `TELEGRAM_REMINDER_CHAT_ID` – Chat ID for daily event reminders and end-of-day summary (message Woody `/chatid` to get yours)
- `SUMMARY_HOUR_UTC` – Hour (UTC) to send daily summary of what Woody did (default: 5 = 9pm PST)
- `DASHBOARD_URL` – Dashboard API URL for Woody reminders (default: http://localhost:8000; use http://dashboard:8000 in Docker)
- `CALENDAR_TIMEZONE` – IANA timezone for calendar events (default: UTC). **Set this to your timezone** (e.g. America/Los_Angeles, America/New_York) or events may appear at the wrong time.
- `CONTACT_AGENT_INTERVAL_MINUTES` – How often to sync contacts from Google (default: 1440 = 24h).
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` – For SMS via COMMUNICATIONS agent (optional).
- `WOODY_DB_PATH` – Path to Woody's SQLite DB (default: woody/app.db). Dashboard chat uses this for conversation & approvals.
- `DASHBOARD_DB_PATH` – Path to dashboard SQLite DB (default: dashboard/dashboard.db). Override in tests via `monkeypatch.setenv`.
