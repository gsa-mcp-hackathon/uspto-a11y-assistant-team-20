"""check_lang_attribute — audit a page's root <html> lang attribute."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckLangAttributeInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_LANG_PATTERN = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$")


def register(mcp: FastMCP) -> None:
    """Register the check_lang_attribute tool with the MCP server."""

    @mcp.tool(
        name="check_lang_attribute",
        annotations={
            "title": "Check a Page's Root Language Attribute",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_lang_attribute(
        params: CheckLangAttributeInput,
    ) -> dict[str, Any]:
        """Scan one page's <html> tag and flag lang-attribute problems.

        Fetches the page as static HTML — no JavaScript execution. Screen
        readers pick a pronunciation/voice engine based on the page's
        declared language; a missing or malformed `lang` attribute on
        <html> means the whole page gets read aloud in the wrong accent
        or pronunciation (or an unpredictable default voice), even though
        it renders visually identical either way.

        Flags:
          - "missing": the page has no <html> tag, or <html> has no lang
            attribute at all.
          - "empty": the lang attribute is present but blank.
          - "malformed": the lang attribute is present but does not look
            like a valid BCP-47 language tag (e.g. "en", "en-US", "es").

        Args:
            params: The page URL to scan.

        Returns:
            {"url", "lang", "status", "issues", "disclaimer"}. Or an error
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
        html_tag = soup.find("html")
        lang = html_tag.get("lang") if html_tag else None

        issues: list[str] = []
        if html_tag is None or lang is None:
            status = "missing"
            issues.append("no lang attribute on <html>")
        elif lang.strip() == "":
            status = "empty"
            issues.append("lang attribute is present but empty")
        elif not _LANG_PATTERN.match(lang.strip()):
            status = "malformed"
            issues.append(
                f'lang="{lang}" does not look like a valid BCP-47 language tag '
                '(e.g. "en", "en-US", "es")'
            )
        else:
            status = "present"

        return {
            "url": params.url,
            "lang": lang,
            "status": status,
            "issues": issues,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. A lang attribute set via client-side JS is not seen."
            ),
        }
