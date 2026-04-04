from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy_layer.portfolio_alpha.holdings_gen.pipeline import run_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate portfolio holdings from a composite signal config."
    )
    parser.add_argument("config", type=Path, help="Path to the holdings_gen YAML config")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_from_config(args.config)
    print(
        json.dumps(
            {
                "holdings_rows": len(result["holdings"]),
                "summary": result["summary"],
                "outputs": result["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()