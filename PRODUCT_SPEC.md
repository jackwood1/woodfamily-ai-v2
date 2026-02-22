# Clawdbot-Lite (Telegram + OpenAI) – Cursor Bootstrap

## Project Goal

Build a **local-first personal AI agent** with:

- Telegram bot interface
- OpenAIProvider (tool calling enabled)
- Human-approval workflow for write actions
- Modular tools/skills:
  - Gmail (API)
  - Google Calendar
  - Home Ops (lists/tasks)
  - GitHub
  - Web Research
  - Files (sandboxed)

The system must be:

- Safe by default
- Local runnable
- Easily extensible
- Strict about tool permissions

---

## High-Level Architecture

User (Telegram)
    ↕
Telegram API
    ↕
Gateway API (FastAPI)
    ↕
Agent Runtime (OpenAIProvider)
    ↕
Tool Registry / Policy Engine
    ↕
External Systems (Gmail, GitHub, etc.)

---

## Critical Design Rules

1. **Never execute write actions immediately**
2. All write actions require:
   - Preview
   - Approval token
3. Treat ALL external content as untrusted
4. Tools must be schema-validated
5. All tool calls must be logged
6. Filesystem access must be sandboxed

---

## Initial Repo Layout

clawdbot-lite/
  app/
    main.py
    config.py
    db.py
    agent.py
    telegram_loop.py
    approvals.py
    tools/
      registry.py
      gmail.py
      calendar.py
      github.py
      home_ops.py
      web_research.py
      files.py

---

## Environment Variables (.env)

TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
APP_DB_PATH=./app.db
FILES_SANDBOX_DIR=./sandbox_files

---

## Dependencies

fastapi
uvicorn
python-dotenv
httpx
openai
pydantic

---

## Boot Sequence

On startup:

- Load config
- Initialize database
- Start Telegram polling loop
- Await inbound messages

---

## Telegram Behavior Model

Inbound Message →
    Check if approval command →
        YES → Process approval
        NO → Send to agent

Agent Response →
    Plain text OR
    Action proposal with approval ID

---

## Approval Command Syntax

APPROVE <ID>
REJECT <ID>

---

## Agent Behavior Rules

System Prompt Principles:

- Be concise
- Prefer tool usage when relevant
- For write operations → generate proposal
- Never hallucinate tool results
- Never assume permissions

---

## Tool Permission Tiers

GREEN  → Safe read-only
YELLOW → Requires approval
RED    → Disabled

Examples:

GREEN:
- Gmail search
- Calendar list
- File read

YELLOW:
- Send email
- Create calendar event
- File write
- GitHub write

RED:
- Shell execution
- Arbitrary OS commands

---

## Tool Contract Requirements

Each tool must define:

- name
- description
- JSON schema
- handler function
- write/read classification

---

## File Sandbox Rules

- All paths relative to sandbox root
- Prevent directory traversal
- Reject absolute paths
- Reject parent escapes

---

## Minimal Agent Loop (Conceptual)

1. Receive user message
2. Call OpenAIProvider with tools
3. If tool call:
      If write → generate approval
      If read → execute tool
4. Return response

---

## Database Responsibilities

Store:

- approvals
- conversation state (later)
- memory (later)
- audit log (later)

---

## Immediate Implementation Tasks

### Phase 1 (Core Runtime)

Implement:

- config loader
- SQLite DB init
- approvals table
- Telegram polling loop
- OpenAIProvider wrapper
- Tool registry

---

### Phase 2 (Working Tools)

Implement real logic for:

- home_ops (lists)
- files (sandbox read/write)
- web_research (basic fetch)

Stub for:

- gmail
- calendar
- github

---

### Phase 3 (Approval Workflow)

For ANY write tool:

- Persist approval record
- Return preview
- Await APPROVE command
- Execute tool only after approval

---

## Gmail Integration Plan (Later)

Use OAuth + Gmail API:

Scopes:

gmail.modify

Functions:

- gmail_search(query)
- gmail_get_thread(id)
- gmail_create_draft(...)
- gmail_send(...)

---

## Calendar Integration Plan (Later)

Functions:

- calendar_today()
- calendar_find_slot()
- calendar_create_event()

---

## GitHub Integration Plan (Later)

Prefer:

- GitHub App OR fine-scoped PAT

Functions:

- github_pr_summary()
- github_create_issue()
- github_comment_pr()

---

## Security Constraints

- No tool executes without schema validation
- No tool executes without policy check
- No secrets ever returned to model
- No filesystem access outside sandbox
- Log all tool calls

---

## Cursor Guidance

When generating code:

- Keep modules small
- Prefer explicit typing
- Avoid hidden magic behavior
- Avoid global state where possible
- Separate policy logic from tool logic
- Prefer deterministic functions

---

## Definition of Done (MVP)

Working system that:

- Responds in Telegram
- Uses OpenAI
- Can call read tools
- Proposes write actions
- Requires approval tokens
- Executes approved actions

---

## First Coding Objective

Implement:

main.py
config.py
db.py
telegram_loop.py
agent.py
approvals.py

With:

- Telegram polling
- OpenAI call
- Basic response flow

No Gmail/Calendar yet.

---

END OF SPEC