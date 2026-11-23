"""check_link_text — audit a web page's links for non-descriptive text."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckLinkTextInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_GENERIC_PHRASES = {
    "click here",
    "here",
    "read more",
    "more",
    "learn more",
    "link",
    "this link",
    "this page",
    "go",
    "continue reading",
    "details",
}
_BARE_URL = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)


def _classify_link(text: str, has_accessible_name: bool) -> dict[str, Any]:
    normalized = text.strip().lower()
    if not text.strip():
        if has_accessible_name:
            return {"status": "empty-text-with-label", "issues": []}
        return {
            "status": "empty",
            "issues": ["no link text and no aria-label/aria-labelledby/title"],
        }
    issues = []
    if normalized in _GENERIC_PHRASES:
        issues.append(f'generic, non-descriptive link text ("{text.strip()}")')
    if _BARE_URL.match(text.strip()):
        issues.append("link text is a raw URL, not a description")
    return {"status": "present", "issues": issues}


def register(mcp: FastMCP) -> None:
    """Register the check_link_text tool with the MCP server."""

    @mcp.tool(
        name="check_link_text",
        annotations={
            "title": "Check a Page's Link Text",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_link_text(params: CheckLinkTextInput) -> dict[str, Any]:
        """Scan one page's <a> tags for non-descriptive or missing link text.

        Fetches the page as static HTML — no JavaScript execution. Screen
        reader users often navigate by jumping link-to-link out of context,
        so "click here" or a bare URL as the only text is a real barrier.

        Classifies each link:
          - "empty": no visible text and no aria-label/aria-labelledby/title.
          - "empty-text-with-label": no visible text, but an accessible name
            is present via aria-label/aria-labelledby/title — commonly a
            valid icon-only button pattern, flagged only for awareness.
          - "present": has visible text; checked for generic filler phrases
            ("click here", "read more", etc.) and raw-URL-as-text.

        Args:
            params: The page URL to scan and a max-links limit.

        Returns:
            {"url", "totalLinksOnPage", "links": [...], "summary": {...},
            "disclaimer"}. Or an error dict with a hint.
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
        all_links = soup.find_all("a", href=True)
        links = []
        for a in all_links[: params.limit]:
            text = a.get_text(strip=True)
            accessible_name = (
                a.get("aria-label") or a.get("aria-labelledby") or a.get("title")
            )
            classification = _classify_link(text, bool(accessible_name))
            links.append(
                {
                    "href": urljoin(params.url, a["href"]),
                    "text": text or None,
                    "status": classification["status"],
                    "issues": classification["issues"],
                }
            )

        summary = {
            "empty": sum(1 for link in links if link["status"] == "empty"),
            "emptyWithLabel": sum(
                1 for link in links if link["status"] == "empty-text-with-label"
            ),
            "presentWithIssues": sum(
                1 for link in links if link["status"] == "present" and link["issues"]
            ),
            "presentClean": sum(
                1
                for link in links
                if link["status"] == "present" and not link["issues"]
            ),
        }

        return {
            "url": params.url,
            "totalLinksOnPage": len(all_links),
            "linksReturned": len(links),
            "links": links,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Links injected by client-side JS are not seen."
            ),
        }
