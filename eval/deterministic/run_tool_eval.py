"""Deterministic tool-level evaluation — all 15 alt-text-mcp tools.

eval/phoenix/ measures whether an LLM agent can pick the right tools given
only their names/schemas/docstrings — it needs a real model (AWS Bedrock
credentials) for both the agent and the judges. This script measures the
other half: whether the tools themselves return correct, well-formed
answers. It calls the real tools in-process (via fastmcp's Client, talking
directly to the live alt-text-mcp server object — no subprocess, no
Databricks) — no LLM involved anywhere in this script.

Q1-Q10 reuse the 10 gold question/answer pairs in
eval/phoenix/datasets/alt-text-eval-0/evaluation.xml (13 of the 15 tools —
one question exercises 4 checks at once), checking each tool's raw JSON
output against the gold answer with plain Python. Q11-Q14 cover the
remaining 2 tools — fetch_image and scan_site — which Phoenix deliberately
excludes because their outputs (raw image bytes,
a multi-page crawl summary) don't reduce to a single stable,
string-comparable gold answer; here they're checked with structural
assertions instead (correct success/error shape for fetch_image; exact
cross-check against an independent scan_page_alt_text call plus
same-origin/max-pages invariants for scan_site).

Run from the repo root (so the alt_text_mcp package resolves):
    uv run python eval/deterministic/run_tool_eval.py
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fastmcp import Client

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from alt_text_mcp.app import mcp as _server  # noqa: E402


def _git_commit() -> str:
    """The commit this run evaluated, for traceability in results.json."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"

BEFORE = "https://www.w3.org/WAI/demos/bad/before/home.html"
AFTER = "https://www.w3.org/WAI/demos/bad/after/home.html"


@dataclass
class CaseResult:
    question: str
    expected: str
    actual: str
    passed: bool
    detail: str = ""


def _pick_page(before_flag: bool, after_flag: bool) -> str:
    if before_flag and after_flag:
        return "both"
    if before_flag:
        return "before"
    if after_flag:
        return "after"
    return "neither"


async def _call(client: Client, name: str, url: str, **extra) -> dict:
    result = await client.call_tool(name, {"params": {"url": url, **extra}})
    return result.data


