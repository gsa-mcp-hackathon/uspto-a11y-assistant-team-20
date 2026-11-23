"""check_heading_structure — audit a web page's heading (h1-h6) outline."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckHeadingStructureInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def register(mcp: FastMCP) -> None:
    """Register the check_heading_structure tool with the MCP server."""

    @mcp.tool(
        name="check_heading_structure",
        annotations={
            "title": "Check a Page's Heading Structure",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_heading_structure(
        params: CheckHeadingStructureInput,
    ) -> dict[str, Any]:
        """Scan one page's h1-h6 tags and flag heading-outline problems.

        Fetches the page as static HTML — no JavaScript execution. Screen
        reader users commonly navigate by jumping between headings, so a
        broken outline (skipped levels, no h1, multiple h1s) makes a page
        much harder to scan non-visually, even though it looks fine
        rendered.

        Flags, page-wide:
          - "no-h1": the page has no <h1>.
          - "multiple-h1": the page has more than one <h1>.
        Flags, per heading:
          - "empty": the heading has no text content.
          - "skipped-level": this heading jumps more than one level deeper
            than the previous heading (e.g. h2 directly to h4).

        Args:
            params: The page URL to scan.

        Returns:
            {"url", "outline": [...], "issues": [...], "summary": {...},
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
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

        outline = []
        issues = []
        previous_level = None
        for heading in headings:
            level = int(heading.name[1])
            text = heading.get_text(strip=True)
            heading_issues = []
            if not text:
                heading_issues.append("empty heading — no text content")
            if previous_level is not None and level > previous_level + 1:
                heading_issues.append(
                    f"skipped level — jumps from h{previous_level} to h{level}"
                )
            outline.append(
                {"level": level, "text": text or None, "issues": heading_issues}
            )
            issues.extend(
                f'h{level} "{text or "(empty)"}": {issue}' for issue in heading_issues
            )
            previous_level = level

        h1_count = sum(1 for h in outline if h["level"] == 1)
        if h1_count == 0:
            issues.insert(0, "no-h1: page has no <h1>")
        elif h1_count > 1:
            issues.insert(0, f"multiple-h1: page has {h1_count} <h1> elements")

        summary = {
            "totalHeadings": len(outline),
            "h1Count": h1_count,
            "skippedLevels": sum(
                1 for h in outline if any("skipped level" in i for i in h["issues"])
            ),
            "emptyHeadings": sum(
                1 for h in outline if any("empty heading" in i for i in h["issues"])
            ),
        }

        return {
            "url": params.url,
            "outline": outline,
            "issues": issues,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Headings injected by client-side JS are not seen."
            ),
        }
