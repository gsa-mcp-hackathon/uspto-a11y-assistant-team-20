"""CLI: upload a registered eval/phoenix dataset CSV to Phoenix.

Examples:
    uv run create_dataset.py --list
    uv run create_dataset.py --dataset-name alt-text-eval-0
    uv run create_dataset.py --dataset-name alt-text-eval-0 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import yaml
from dotenv import load_dotenv

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REGISTRY_PATH = os.path.join(_THIS_DIR, "datasets.yaml")


def _load_registry() -> dict:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _print_list(registry: dict) -> None:
    datasets = registry.get("datasets", {})
    if not datasets:
        print("No datasets registered in datasets.yaml.")
        return
    print("Registered datasets:")
    for name, entry in datasets.items():
        description = entry.get("description", "(no description)")
        print(f"  - {name}: {description}")


def _resolve_csv_path(entry: dict, override: str | None) -> str:
    if override:
        return override
    return os.path.join(_THIS_DIR, entry["csv_path"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print registered dataset names and descriptions, then exit.",
    )
    parser.add_argument(
        "--dataset-name",
        help="Dataset name as registered in datasets.yaml (required unless --list).",
    )
    parser.add_argument(
        "--phoenix-name",
        help="Name to use for the dataset in Phoenix (defaults to --dataset-name).",
    )
    parser.add_argument(
        "--csv-path",
        help="Override the registry's csv_path (useful for testing a new CSV).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the CSV's columns and print a row count; do not upload.",
    )
    args = parser.parse_args()

    registry = _load_registry()

    if args.list:
        _print_list(registry)
        return 0

    if not args.dataset_name:
        parser.error("--dataset-name is required unless --list is given.")

    datasets = registry.get("datasets", {})
    if args.dataset_name not in datasets:
        print(
            f"Dataset '{args.dataset_name}' is not registered in datasets.yaml. "
            f"Known datasets: {sorted(datasets)}",
            file=sys.stderr,
        )
        return 1

    entry = datasets[args.dataset_name]
    csv_path = _resolve_csv_path(entry, args.csv_path)
    input_keys = entry.get("input_keys", [])
    output_keys = entry.get("output_keys", [])
    phoenix_name = args.phoenix_name or args.dataset_name

    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1

    dataframe = pd.read_csv(csv_path)
    required_columns = list(input_keys) + list(output_keys)
    missing = [col for col in required_columns if col not in dataframe.columns]
    if missing:
        print(
            f"CSV at {csv_path} is missing required column(s): {missing}. "
            f"Found columns: {list(dataframe.columns)}",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"[dry-run] CSV: {csv_path}")
        print(f"[dry-run] Row count: {len(dataframe)}")
        print(
            f"[dry-run] input_keys={input_keys} output_keys={output_keys} "
            "— all present."
        )
        print("[dry-run] No connection made to Phoenix; nothing uploaded.")
        return 0

    load_dotenv()

    # Verified against the installed arize-phoenix-client: `Client().datasets
    # .create_dataset(name=, dataframe=, input_keys=, output_keys=)` matches.
    from phoenix.client import Client

    client = Client()
    try:
        dataset = client.datasets.create_dataset(
            name=phoenix_name,
            dataframe=dataframe,
            input_keys=input_keys,
            output_keys=output_keys,
        )
    except Exception as exc:  # noqa: BLE001 - surface any upload failure clearly
        print(
            f"Failed to create dataset '{phoenix_name}' in Phoenix: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Created dataset '{phoenix_name}' in Phoenix from {csv_path} "
        f"({len(dataframe)} rows)."
    )
    print(f"Dataset object: {dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
