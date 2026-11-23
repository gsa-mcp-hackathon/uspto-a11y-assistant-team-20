"""Tools submodule — one tool per file.

Each tool module (e.g. `fetch_image.py`) exposes a `register(mcp)` function
that attaches its `@mcp.tool`-decorated function to the server. This file
aggregates them into a single `register_tools(mcp)` that `app.py` calls.

To add a tool:
  1. Create `tools/<your_tool>.py` with a `register(mcp)` function.
  2. Import it below and call `<your_tool>.register(mcp)` inside register_tools.
"""

from __future__ import annotations

from alt_text_mcp.tools import (
    check_aria_conflicts,
    check_color_contrast,
    check_duplicate_ids,
    check_form_labels,
    check_heading_structure,
    check_iframe_titles,
    check_landmarks,
    check_lang_attribute,
    check_link_text,
    check_media_captions,
    check_page_title,
    check_table_headers,
    fetch_image,
    scan_alt_text,
    scan_site,
)


def register_tools(mcp) -> None:
    """Register all tools with the MCP server."""
    scan_alt_text.register(mcp)
    fetch_image.register(mcp)
    check_link_text.register(mcp)
    check_heading_structure.register(mcp)
    check_form_labels.register(mcp)
    scan_site.register(mcp)
    check_duplicate_ids.register(mcp)
    check_landmarks.register(mcp)
    check_table_headers.register(mcp)
    check_lang_attribute.register(mcp)
    check_page_title.register(mcp)
    check_iframe_titles.register(mcp)
    check_media_captions.register(mcp)
    check_aria_conflicts.register(mcp)
    check_color_contrast.register(mcp)


__all__ = ["register_tools"]
