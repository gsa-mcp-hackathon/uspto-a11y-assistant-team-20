"""Generate EVALUATION.docx — the hackathon's required evaluation documentation.

One-off doc-generation script, not a server dependency: run with python-docx
installed ephemerally so it never touches pyproject.toml.

Run from the repo root:
    uv run --with python-docx python eval/build_evaluation_doc.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "EVALUATION.docx"

ACCENT = RGBColor(0x00, 0x54, 0xA6)  # USPTO blue, matches the chat UI theme


def add_heading(doc: Document, text: str, level: int = 1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = ACCENT
    return h


def add_bullets(doc: Document, items: list[str]):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def add_table(doc: Document, headers: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for p in hdr_cells[i].paragraphs:
            for r in p.runs:
                r.font.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = val
    doc.add_paragraph()
    return table


def build() -> None:
    doc = Document()

    title = doc.add_heading("Alt-Text Accessibility MCP Server", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = ACCENT

    subtitle = doc.add_paragraph(
        "Evaluation Documentation — GSA MCP Hackathon, Team 20"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(14)
    subtitle.runs[0].font.italic = True

    doc.add_paragraph(
        "This document covers the testing methodology, performance metrics, "
        "security considerations, and lessons learned for alt-text-mcp — an "
        "MCP server that scans public web pages for Section 508 / WCAG "
        "accessibility issues (missing alt text, broken heading structure, "
        "unlabeled form fields, ARIA conflicts, low color contrast, and "
        "more) and the chat agent built on top of it."
    )

    # ------------------------------------------------------------------
    add_heading(doc, "1. Testing Methodology")
    doc.add_paragraph(
        "Three complementary layers of testing were used, each covering a "
        "different failure mode. The first two need no LLM credentials at "
        "all; the third was initially expected to be blocked on missing "
        "LLM-gateway credentials, but ran successfully against AWS Bedrock "
        "credentials already available in this hackathon environment (see "
        "Lessons Learned)."
    )
    add_table(
        doc,
        ["Layer", "What it validates", "Scope", "Status"],
        [
            [
                "Unit tests\n(tests/)",
                "Each tool's parsing logic against fixed HTML fixtures: "
                "edge cases, malformed markup, SSRF-blocked URLs, "
                "error-dict shape.",
                "122 tests across all 15 tools plus dedicated SSRF "
                "security tests (test_http_security.py) and server "
                "wiring (test_server.py).",
                "122 / 122 passing",
            ],
            [
                "Deterministic tool-level eval\n(eval/deterministic/)",
                "Whether the real tools, called directly with no LLM in "
                "the loop, return correct answers against curated gold "
                "data and live upstream pages.",
                "All 15 of 15 tools. 10 gold Q&A pairs shared with the "
                "Phoenix dataset (13 tools — one question exercises 4 "
                "checks at once) plus structural checks for fetch_image "
                "and scan_site (the 2 remaining tools, whose outputs "
                "don't reduce to a single gold string).",
                "14 / 14 passing",
            ],
            [
                "Agent tool-selection eval\n(eval/phoenix/)",
                "Whether an LLM agent, given only the tools' names, "
                "schemas, and docstrings — no other page context — picks "
                "the right tool(s) and answers correctly. A "
                "correctness judge and a relevance judge grade each run.",
                "alt-text-eval-0: 10 questions covering 13 tools, "
                "against the same W3C WAI before/after demo pages.",
                "Run via AWS Bedrock — 10 / 10 correctness, "
                "10 / 10 relevance (perfect score on both judges).",
            ],
        ],
    )
    doc.add_paragraph(
        "The deterministic layer exists specifically to isolate failure "
        "attribution: because it proves the tools themselves are correct "
        "independent of any LLM, a Phoenix failure can be attributed to "
        "tool-selection/schema clarity (Criterion 3) rather than a "
        "tool-implementation bug. With both layers now green, that "
        "attribution logic is moot for this run, but the separation of "
        "concerns is the reason a perfect Phoenix score is strong evidence "
        "of schema/docstring clarity specifically, not just general "
        "correctness."
    )

    # ------------------------------------------------------------------
    add_heading(doc, "2. Performance Metrics")

    add_heading(doc, "2.1 Unit test suite", level=2)
    doc.add_paragraph("uv run pytest tests/ -v → 122 passed, 0 failed, 0 skipped.")
    add_bullets(
        doc,
        [
            "Covers all 15 tools' parsing logic against static HTML fixtures.",
            "Dedicated SSRF defense tests (test_http_security.py) assert "
            "loopback/private/link-local/metadata-endpoint addresses are "
            "rejected before any request is made.",
            "Error paths are asserted to return structured "
            '{"error", "hint"} dicts, never a raw traceback.',
        ],
    )

    add_heading(doc, "2.2 Deterministic tool-level evaluation", level=2)
    doc.add_paragraph(
        "uv run python eval/deterministic/run_tool_eval.py → 14/14 cases "
        "passed, exercising all 15 tools against the live W3C WAI "
        "before/after accessibility demo pages over the real network. "
        "Full detail is in eval/deterministic/results.json."
    )
    add_table(
        doc,
        ["#", "Check", "Tool(s)", "Expected", "Actual", "Result"],
        [
            [
                "1",
                "Missing-alt-text count decrease, before→after",
                "scan_page_alt_text",
                "17",
                "17",
                "PASS",
            ],
            [
                "2",
                "Differing word in <title> brackets",
                "check_page_title",
                "Inaccessible",
                "Inaccessible",
                "PASS",
            ],
            [
                "3",
                "lang value present on exactly one page",
                "check_lang_attribute",
                "en",
                "en",
                "PASS",
            ],
            [
                "4",
                "Page whose <select> is unlabeled",
                "check_form_labels",
                "before",
                "before",
                "PASS",
            ],
            [
                "5",
                "Page with a detectable skip-navigation link",
                "check_landmarks",
                "after",
                "after",
                "PASS",
            ],
            [
                "6",
                "Table-count difference, before − after",
                "check_table_headers",
                "10",
                "10",
                "PASS",
            ],
            [
                "7",
                'Page with a "multiple-h1" issue',
                "check_heading_structure",
                "after",
                "after",
                "PASS",
            ],
            [
                "8",
                "Page with more elements carrying an id",
                "check_duplicate_ids",
                "after",
                "after",
                "PASS",
            ],
            [
                "9",
                'Shared href of the two "Click here" links',
                "check_link_text",
                "…/offsite.html",
                "matched",
                "PASS",
            ],
            [
                "10",
                "Any nonzero finding across 4 checks, both pages",
                "check_iframe_titles, check_media_captions, "
                "check_aria_conflicts, check_color_contrast",
                "False",
                "False",
                "PASS",
            ],
            [
                "11",
                "Real image URL returns genuine image content",
                "fetch_image",
                "image/png, non-empty",
                "image/png, 2376 bytes",
                "PASS",
            ],
            [
                "12",
                "Non-image URL returns a graceful error, not a crash",
                "fetch_image",
                "{error, hint} dict",
                "matched",
                "PASS",
            ],
            [
                "13",
                "Start-page scan matches an independent single-page call",
                "scan_site, scan_page_alt_text",
                "identical",
                "identical",
                "PASS",
            ],
            [
                "14",
                "Respects max_pages cap, same-origin-only crawling",
                "scan_site",
                "≤3 pages, same-origin",
                "3 pages, same-origin",
                "PASS",
            ],
        ],
    )

    add_heading(doc, "2.3 Agent tool-selection evaluation (Phoenix)", level=2)
    doc.add_paragraph(
        "The harness (eval/phoenix/) is a LangChain agent wired to the "
        "live MCP server over stdio, tested against a 10-question gold "
        "dataset (alt-text-eval-0) and graded by two independent LLM "
        "judges — correctness (does the answer match the known-correct "
        "reference?) and relevance (did the agent stay within the tools' "
        "answerable scope, rather than refusing or wandering off-task?). "
        "No OpenAI-compatible gateway was ever obtained during this "
        "hackathon; instead the harness was repointed at AWS Bedrock, "
        "using credentials already available in this environment — the "
        "agent-under-test runs on a Haiku-tier model, the judges on a "
        "distinct, stronger Sonnet-tier model, to reduce self-preference "
        "bias. Full detail is in eval/phoenix/results.json."
    )
    doc.add_paragraph(
        "uv run run_experiment.py --dataset-name alt-text-eval-0 → "
        "10 task runs, 20 evaluator runs, both judges scoring 10 / 10."
    )
    add_table(
        doc,
        ["Evaluator", "Correct / in-scope", "Total", "Result"],
        [
            ["match_expected_response (correctness)", "10", "10", "10/10"],
            ["check_answer_scope (relevance)", "10", "10", "10/10"],
        ],
    )
    doc.add_paragraph(
        "Every one of the 10 gold questions was answered correctly by an "
        "agent that had access to nothing but the tools' names, schemas, "
        "and docstrings — no other page context, and no hint about which "
        "tool(s) a given question required. Combined with the "
        "deterministic layer's 14/14, this is strong evidence that the "
        'gap between "tool works" and "an LLM can discover and use the '
        'tool correctly from its schema alone" (the actual thing Criterion '
        "3 measures) is closed for this server, not just assumed closed."
    )

    # ------------------------------------------------------------------
    add_heading(doc, "3. Security Considerations")
    doc.add_paragraph(
        "This server's core job is fetching caller-supplied URLs (an agent, "
        "possibly relaying an untrusted user's request) rather than one "
        "fixed, operator-controlled API — a materially different threat "
        "model than a typical internal-API wrapper, since the attacker "
        "controls the input that becomes an outbound request."
    )
    add_heading(doc, "3.1 SSRF defenses (utils.fetch_url_safely)", level=2)
    add_bullets(
        doc,
        [
            "Allowlists the http/https schemes only.",
            "Resolves the hostname and rejects any address in a "
            "loopback / private / link-local / multicast / reserved / "
            "CGNAT range — this also covers the cloud metadata endpoint, "
            "169.254.169.254.",
            "Disables automatic redirects and re-validates every "
            "redirect hop against the same checks, rather than trusting "
            "the first validated hop.",
            "Disables environment proxies (which could otherwise be used "
            "to reach internal addresses indirectly).",
            "Caps response size to bound memory use against a "
            "malicious or oversized upstream response.",
            "Sanitizes upstream failures before returning them — no raw "
            "tracebacks, headers, or full response bodies reach the "
            "caller.",
        ],
    )
    add_heading(doc, "3.2 Named residual risk — DNS rebinding", level=2)
    doc.add_paragraph(
        "The pre-connect resolve check and the actual HTTP connection are "
        "two separate steps, so an attacker controlling DNS for their own "
        "domain could in principle return a safe IP for the check and a "
        "blocked one for the connection. A full fix needs a connect-time "
        "socket hook that pins the validated IP; this is out of scope for "
        "the hackathon pass and is documented as a comment on "
        "_assert_host_resolves_safely in utils.py rather than silently "
        "assumed away."
    )
    add_heading(doc, "3.3 Other considerations", level=2)
    add_bullets(
        doc,
        [
            "All 15 tools are read-only (readOnlyHint=True, "
            "destructiveHint=False) — the server takes no destructive or "
            "state-changing action against any target.",
            "No secrets are required to run the server itself; credentials "
            "that do exist (AWS Bedrock access for the eval harness, "
            "Databricks service-principal secrets for deployment) are "
            "environment-only and git-ignored, never committed.",
            "Per SECURITY.md, the /mcp endpoint ships without "
            "authentication by default, matching the hackathon's "
            "public-data pilot posture — explicitly flagged as something "
            "to revisit (front with auth, review ATO requirements) before "
            "any non-hackathon use.",
            "Tool error responses are restricted to an {error, hint} shape "
            "that never includes upstream headers, full URLs with query "
            "strings, stack traces, or any other potentially sensitive "
            "upstream detail.",
        ],
    )

    # ------------------------------------------------------------------
    add_heading(doc, "4. Lessons Learned and Recommendations")

    add_heading(doc, "4.1 Lessons learned", level=2)
    add_bullets(
        doc,
        [
            "A single-Pydantic-model tool parameter is not flattened into "
            "top-level arguments by this fastmcp version — the schema (and "
            "therefore every caller, LLM or script) nests it under "
            '"params". This surfaced while building the deterministic '
            "eval and wiring a local chat UI against the real tool "
            "schemas, and is worth calling out explicitly since it's easy "
            "to assume flattening happens by default.",
            "A mismatch in the deterministic eval (Q2) initially looked "
            "like a tool bug — check_page_title appeared to return the "
            "wrong value — but the tool's output was correct all along; "
            "the test was comparing the whole bracketed phrase instead of "
            "the single word that actually differs between the before/"
            "after pages. Lesson: when a gold-data comparison fails, "
            "verify the comparison logic against the raw tool output "
            "before concluding the tool is wrong.",
            "Credential-free, deterministic evaluation against real tool "
            "calls (not mocks) is a cheap, high-value layer that's easy to "
            "under-invest in relative to LLM-judged evaluation — it caught "
            "a real gap (4 of 15 tools had zero evaluation coverage) and a "
            "real test bug before any LLM budget was spent.",
            "Keeping scan_site and scan_page_alt_text as two separate "
            'tools (rather than one tool with a "scan mode" flag) paid '
            "off beyond the API design benefit: it let the evaluation "
            "cross-check one against the other (eval/deterministic, "
            "case 13) as a correctness test that wouldn't exist if there "
            "were only one tool to call.",
            "The Phoenix harness was designed around a generic "
            "OpenAI-compatible gateway (USAI_API_KEY/USAI_BASE_URL) that "
            "never materialized this hackathon — but AWS Bedrock access "
            "was already present in the environment the whole time. "
            "Pivoting agent.py and the judges from ChatOpenAI/"
            "phoenix.evals' openai provider to langchain_aws."
            "ChatBedrockConverse and phoenix.evals' litellm-backed bedrock "
            "provider took under an hour, once recognized as an option. "
            'Lesson: "blocked on an LLM gateway" and "blocked on any '
            'LLM access" are not the same claim — worth checking what '
            "credentials are already available before assuming a hard "
            "external dependency.",
            "Two environment-specific gotchas surfaced only by actually "
            "running the harness, not by reading its code: (1) this "
            "network's TLS-inspecting proxy makes a bare `uv run` fail its "
            "own dependency-resolution check before the MCP subprocess "
            'ever starts, surfacing as an opaque "Connection closed" '
            "from the MCP client with no mention of TLS — fixed by passing "
            "UV_SYSTEM_CERTS=1 in that subprocess's env; (2) Phoenix's own "
            "progress-indicator emoji crash Python's default stdout "
            "encoding on Windows (cp1252) — fixed by forcing "
            "PYTHONIOENCODING=utf-8/PYTHONUTF8=1. Neither is a bug in this "
            "server; both would silently block anyone re-running the "
            "harness on a similar Windows/corporate-proxy setup without "
            "this note.",
        ],
    )

    add_heading(doc, "4.2 Recommendations", level=2)
    add_bullets(
        doc,
        [
            "eval/deterministic/run_tool_eval.py is now wired into "
            ".gitlab-ci.yml as a CI step (needs no credentials, completes "
            "in well under a minute) alongside ruff + pytest — a live "
            "regression in the W3C WAI demo pages' content or in any "
            "tool's parsing logic now fails CI instead of going unnoticed.",
            "Re-run eval/phoenix/run_experiment.py periodically (e.g. "
            "before any future submission/demo), not just once — its "
            "gold answers depend on the live content of two external W3C "
            "pages this project doesn't control, and an LLM-judged score "
            "can drift with model updates in a way a deterministic test "
            "cannot.",
            "If this server moves beyond hackathon scope: add a "
            "connect-time socket hook to close the named DNS-rebinding "
            "gap, and front the /mcp endpoint with authentication per "
            "SECURITY.md's hackathon note.",
        ],
    )

    doc.save(str(OUT_PATH))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
