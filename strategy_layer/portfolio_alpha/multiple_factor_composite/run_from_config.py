from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy_layer.portfolio_alpha.multiple_factor_composite.pipeline import run_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a multiple factor composite config and write signal artifacts."
    )
    parser.add_argument("config", type=Path, help="Path to the composite YAML config")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_from_config(args.config)
    print(
        json.dumps(
            {
                "signal_rows": len(result["signal"]),
                "outputs": result["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()