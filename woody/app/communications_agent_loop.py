"""COMMUNICATIONS agent loop - runs regularly to scan inbox and feed CONTACT + EVENTS agents."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# Ensure repo root on path for shared
_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _communications_agent_interval_minutes() -> int:
    try:
        return int(os.environ.get("COMMUNICATIONS_AGENT_INTERVAL_MINUTES", "60"))  # 1 hour default
    except ValueError:
        return 60


def _run_communications_agent_once() -> bool:
    """Scan inbox, pass to contacts and events agents. Returns True if any proposals created."""
    try:
        from shared.communications_agent import run_communications_agent
        result = run_communications_agent()
        if result.get("error"):
            print(f"[COMMUNICATIONS Agent] Error: {result['error']}")
            return False
        circle_props = result.get("circle_proposals", 0)
        event_props = result.get("event_proposals", 0)
        if circle_props > 0:
            print(f"[COMMUNICATIONS Agent] Proposed {circle_props} circle addition(s) from inbox")
        if event_props > 0:
            print(f"[COMMUNICATIONS Agent] Proposed {event_props} event suggestion(s) from inbox")
        return circle_props > 0 or event_props > 0
    except Exception as e:
        print(f"[COMMUNICATIONS Agent] Error: {e}")
        return False


def _communications_agent_loop(interval_minutes: int) -> None:
    """Run communications agent every interval_minutes. Run once at startup."""
    _run_communications_agent_once()
    while True:
        try:
            time.sleep(interval_minutes * 60)
            _run_communications_agent_once()
        except Exception as e:
            print(f"[COMMUNICATIONS Agent] Loop error: {e}")


def start_communications_agent_loop(interval_minutes: int | None = None) -> None:
    """Start COMMUNICATIONS agent loop in a daemon thread."""
    interval = interval_minutes or _communications_agent_interval_minutes()
    thread = threading.Thread(
        target=_communications_agent_loop,
        args=(interval,),
        daemon=True,
    )
    thread.start()
    print(f"[COMMUNICATIONS Agent] Started (runs every {interval} min)")
