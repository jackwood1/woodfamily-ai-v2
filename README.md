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

# Dashboard (HTTP)
cd dashboard && uvicorn app.main:app --reload

# Dashboard (HTTPS with dev certs)
cd dashboard && uvicorn app.main:app --reload --host localhost --port 8443 \
  --ssl-keyfile=dev-certs/key.pem --ssl-certfile=dev-certs/cert.pem
```

## Docker (SSL)

```bash
docker-compose up
```

Dashboard: **https://localhost:8443**  
OAuth callbacks (Google, Yahoo) use `https://localhost:8443/api/integrations/.../callback`. Add these redirect URIs in your Google/Yahoo app settings.

## Testing

```bash
python -m pytest tests/ -v
```

## PR Review Agent

On every pull request, a [GitHub Action](.github/workflows/pr-review.yml) runs tests, reviews the diff with an LLM, and posts recommendations. Add `OPENAI_API_KEY` as a repo secret to enable the LLM review. See [.github/PR-REVIEW.md](.github/PR-REVIEW.md).

Tests cover the shared agents (events, contact, communications, memory), approvals, and dashboard API. Agent tests use temp SQLite DBs; set `DASHBOARD_DB_PATH` via `monkeypatch` to point at temp dashboard DB.

## Docker

```bash
docker-compose up
```

## Deployment

See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** for AWS deployment (EC2 + Docker Compose or ECS).

## Integrations

- **Google (Gmail, Calendar, Contacts)**: Visit `http://localhost:8000/api/integrations/google/authorize` to connect. Enable **People API** for contact sync. Reconnect after adding to grant gmail.modify (archive/trash). For production, set `GOOGLE_REDIRECT_URI=https://your-domain/api/integrations/google/callback`.
- **Yahoo Mail**: Create an app at [developer.yahoo.com](https://developer.yahoo.com/apps/), add `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, and `YAHOO_REDIRECT_URI` to `.env`. Local: `https://localhost:8443/api/integrations/yahoo/callback`. Production: `https://your-domain/api/integrations/yahoo/callback`.
- **GitHub**: Set `GITHUB_TOKEN` in `.env`

## Optional env vars

- `OTEL_EXPORTER_OTLP_ENDPOINT` – OTLP collector URL
- `OTEL_CONSOLE_EXPORT=true` – Print traces to stdout
- `DASHBOARD_USER` / `DASHBOARD_PASSWORD` – Basic auth for dashboard
- **Google Auth (Sign in with Google)**: Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` (e.g. `openssl rand -hex 32`). Add redirect URI `https://your-domain/api/auth/google/callback` in Google Cloud Console. Optional: `GOOGLE_AUTH_ALLOWED_DOMAINS=gmail.com,woodfamily.ai` to restrict login.
- `TELEGRAM_REMINDER_CHAT_ID` – Chat ID for daily event reminders and end-of-day summary (message Woody `/chatid` to get yours)
- `SUMMARY_HOUR_UTC` – Hour (UTC) to send daily summary of what Woody did (default: 5 = 9pm PST)
- `DASHBOARD_URL` – Dashboard API URL for Woody reminders (default: http://localhost:8000; use http://dashboard:8000 in Docker)
- `CALENDAR_TIMEZONE` – IANA timezone for calendar events (default: UTC). **Set this to your timezone** (e.g. America/Los_Angeles, America/New_York) or events may appear at the wrong time.
- `CONTACT_AGENT_INTERVAL_MINUTES` – How often to sync contacts from Google (default: 1440 = 24h).
- `COMMUNICATIONS_AGENT_INTERVAL_MINUTES` – How often to scan inbox and feed contacts/events agents (default: 60).
- **SMS (Twilio)**: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` – For SMS via Woody. [Create a Twilio account](https://www.twilio.com/try-twilio), buy a phone number, add the three values to `.env`, then restart. Woody can send SMS when you say "text +15551234567 saying Hello".
- `WOODY_DB_PATH` – Path to Woody's SQLite DB (default: woody/app.db). Dashboard chat uses this for conversation & approvals.
- `DASHBOARD_DB_PATH` – Path to dashboard SQLite DB (default: dashboard/dashboard.db). Override in tests via `monkeypatch.setenv`.
