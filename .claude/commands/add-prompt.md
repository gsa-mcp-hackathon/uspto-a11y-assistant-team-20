---
description: Scaffold a new MCP Prompt that pairs a pasted persona/instructions with an existing tool.
allowed-tools: Read, Edit, Write, Bash, Glob, Grep
---

# /add-prompt — Add a custom MCP Prompt for a tool

Generalizes the pattern used for `prompts/scan_alt_text.py` (the
`scout_image_accessibility_analysis` prompt paired with the
`scan_page_alt_text` tool). The user supplies a tool name and pastes a
custom persona/instructions block; this command turns that into a
registered MCP Prompt, following the project's existing conventions.

Reminder of what a prompt is here, so the result matches expectations:
an MCP Prompt is a user-triggered, named conversation starter (shows up
as a slash command/preset in MCP clients that support it) — it is
**not** auto-injected when a tool runs. It bundles "run tool X with this
persona/ruleset applied" into one click.

## Inputs

Expect the user's message (`$ARGUMENTS` or the conversation) to contain:
1. **A tool name** — e.g. `check_aria_conflicts`. Must match a file in
   `src/alt_text_mcp/tools/`.
2. **A pasted prompt** — a persona, ruleset, or instructions block to
   apply when using that tool.

If either is missing, ask for it before proceeding. Don't guess at the
persona content — use exactly what the user pasted, word for word.

## Steps

### 1. Validate the tool

Run:
```
ls src/alt_text_mcp/tools/
```
Confirm the named tool has a matching `<tool_name>.py` file. If not,
show the available tool names and ask the user to pick one.

Read `src/alt_text_mcp/tools/<tool_name>.py` to see its real docstring,
parameters, and whether it pairs naturally with another tool (e.g.
`scan_page_alt_text` pairs with `fetch_image` — check if the target
tool has a similar natural companion before writing the prompt body).

### 2. Pick the prompt's registered name

Default to `<persona_or_purpose>_<short_verb>` in snake_case (e.g.
`scout_image_accessibility_analysis`). If it's not obvious from the
pasted text, ask the user what to call it. This is the name that shows
up in the client's slash-command/preset list — keep the filename
separate from this (see next step).

### 3. Create the prompt file

File path: `src/alt_text_mcp/prompts/<tool_name>.py` — **mirror the
tool's own filename**, not the persona name. This was a deliberate
convention decision (see the renamed `scout_alt_text.py` →
`scan_alt_text.py`): the filename should make it obvious at a glance
which tool a prompt pairs with, even though the MCP-facing prompt name
can carry whatever branding the persona uses.

Follow this exact structure (same shape as
`src/alt_text_mcp/prompts/scan_alt_text.py`):

```python
"""<prompt_name> — <one-line summary> applied to <tool_name> results.

Example prompt demonstrating how to add a custom prompt to this server: see
prompts/__init__.py for the registration convention this follows.
"""

from __future__ import annotations

from fastmcp import FastMCP

_PERSONA = """\
<the user's pasted text, verbatim, line-wrapped with trailing backslash
continuations to respect the project's 88-char line length>
"""


def register(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="<prompt_name>",
        description=(
            "<short description of what this prompt does, for the client's"
            " prompt picker>"
        ),
    )
    def <prompt_name>(url: str) -> str:
        return (
            f"{_PERSONA}\n\n"
            f"Apply the persona and rules above to {url}. Run "
            "<tool_name> on the page first, then <describe any natural"
            " companion-tool chaining, e.g. fetch_image for flagged"
            " items>, and produce output following the format described"
            " above."
        )


__all__ = ["register"]
```

Keep the pasted persona text completely unmodified — only reflow line
breaks to satisfy the 88-char line limit (`ruff` will flag anything
longer). Do not summarize, trim, or rephrase it.

### 4. Wire it into the registry

Edit `src/alt_text_mcp/prompts/__init__.py`:
- Add `from alt_text_mcp.prompts import <tool_name>` to the imports.
- Add `<tool_name>.register(mcp)` inside `register_prompts(mcp)`.

Preserve any prompts already registered there — append, don't replace.

### 5. Verify

Run, in order:
```
uv run ruff check src/alt_text_mcp/prompts/
uv run pytest -q
```
Both must pass. Then confirm the prompt actually registers:
```
uv run python -c "
from alt_text_mcp.app import mcp
import asyncio
for p in asyncio.run(mcp.list_prompts()):
    print(p.name, '-', p.description)
"
```
Confirm the new prompt name appears in the output.

### 6. Report, don't commit

Tell the user the file path, the registered prompt name, and that
tests/lint pass. **Do not** create a branch, commit, or push — that's
a separate, explicit step the user asks for (per this project's git
workflow), since it's visible/shared state.
