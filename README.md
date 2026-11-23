# Alt-Text Accessibility MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server, built from the
[GSA MCP hackathon template](https://github.com/GSA-TTS/mcp-hackathon-template), that scans a
public web page for images with missing, empty, or low-quality `alt` text, and lets an agent
visually inspect flagged images to suggest real replacements — a concrete Section 508
accessibility-compliance aid.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and [uv](https://docs.astral.sh/uv/). If you have never built an MCP server before, start with **[QUICKSTART.md](QUICKSTART.md)**.

---

## What is an MCP server?

An MCP server exposes **tools** (functions the model can call), **prompts** (reusable conversation starters), and **resources** (data the model can read) to an AI client such as Claude Desktop or Claude Code. You write the tools; the client's model decides when to call them.

---

## Repo structure

```
gsahackathon/
├── README.md                  # This file
├── QUICKSTART.md              # 5-minute clone → run → connect walkthrough
├── main.py                    # Local entry point (uv run python main.py)
├── pyproject.toml             # Package + dependencies (uv)
├── requirements.txt           # Mirror of runtime deps (for buildpack hosts)
├── Dockerfile                 # Container image (streamable-HTTP, port 8080)
├── manifest.yaml              # cloud.gov (Cloud Foundry) deploy
├── server.json                # MCP registry metadata
├── .env.example               # Copy to .env for local dev
├── .gitlab-ci.yml             # Lint + test on every branch; deploy on merge to master
├── src/
│   └── alt_text_mcp/
│       ├── app.py             # Thin entry point: builds FastMCP, picks transport
│       ├── config.py          # Settings from env vars / .env
│       ├── models.py          # Pydantic models & enums for tool params
│       ├── utils.py           # SSRF-hardened fetch helpers for arbitrary URLs
│       ├── routes.py          # HTTP-only routes (/health, /version)
│       ├── tools/             # ONE FILE PER TOOL (15 tools)
│       │   ├── __init__.py    #   register_tools(mcp) aggregator
│       │   ├── scan_alt_text.py          # scan_page_alt_text
│       │   ├── fetch_image.py            # fetch_image
│       │   ├── scan_site.py              # scan_site
│       │   ├── check_link_text.py        # check_link_text
│       │   ├── check_heading_structure.py # check_heading_structure
│       │   ├── check_form_labels.py      # check_form_labels
│       │   ├── check_duplicate_ids.py    # check_duplicate_ids
│       │   ├── check_landmarks.py        # check_landmarks
│       │   ├── check_table_headers.py    # check_table_headers
│       │   ├── check_lang_attribute.py   # check_lang_attribute
│       │   ├── check_page_title.py       # check_page_title
│       │   ├── check_iframe_titles.py    # check_iframe_titles
│       │   ├── check_media_captions.py   # check_media_captions
│       │   ├── check_aria_conflicts.py   # check_aria_conflicts
│       │   └── check_color_contrast.py   # check_color_contrast
│       ├── prompts/
│       │   └── __init__.py    #   register_prompts(mcp) aggregator — none registered yet
│       └── resources/
│           └── __init__.py    #   register_resources(mcp) aggregator — none registered yet
├── tests/                     # 122 unit tests: per-tool logic, SSRF defenses, server wiring
├── eval/
│   ├── README.md              # Overview of both local eval harnesses below
│   ├── deterministic/         # No-LLM tool-correctness checks, all 15 tools (14/14 passing)
│   ├── phoenix/               # LLM agent tool-selection eval (via AWS Bedrock; 10/10 correctness, 10/10 relevance)
│   └── databricks/            # Real MLflow eval harness for the deployed Databricks App
└── deploy/
    ├── README.md              # Deployment notes
    └── databricks/            # Databricks Apps kit
```

---

## Getting started

### Prerequisites
- [uv](https://docs.astral.sh/uv/) — `pip install uv` or `brew install uv`

### Install and run

```bash
cp .env.example .env
uv sync
uv run python main.py
```

The server starts in **stdio** mode — it talks JSON-RPC over stdin/stdout, which is how local clients (Claude Desktop, Claude Code) launch it. See [QUICKSTART.md](QUICKSTART.md) to connect a client.

---

## Testing your changes

Before opening an MR, run the same checks `.gitlab-ci.yml` runs on every push — this is the full gate for merging to `master`:

```bash
uv sync --group dev
uv run ruff check .             # lint
uv run ruff format --check .    # formatting
uv run pytest tests/ -v         # tests
```

If you added or changed a tool, add a matching test in `tests/` — see `tests/test_alt_text_tools.py` for the pattern (mock the HTTP layer via `utils.fetch_url_safely`/`fetch_text_safely`, don't hit real network in tests).

To sanity-check the server end-to-end, not just via pytest:

```bash
# stdio mode — wire into a client's .mcp.json per QUICKSTART.md, then invoke a tool
uv run python main.py

# HTTP mode — same code path Databricks Apps uses in production
MCP_TRANSPORT=streamable-http uv run python main.py
curl http://localhost:8000/health
```

---

## Tools

### `scan_page_alt_text(url, limit=20)`

Fetches a page's static HTML (no JavaScript execution) and classifies every
`<img>` tag:

- **missing** — no `alt` attribute at all (a real accessibility bug).
- **empty-decorative** — `alt=""` or `role="presentation"` (valid for
  genuinely decorative images; flagged only for awareness).
- **present** — has alt text, heuristically checked for filename-as-alt,
  generic-phrase prefixes ("image of", "picture of"), and excessive length
  (WCAG guidance).

Returns the per-image list, summary counts, and a disclaimer that these are
heuristics, not a substitute for a manual accessibility audit. Images
injected by client-side JS on single-page apps aren't seen — a named
limitation, not a silent gap.

### `fetch_image(url)`

Fetches one image's bytes and returns them as an MCP image content block, so
the agent can actually look at a flagged image before suggesting replacement
alt text — grounded in what the image shows, not guessed from surrounding
page text.

### `scan_site(url, max_pages=5, limit_per_page=20)`

Fetches the start page, discovers same-origin `<a href>` links on it, and
runs the same alt-text scan as `scan_page_alt_text` on the start page plus
each discovered link (one level deep, up to `max_pages` total). Useful when
a shared template issue (e.g. a missing header-image `alt`) repeats across
many pages — one call instead of one `scan_page_alt_text` call per page.

### `check_link_text(url, limit=50)`

Scans `<a>` tags for non-descriptive link text — generic filler phrases
("click here", "read more"), raw URLs used as the visible text, or no text
and no `aria-label`/`aria-labelledby`/`title`. Screen reader users often
navigate link-to-link out of surrounding context, so this is a real barrier,
not just a style nit.

### `check_heading_structure(url)`

Scans `<h1>`–`<h6>` tags and flags outline problems: no `<h1>`, multiple
`<h1>`s, empty headings, and skipped levels (e.g. `h2` straight to `h4`).
Screen reader users commonly jump between headings to navigate, so a broken
outline is a real barrier even on a page that looks fine visually.

### `check_form_labels(url, limit=50)`

Scans `<input>` (excluding hidden/submit/button/image/reset),
`<select>`, and `<textarea>` fields for a programmatically associated
label — `<label for="...">`, a wrapping `<label>`, or
`aria-label`/`aria-labelledby` — and flags fields with none, noting
separately when a placeholder is present but insufficient on its own.

### `check_duplicate_ids(url, limit=50)`

Scans all elements for `id` attribute values that appear more than once.
Duplicate ids break `<label for="...">`, `aria-labelledby`,
`aria-describedby`, and `href="#id"` fragment navigation — `getElementById`
and assistive tech resolve only the first match, leaving every subsequent
element unreachable or mislabeled for screen reader users even though the
page looks fine visually. Empty or whitespace-only ids are ignored.

### `check_landmarks(url)`

Scans for ARIA landmark elements (`<main>`, `<nav>`, `<header>`, `<footer>`
and their `role=` equivalents) and a skip-to-content link. Screen reader
users jump between landmarks the way sighted users scan a page visually.
Flags: no `<main>`, multiple `<main>`s, and no skip link.

### `check_table_headers(url, limit=20)`

Scans `<table>` elements for header cells and captions. Flags:
- **no-th** — table has no `<th>` cells at all (possible false positive for
  purely visual layout tables).
- **missing-caption** — table has no `<caption>`.
- **th-missing-scope** — multi-dimensional table (more than 2 rows) has
  `<th>` cells that lack a `scope` attribute, making row/column associations
  ambiguous for screen readers.

### `check_lang_attribute(url)`

Checks the `lang` attribute on the root `<html>` element. Screen readers
pick a pronunciation/voice engine based on the declared language; a missing
or malformed `lang` means the whole page gets read in the wrong accent or
voice. Flags: missing, empty, or not a valid BCP-47 tag (e.g. `en`, `en-US`).

### `check_page_title(url)`

Checks the `<title>` element. The title is the first thing a screen reader
announces on page load and when switching browser tabs — it's how a
non-sighted user confirms they landed on the right page. Flags: missing,
empty, or a generic non-descriptive placeholder ("Untitled Document", "Home",
"Index", etc.).

### `check_iframe_titles(url, limit=50)`

Checks every `<iframe>` for a non-empty `title` attribute. Screen readers
announce iframes by their `title` (e.g. "YouTube video player, iframe");
without one, every iframe is announced as a generic indistinguishable
"iframe." Flags iframes with a missing or whitespace-only title.

### `check_media_captions(url, limit=20)`

Checks `<video>` and `<audio>` elements for caption tracks. For `<video>`,
looks for a `<track kind="captions">` or `<track kind="subtitles">` child and
flags its absence. For `<audio>`, always flags for manual review — whether a
transcript exists elsewhere on the page cannot be verified from markup alone.

### `check_aria_conflicts(url, limit=50)`

Scans for conflicting or invalid ARIA usage across the page. Flags:
- **Invalid role** — `role=` value whose first token isn't a recognized
  WAI-ARIA role (simply ignored by assistive tech, leaving no semantics).
- **Redundant role** — `role=` value that duplicates the element's own
  implicit role (e.g. `role="button"` on `<button>`).
- **aria-hidden on focusable element** — creates a keyboard trap where
  sighted keyboard users can tab to something a screen reader user is told
  doesn't exist.
- **Positive tabindex** — overrides natural reading-order tab sequence,
  disorienting keyboard and screen reader users.

### `check_color_contrast(url, limit=50)`

Checks inline-styled text for foreground/background contrast below WCAG AA's
4.5:1 minimum. **Important limitation:** only evaluates elements that set
*both* `color` and `background-color` via an inline `style="..."` attribute.
The vast majority of real-world contrast issues come from external or embedded
stylesheets, not inline styles — so this tool will see almost nothing on a
typical page. It is not a substitute for a tooling-based audit (e.g. axe,
Lighthouse). Also does not account for font size/weight, so large/bold text
(which only needs 3:1) may be over-flagged.

---

All tools fetch **caller-supplied URLs**, not a fixed operator-controlled
origin, so all route through `utils.fetch_url_safely`/`fetch_text_safely` —
see [SECURITY.md](SECURITY.md) for the SSRF defense that makes that safe.

---

## The one-tool-per-file pattern

Each tool lives in its own file under `src/alt_text_mcp/tools/` and exposes a `register(mcp)` function. `tools/__init__.py` calls each one from a single `register_tools(mcp)`. This keeps the tool list scannable and lets you add or remove an integration by touching two files.

**Step 1 — create `src/alt_text_mcp/tools/my_tool.py`:**

```python
from typing import Annotated
from fastmcp import FastMCP

from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="my_tool",
        annotations={
            "title": "Describe what this does",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def my_tool(url: Annotated[str, "A page URL."]) -> dict:
        """One-line summary. Document what it returns — the model reads this docstring."""
        try:
            html = await fetch_text_safely(url)
        except (BlockedUrlError, UpstreamServiceError) as exc:
            return {"error": str(exc)}
        return {"length": len(html)}
```

**Step 2 — wire it up in `tools/__init__.py`:**

```python
from alt_text_mcp.tools import fetch_image, my_tool, scan_alt_text

def register_tools(mcp) -> None:
    scan_alt_text.register(mcp)
    fetch_image.register(mcp)
    my_tool.register(mcp)  # ← add this line
```

**Step 3 — add any API key** as a typed field in `config.py` and document the env var in `.env.example`.

Prompts (`prompts/`) and resources (`resources/`) follow the exact same `register(mcp)` + aggregator pattern.

---

## Rename the package

Before publishing your server, rename `alt_text_mcp` to your service (e.g. `census_mcp`):

1. Rename the folder `src/alt_text_mcp/` → `src/<your_name>/`.
2. Update `pyproject.toml`: the `[project].name`, `[project.scripts]`, and `[tool.hatch.build.targets.wheel].packages`.
3. Find-and-replace `alt_text_mcp` across `src/`, `tests/`, `main.py`, `Dockerfile`, and `manifest.yaml`.

---

## Tool design tips

- **Return structured data, not prose.** Return dicts/lists with consistent keys and let the model narrate.
- **Actionable errors.** Return an error dict with a `hint`, not a raw stack trace — see `scan_alt_text.py`/`fetch_image.py` for the pattern.
- **Expose pagination.** Use `PaginationParams` / `paginate()` from `utils.py` for any list-style tool you add, and return `has_more` / `next_offset`.
- **Caller-supplied URLs need resolve-and-check, not path-escape checks.** This server's whole job is fetching URLs the *caller* supplies (an agent, which might be relaying an untrusted user's request) — a materially different threat model than a tool that calls one fixed, operator-controlled API. Every new tool that fetches a URL must go through `utils.fetch_url_safely`/`fetch_text_safely`, which resolves DNS and checks every IP (and every redirect hop) against private/loopback/link-local/multicast/CGNAT/metadata ranges before connecting. Never hand a tool-supplied URL to an HTTP client directly.
- **DNS rebinding is a named residual risk, not a solved one.** The pre-connect resolve check and the actual connection are two separate steps; see the docstring on `_assert_host_resolves_safely` in `utils.py`.
- **Keep sensitive data out of errors and logs.** Do not expose or log upstream bodies, headers, resolved IPs, credentials, or stack traces.

---

## Deploying

Local development uses stdio. To share your server with an agent platform, deploy it as a
Databricks App — see **[deploy/README.md](deploy/README.md)** and
[deploy/databricks/README.md](deploy/databricks/README.md). `app.py` automatically serves HTTP
when the platform injects a port.

In this repo, live deploys are run manually (`bash deploy/databricks/deploy-databricks-app.sh`)
rather than through GitLab CI, since this shared hackathon workspace has no service principal
available for CI to deploy as — see [deploy/databricks/README.md](deploy/databricks/README.md).

---

## Evaluations

Measuring how well an LLM can use your tools is the real test of server quality. Two separate paths exist here:

- **Local, pre-deploy eval (built).** Two complementary harnesses — see [eval/README.md](eval/README.md):
  - [eval/deterministic/](eval/deterministic/README.md) calls the real tools directly, no LLM required — 14/14 cases passing across all 15 tools.
  - [eval/phoenix/](eval/phoenix/README.md) is an Arize Phoenix harness that scores whether an LLM agent, given only the tools' names/schemas/docstrings, picks the right tool and answers correctly. Runs via AWS Bedrock credentials for both the agent and the judges. Latest run: 10/10 correctness, 10/10 relevance.
- **Post-deploy eval (built).** [eval/databricks/](eval/databricks/README.md) is a real MLflow GenAI harness that evaluates an agent using your *deployed* Databricks App — Correctness, Safety, RelevanceToQuery, and a conciseness guideline, scored in a notebook against the live app.

---

## License

[MIT](LICENSE). See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy and hackathon security notes.
