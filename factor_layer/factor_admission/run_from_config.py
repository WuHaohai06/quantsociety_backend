from __future__ import annotations

import argparse
from pathlib import Path

from factor_layer.factor_admission.config_runner import run_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run factor admission from YAML config.")
    parser.add_argument("config", type=Path, help="Path to factor admission YAML config.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_from_config(args.config)
    print(f"factor_id={result['factor_id']} run_id={result['run_id']} decision={result['decision']}")


if __name__ == "__main__":
    main()