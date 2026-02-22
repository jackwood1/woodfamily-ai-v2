"""Web research tools - fetch and summarize URLs."""

from app.tools.registry import PermissionTier, ToolDef, register

try:
    import httpx
except ImportError:
    httpx = None


def _web_fetch_handler(url: str) -> str:
    """Fetch a URL and return text content (truncated)."""
    if not httpx:
        return "httpx not installed"
    if not url.startswith(("http://", "https://")):
        return "Invalid URL: must start with http:// or https://"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            text = r.text
            if len(text) > 8000:
                text = text[:8000] + "\n\n... (truncated)"
            return text
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 404:
            return "URL not found (404). The page may have been removed."
        if code in (401, 403):
            return "Access denied. The page may require login or block automated access."
        if code >= 500:
            return f"Server error ({code}). The site may be down—try again later."
        return f"HTTP {code}: {e.response.reason_phrase}"
    except httpx.ConnectError as e:
        return "Connection failed. The site may be down or unreachable."
    except httpx.TimeoutException:
        return "Request timed out. The site may be slow or unresponsive."
    except Exception as e:
        return f"Error fetching URL: {e}"


register(
    ToolDef(
        name="web_fetch",
        description="Fetch the text content of a URL for research. Use for reading web pages.",
        parameters={
            "properties": {"url": {"type": "string", "description": "URL to fetch (http or https)"}},
            "required": ["url"],
        },
        handler=_web_fetch_handler,
        tier=PermissionTier.GREEN,
    )
)
