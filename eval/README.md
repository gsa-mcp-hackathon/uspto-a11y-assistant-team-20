# Evaluations

Two local, pre-deploy harnesses are built here, covering the two things that
can independently go wrong with an MCP server: whether the *tools* are
correct, and whether an *agent* can find and use them correctly.

## Why evaluate?

The quality of an MCP server is **not** how many tools it has — it's how well an
LLM with no other context can use those tools (their names, schemas, docstrings,
and return shapes) to answer realistic, difficult questions, *and* whether the
tools themselves return correct, well-formed answers. One harness measures
each of those two things.

## [`eval/deterministic/`](deterministic/README.md) — tool correctness, no LLM required

Calls all 15 tools directly and in-process (via `fastmcp.Client` against the
live server object — no subprocess, no credentials) against real gold
question/answer pairs and structural invariants, hitting the real network.
14/14 cases passing. Run it any time with:

```bash
uv run python eval/deterministic/run_tool_eval.py
```

## [`eval/phoenix/`](phoenix/README.md) — agent tool-selection quality

An [Arize Phoenix](https://docs.arize.com/phoenix) harness that:

1. Launches the MCP server over stdio and connects a LangChain agent to it.
2. Feeds the agent a dataset of natural-language questions with known answers
   (`alt-text-eval-0`: 10 questions covering 13 tools).
3. Scores each answer with LLM-as-judge evaluators (correctness, relevance)
   and logs traces to Phoenix.

Run via AWS Bedrock credentials (`AGENT_MODEL`/`JUDGE_MODEL` +
`AWS_PROFILE`/`AWS_REGION` in the root `.env`) — no separate gateway API key
needed. Latest run: 10/10 correctness, 10/10 relevance — see
[eval/phoenix/README.md](phoenix/README.md) for setup and the exact commands.

## Layout

```
eval/
├── deterministic/
│   ├── run_tool_eval.py  # No-LLM tool-correctness checks (all 15 tools)
│   └── results.json      # Latest run's results
└── phoenix/
    ├── agent.py            # AltTextAgent — launches the server over stdio
    ├── create_dataset.py   # CLI: upload a CSV dataset to Phoenix
    ├── run_experiment.py   # CLI: run agent + judges against a dataset
    ├── datasets.yaml       # Dataset registry
    ├── judges/             # LLM-as-judge evaluators (correctness, relevance)
    ├── prompts/            # Versioned agent system prompts
    └── datasets/alt-text-eval-0/  # evaluation.xml (source) + examples/*.csv
```
