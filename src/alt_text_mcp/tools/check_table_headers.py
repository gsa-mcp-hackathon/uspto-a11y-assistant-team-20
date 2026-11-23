"""check_table_headers — audit a web page's data tables for header cells."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckTableHeadersInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def register(mcp: FastMCP) -> None:
    """Register the check_table_headers tool with the MCP server."""

    @mcp.tool(
        name="check_table_headers",
        annotations={
            "title": "Check a Page's Table Header Cells",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_table_headers(params: CheckTableHeadersInput) -> dict[str, Any]:
        """Scan one page's data tables for programmatically associated headers.

        Fetches the page as static HTML — no JavaScript execution. A screen
        reader announces a data cell's row/column header on request via
        <th>/scope (or headers/id) associations; a table with no <th> at
        all, or ambiguous headers in a multi-dimensional table, reads as a
        flat wall of unlabeled numbers to a non-sighted user even though a
        sighted user can visually trace the header row/column.

        For each <table>, in document order:
          - "no-th" if the table has no <th> cells at all.
          - "missing-caption" if the table has no <caption>, checked
            regardless of whether it has <th> cells.
          - "th-missing-scope" if the table has more than 2 rows (treated
            as "multi-dimensional" — likely a header row plus several data
            rows, where the row/column association isn't obvious from
            markup alone) and at least one <th> lacks a scope attribute.

        This heuristic can't distinguish a real data table from a purely
        visual/layout table (a <table> used just for page layout), so a
        "no-th" flag can be a false positive for layout-only tables — a
        known, named limitation of static-HTML analysis.

        Args:
            params: The page URL to scan and a max-tables limit.

        Returns:
            {"url", "totalTablesOnPage", "tablesReturned", "tables": [...],
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
        all_tables = soup.find_all("table")

        tables = []
        for index, table in enumerate(all_tables[: params.limit]):
            rows = table.find_all("tr")
            row_count = len(rows)
            has_th = table.find("th") is not None
            has_caption = table.find("caption") is not None
            multi_dimensional = row_count > 2

            issues = []
            if not has_th:
                issues.append("no-th")
            if not has_caption:
                issues.append("missing-caption")
            if multi_dimensional and has_th:
                ths_missing_scope = [
                    th for th in table.find_all("th") if not th.get("scope")
                ]
                if ths_missing_scope:
                    issues.append("th-missing-scope")

            tables.append(
                {
                    "index": index,
                    "rows": row_count,
                    "hasTh": has_th,
                    "hasCaption": has_caption,
                    "issues": issues,
                }
            )

        summary = {
            "tablesWithNoTh": sum(1 for t in tables if "no-th" in t["issues"]),
            "tablesMissingCaption": sum(
                1 for t in tables if "missing-caption" in t["issues"]
            ),
            "tablesWithScopeIssues": sum(
                1 for t in tables if "th-missing-scope" in t["issues"]
            ),
        }

        return {
            "url": params.url,
            "totalTablesOnPage": len(all_tables),
            "tablesReturned": len(tables),
            "tables": tables,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. This cannot distinguish a real data table from a "
                'purely visual layout table, so a "no-th" flag may be a '
                "false positive for layout-only tables. Tables injected by "
                "client-side JS are not seen."
            ),
        }
