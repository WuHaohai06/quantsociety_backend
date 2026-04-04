from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_multi_asset_backtest


def main() -> None:
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    ohlcv_by_symbol = {
        "XAU": pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 102.5, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 103.5, 104.0, 105.0],
                "low": [99.5, 100.5, 101.5, 102.0, 102.5, 103.5],
                "close": [100.0, 101.0, 102.0, 103.0, 103.5, 104.5],
                "volume": [100, 110, 120, 130, 140, 150],
            },
            index=idx,
        ),
        "XAG": pd.DataFrame(
            {
                "open": [20.0, 19.7, 19.9, 20.1, 20.4, 20.7],
                "high": [20.2, 19.9, 20.1, 20.3, 20.6, 21.0],
                "low": [19.8, 19.5, 19.7, 19.9, 20.2, 20.5],
                "close": [20.0, 19.8, 20.0, 20.2, 20.5, 20.8],
                "volume": [200, 210, 220, 230, 240, 250],
            },
            index=idx,
        ),
    }

    target_weights = pd.DataFrame(
        {
            "timestamp": [idx[0], idx[0], idx[2], idx[2], idx[4], idx[4]],
            "symbol": ["XAU", "XAG", "XAU", "XAG", "XAU", "XAG"],
            "target_weight": [0.6, 0.4, 0.3, 0.7, 0.5, 0.5],
        }
    )

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(
            initial_cash=100_000.0,
            portfolio_mode="multi",
            portfolio_commission_bps=5.0,
            portfolio_half_turnover=True,
            metrics_profile="standard",
        ),
        symbols=["XAU", "XAG"],
    )

    print("metrics")
    for k, v in report["metrics"].items():
        if k in {"portfolio_turnover_total", "portfolio_cost_total", "total_return", "sharpe"}:
            print(f"  {k}: {v}")

    print("summary")
    for k in ["mode", "run_id", "data_fingerprint", "git_sha", "bars", "initial_cash", "final_equity"]:
        print(f"  {k}: {report['summary'].get(k)}")


if __name__ == "__main__":
    main()
