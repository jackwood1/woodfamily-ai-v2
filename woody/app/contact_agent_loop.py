"""CONTACT agent loop - runs regularly to sync contacts from Google People API."""

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


def _contact_agent_interval_minutes() -> int:
    try:
        return int(os.environ.get("CONTACT_AGENT_INTERVAL_MINUTES", "1440"))  # 24h default
    except ValueError:
        return 1440


def _run_contact_agent_once() -> bool:
    """Sync contacts from Google, build circles from activity. Returns True if any changes."""
    try:
        from shared.contact_agent import run_contact_agent
        result = run_contact_agent()
        if result.get("error"):
            print(f"[CONTACT Agent] Error: {result['error']}")
            return False
        added = result.get("added", 0)
        skipped = result.get("skipped", 0)
        proposals = result.get("circle_proposals", 0)
        if added > 0:
            print(f"[CONTACT Agent] Added {added} contact(s), skipped {skipped} existing")
        if proposals > 0:
            print(f"[CONTACT Agent] Proposed {proposals} circle addition(s)")
        return added > 0 or proposals > 0
    except Exception as e:
        print(f"[CONTACT Agent] Error: {e}")
        return False


def _contact_agent_loop(interval_minutes: int) -> None:
    """Run contact sync every interval_minutes. Run once at startup."""
    _run_contact_agent_once()
    while True:
        try:
            time.sleep(interval_minutes * 60)
            _run_contact_agent_once()
        except Exception as e:
            print(f"[CONTACT Agent] Loop error: {e}")


def start_contact_agent_loop(interval_minutes: int | None = None) -> None:
    """Start CONTACT agent loop in a daemon thread."""
    interval = interval_minutes or _contact_agent_interval_minutes()
    thread = threading.Thread(
        target=_contact_agent_loop,
        args=(interval,),
        daemon=True,
    )
    thread.start()
    print(f"[CONTACT Agent] Started (runs every {interval} min)")
