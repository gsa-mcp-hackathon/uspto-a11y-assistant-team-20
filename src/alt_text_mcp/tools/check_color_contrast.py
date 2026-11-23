"""check_color_contrast — audit a page's inline-styled text for low color contrast."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckColorContrastInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "navy": (0, 0, 128),
    "teal": (0, 128, 128),
    "maroon": (128, 0, 0),
    "purple": (128, 0, 128),
    "orange": (255, 165, 0),
}
_HEX3_RE = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX6_RE = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGB_RE = re.compile(
    r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)$"
)


def _parse_color(value: str) -> tuple[int, int, int] | None:
    """Parse a CSS color value into (r, g, b), or None if unsupported."""
    value = value.strip().lower()
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]
    m = _HEX6_RE.match(value)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = _HEX3_RE.match(value)
    if m:
        h = m.group(1)
        return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
    m = _RGB_RE.match(value)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def _channel(c: int) -> float:
        c_norm = c / 255
        if c_norm <= 0.03928:
            return c_norm / 12.92
        return ((c_norm + 0.055) / 1.055) ** 2.4

    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_inline_style(style: str) -> dict[str, str]:
    """Split a style attribute into a lowercase-property-name dict.

    Last declaration wins on repeated properties.
    """
    declarations = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        declarations[prop.strip().lower()] = val.strip()
    return declarations


def register(mcp: FastMCP) -> None:
    """Register the check_color_contrast tool with the MCP server."""

    @mcp.tool(
        name="check_color_contrast",
        annotations={
            "title": "Check a Page's Inline-Styled Text for Low Color Contrast",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_color_contrast(params: CheckColorContrastInput) -> dict[str, Any]:
        """Scan one page's inline-styled text for low foreground/background contrast.

        **Narrow, best-effort heuristic — read this before relying on it.**
        This tool can ONLY evaluate elements that set BOTH `color` and
        `background-color` via an inline `style="..."` attribute, parsed from
        the raw HTML with no CSS cascade/inheritance resolution and no
        computed styles. The overwhelming majority of real-world contrast
        issues come from external or embedded stylesheets, not inline
        styles — so on a typical page this tool will see almost nothing. It
        is not a substitute for a manual or tooling-based (e.g. axe,
        Lighthouse) contrast audit. It also ignores font-size/weight, so it
        applies the normal-text 4.5:1 WCAG AA threshold uniformly even though
        large/bold text would only need 3:1 — meaning it can over-flag
        large/bold text.

        Fetches the page as static HTML — no JavaScript execution. For every
        element with a `style` attribute, in document order, parses `color`
        and `background-color` (hex, rgb()/rgba(), or a small set of named
        colors). If either is missing or unparseable, the element is skipped
        silently — not counted and not flagged. Otherwise computes the WCAG
        relative-luminance contrast ratio and flags it if under 4.5:1.

        Args:
            params: The page URL to scan and a max-issues limit.

        Returns:
            {"url", "elementsChecked", "issuesReturned", "issues": [...],
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

        elements_checked = 0
        issues = []
        for el in soup.find_all(style=True):
            declarations = _parse_inline_style(el["style"])
            if "color" not in declarations or "background-color" not in declarations:
                continue

            fg_raw = declarations["color"]
            bg_raw = declarations["background-color"]
            fg_rgb = _parse_color(fg_raw)
            bg_rgb = _parse_color(bg_raw)
            if fg_rgb is None or bg_rgb is None:
                continue

            elements_checked += 1
            ratio = _contrast_ratio(fg_rgb, bg_rgb)
            if ratio < 4.5:
                element_id = el.get("id")
                element_name = f"{el.name}#{element_id}" if element_id else el.name
                rounded = round(ratio, 2)
                issues.append(
                    {
                        "element": element_name,
                        "foreground": fg_raw.strip(),
                        "background": bg_raw.strip(),
                        "ratio": rounded,
                        "issue": (
                            f"contrast ratio {rounded}:1 — below WCAG AA's 4.5:1 "
                            "minimum for normal text"
                        ),
                    }
                )

        low_contrast_count = len(issues)
        issues = issues[: params.limit]

        return {
            "url": params.url,
            "elementsChecked": elements_checked,
            "issuesReturned": len(issues),
            "issues": issues,
            "summary": {"lowContrastCount": low_contrast_count},
            "disclaimer": (
                "Heuristic checks only, and limited to elements with BOTH color and "
                "background-color set via inline style attributes — the overwhelming "
                "majority of real contrast issues come from external or embedded CSS "
                "and computed/inherited styles, which this cannot see. Not a "
                "substitute for a manual or tooling-based (e.g. axe, Lighthouse) "
                "contrast audit. Also does not account for font size/weight, so "
                "large/bold text that only needs a 3:1 ratio may be over-flagged here."
            ),
        }
