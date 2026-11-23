"""check_answer_scope — LLM-as-judge relevance/scope evaluator.

Judges whether the agent answered within the bounds of what alt-text-mcp's
tools can actually determine, rather than refusing an in-scope question or
wandering off-task. No ground-truth reference is needed.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Verified against the installed arize-phoenix-evals (3.x) — see
# judges/correctness_judge.py for the API notes.
from phoenix.evals import LLM, ClassificationEvaluator

load_dotenv()

_SCOPE_DESCRIPTION = """\
The agent being judged is a web-accessibility analyst. It can answer a
question ONLY by calling tools that scan a given page or site (specified by
URL, either given directly in the question or discovered via the tools, e.g.
scan_site) for: missing/low-quality image alt text, heading structure,
non-descriptive link text, form field labeling, ARIA landmarks and
skip-navigation links, duplicate element ids, table header cells, the root
lang attribute, the <title> element, iframe titles, video/audio caption
tracks, conflicting/invalid ARIA usage, or low-contrast inline styles —
including questions that compare two or more pages against each other (e.g.
"before" vs. "after" pages).

Anything requiring information these tools cannot provide is OUT of scope:
rendering JavaScript-driven content, visual layout judgments beyond what the
image-fetching tool's raw bytes show, subjective opinions or design
recommendations beyond what a tool literally reports, or page content
unrelated to accessibility structure.
"""

_SCOPE_PROMPT_TEMPLATE = (
    _SCOPE_DESCRIPTION
    + """

Question asked of the agent:
{input}

Agent's answer:
{output}

Judge whether the agent's answer stayed within scope: did it attempt to
directly answer an in-scope accessibility question using tool-derived
evidence (even if the specific value turns out to be wrong — correctness is
judged separately)? That counts as "within_scope".

If instead the agent refused to answer an in-scope question, deflected,
answered a different question than the one asked, or fabricated an answer
without apparent grounding in tool output, judge it "out_of_scope".

Respond with exactly one phrase: "within_scope" or "out_of_scope".
"""
)

_CHOICES = {"within_scope": 1, "out_of_scope": 0}

_evaluator: ClassificationEvaluator | None = None


def _get_evaluator() -> ClassificationEvaluator:
    """Lazily build the judge so JUDGE_MODEL/AWS_* env vars are read after
    load_dotenv() has had a chance to populate them."""
    global _evaluator
    if _evaluator is None:
        llm = LLM(
            provider="bedrock",
            model=os.getenv("JUDGE_MODEL"),
            temperature=0.0,
        )
        _evaluator = ClassificationEvaluator(
            name="relevance",
            prompt_template=_SCOPE_PROMPT_TEMPLATE,
            llm=llm,
            choices=_CHOICES,
        )
    return _evaluator


def check_answer_scope(input: dict, output: str, **kwargs):
    """Phoenix evaluator: did the agent stay within the tools' answerable scope?

    `**kwargs` absorbs extra keyword arguments (e.g. `expected`, `metadata`)
    that `run_experiment` passes to every evaluator but this judge ignores.

    Returns a single classification label ("within_scope" / "out_of_scope").
    """
    evaluator = _get_evaluator()
    result = evaluator.evaluate({"input": input["query"], "output": output})
    return result[0].label
