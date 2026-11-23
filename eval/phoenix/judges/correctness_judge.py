"""match_expected_response — LLM-as-judge correctness evaluator.

Compares the agent-under-test's answer to the dataset's ground-truth answer for
the original question, tolerating cosmetic formatting differences.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Verified against the installed arize-phoenix-evals (3.x): `LLM(provider=,
# model=, **kwargs)` forwards api_key/base_url to the underlying SDK client,
# and `ClassificationEvaluator.evaluate(eval_input: dict) -> list[Score]`
# takes one record dict and returns `Score` objects (read `.label`).
from phoenix.evals import LLM, ClassificationEvaluator

load_dotenv()

_CORRECTNESS_PROMPT_TEMPLATE = """\
You are grading whether an AI agent's answer to a web-accessibility question is
correct, compared against a known-correct reference answer.

Question asked of the agent:
{input}

Agent's answer:
{output}

Reference (ground-truth) answer:
{reference}

These answers are short and simple: a number, a single word, a URL, or
"True"/"False". Tolerate reasonable formatting differences — extra prose or
context wrapped around the answer, case differences (e.g. "before" vs.
"Before"), minor punctuation, or restating the question. Do NOT mark an answer
wrong for cosmetic reasons alone.

Judge the answer "correct" only if the core value from the reference answer is
clearly and unambiguously present in the agent's answer. Judge it "incorrect"
if that core value is missing, contradicted, or a different value is given
instead.

Respond with exactly one word: "correct" or "incorrect".
"""

_CHOICES = {"correct": 1, "incorrect": 0}

_evaluator: ClassificationEvaluator | None = None


def _get_evaluator() -> ClassificationEvaluator:
    """Lazily build the judge so JUDGE_MODEL/AWS_* env vars are read after
    load_dotenv() has had a chance to populate them (e.g. when this module is
    imported before a caller's own load_dotenv() runs)."""
    global _evaluator
    if _evaluator is None:
        llm = LLM(
            provider="bedrock",
            model=os.getenv("JUDGE_MODEL"),
            temperature=0.0,
        )
        _evaluator = ClassificationEvaluator(
            name="correctness",
            prompt_template=_CORRECTNESS_PROMPT_TEMPLATE,
            llm=llm,
            choices=_CHOICES,
        )
    return _evaluator


def match_expected_response(input: dict, output: str, expected: dict, **kwargs):
    """Phoenix evaluator: does `output` match `expected["responses"]` for the query?

    `run_experiment` calls evaluators with `output=`/`expected=`/`metadata=`/
    `input=` keyword arguments (per `phoenix.client`'s `Evaluator` protocol);
    `**kwargs` absorbs any of those (e.g. `metadata`) this judge doesn't need.

    Returns a single classification label ("correct" / "incorrect").
    """
    evaluator = _get_evaluator()
    result = evaluator.evaluate(
        {
            "input": input["query"],
            "output": output,
            "reference": expected["responses"],
        }
    )
    # ClassificationEvaluator.evaluate returns a list of Score objects even
    # for a single record; the classification label lives on `.label`.
    return result[0].label
