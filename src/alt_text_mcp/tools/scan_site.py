"""scan_site — crawl a page's same-origin links and scan each for alt-text issues."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import ScanSiteInput
from alt_text_mcp.tools.scan_alt_text import scan_images_in_html
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def _discover_same_origin_links(start_url: str, html: str) -> list[str]:
    origin = urlsplit(start_url)._replace(path="", query="", fragment="").geturl()
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        absolute = urljoin(start_url, a["href"])
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        link_origin = parts._replace(path="", query="", fragment="").geturl()
        if link_origin != origin:
            continue
        normalized = parts._replace(fragment="").geturl()
        if normalized != start_url:
            seen.setdefault(normalized, None)
    return list(seen)


def register(mcp: FastMCP) -> None:
    """Register the scan_site tool with the MCP server."""

    @mcp.tool(
        name="scan_site",
        annotations={
            "title": "Scan a Site for Alt-Text Issues",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def scan_site(params: ScanSiteInput) -> dict[str, Any]:
        """Scan a start page plus its same-origin linked pages for alt-text issues.

        Fetches the start page, discovers <a href> links that point at the
        same scheme+host+port, then runs the same alt-text scan as
        scan_page_alt_text on the start page and each discovered link, up to
        max_pages total. Stops discovering new pages once that cap is hit —
        it does not recurse into links found on the linked pages themselves
        (one level deep from the start page only).

        Useful for an agency site where the same template (missing alt on a
        shared header image, for example) repeats across many pages — this
        surfaces that in one call instead of one scan_page_alt_text call per
        page.

        Args:
            params: The starting page URL, a max-pages cap, and a
                max-images-per-page limit.

        Returns:
            {"startUrl", "pagesScanned": [...], "pagesSkipped": [...],
            "summary": {...}, "disclaimer"}. Or an error dict with a hint,
            if the start page itself can't be fetched.
        """
        try:
            start_html = await fetch_text_safely(params.url)
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

        candidate_links = _discover_same_origin_links(params.url, start_html)
        urls_to_scan = [params.url, *candidate_links][: params.max_pages]
        skipped_links = candidate_links[max(0, params.max_pages - 1) :]

        pages = [
            {
                "url": params.url,
                **scan_images_in_html(params.url, start_html, params.limit_per_page),
            }
        ]
        for page_url in urls_to_scan[1:]:
            try:
                html = await fetch_text_safely(page_url)
            except BlockedUrlError as exc:
                pages.append({"url": page_url, "error": str(exc)})
                continue
            except UpstreamServiceError as exc:
                pages.append({"url": page_url, "error": str(exc)})
                continue
            pages.append(
                {
                    "url": page_url,
                    **scan_images_in_html(page_url, html, params.limit_per_page),
                }
            )

        scanned_pages = [p for p in pages if "error" not in p]
        summary = {
            "pagesScanned": len(scanned_pages),
            "pagesFailed": len(pages) - len(scanned_pages),
            "totalMissing": sum(p["summary"]["missing"] for p in scanned_pages),
            "totalPresentWithIssues": sum(
                p["summary"]["presentWithIssues"] for p in scanned_pages
            ),
        }

        return {
            "startUrl": params.url,
            "pages": pages,
            "pagesSkipped": skipped_links,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Only same-origin links found directly on the start "
                "page are followed (one level deep); links injected by "
                "client-side JS are not seen."
            ),
        }
