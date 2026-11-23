# alt-text-mcp evaluation harness (Phoenix)

This harness measures whether an LLM with access to **only** alt-text-mcp's 15
tools — no other context about any page — can correctly answer the 10 gold
questions in [`datasets/alt-text-eval-0/`](datasets/alt-text-eval-0/). It is not
a test of the tools' implementation correctness directly; it's a test of
whether the tools' names, schemas, docstrings, and return shapes give an agent
enough to work with.

## What `alt-text-eval-0` covers

10 questions exercising **13 of the 15** tools (one question exercises 4
checks at once), built around before/after
comparisons on the stable W3C WAI accessibility teaching demo pages
(`https://www.w3.org/WAI/demos/bad/{before,after}/home.html`). `fetch_image`
and `scan_site` are intentionally not covered — their outputs (raw image
bytes, a multi-page crawl summary) don't reduce to a single stable,
string-comparable gold answer the way a count, a word, a URL, or a
True/False does.

## Setup

1. Populate a root-level `.env` from [`.env.example`](../../.env.example) —
   you need `AGENT_MODEL` and `JUDGE_MODEL` (AWS Bedrock model ids or
   application-inference-profile ARNs) plus `AWS_PROFILE`/`AWS_REGION`.
   Models run via AWS Bedrock using standard boto3 credential resolution —
   no separate API key. The alt-text-mcp server itself needs no credentials.
2. Install this harness's dependencies into its **own** isolated environment
   (this directory has its own `pyproject.toml` — it is a separate uv project
   from the repo root, not the root's `dev` dependency group):
   ```bash
   cd eval/phoenix
   uv sync
   ```
   **Why isolated:** `langchain-mcp-adapters` requires `mcp<2.0.0`, while the
   server's own `fastmcp>=2.0.0` requires `mcp>=2.0.0` — those two can't be
   installed into the same venv. Keeping this harness in its own project
   sidesteps the conflict entirely: `agent.py` still launches the real server
   via `uv run python main.py` with `cwd` set to the repo root, so that
   subprocess resolves and uses the *root* project's own venv (fastmcp +
   mcp 2.x) — only `agent.py`'s own process (the LangChain *client* side)
   needs the older `mcp` client library, and it gets it from
   `eval/phoenix/.venv`, never the root one.
3. If `uv sync` fails with a TLS/certificate error (common behind a corporate
   TLS-inspecting proxy), retry with `uv sync --native-tls` (or the current
   `--system-certs` flag) to trust the OS certificate store instead of uv's
   bundled CA list.

Run everything below from this directory (`eval/phoenix/`).

## Workflow

1. **Start Phoenix** (UI at `:6006`, OTLP collector at `:4317`):
   ```bash
   uv run arize-phoenix serve
   ```

2. **Create the dataset in Phoenix** (one-time per dataset):
   ```bash
   uv run create_dataset.py --dataset-name alt-text-eval-0
   # validate the CSV's columns without uploading:
   uv run create_dataset.py --dataset-name alt-text-eval-0 --dry-run
   ```

3. **Run an experiment** (agent + judges against the dataset):
   ```bash
   uv run run_experiment.py --dataset-name alt-text-eval-0
   # try the scope-boundary system prompt instead:
   uv run run_experiment.py --dataset-name alt-text-eval-0 --system-prompt-version v2
   ```

4. **Review results** in the Phoenix UI at <http://localhost:6006>. Each run
   logs per-question traces (every tool call the agent made) alongside the
   `correctness` and `relevance` judge scores. Inspect failing cases to decide
   whether the fix belongs in a tool's schema/docstring, the system prompt, or
   the question itself.

**Latest run:** 10/10 correctness, 10/10 relevance — see
[`results.json`](results.json) for the summary.

**On Windows, if `run_experiment.py` crashes with a `UnicodeEncodeError`**
pointing at an emoji: Phoenix's own progress output doesn't survive the
default `cp1252` console encoding. Run with
`PYTHONIOENCODING=utf-8 PYTHONUTF8=1` set.

## Layout

```
eval/phoenix/
├── agent.py                 # AltTextAgent — launches alt-text-mcp (main.py) over stdio
├── create_dataset.py        # CLI: upload a CSV dataset to Phoenix
├── run_experiment.py        # CLI: run agent + judges against a dataset
├── datasets.yaml            # Dataset registry
├── judges/
│   ├── correctness_judge.py # match_expected_response — compares to ground truth
│   └── relevance_judge.py   # check_answer_scope — in-scope vs. out-of-scope
├── prompts/
│   ├── system_prompt_v1.txt # basic domain analyst
│   └── system_prompt_v2.txt # + explicit scope boundaries
└── datasets/
    └── alt-text-eval-0/
        ├── evaluation.xml           # source Q&A pairs
        └── examples/alt-text-eval-0.csv
```
