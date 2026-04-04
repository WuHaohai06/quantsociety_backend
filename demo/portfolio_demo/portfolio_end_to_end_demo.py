from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_layer.portfolio_backtest.config_runner import run_from_config as run_portfolio_backtest
from strategy_layer.portfolio_alpha.holdings_gen.pipeline import run_from_config as run_holdings_gen
from strategy_layer.portfolio_alpha.multiple_factor_composite.pipeline import run_from_config as run_composite_signal


def _write_factor(
    lake_root: Path,
    factor_id: str,
    rows: list[tuple[str, str, float]],
) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def _build_demo_inputs(demo_root: Path) -> dict[str, str]:
    factor_lake_root = demo_root / "factor_lake"
    inputs_root = demo_root / "inputs"
    factor_lake_root.mkdir(parents=True, exist_ok=True)
    inputs_root.mkdir(parents=True, exist_ok=True)

    dates = pd.date_range("2024-01-02", periods=10, freq="D")
    symbols = ["AAA", "BBB", "CCC", "DDD"]

    value_base = {"AAA": 4.0, "BBB": 3.0, "CCC": 2.0, "DDD": 1.0}
    quality_base = {"AAA": 3.6, "BBB": 3.1, "CCC": 1.8, "DDD": 1.0}
    price_start = {"AAA": 100.0, "BBB": 80.0, "CCC": 60.0, "DDD": 40.0}
    daily_return = {"AAA": 0.012, "BBB": 0.008, "CCC": -0.004, "DDD": -0.007}

    value_rows: list[tuple[str, str, float]] = []
    quality_rows: list[tuple[str, str, float]] = []
    kline_rows: list[dict[str, object]] = []

    latest_close = dict(price_start)
    for day_idx, date in enumerate(dates):
        date_text = date.strftime("%Y-%m-%d")
        for symbol in symbols:
            value_rows.append(
                (
                    date_text,
                    symbol,
                    float(value_base[symbol] + 0.05 * day_idx),
                )
            )
            quality_rows.append(
                (
                    date_text,
                    symbol,
                    float(quality_base[symbol] + (day_idx % 3) * 0.04),
                )
            )

            if day_idx > 0:
                latest_close[symbol] = latest_close[symbol] * (1.0 + daily_return[symbol])
            close = round(float(latest_close[symbol]), 6)
            open_price = round(close / (1.0 + daily_return[symbol] / 2.0), 6)
            kline_rows.append(
                {
                    "trade_date": date,
                    "symbol": symbol,
                    "open": open_price,
                    "high": round(max(open_price, close) * 1.002, 6),
                    "low": round(min(open_price, close) * 0.998, 6),
                    "close": close,
                    "volume": 100000 + day_idx * 1000,
                }
            )

    _write_factor(factor_lake_root, "demo_value_factor_v1", value_rows)
    _write_factor(factor_lake_root, "demo_quality_factor_v1", quality_rows)

    kline_frame = pd.DataFrame(kline_rows)
    kline_frame.to_parquet(inputs_root / "mock_kline.parquet", index=False)

    return {
        "factor_lake_root": str(factor_lake_root),
        "kline_path": str(inputs_root / "mock_kline.parquet"),
    }


def main() -> None:
    demo_root = Path(__file__).resolve().parent
    configs_root = demo_root / "configs"

    prepared = _build_demo_inputs(demo_root)

    previous_cwd = Path.cwd()
    try:
        os.chdir(configs_root)
        composite_result = run_composite_signal("composite_signal.yaml")
    finally:
        os.chdir(previous_cwd)

    composite_signal_path = Path(composite_result["outputs"]["signal"])
    if not composite_signal_path.is_absolute():
        composite_signal_path = (configs_root / composite_signal_path).resolve()

    holdings_result = run_holdings_gen(configs_root / "holdings_from_signal.yaml")
    backtest_result = run_portfolio_backtest(configs_root / "portfolio_backtest.yaml")

    summary = {
        "prepared_inputs": prepared,
        "composite": {
            "signal_rows": int(len(composite_result["signal"])),
            "signal_path": str(composite_signal_path),
        },
        "holdings": {
            "rows": int(len(holdings_result["holdings"])),
            "path": holdings_result["outputs"]["holdings"],
            "summary": holdings_result["summary"],
        },
        "backtest": {
            "output_dir": backtest_result["output_dir"],
            "summary": backtest_result["backtest"]["summary_df"].iloc[0].to_dict(),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()