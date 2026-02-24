#!/usr/bin/env python3
"""Purge all pending approvals from the Woody database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.db_path import get_woody_db_path


def main():
    db_path = get_woody_db_path()
    if not db_path.exists():
        print(f"Woody database not found: {db_path}")
        sys.exit(1)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("DELETE FROM approvals WHERE status = 'pending'")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"Purged {deleted} pending approval(s) from {db_path}")


if __name__ == "__main__":
    main()
