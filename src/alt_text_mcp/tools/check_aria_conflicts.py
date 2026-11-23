"""check_aria_conflicts — audit a web page for conflicting or invalid ARIA usage."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckAriaConflictsInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_VALID_ARIA_ROLES = frozenset(
    {
        "alert",
        "alertdialog",
        "application",
        "article",
        "banner",
        "blockquote",
        "button",
        "caption",
        "cell",
        "checkbox",
        "code",
        "columnheader",
        "combobox",
        "comment",
        "complementary",
        "contentinfo",
        "definition",
        "deletion",
        "dialog",
        "directory",
        "document",
        "emphasis",
        "feed",
        "figure",
        "form",
        "generic",
        "grid",
        "gridcell",
        "group",
        "heading",
        "img",
        "insertion",
        "link",
        "list",
        "listbox",
        "listitem",
        "log",
        "main",
        "mark",
        "marquee",
        "math",
        "menu",
        "menubar",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "meter",
        "navigation",
        "none",
        "note",
        "option",
        "paragraph",
        "presentation",
        "progressbar",
        "radio",
        "radiogroup",
        "region",
        "row",
        "rowgroup",
        "rowheader",
        "scrollbar",
        "search",
        "searchbox",
        "separator",
        "slider",
        "spinbutton",
        "status",
        "strong",
        "subscript",
        "suggestion",
        "superscript",
        "switch",
        "tab",
        "table",
        "tablist",
        "tabpanel",
        "term",
        "textbox",
        "time",
        "timer",
        "toolbar",
        "tooltip",
        "tree",
        "treegrid",
        "treeitem",
    }
)

_IMPLICIT_ROLES = {
    "button": "button",
    "nav": "navigation",
    "header": "banner",
    "footer": "contentinfo",
    "main": "main",
    "img": "img",
    "table": "table",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "form": "form",
    "textarea": "textbox",
    "dialog": "dialog",
    "article": "article",
}


def _element_identity(el) -> str:
    return f"{el.name}#{el['id']}" if el.get("id") else el.name


def _first_role_token(el) -> str:
    return el["role"].split()[0].lower()


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _is_focusable(el) -> bool:
    if el.name == "button":
        return True
    if el.name == "a" and el.get("href") is not None:
        return True
    if el.name == "input" and (el.get("type") or "").lower() != "hidden":
        return True
    if el.name in ("select", "textarea"):
        return True
    tabindex = _parse_int(el.get("tabindex"))
    if tabindex is not None and tabindex >= 0:
        return True
    return False


def register(mcp: FastMCP) -> None:
    """Register the check_aria_conflicts tool with the MCP server."""

    @mcp.tool(
        name="check_aria_conflicts",
        annotations={
            "title": "Check a Page for Conflicting or Invalid ARIA Usage",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_aria_conflicts(params: CheckAriaConflictsInput) -> dict[str, Any]:
        """Scan one page for conflicting, redundant, or invalid ARIA usage.

        Fetches the page as static HTML — no JavaScript execution. ARIA
        roles and states tell assistive tech how to present an element: an
        invalid role is simply ignored (falling back to no semantics at
        all), a redundant role is harmless but signals carelessness worth
        flagging, aria-hidden="true" on a focusable element creates a trap
        where sighted keyboard users can tab to something a screen reader
        user is told doesn't exist, and a positive tabindex silently
        overrides the natural reading-order tab sequence — disorienting
        keyboard and screen reader users even though the page looks and
        behaves normally to a mouse user.

        Flags, across the whole page:
          1. Invalid role: a role= value whose first token isn't a
             recognized, concrete WAI-ARIA role.
          2. Redundant role: a role= value that duplicates the element's
             own implicit role (e.g. role="button" on a <button>).
          3. aria-hidden="true" on a focusable element (<button>, a link
             with href, a non-hidden <input>, <select>/<textarea>, or
             anything with a non-negative tabindex).
          4. A positive tabindex (tabindex > 0), which overrides natural
             tab order.

        Args:
            params: The page URL to scan and a max-findings limit.

        Returns:
            {"url", "elementsScanned", "findingsReturned", "findings": [...],
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

        findings: list[dict[str, Any]] = []
        invalid_roles = 0
        redundant_roles = 0
        aria_hidden_focusable = 0
        positive_tabindex = 0

        role_elements = soup.find_all(attrs={"role": True})

        for el in role_elements:
            role_value = _first_role_token(el)
            if role_value not in _VALID_ARIA_ROLES:
                findings.append(
                    {
                        "element": _element_identity(el),
                        "issue": f'role="{role_value}" is not a recognized ARIA role',
                    }
                )
                invalid_roles += 1

        for el in role_elements:
            if el.name in ("a", "input"):
                continue
            role_value = _first_role_token(el)
            implicit_role = _IMPLICIT_ROLES.get(el.name)
            if implicit_role is not None and role_value == implicit_role:
                findings.append(
                    {
                        "element": _element_identity(el),
                        "issue": (
                            f'role="{role_value}" duplicates the element\'s '
                            "implicit role — redundant"
                        ),
                    }
                )
                redundant_roles += 1

        for el in soup.find_all(attrs={"aria-hidden": True}):
            if (el.get("aria-hidden") or "").lower() != "true":
                continue
            if _is_focusable(el):
                findings.append(
                    {
                        "element": _element_identity(el),
                        "issue": (
                            'aria-hidden="true" on a focusable element — it\'s '
                            "reachable by keyboard but hidden from assistive tech"
                        ),
                    }
                )
                aria_hidden_focusable += 1

        for el in soup.find_all(attrs={"tabindex": True}):
            tabindex = _parse_int(el.get("tabindex"))
            if tabindex is not None and tabindex > 0:
                findings.append(
                    {
                        "element": _element_identity(el),
                        "issue": (
                            f'tabindex="{tabindex}" is positive — this overrides '
                            "natural tab order and can disorient keyboard users"
                        ),
                    }
                )
                positive_tabindex += 1

        elements_scanned = len(
            {
                id(el)
                for el in soup.find_all(True)
                if el.has_attr("role")
                or el.has_attr("aria-hidden")
                or el.has_attr("tabindex")
            }
        )

        truncated_findings = findings[: params.limit]

        return {
            "url": params.url,
            "elementsScanned": elements_scanned,
            "findingsReturned": len(truncated_findings),
            "findings": truncated_findings,
            "summary": {
                "invalidRoles": invalid_roles,
                "redundantRoles": redundant_roles,
                "ariaHiddenFocusable": aria_hidden_focusable,
                "positiveTabindex": positive_tabindex,
            },
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Does not evaluate ARIA attribute *values* beyond "
                "role/aria-hidden/tabindex (e.g. aria-expanded correctness), "
                "and attributes set via client-side JS are not seen."
            ),
        }
