"""EVENTS agent loop - runs regularly to process scheduled templates and surface Requires Scheduling."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root on path for shared
_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _events_agent_interval_minutes() -> int:
    try:
        return int(os.environ.get("EVENTS_AGENT_INTERVAL_MINUTES", "360"))  # 6 hours default
    except ValueError:
        return 360


def _run_events_agent_once() -> bool:
    """Process scheduled templates (create events when due). Returns True if any events created."""
    try:
        from shared.events_agent import process_scheduled_templates
        created, requires = process_scheduled_templates()
        if created > 0:
            print(f"[EVENTS Agent] Created {created} event(s) from scheduled templates")
        if requires:
            print(f"[EVENTS Agent] {len(requires)} item(s) require scheduling")
        return created > 0
    except Exception as e:
        print(f"[EVENTS Agent] Error: {e}")
        return False


def _events_agent_loop(interval_minutes: int) -> None:
    """Run process_scheduled_templates every interval_minutes. Run once at startup."""
    _run_events_agent_once()
    while True:
        try:
            time.sleep(interval_minutes * 60)
            _run_events_agent_once()
        except Exception as e:
            print(f"[EVENTS Agent] Loop error: {e}")


def start_events_agent_loop(interval_minutes: int | None = None) -> None:
    """Start EVENTS agent loop in a daemon thread."""
    interval = interval_minutes or _events_agent_interval_minutes()
    thread = threading.Thread(
        target=_events_agent_loop,
        args=(interval,),
        daemon=True,
    )
    thread.start()
    print(f"[EVENTS Agent] Started (runs every {interval} min)")
