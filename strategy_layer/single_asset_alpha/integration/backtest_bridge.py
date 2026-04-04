"""研究员 C（``single_asset_alpha``）与研究员 D（``single_asset_backtest``）衔接层。

任务清单对应关系（与协作文档一致）::

    C-1 信号 → C-2 target_position → D-1/D-2 Backtrader 执行与 returns/metrics/summary

- **输入**：``StrategyPipeline.run`` 产出的 DataFrame（含 ``timestamp`` / ``symbol`` / ``target_position`` …）
  或任意已通过 ``TargetPositionSchema`` 格式化的表。
- **输出**：直接传入 ``run_single_asset_backtest(..., ohlcv=..., target_position=...)``。

依赖：需安装 ``factor-engine[backtest]``（Backtrader），且 ``PYTHONPATH`` 同时包含
``backtest_layer`` 与 ``factor_layer/factor_engine``（见 ``single_asset_backtest/README.md`` 文首）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline


def target_position_dataframe_to_backtest_input(df: pd.DataFrame) -> pd.DataFrame:
    """将 C 侧标准长表裁剪为 D 侧 ``validate_target_position`` 可直接消费的列集。

    保留 ``timestamp`` 与 ``target_position``；若存在 ``symbol`` / ``signal_value`` / ``action_name``，
    仍原样保留（D 侧只读 ``target_position`` 列，多余列不影响对齐）。
    """
    required = {"timestamp", "target_position"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"target_position DataFrame 缺少列: {sorted(missing)}")
    extra = [c for c in ("symbol", "signal_value", "action_name") if c in df.columns]
    cols = ["timestamp", "target_position", *extra]
    return df[cols].copy()


def run_pipeline_then_single_asset_backtest(
    pipeline: StrategyPipeline,
    *,
    market_data: pd.DataFrame,
    backtest_config: BacktestConfig | None = None,
    strategy_name: str = "target_position",
    strategy_version: str | None = None,
    strategy_params: dict[str, Any] | None = None,
    pipeline_save_outputs: bool = False,
    **pipeline_run_kwargs: Any,
) -> dict[str, Any]:
    """先跑 C 流水线生成 ``target_position``，再调用 D 的 ``run_single_asset_backtest``。

    Parameters
    ----------
    pipeline :
        已配置好 ``signal_generator`` + ``position_mapper`` 的 ``StrategyPipeline``。
    market_data :
        与 C、D 共用的 OHLCV（索引为 ``DatetimeIndex``，列含 open/high/low/close/volume）。
    backtest_config :
        ``BacktestConfig``；默认 ``None`` 时使用库内默认。
    pipeline_save_outputs :
        若为 ``True``，``pipeline.run`` 仍会落盘（与单独跑 pipeline 行为一致）；端到端调试可设 ``False``。
    **pipeline_run_kwargs :
        透传给 ``StrategyPipeline.run``（如 ``start_date`` / ``end_date`` / ``factor_data``）。

    Returns
    -------
    dict
        与 ``run_single_asset_backtest`` 相同：含 ``returns`` / ``metrics`` / ``summary`` 等。
    """
    from single_asset_backtest.runner import run_single_asset_backtest

    tp_df = pipeline.run(
        market_data=market_data,
        save_full_timeseries=pipeline_save_outputs,
        save_debounced=pipeline_save_outputs,
        **pipeline_run_kwargs,
    )
    tp_df = target_position_dataframe_to_backtest_input(tp_df)
    cfg = backtest_config if backtest_config is not None else BacktestConfig()
    return run_single_asset_backtest(
        ohlcv=market_data,
        target_position=tp_df,
        config=cfg,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        strategy_params=strategy_params,
    )
