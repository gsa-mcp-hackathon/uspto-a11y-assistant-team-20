"""check_landmarks — audit a web page's ARIA landmarks and skip-navigation link."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckLandmarksInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_SKIP_LINK_PHRASES = {
    "skip to main content",
    "skip to content",
    "skip navigation",
    "skip nav",
    "skip to main",
    "skip links",
}


def _count_landmarks(soup: BeautifulSoup, tag: str, role: str) -> int:
    """Count elements matching a landmark tag or explicit role, deduped."""
    elements = soup.find_all([tag]) + soup.find_all(attrs={"role": role})
    return len({id(element) for element in elements})


def _find_skip_link(soup: BeautifulSoup) -> tuple[bool, str | None]:
    """Return (has_skip_link, skip_link_text) for the first matching <a href>."""
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        lowered = text.lower()
        if lowered in _SKIP_LINK_PHRASES:
            return True, text
        if "skip" in lowered and (
            "content" in lowered or "main" in lowered or "navigation" in lowered
        ):
            return True, text
    return False, None


def register(mcp: FastMCP) -> None:
    """Register the check_landmarks tool with the MCP server."""

    @mcp.tool(
        name="check_landmarks",
        annotations={
            "title": "Check a Page's ARIA Landmarks and Skip Link",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_landmarks(params: CheckLandmarksInput) -> dict[str, Any]:
        """Scan one page's ARIA landmarks and skip-navigation link.

        Fetches the page as static HTML — no JavaScript execution. Screen
        reader users jump between landmarks (main, nav, header, footer) the
        way sighted users scan a page visually, so missing or duplicated
        landmarks, and the absence of a skip-to-content link, make a page
        much harder to navigate non-visually, even though it looks fine
        rendered.

        Flags, page-wide:
          - "no-main": the page has no <main> landmark (or role="main").
          - "multiple-main": the page has more than one <main> landmark
            (or role="main").
          - "no-skip-link": no skip-to-content link was found.

        Args:
            params: The page URL to scan.

        Returns:
            {"url", "landmarks": {...}, "hasSkipLink", "skipLinkText",
            "issues": [...], "summary": {...}, "disclaimer"}. Or an error
            dict with a hint.
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

        main_count = _count_landmarks(soup, "main", "main")
        nav_count = _count_landmarks(soup, "nav", "navigation")
        header_count = _count_landmarks(soup, "header", "banner")
        footer_count = _count_landmarks(soup, "footer", "contentinfo")
        has_skip_link, skip_link_text = _find_skip_link(soup)

        issues = []
        if main_count == 0:
            issues.append('no-main: page has no <main> landmark (or role="main")')
        elif main_count > 1:
            issues.append(
                f"multiple-main: page has {main_count} <main> landmarks "
                '(or role="main")'
            )
        if not has_skip_link:
            issues.append("no-skip-link: no skip-to-content link found")

        return {
            "url": params.url,
            "landmarks": {
                "main": main_count,
                "nav": nav_count,
                "header": header_count,
                "footer": footer_count,
            },
            "hasSkipLink": has_skip_link,
            "skipLinkText": skip_link_text,
            "issues": issues,
            "summary": {"mainCount": main_count, "hasSkipLink": has_skip_link},
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Landmarks injected by client-side JS are not seen."
            ),
        }
