"""check_form_labels — audit a web page's form fields for accessible labels."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckFormLabelsInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_LABELABLE_INPUT_TYPES = {
    "text",
    "email",
    "password",
    "tel",
    "url",
    "number",
    "search",
    "date",
    "checkbox",
    "radio",
}


def _field_identity(field) -> str:
    name = field.get("name") or field.get("id")
    return f"{field.name}[{name}]" if name else field.name


def register(mcp: FastMCP) -> None:
    """Register the check_form_labels tool with the MCP server."""

    @mcp.tool(
        name="check_form_labels",
        annotations={
            "title": "Check a Page's Form Field Labels",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_form_labels(params: CheckFormLabelsInput) -> dict[str, Any]:
        """Scan one page's form fields for a programmatically associated label.

        Fetches the page as static HTML — no JavaScript execution. A sighted
        user can infer a field's purpose from its visual layout; a screen
        reader announces only what's programmatically associated with it, so
        a placeholder alone (which disappears once typing starts, and many
        screen readers don't announce consistently) is not a substitute for
        a real label.

        Checks each <input> (excluding hidden/submit/button/image types),
        <select>, and <textarea> for, in order of precedence:
          1. A <label for="..."> referencing the field's id.
          2. The field nested inside a <label>.
          3. aria-label or aria-labelledby.
        Flags "unlabeled" if none apply, even if a placeholder is present —
        noted separately since it's a common but insufficient pattern.

        Args:
            params: The page URL to scan and a max-fields limit.

        Returns:
            {"url", "totalFieldsOnPage", "fields": [...], "summary": {...},
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
        labels_by_for = {
            label["for"]: label for label in soup.find_all("label", attrs={"for": True})
        }

        all_fields = []
        for field in soup.find_all(["input", "select", "textarea"]):
            if field.name == "input":
                field_type = (field.get("type") or "text").lower()
                if field_type in {"hidden", "submit", "button", "image", "reset"}:
                    continue
            all_fields.append(field)

        fields = []
        for field in all_fields[: params.limit]:
            field_id = field.get("id")
            has_label_for = field_id is not None and field_id in labels_by_for
            has_wrapping_label = field.find_parent("label") is not None
            aria_label = field.get("aria-label") or field.get("aria-labelledby")
            has_placeholder_only = field.get("placeholder") is not None and not (
                has_label_for or has_wrapping_label or aria_label
            )

            if has_label_for or has_wrapping_label or aria_label:
                status = "labeled"
                issues = []
            else:
                status = "unlabeled"
                issues = ["no <label>, aria-label, or aria-labelledby"]
                if has_placeholder_only:
                    issues.append(
                        "has a placeholder, but that is not an accessible label"
                    )

            fields.append(
                {
                    "field": _field_identity(field),
                    "status": status,
                    "issues": issues,
                }
            )

        summary = {
            "labeled": sum(1 for f in fields if f["status"] == "labeled"),
            "unlabeled": sum(1 for f in fields if f["status"] == "unlabeled"),
        }

        return {
            "url": params.url,
            "totalFieldsOnPage": len(all_fields),
            "fieldsReturned": len(fields),
            "fields": fields,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Fields injected by client-side JS are not seen."
            ),
        }
