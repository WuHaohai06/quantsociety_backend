from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_single_asset_backtest


def _print_report(report: dict) -> None:
    print("metrics")
    for k, v in report["metrics"].items():
        print(f"  {k}: {v}")

    print("strategy")
    print(f"  name: {report['summary'].get('strategy_name')}")
    print(f"  version: {report['summary'].get('strategy_version')}")
    print(f"  params: {report['summary'].get('strategy_params')}")

    print("summary")
    for k, v in report["summary"].items():
        if k in {"config", "strategy_name", "strategy_version", "strategy_params", "strategy_instance_id"}:
            continue
        print(f"  {k}: {v}")

    if "artifacts" in report and "trade_ledger" in report["artifacts"]:
        print(f"trade_ledger rows: {len(report['artifacts']['trade_ledger'])}")


def main() -> None:
    config = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.001,
        metrics_profile="industrial",
        strict_real_data=True,
        data_root="/home/yluel/share/data/ibkr",
        symbol="XAUUSD",
        frequency="1h",
        include_trade_ledger=True,
        risk_free_rate_annual=0.02,
    )

    print("=== target_position strategy ===")
    target_position = pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01 09:30:00",
                "2026-01-03 09:30:00",
                "2026-01-06 09:30:00",
            ],
            "target_position": [0.0, 0.8, 0.3],
        }
    )

    report_target = run_single_asset_backtest(
        target_position=target_position,
        config=config,
        strategy_name="target_position",
        strategy_version="1.0",
        strategy_params={"rebalance_threshold": 0.005},
    )
    _print_report(report_target)

    print("\n=== dual_ma strategy ===")
    report_dual_ma = run_single_asset_backtest(
        config=config,
        strategy_name="dual_ma",
        strategy_version="1.0",
        strategy_params={"short_window": 5, "long_window": 20, "position_size": 1.0},
    )
    _print_report(report_dual_ma)


if __name__ == "__main__":
    main()
