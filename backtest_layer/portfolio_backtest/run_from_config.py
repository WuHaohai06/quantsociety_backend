from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_layer.portfolio_backtest.config_runner import run_from_config


def _scalarize(value):
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a portfolio_backtest YAML config and optionally evaluate registry rules."
    )
    parser.add_argument("config", type=Path, help="Path to the portfolio_backtest YAML config")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_from_config(args.config)
    summary_row = result["backtest"]["summary_df"].iloc[0].to_dict()
    registry_result = result.get("registry")
    approved = None
    if registry_result is not None:
        approved = bool(registry_result["registry_evaluation_json"].get("approved", False))
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "config_snapshot": result["config_snapshot"],
                "summary": {key: _scalarize(value) for key, value in summary_row.items()},
                "registry_approved": approved,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()