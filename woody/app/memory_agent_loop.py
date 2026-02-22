"""Nightly memory agent loop - proposes memory changes for user approval."""

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


def _memory_agent_hour_utc() -> int:
    try:
        return int(os.environ.get("MEMORY_AGENT_HOUR_UTC", "3"))  # 3 AM UTC
    except ValueError:
        return 3


def _run_memory_agent_once(db_path: Path) -> bool:
    """Run memory agent if not already run today. Returns True if ran."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM memory_agent_run WHERE run_date = ?",
            (today,),
        ).fetchone()
        if row:
            return False
    finally:
        conn.close()

    try:
        from shared.memory_agent import run_memory_agent
        summary = run_memory_agent(db_path)
        total = sum(summary.values())
        if total > 0:
            print(f"[Memory Agent] Proposed {total} changes: {summary}")
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("INSERT OR IGNORE INTO memory_agent_run (run_date) VALUES (?)", (today,))
            conn.commit()
        finally:
            conn.close()
        return total > 0
    except Exception as e:
        print(f"[Memory Agent] Error: {e}")
        return False


def _memory_agent_loop(db_path: Path, hour_utc: int, interval_minutes: int = 60) -> None:
    """Check every interval_minutes; run at hour_utc if we haven't today."""
    last_run_date = ""
    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            if now.hour == hour_utc and last_run_date != today:
                if _run_memory_agent_once(db_path):
                    last_run_date = today
        except Exception as e:
            print(f"[Memory Agent] Loop error: {e}")
        time.sleep(interval_minutes * 60)


def start_memory_agent_loop(db_path: Path) -> None:
    """Start memory agent loop in a daemon thread."""
    hour = _memory_agent_hour_utc()
    thread = threading.Thread(
        target=_memory_agent_loop,
        args=(db_path, hour),
        kwargs={"interval_minutes": 60},
        daemon=True,
    )
    thread.start()
    print(f"[Memory Agent] Started (runs at {hour}:00 UTC)")
