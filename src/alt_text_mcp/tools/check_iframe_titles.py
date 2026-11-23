"""check_iframe_titles — audit a web page's iframes for a title attribute."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckIframeTitlesInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def register(mcp: FastMCP) -> None:
    """Register the check_iframe_titles tool with the MCP server."""

    @mcp.tool(
        name="check_iframe_titles",
        annotations={
            "title": "Check a Page's Iframe Titles",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_iframe_titles(params: CheckIframeTitlesInput) -> dict[str, Any]:
        """Scan one page's iframes for a descriptive title attribute.

        Fetches the page as static HTML — no JavaScript execution. A screen
        reader announces an <iframe> by its title attribute (e.g. "YouTube
        video player, iframe") so a user knows what the embedded content is
        before deciding whether to enter it. Without one, every iframe is
        announced as a generic, indistinguishable "iframe."

        Checks each <iframe> for a non-empty title attribute. Flags
        "missing" if the attribute is absent or contains only whitespace.

        Args:
            params: The page URL to scan and a max-iframes limit.

        Returns:
            {"url", "totalIframesOnPage", "iframesReturned", "iframes": [...],
            "summary": {...}, "disclaimer"}. Or an error dict with a hint.
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
        all_iframes = soup.find_all("iframe")

        iframes = []
        for iframe in all_iframes[: params.limit]:
            title = iframe.get("title")
            if title is None or title.strip() == "":
                status = "missing"
                issues = ["no title attribute on <iframe>"]
            else:
                status = "present"
                issues = []

            iframes.append(
                {
                    "src": iframe.get("src"),
                    "status": status,
                    "issues": issues,
                }
            )

        summary = {
            "present": sum(1 for f in iframes if f["status"] == "present"),
            "missing": sum(1 for f in iframes if f["status"] == "missing"),
        }

        return {
            "url": params.url,
            "totalIframesOnPage": len(all_iframes),
            "iframesReturned": len(iframes),
            "iframes": iframes,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Iframes injected by client-side JS are not seen."
            ),
        }
