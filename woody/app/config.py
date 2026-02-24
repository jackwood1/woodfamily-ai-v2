"""Configuration loader for woody."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env: woody/ first, then repo root (root fills in shared keys like OPENAI_API_KEY)
# Use override=False for WOODY_DB_PATH so docker-compose env wins (both services share same DB)
_root = Path(__file__).resolve().parent.parent.parent
_woody_db = os.environ.get("WOODY_DB_PATH")
for p in [Path(__file__).resolve().parent.parent / ".env", _root / ".env"]:
    if p.exists():
        load_dotenv(p, override=True)
if _woody_db is not None:
    os.environ["WOODY_DB_PATH"] = _woody_db  # Restore so container path is preserved


def _get(key: str, default: Optional[str] = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise ValueError(f"Missing required env var: {key}")
    return val


def get_telegram_token() -> str:
    return _get("TELEGRAM_BOT_TOKEN")


def get_openai_key() -> str:
    return _get("OPENAI_API_KEY")


def get_db_path() -> Path:
    # Use shared module so Woody and dashboard always use same DB (fixes "Unknown approval ID")
    import sys
    from pathlib import Path
    _repo = Path(__file__).resolve().parent.parent.parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    from shared.db_path import get_woody_db_path
    return get_woody_db_path()


def get_sandbox_dir() -> Path:
    return Path(_get("FILES_SANDBOX_DIR", "./sandbox_files"))