async def run_cases(client: Client) -> list[CaseResult]:
    cases: list[CaseResult] = []

    # Q1 — missing-alt-text count decrease, before -> after
    alt_before = await _call(client, "scan_page_alt_text", BEFORE)
    alt_after = await _call(client, "scan_page_alt_text", AFTER)
    decrease = alt_before["summary"]["missing"] - alt_after["summary"]["missing"]
    cases.append(
        CaseResult(
            "Missing-alt-text count decrease, before -> after",
            "17",
            str(decrease),
            decrease == 17,
            f"before.missing={alt_before['summary']['missing']} "
            f"after.missing={alt_after['summary']['missing']}",
        )
    )

    # Q2 — the one word that differs between the two pages' bracketed <title> suffix
    title_before = await _call(client, "check_page_title", BEFORE)
    title_after = await _call(client, "check_page_title", AFTER)

    def _bracket_words(title: str | None) -> list[str]:
        match = re.search(r"\[([^\]]+)\]", title or "")
        return match.group(1).split() if match else []

    before_words, after_words = (
        _bracket_words(title_before["title"]),
        _bracket_words(title_after["title"]),
    )
    differing_word = next(
        (b for b, a in zip(before_words, after_words) if b != a), None
    )
    cases.append(
        CaseResult(
            "The one word that differs between before/after <title> brackets",
            "Inaccessible",
            str(differing_word),
            differing_word == "Inaccessible",
            f"before_title={title_before['title']!r} "
            f"after_title={title_after['title']!r}",
        )
    )

    # Q3 — lang value present on exactly one page
    lang_before = await _call(client, "check_lang_attribute", BEFORE)
    lang_after = await _call(client, "check_lang_attribute", AFTER)
    before_lang, after_lang = lang_before.get("lang"), lang_after.get("lang")
    if before_lang and not after_lang:
        unique = before_lang
    elif after_lang and not before_lang:
        unique = after_lang
    else:
        unique = None
    cases.append(
        CaseResult(
            "lang value present on exactly one page, absent on the other",
            "en",
            str(unique),
            unique == "en",
            f"before_lang={before_lang!r} after_lang={after_lang!r}",
        )
    )

    # Q4 — which page's <select> is unlabeled
    form_before = await _call(client, "check_form_labels", BEFORE)
    form_after = await _call(client, "check_form_labels", AFTER)
    unlabeled_page = _pick_page(
        any(f["status"] == "unlabeled" for f in form_before["fields"]),
        any(f["status"] == "unlabeled" for f in form_after["fields"]),
    )
    cases.append(
        CaseResult(
            "Page whose <select> field is 'unlabeled'",
            "before",
            unlabeled_page,
            unlabeled_page == "before",
            f"before_fields={form_before['fields']} "
            f"after_fields={form_after['fields']}",
        )
    )

    # Q5 — which page has a detectable skip-navigation link
    land_before = await _call(client, "check_landmarks", BEFORE)
    land_after = await _call(client, "check_landmarks", AFTER)
    skip_page = _pick_page(land_before["hasSkipLink"], land_after["hasSkipLink"])
    cases.append(
        CaseResult(
            "Page with a detectable skip-navigation link",
            "after",
            skip_page,
            skip_page == "after",
            f"before_skip={land_before['hasSkipLink']} "
            f"after_skip={land_after['hasSkipLink']}",
        )
    )

    # Q6 — table-count difference, before minus after
    tables_before = await _call(client, "check_table_headers", BEFORE)
    tables_after = await _call(client, "check_table_headers", AFTER)
    diff = tables_before["totalTablesOnPage"] - tables_after["totalTablesOnPage"]
    cases.append(
        CaseResult(
            "Table-count difference, before minus after",
            "10",
            str(diff),
            diff == 10,
            f"before={tables_before['totalTablesOnPage']} "
            f"after={tables_after['totalTablesOnPage']}",
        )
    )

    # Q7 — which page's heading outline includes a 'multiple-h1' issue
    head_before = await _call(client, "check_heading_structure", BEFORE)
    head_after = await _call(client, "check_heading_structure", AFTER)

    def _has_multi_h1(result: dict) -> bool:
        return any(issue.startswith("multiple-h1") for issue in result["issues"])

    multi_h1_page = _pick_page(_has_multi_h1(head_before), _has_multi_h1(head_after))
    cases.append(
        CaseResult(
            "Page whose heading outline includes a 'multiple-h1' issue",
            "after",
            multi_h1_page,
            multi_h1_page == "after",
            f"before_issues={head_before['issues']} "
            f"after_issues={head_after['issues']}",
        )
    )

    # Q8 — which page has more elements carrying an id attribute
    ids_before = await _call(client, "check_duplicate_ids", BEFORE)
    ids_after = await _call(client, "check_duplicate_ids", AFTER)
    before_count = ids_before["totalIdsOnPage"]
    after_count = ids_after["totalIdsOnPage"]
    if after_count > before_count:
        more_ids_page = "after"
    elif before_count > after_count:
        more_ids_page = "before"
    else:
        more_ids_page = "tie"
    cases.append(
        CaseResult(
            "Page with more total elements carrying an id attribute",
            "after",
            more_ids_page,
            more_ids_page == "after",
            f"before={before_count} after={after_count}",
        )
    )

    # Q9 — shared href of the two 'Click here' links on the before page
    links_before = await _call(client, "check_link_text", BEFORE, limit=200)
    click_here_hrefs = {
        link["href"]
        for link in links_before["links"]
        if link["text"] and link["text"].strip().lower() == "click here"
    }
    shared_href = click_here_hrefs.pop() if len(click_here_hrefs) == 1 else None
    cases.append(
        CaseResult(
            "Shared href of the two 'Click here' links on the before page",
            "https://www.w3.org/WAI/demos/bad/offsite.html",
            str(shared_href),
            shared_href == "https://www.w3.org/WAI/demos/bad/offsite.html",
            f"click_here_hrefs="
            f"{click_here_hrefs if not shared_href else {shared_href}}",
        )
    )

    # Q10 — across iframe/media/aria/contrast checks on both pages, any nonzero count?
    any_issue = False
    detail_parts = []
    for url in (BEFORE, AFTER):
        iframe = await _call(client, "check_iframe_titles", url)
        media = await _call(client, "check_media_captions", url)
        aria = await _call(client, "check_aria_conflicts", url)
        contrast = await _call(client, "check_color_contrast", url)
        counts = {
            "iframe_missing": iframe["summary"]["missing"],
            "media_missing_or_manual": (
                media["summary"]["missingCaptions"]
                + media["summary"]["needsManualCheck"]
            ),
            "aria_total": sum(aria["summary"].values()),
            "contrast_low": contrast["summary"]["lowContrastCount"],
        }
        detail_parts.append(f"{url}: {counts}")
        if any(v > 0 for v in counts.values()):
            any_issue = True
    cases.append(
        CaseResult(
            "Any nonzero count across iframe/media/aria/contrast checks on either page",
            "False",
            str(any_issue),
            any_issue is False,
            "; ".join(detail_parts),
        )
    )

    # Q11 — fetch_image success path: a real image URL comes back as image content
    image_url = "https://www.w3.org/WAI/demos/bad/img/w3c.png"
    image_result = await client.call_tool("fetch_image", {"params": {"url": image_url}})
    image_block = image_result.content[0] if image_result.content else None
    image_ok = (
        not image_result.is_error
        and image_block is not None
        and getattr(image_block, "type", None) == "image"
        and getattr(image_block, "mime_type", None) == "image/png"
        and bool(getattr(image_block, "data", None))
    )
    cases.append(
        CaseResult(
            "fetch_image returns real PNG image content for a direct image URL",
            "type=image, mime_type=image/png, non-empty data",
            (
                f"type={getattr(image_block, 'type', None)} "
                f"mime_type={getattr(image_block, 'mime_type', None)} "
                f"data_len={len(getattr(image_block, 'data', '') or '')}"
            ),
            image_ok,
            f"url={image_url} is_error={image_result.is_error}",
        )
    )

    # Q12 — fetch_image error path: a non-image URL comes back as a graceful error dict
    bad_fetch = await _call(client, "fetch_image", BEFORE)
    fetch_error_ok = (
        isinstance(bad_fetch, dict)
        and "error" in bad_fetch
        and "hint" in bad_fetch
        and "image" in bad_fetch["error"].lower()
    )
    cases.append(
        CaseResult(
            "fetch_image returns a graceful {error, hint} dict for a non-image URL",
            "{'error': ..., 'hint': ...} mentioning 'image', not a crash",
            str(bad_fetch),
            fetch_error_ok,
            f"url={BEFORE}",
        )
    )

    # Q13 — scan_site's own start-page entry exactly matches an independent
    # scan_page_alt_text call on the same URL (same underlying scan, two entry points)
    site_result = await _call(
        client, "scan_site", BEFORE, max_pages=3, limit_per_page=20
    )
    direct_scan = await _call(client, "scan_page_alt_text", BEFORE, limit=20)
    start_page_entry = site_result["pages"][0] if site_result.get("pages") else {}
    fields_match = all(
        start_page_entry.get(key) == direct_scan.get(key)
        for key in ("images", "summary", "totalImagesOnPage", "imagesReturned")
    )
    cases.append(
        CaseResult(
            "scan_site's start-page scan matches an independent "
            "scan_page_alt_text call",
            "identical images/summary for the start URL",
            "match" if fields_match else "mismatch",
            fields_match,
            f"site_summary={start_page_entry.get('summary')} "
            f"direct_summary={direct_scan.get('summary')}",
        )
    )

    # Q14 — scan_site respects max_pages and only follows same-origin links
    succeeded_pages = [p for p in site_result.get("pages", []) if "error" not in p]
    origin = "https://www.w3.org"
    within_cap = len(site_result.get("pages", [])) <= 3
    same_origin = all(p["url"].startswith(origin) for p in succeeded_pages)
    covers_start_page = site_result.get("summary", {}).get("totalMissing", -1) >= 17
    structural_ok = within_cap and same_origin and covers_start_page
    cases.append(
        CaseResult(
            "scan_site respects max_pages=3 and only follows same-origin links",
            "<=3 pages, all same-origin, totalMissing >= 17",
            f"pages={len(site_result.get('pages', []))} same_origin={same_origin} "
            f"totalMissing={site_result.get('summary', {}).get('totalMissing')}",
            structural_ok,
            f"pagesSkipped={site_result.get('pagesSkipped')}",
        )
    )

    return cases


async def main() -> None:
    async with Client(_server) as client:
        results = await run_cases(client)

    passed = sum(1 for r in results if r.passed)
    print(f"{passed}/{len(results)} passed\n")
    for i, r in enumerate(results, 1):
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] Q{i}: {r.question}")
        print(f"       expected={r.expected!r} actual={r.actual!r}")
        if r.detail:
            print(f"       detail: {r.detail}")
        print()

    report = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "evaluated_at_commit": _git_commit(),
        "cases": [
            {
                "question": r.question,
                "expected": r.expected,
                "actual": r.actual,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in results
        ],
    }
    out_path = Path(__file__).with_name("results.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Results written to {out_path}")

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
