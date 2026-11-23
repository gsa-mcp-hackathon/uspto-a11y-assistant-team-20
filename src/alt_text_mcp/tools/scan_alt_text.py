"""scan_page_alt_text — audit a web page's images for missing/low-quality alt text."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import ScanPageInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_FILENAME_ALT = re.compile(
    r"\.(jpe?g|png|gif|webp|svg|bmp|tiff?)(\?.*)?$", re.IGNORECASE
)
_GENERIC_PREFIX = re.compile(r"^\s*(image|picture|photo|img)\s+of\b", re.IGNORECASE)
_MAX_ALT_LENGTH = 125  # WCAG guidance: keep alt text concise.


def _classify_alt(alt: str | None, role: str | None) -> dict[str, Any]:
    if alt is None:
        return {"status": "missing", "issues": ["no alt attribute present"]}
    if alt == "" or (role or "").lower() == "presentation":
        return {"status": "empty-decorative", "issues": []}

    issues = []
    if _FILENAME_ALT.search(alt):
        issues.append("looks like a filename, not a description")
    if _GENERIC_PREFIX.match(alt):
        issues.append('starts with a generic phrase ("image of"/"picture of"/etc.)')
    if len(alt) > _MAX_ALT_LENGTH:
        issues.append(
            f"longer than {_MAX_ALT_LENGTH} characters — WCAG guidance: be concise"
        )
    return {"status": "present", "issues": issues}


def scan_images_in_html(page_url: str, html: str, limit: int) -> dict[str, Any]:
    """Parse `html` for <img> tags and classify each one's alt text.

    Pure parsing logic shared by scan_page_alt_text and scan_site — the only
    difference between callers is how the HTML was obtained.
    """
    soup = BeautifulSoup(html, "html.parser")
    all_imgs = soup.find_all("img")
    images = []
    for img in all_imgs[:limit]:
        src = img.get("src")
        absolute_src = urljoin(page_url, src) if src else None
        alt = img.get("alt")
        classification = _classify_alt(alt, img.get("role"))
        figure = img.find_parent("figure")
        caption = figure.find("figcaption") if figure else None
        images.append(
            {
                "src": absolute_src,
                "alt": alt,
                "status": classification["status"],
                "issues": classification["issues"],
                "nearbyCaption": caption.get_text(strip=True) if caption else None,
            }
        )

    summary = {
        "missing": sum(1 for i in images if i["status"] == "missing"),
        "emptyDecorative": sum(1 for i in images if i["status"] == "empty-decorative"),
        "presentWithIssues": sum(
            1 for i in images if i["status"] == "present" and i["issues"]
        ),
        "presentClean": sum(
            1 for i in images if i["status"] == "present" and not i["issues"]
        ),
    }

    return {
        "totalImagesOnPage": len(all_imgs),
        "imagesReturned": len(images),
        "images": images,
        "summary": summary,
    }


def register(mcp: FastMCP) -> None:
    """Register the scan_page_alt_text tool with the MCP server."""

    @mcp.tool(
        name="scan_page_alt_text",
        annotations={
            "title": "Scan a Page for Alt-Text Issues",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def scan_page_alt_text(params: ScanPageInput) -> dict[str, Any]:
        """Scan one page's <img> tags for missing, empty, or low-quality alt text.

        Fetches the page as static HTML — no JavaScript execution — and
        parses every <img> tag. Images injected by client-side JS (common
        on single-page apps) are not seen; a named limitation, not a
        silent gap.

        Classifies each image:
          - "missing": no alt attribute at all (a real accessibility bug).
          - "empty-decorative": alt="" or role="presentation" — valid for
            genuinely decorative images, flagged only for awareness.
          - "present": has alt text; heuristically checked for
            filename-as-alt, generic-phrase prefixes, and excessive length
            (WCAG guidance).

        These are heuristics, not a substitute for a manual accessibility
        audit — "present" with no flagged issues does not guarantee the
        alt text is actually accurate for the image. Call fetch_image on a
        flagged image before suggesting a replacement, rather than
        guessing from surrounding text alone.

        Args:
            params: The page URL to scan and a max-images limit.

        Returns:
            {"url", "totalImagesOnPage", "images": [...], "summary": {...},
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

        scanned = scan_images_in_html(params.url, html, params.limit)

        return {
            "url": params.url,
            **scanned,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Images injected by client-side JS are not seen."
            ),
        }
