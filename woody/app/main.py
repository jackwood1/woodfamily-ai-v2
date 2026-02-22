"""Entry point for woody."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from otel_setup import init_tracing

from app.config import get_db_path, get_openai_key, get_telegram_token
from app.db import init_db
from app.health_server import start_health_server
from app.communications_agent_loop import start_communications_agent_loop
from app.contact_agent_loop import start_contact_agent_loop
from app.events_agent_loop import start_events_agent_loop
from app.memory_agent_loop import start_memory_agent_loop
from app.reminder_loop import start_reminder_loop
from app.telegram_loop import run_polling_loop


def main() -> None:
    """Boot sequence: load config, init DB, start health server, Telegram polling."""
    init_tracing(service_name="woody")
    start_health_server()
    token = get_telegram_token()
    openai_key = get_openai_key()
    db_path = get_db_path()

    init_db(db_path)
    start_memory_agent_loop(db_path)
    start_events_agent_loop()
    start_contact_agent_loop()
    start_communications_agent_loop()
    start_reminder_loop(token, db_path)
    run_polling_loop(token, db_path, openai_key)


if __name__ == "__main__":
    main()
