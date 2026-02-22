# Woody – State Conventions

## Purpose

Define where and how Woody stores persistent state. Markdown files are **system-of-record** for conventions; actual data lives in SQLite, JSON, and Chromadb.

---

## State Locations

| State | Location | Format |
|-------|----------|--------|
| Approvals | Woody `app.db` | SQLite |
| Conversation | Woody `app.db` | SQLite |
| Home ops (lists) | Woody `app.db` | SQLite |
| Google tokens | `.google_tokens.json` (repo root) | JSON |
| Long-term memory | `chroma_db/` | Chromadb |
| Scheduled templates | `dashboard/dashboard.db` | SQLite |
| Dashboard data | `dashboard/dashboard.db` | SQLite |
| Contacts, places, circles | `dashboard/dashboard.db` | SQLite |
| Reminder digest sent | Woody `app.db` | SQLite |
| User reminders | Woody `app.db` | SQLite |
| TODOs | Woody `app.db` | SQLite |
| Wishlist | Woody `app.db` | SQLite |
| Memory agent proposals | Woody `app.db` | SQLite |
| Memory agent audit | Woody `app.db` | SQLite |
| User actions | Woody `app.db` | SQLite |

---

## Rules

1. **No ad-hoc state** – Only use the locations above. Don't create new state files without updating this doc.
2. **Tokens** – `.google_tokens.json` is refreshed automatically; refreshed tokens are persisted.
3. **Approvals** – IDs are 8-char alphanumeric. Never regenerate. Status: pending → approved/rejected.
4. **Timestamps** – Use UTC, ISO 8601 when storing.
5. **Mutations** – Read before write. Preserve existing data when updating.

---

## Woody DB Schema (app.db)

- `approvals` – Pending/approved/rejected tool executions
- `home_ops_lists`, `home_ops_items` – Lists (shopping, tasks)
- `conversation_messages` – Last N messages per chat
- `reminder_digest_sent` – Dates we've sent daily event digest
- `reminders` – User-created reminders (chat_id, text, remind_at, status)
- `todos` – TODOs (chat_id, content, status, due_date)
- `wishlist` – Wishlist items (chat_id, content) – aspirational, may never complete
- `memory_agent_proposals` – Pending memory changes (add/remove/consolidate/promote/event_memory)
- `memory_agent_audit` – Log of committed memory agent actions
- `user_actions` – Log of user actions (calendar_added, todo_added, event_deleted, event_approved, event_rejected) for preference learning

---

## Dashboard DB Schema (dashboard.db)

- `events` – date, title, description, event_type, recurrence
- `scheduled_templates` – title, description, recurrence (YEARLY|MONTHLY|WEEKLY), anchor_date
- `about_me` – content (user preferences for agent), updated_at
- `decisions` – date, decision, context, outcome
- `notes` – title, content, tags
- `contacts` – name, email, phone, notes
- `places` – name, address, notes
- `circles` – name, description (groups connecting people, places, memories)
- `circle_members` – circle_id, entity_type (contact|place|memory), entity_id
