"""
研究员 C → 研究员 D 端到端示例
==============================

同一份模拟行情：先经 ``single_asset_alpha`` 生成 ``target_position``，再交给
``single_asset_backtest.run_single_asset_backtest`` 出 ``returns/metrics/summary``。

运行（在 monorepo 根目录）::

    export PYTHONPATH="/path/to/quantsociety_backend_project:/path/to/quantsociety_backend_project/backtest_layer:/path/to/quantsociety_backend_project/factor_layer/factor_engine"
    python strategy_layer/single_asset_alpha/examples/c_to_d_end_to_end.py

或分三行写进 shell 配置；与 ``backtest_layer/single_asset_backtest/README.md`` 文首一致。
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in (
    _REPO,
    os.path.join(_REPO, "backtest_layer"),
    os.path.join(_REPO, "factor_layer", "factor_engine"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from single_asset_backtest.config import BacktestConfig

from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.integration.backtest_bridge import (
    run_pipeline_then_single_asset_backtest,
)
from strategy_layer.single_asset_alpha.pipeline import create_combined_strategy


def main() -> None:
    symbol = "C_DEMO"
    market = DataFetcher.generate_sample_data(symbol=symbol, periods=400, seed=7)

    pipeline = create_combined_strategy(symbol=symbol, allow_short=False, output_dir="outputs")
    cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.001,
        metrics_profile="standard",
        enforce_target_bounds=True,
    )

    report = run_pipeline_then_single_asset_backtest(
        pipeline,
        market_data=market,
        backtest_config=cfg,
        pipeline_save_outputs=False,
    )

    print("metrics (节选):")
    for k in ("total_return", "sharpe", "max_drawdown", "turnover"):
        if k in report.get("metrics", {}):
            print(f"  {k}: {report['metrics'][k]}")
    print("summary:")
    s = report.get("summary", {})
    for k in ("start", "end", "bars", "final_equity", "strategy_name"):
        if k in s:
            print(f"  {k}: {s[k]}")


if __name__ == "__main__":
    main()
