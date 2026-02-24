"""Single source of truth for Woody DB path. Used by Woody, dashboard, and shared agents."""

import os
from pathlib import Path

_root = Path(__file__).resolve().parent.parent

# Docker: working_dir is /app, volume mounts repo there. ALWAYS use /app/woody/app.db.
# This overrides .env host paths that don't exist in container.
_DOCKER_DB = Path("/app/woody/app.db")


def get_woody_db_path() -> Path:
    """Return the Woody SQLite DB path. Woody and dashboard must use this same path."""
    if Path("/app").exists():
        return _DOCKER_DB.resolve()
    default = _root / "woody" / "app.db"
    path = os.environ.get("WOODY_DB_PATH") or os.environ.get("APP_DB_PATH") or str(default)
    p = Path(path)
    if not p.is_absolute():
        p = (_root / path).resolve()
    else:
        p = p.resolve()
    return p
