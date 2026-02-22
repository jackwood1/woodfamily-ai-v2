"""Shared Google OAuth token storage."""

import json
import os
from pathlib import Path
from typing import Optional

# Default: repo root .google_tokens.json
_default = Path(__file__).resolve().parent.parent / ".google_tokens.json"
TOKENS_PATH = Path(os.environ.get("GOOGLE_TOKENS_PATH", str(_default)))


def load_tokens() -> Optional[dict]:
    if not TOKENS_PATH.exists():
        return None
    try:
        return json.loads(TOKENS_PATH.read_text())
    except Exception:
        return None


def save_tokens(tokens: dict) -> None:
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))


def has_valid_tokens() -> bool:
    t = load_tokens()
    return t is not None and "refresh_token" in t


def clear_tokens() -> bool:
    """Remove stored tokens (disconnect). Returns True if tokens were cleared."""
    if not TOKENS_PATH.exists():
        return False
    try:
        TOKENS_PATH.unlink()
        return True
    except Exception:
        return False


def get_credentials():
    """
    Return Google Credentials that persist refreshed tokens to disk.
    Use this instead of constructing Credentials directly.
    Returns (creds, error_msg) - error_msg is None on success.
    """
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None, "Google API libraries not installed"

    t = load_tokens()
    if not t or "refresh_token" not in t:
        return None, "Google not connected. Complete OAuth at dashboard /integrations"

    class PersistingCredentials(Credentials):
        """Credentials that save refreshed tokens to disk."""

        def refresh(self, request):
            super().refresh(request)
            updated = dict(t)
            updated["token"] = self.token
            if self.expiry:
                updated["expiry"] = self.expiry.isoformat()
            save_tokens(updated)

    creds = PersistingCredentials(
        token=t.get("token"),
        refresh_token=t.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=t.get("client_id"),
        client_secret=t.get("client_secret"),
    )
    if t.get("expiry"):
        from datetime import datetime
        try:
            creds.expiry = datetime.fromisoformat(t["expiry"].replace("Z", "+00:00"))
        except Exception:
            pass
    return creds, None
