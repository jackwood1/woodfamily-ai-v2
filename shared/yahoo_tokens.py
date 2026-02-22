"""Shared Yahoo OAuth token storage for Yahoo Mail (IMAP/SMTP via XOAUTH2)."""

import json
import os
from pathlib import Path
from typing import Optional, Tuple

# Default: repo root .yahoo_tokens.json
_default = Path(__file__).resolve().parent.parent / ".yahoo_tokens.json"
TOKENS_PATH = Path(os.environ.get("YAHOO_TOKENS_PATH", str(_default)))


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


def get_access_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Return a valid access token, refreshing if needed.
    Returns (access_token, error_msg). error_msg is None on success.
    """
    t = load_tokens()
    if not t or "refresh_token" not in t:
        return None, "Yahoo not connected. Complete OAuth at dashboard /integrations"

    client_id = t.get("client_id") or os.environ.get("YAHOO_CLIENT_ID", "").strip()
    client_secret = t.get("client_secret") or os.environ.get("YAHOO_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None, "YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET required"

    # Check if we have a valid (non-expired) access token
    import time
    expires_at = t.get("expires_at")
    if expires_at and time.time() < expires_at - 60:  # 60s buffer
        return t.get("token"), None

    # Refresh the token
    try:
        import httpx
        resp = httpx.post(
            "https://api.login.yahoo.com/oauth2/get_token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": t["refresh_token"],
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            return None, "No access_token in Yahoo refresh response"

        expires_in = int(data.get("expires_in", 3600))
        updated = dict(t)
        updated["token"] = access_token
        updated["expires_at"] = time.time() + expires_in
        if data.get("refresh_token"):
            updated["refresh_token"] = data["refresh_token"]
        save_tokens(updated)
        return access_token, None
    except Exception as e:
        err = str(e).lower()
        if "invalid_grant" in err or "401" in err or "400" in err:
            return None, "Yahoo token expired. Reconnect Yahoo in dashboard."
        return None, str(e)
