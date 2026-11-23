"""check_duplicate_ids — audit a web page for elements sharing an id value."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckDuplicateIdsInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def register(mcp: FastMCP) -> None:
    """Register the check_duplicate_ids tool with the MCP server."""

    @mcp.tool(
        name="check_duplicate_ids",
        annotations={
            "title": "Check a Page for Duplicate Element IDs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_duplicate_ids(
        params: CheckDuplicateIdsInput,
    ) -> dict[str, Any]:
        """Scan one page's elements and flag id attribute values reused more than once.

        Fetches the page as static HTML — no JavaScript execution. Duplicate
        ids break `<label for="...">`, `aria-labelledby`, `aria-describedby`,
        and `href="#id"` fragment navigation, because `getElementById`-style
        lookups and assistive tech only ever resolve the first matching
        element — every subsequent element sharing that id becomes
        unreachable or mislabeled for screen reader users, even though the
        page can look and behave fine visually.

        Elements with an empty or whitespace-only id attribute are ignored.

        Args:
            params: The page URL to scan, and the maximum number of
                duplicate id groups to return.

        Returns:
            {"url", "totalIdsOnPage", "uniqueIds", "duplicateIds": [...],
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
        elements = [el for el in soup.find_all(id=True) if el.get("id", "").strip()]

        groups: dict[str, list[str]] = {}
        for el in elements:
            id_value = el["id"].strip()
            groups.setdefault(id_value, []).append(el.name)

        all_duplicate_ids = [
            {"id": id_value, "count": len(tags), "elements": tags}
            for id_value, tags in groups.items()
            if len(tags) >= 2
        ]
        duplicate_ids = all_duplicate_ids[: params.limit]

        summary = {
            "duplicateGroups": len(all_duplicate_ids),
            "duplicateElements": sum(group["count"] for group in all_duplicate_ids),
        }

        return {
            "url": params.url,
            "totalIdsOnPage": len(elements),
            "uniqueIds": len(groups),
            "duplicateIds": duplicate_ids,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Elements injected by client-side JS are not seen."
            ),
        }
