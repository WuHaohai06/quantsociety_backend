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

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))  # quantsociety_backend_project 根
for _p in (
    _REPO,  # strategy_layer.* 包
    os.path.join(_REPO, "backtest_layer"),  # single_asset_backtest
    os.path.join(_REPO, "factor_layer", "factor_engine"),  # runtime.perf_config 等
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
    market = DataFetcher.generate_sample_data(symbol=symbol, periods=400, seed=7)  # 与 pipeline 共用同一 OHLCV

    # 三信号组合 + ATR 仓位映射；换策略可改用 create_dual_ma_strategy / create_macd_strategy
    pipeline = create_combined_strategy(symbol=symbol, allow_short=False, output_dir="outputs")
    cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.001,
        metrics_profile="standard",  # core < standard < industrial 指标丰富度
        enforce_target_bounds=True,  # target_position 超出 [-1,1] 时严格报错；与 C 侧 Schema 一致
        target_lag_bars=0,  # C 侧 mapper.shift_bars 已默认 1；D 侧这里保持 0，避免双 lag
    )

    report = run_pipeline_then_single_asset_backtest(
        pipeline,
        market_data=market,
        backtest_config=cfg,
        pipeline_save_outputs=False,  # 端到端调试不落盘 parquet；需文件交付时改 True
    )

    print("metrics (节选):")
    for k in ("total_return", "sharpe", "max_drawdown", "turnover"):  # 完整键见 compute_backtest_metrics
        if k in report.get("metrics", {}):
            print(f"  {k}: {report['metrics'][k]}")
    print("summary:")
    s = report.get("summary", {})
    for k in ("start", "end", "bars", "final_equity", "strategy_name"):  # 审计字段另有 data_fingerprint、run_id 等
        if k in s:
            print(f"  {k}: {s[k]}")


if __name__ == "__main__":
    main()
