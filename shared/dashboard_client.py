"""Client for dashboard API. Used by Woody tools."""

from __future__ import annotations

import base64
import os
from typing import Any, Optional

import httpx


def _get_base_url() -> str:
    return (os.environ.get("DASHBOARD_URL") or "http://localhost:8000").rstrip("/")


def _get_auth_headers() -> dict[str, str]:
    user = os.environ.get("DASHBOARD_USER", "").strip()
    passwd = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    if not user or not passwd:
        return {}
    creds = base64.b64encode(f"{user}:{passwd}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def dashboard_request(
    method: str,
    path: str,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """Call dashboard API. Returns (data, error)."""
    url = f"{_get_base_url()}{path}"
    headers = _get_auth_headers()
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.request(method, url, json=json, params=params, headers=headers)
            if r.status_code >= 400:
                return None, f"Dashboard: {r.status_code} {r.text[:200]}"
            return r.json() if r.content else {}, None
    except Exception as e:
        return None, str(e)
