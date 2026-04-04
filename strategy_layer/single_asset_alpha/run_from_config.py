from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy_layer.single_asset_alpha.config_runner import run_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single_asset_alpha YAML config")
    parser.add_argument("config", type=Path, help="Path to the single_asset_alpha YAML config")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_from_config(args.config)
    factor_data = result["factor_data"]
    print(
        json.dumps(
            {
                "rows": len(result["target_position"]),
                "output_dir": result["output_dir"],
                "factor_columns": list(factor_data.columns) if factor_data is not None else [],
                "config_snapshot": result["config_snapshot"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
