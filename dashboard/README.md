# Woody Dashboard

Track important events, decisions, and notes in one place.

## Run

```bash
# From repo root, with venv activated
cd dashboard
uvicorn app.main:app --reload
```

Open http://localhost:8000

## Features

- **Events** – Dates, milestones, reminders
- **Decisions** – What was decided, context, outcome
- **Notes** – Quick notes with tags

Data is stored in `dashboard.db` (SQLite) in the dashboard directory.
