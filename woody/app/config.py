"""Configuration loader for woody."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env: woody/ first, then repo root (root fills in shared keys like OPENAI_API_KEY)
_root = Path(__file__).resolve().parent.parent.parent
for p in [Path(__file__).resolve().parent.parent / ".env", _root / ".env"]:
    if p.exists():
        load_dotenv(p, override=True)


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
    return Path(_get("APP_DB_PATH", "./app.db"))


def get_sandbox_dir() -> Path:
    return Path(_get("FILES_SANDBOX_DIR", "./sandbox_files"))
