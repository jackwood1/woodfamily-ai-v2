"""GitHub tools - uses GITHUB_TOKEN from env."""

import os
from typing import Any, Optional

import httpx

from app.tools.registry import PermissionTier, ToolDef, register


def _get_token() -> Optional[str]:
    return os.environ.get("GITHUB_TOKEN", "").strip() or None


def _api_get(path: str, params: Optional[dict] = None) -> dict:
    token = _get_token()
    if not token:
        return {"error": "GITHUB_TOKEN not set. Add it to .env"}
    url = f"https://api.github.com{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                url,
                params=params or {},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            return {"error": "GitHub: Invalid or expired token. Check GITHUB_TOKEN in .env"}
        if code == 404:
            return {"error": "GitHub: Not found. Check repo name, owner, or PR/issue number."}
        if code == 403:
            return {"error": "GitHub: Access denied or rate limited. Try again later."}
        if code >= 500:
            return {"error": "GitHub API is down. Try again later."}
        return {"error": f"GitHub API error {code}: {e.response.reason_phrase}"}
    except httpx.ConnectError:
        return {"error": "GitHub: Connection failed. Check your network."}
    except httpx.TimeoutException:
        return {"error": "GitHub: Request timed out. Try again."}
    except Exception as e:
        return {"error": f"GitHub error: {e}"}


def _api_post(path: str, json_body: dict) -> dict:
    token = _get_token()
    if not token:
        return {"error": "GITHUB_TOKEN not set. Add it to .env"}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"https://api.github.com{path}",
                json=json_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            return {"error": "GitHub: Invalid or expired token. Check GITHUB_TOKEN in .env"}
        if code == 404:
            return {"error": "GitHub: Not found. Check repo name, owner, or issue number."}
        if code == 403:
            return {"error": "GitHub: Access denied or rate limited. Try again later."}
        if code >= 500:
            return {"error": "GitHub API is down. Try again later."}
        return {"error": f"GitHub API error {code}: {e.response.reason_phrase}"}
    except httpx.ConnectError:
        return {"error": "GitHub: Connection failed. Check your network."}
    except httpx.TimeoutException:
        return {"error": "GitHub: Request timed out. Try again."}
    except Exception as e:
        return {"error": f"GitHub error: {e}"}


def _github_pr_summary_handler(owner: str, repo: str, pr_number: int) -> str:
    data = _api_get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
    if "error" in data:
        return data["error"]
    return f"PR #{pr_number}: {data.get('title', '')}\nState: {data.get('state')}\nBody: {(data.get('body') or '')[:500]}"


def _github_create_issue_handler(owner: str, repo: str, title: str, body: str = "") -> str:
    data = _api_post(f"/repos/{owner}/{repo}/issues", {"title": title, "body": body or ""})
    if "error" in data:
        return data["error"]
    return f"Created issue #{data.get('number')}: {data.get('html_url', '')}"


def _github_comment_pr_handler(owner: str, repo: str, pr_number: int, body: str) -> str:
    data = _api_post(
        f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
        {"body": body},
    )
    if "error" in data:
        return data["error"]
    return f"Posted comment on PR #{pr_number}"


register(
    ToolDef(
        name="github_pr_summary",
        description="Get summary of a GitHub pull request",
        parameters={
            "properties": {
                "owner": {"type": "string", "description": "Repo owner"},
                "repo": {"type": "string", "description": "Repo name"},
                "pr_number": {"type": "integer", "description": "PR number"},
            },
            "required": ["owner", "repo", "pr_number"],
        },
        handler=_github_pr_summary_handler,
        tier=PermissionTier.GREEN,
    )
)

register(
    ToolDef(
        name="github_create_issue",
        description="Create a GitHub issue",
        parameters={
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["owner", "repo", "title"],
        },
        handler=_github_create_issue_handler,
        tier=PermissionTier.YELLOW,
    )
)

register(
    ToolDef(
        name="github_comment_pr",
        description="Comment on a GitHub pull request",
        parameters={
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["owner", "repo", "pr_number", "body"],
        },
        handler=_github_comment_pr_handler,
        tier=PermissionTier.YELLOW,
    )
)
