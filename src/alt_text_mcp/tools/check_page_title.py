"""check_page_title — audit a web page's <title> element."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckPageTitleInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_GENERIC_TITLES = {
    "untitled document",
    "untitled",
    "document",
    "new page",
    "home",
    "home page",
    "page title",
    "index",
    "index.html",
    "page",
}


def register(mcp: FastMCP) -> None:
    """Register the check_page_title tool with the MCP server."""

    @mcp.tool(
        name="check_page_title",
        annotations={
            "title": "Check a Page's <title> Element",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_page_title(params: CheckPageTitleInput) -> dict[str, Any]:
        """Scan one page's <title> element and flag missing/empty/generic titles.

        Fetches the page as static HTML — no JavaScript execution. The
        <title> is the very first thing a screen reader announces when a
        page loads or when switching browser tabs — it's how a non-sighted
        user confirms they landed on the right page or distinguishes
        between open tabs. A missing, empty, or generic title ("Untitled
        Document", "Home") gives no such confirmation, even though a
        sighted user can just glance at page content to orient themselves.

        Flags:
          - "missing": the page has no <title> element at all.
          - "empty": a <title> element exists but has no text content.
          - generic title: the title text matches a common non-descriptive
            placeholder (e.g. "Untitled Document", "Home", "Index").

        Args:
            params: The page URL to scan.

        Returns:
            {"url", "title", "status", "issues", "disclaimer"}. Or an
            error dict with a hint.
        """
        try:
            html = await fetch_text_safely(params.url)
        except BlockedUrlError as exc:
            return {
                "error": str(exc),
                "hint": "Only public http(s) URLs outside private ranges are allowed.",
            }
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "Check the URL is reachable and returns HTML.",
            }

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        text = title_tag.get_text(strip=True) if title_tag else ""

        issues: list[str] = []
        if title_tag is None:
            status = "missing"
            issues.append("no <title> element on the page")
        elif text == "":
            status = "empty"
            issues.append("<title> element is present but empty")
        else:
            status = "present"
            if text.strip().lower() in _GENERIC_TITLES:
                issues.append(f'generic, non-descriptive page title ("{text}")')

        return {
            "url": params.url,
            "title": text or None,
            "status": status,
            "issues": issues,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. A title set via client-side JS (e.g. document.title "
                "in an SPA) is not seen."
            ),
        }
