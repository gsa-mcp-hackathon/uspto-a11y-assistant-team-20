"""CLI: run the AltTextAgent + judges against a registered Phoenix dataset.

Run from eval/phoenix/ (after `uv sync --group dev`, populating .env, and
`uv run arize-phoenix serve` in another terminal):

    uv run run_experiment.py --dataset-name alt-text-eval-0
    uv run run_experiment.py --dataset-name alt-text-eval-0 --system-prompt-version v2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import yaml
from agent import AltTextAgent
from dotenv import load_dotenv
from judges import check_answer_scope, match_expected_response

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REGISTRY_PATH = os.path.join(_THIS_DIR, "datasets.yaml")

# Keep in sync with the files that actually exist in prompts/.
_PROMPT_VERSION_CHOICES = ["v1", "v2"]


def _load_registry() -> dict:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-name",
        required=True,
        help="Dataset name as registered in datasets.yaml and in Phoenix.",
    )
    parser.add_argument(
        "--system-prompt-version",
        choices=_PROMPT_VERSION_CHOICES,
        default="v1",
        help="Which prompts/system_prompt_{version}.txt the agent should use.",
    )
    parser.add_argument(
        "--project-name",
        default="alt-text-mcp-eval",
        help="Phoenix project name traces/experiments are grouped under.",
    )
    parser.add_argument(
        "--phoenix-endpoint",
        default="http://localhost:6006",
        help="Phoenix client/UI base URL (separate from the OTLP collector endpoint).",
    )
    parser.add_argument(
        "--experiment-description",
        default=None,
        help="Optional free-text description stored with the experiment.",
    )
    parser.add_argument(
        "--dataset-version-id",
        default=None,
        help="Optional specific dataset version to run against (defaults to latest).",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip the dataset client's own validation step, if it has one.",
    )
    args = parser.parse_args()

    load_dotenv()

    registry = _load_registry()
    datasets = registry.get("datasets", {})
    if args.dataset_name not in datasets:
        print(
            f"Dataset '{args.dataset_name}' is not registered in datasets.yaml. "
            f"Known datasets: {sorted(datasets)}",
            file=sys.stderr,
        )
        return 1

    # Verified against the installed arize-phoenix-client: `get_dataset` takes
    # `dataset=` (a name, Dataset, or dict), not `name=`; `run_experiment`'s
    # `dataset`/`task` params are keyword-only.
    from phoenix.client import Client

    client = Client(base_url=args.phoenix_endpoint)

    get_dataset_kwargs = {"dataset": args.dataset_name}
    if args.dataset_version_id:
        get_dataset_kwargs["version_id"] = args.dataset_version_id
    dataset = client.datasets.get_dataset(**get_dataset_kwargs)

    if not args.no_validate and hasattr(dataset, "validate"):
        dataset.validate()

    agent = AltTextAgent(
        system_prompt_version=args.system_prompt_version,
        project_name=args.project_name,
    )
    asyncio.run(agent.initialize())

    experiment_name = f"{args.dataset_name}-{args.system_prompt_version}"
    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=agent.create_experiment_task(),
        evaluators=[check_answer_scope, match_expected_response],
        experiment_name=experiment_name,
        experiment_description=args.experiment_description,
    )

    print(f"Experiment '{experiment_name}' finished.")
    print(f"Dataset: {args.dataset_name} | system prompt: {args.system_prompt_version}")
    print(f"Experiment result object: {experiment}")
    print(f"Review traces and scores in the Phoenix UI: {args.phoenix_endpoint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
