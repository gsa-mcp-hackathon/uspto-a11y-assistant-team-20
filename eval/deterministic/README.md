# Deterministic tool-level evaluation

`eval/phoenix/` measures whether an LLM *agent* can pick the right tool
given only its name/schema/docstring — that requires a real model for both
the agent and the judges (AWS Bedrock credentials). This
harness measures the other half: **do the tools themselves return
correct, well-formed answers** — with no LLM anywhere in the loop, so it
runs with zero credentials.

## Methodology

`run_tool_eval.py` covers all **15 of 15** tools the server exposes, in
two parts:

**Q1-Q10** reuse the same 10 gold question/answer pairs as
`eval/phoenix/datasets/alt-text-eval-0/evaluation.xml` (13 tools — one
question exercises 4 checks at once), but
instead of routing them through an LLM agent, it:

1. Reads each question to determine, by hand, which tool(s) a correct
   answer requires (e.g. "which page has more tables" → `check_table_headers`
   on both URLs, compare `totalTablesOnPage`).
2. Calls those tools **directly and in-process** via `fastmcp.Client`
   against the real `alt_text_mcp` server object — no subprocess, no
   mocking, no Databricks dependency.
3. Each call hits the real network: the live W3C WAI "before"/"after"
   accessibility teaching demo pages
   (`https://www.w3.org/WAI/demos/bad/{before,after}/home.html`).
4. Extracts the relevant field from each tool's real JSON response with
   plain Python and asserts it against the gold answer.

**Q11-Q14** cover the remaining 4 tools — `fetch_image` and `scan_site` —
which Phoenix deliberately excludes because their outputs (raw image
bytes, a multi-page crawl summary) don't reduce to a single stable,
string-comparable gold answer. Instead of a gold string, these are
checked with structural assertions against real calls:

- `fetch_image`: a real image URL returns genuine `image/png` content
  (Q11); a non-image URL returns a graceful `{error, hint}` dict instead
  of a crash (Q12).
- `scan_site`: its entry for the start page is byte-for-byte identical to
  an independent `scan_page_alt_text` call on the same URL — the same
  underlying scan reached through two different entry points (Q13) — and
  it respects the `max_pages` cap and only follows same-origin links
  (Q14).

This is complementary to, not a replacement for, `eval/phoenix/`: this
harness validates tool *correctness* against curated gold data (and, for
the two tools gold data doesn't fit, structural invariants) over a live
network; Phoenix (once credentials are available) validates agent *tool
selection* quality. Together they cover both halves of Criterion 2.

## Running it

No setup beyond the root project's own `uv sync` — no extra dependencies,
no `.env` values required:

```bash
uv run python eval/deterministic/run_tool_eval.py
```

## Results (latest run)

**14/14 passed — all 15 tools exercised.** Full detail, including every
tool's raw field values, is in [`results.json`](results.json). Summary:

| # | Question | Tool(s) | Expected | Actual |
|---|----------|---------|----------|--------|
| 1 | Missing-alt-text count decrease, before→after | `scan_page_alt_text` | 17 | 17 |
| 2 | Differing word in `<title>` brackets | `check_page_title` | Inaccessible | Inaccessible |
| 3 | `lang` value present on exactly one page | `check_lang_attribute` | en | en |
| 4 | Page whose `<select>` is unlabeled | `check_form_labels` | before | before |
| 5 | Page with a detectable skip-navigation link | `check_landmarks` | after | after |
| 6 | Table-count difference, before − after | `check_table_headers` | 10 | 10 |
| 7 | Page with a "multiple-h1" issue | `check_heading_structure` | after | after |
| 8 | Page with more elements carrying an `id` | `check_duplicate_ids` | after | after |
| 9 | Shared href of the two "Click here" links | `check_link_text` | w3.org/.../offsite.html | matched |
| 10 | Any nonzero finding across iframe/media/aria/contrast checks | `check_iframe_titles`, `check_media_captions`, `check_aria_conflicts`, `check_color_contrast` | False | False |
| 11 | Real image URL returns genuine image content | `fetch_image` | image/png, non-empty | image/png, 2376 bytes |
| 12 | Non-image URL returns a graceful error, not a crash | `fetch_image` | `{error, hint}` dict | matched |
| 13 | Start-page scan matches an independent `scan_page_alt_text` call | `scan_site`, `scan_page_alt_text` | identical | identical |
| 14 | Respects `max_pages` cap and same-origin-only crawling | `scan_site` | ≤3 pages, same-origin | 3 pages, same-origin |

One early iteration of this harness (not shown above) initially mismatched
Q2 by comparing the whole bracketed phrase instead of the single word that
differs between the before/after titles — a bug in the *test's* comparison
logic, not the tool. `check_page_title` had already returned the fully
correct title text in both runs; fixing the comparison to diff the two
titles' bracket content word-by-word resolved it. Kept here as the one
concrete example of this harness catching (and self-correcting) a mismatch
during development.

## Coverage note

All 15 of the repo's tools are exercised: the 11 covered by
`alt-text-eval-0`'s gold Q&A (Q1-Q10 above; `scan_page_alt_text` is
exercised twice, in Q1 and again independently in Q13), plus `fetch_image`
and `scan_site` (Q11-Q14) via structural assertions instead of a gold
string, for the same reason Phoenix excludes them — their outputs don't
reduce to a single stable, string-comparable answer.
