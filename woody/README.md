# Woody

Local-first personal AI agent with Telegram interface, OpenAI, and human-approval workflow for write actions.

## Setup

```bash
# From repo root, with venv activated
cd woody
pip install -r ../requirements.txt   # or already installed
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and OPENAI_API_KEY
```

## Run

```bash
python -m app.main
# or
python run.py
```

## Features

- **Telegram polling** – receives messages via long polling
- **OpenAI integration** – GPT-4o-mini with tool calling
- **Approval workflow** – write actions require `APPROVE <ID>` or `REJECT <ID>`
- **Tool registry** – modular tools with GREEN (read) / YELLOW (write) / RED (disabled) tiers

## Commands

- Send any message → agent responds (may propose write actions)
- `APPROVE <id>` → execute approved write action
- `REJECT <id>` → reject pending approval
