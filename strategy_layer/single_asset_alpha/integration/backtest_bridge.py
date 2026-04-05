"""研究员 C（``single_asset_alpha``）与研究员 D（``single_asset_backtest``）衔接层。

任务清单对应关系（与协作文档一致）::

    C-1 信号 → C-2 target_position → D-1/D-2 Backtrader 执行与 returns/metrics/summary

- **输入**：``StrategyPipeline.run`` 产出的 DataFrame（含 ``timestamp`` / ``symbol`` / ``target_position`` …）
  或任意已通过 ``TargetPositionSchema`` 格式化的表。
- **输出**：直接传入 ``run_single_asset_backtest(..., ohlcv=..., target_position=...)``。

返回的 ``report["summary"]`` 中，本模块会在 ``run_single_asset_backtest`` 生成报告后，**覆盖写入**
``execution_effective_lag_bars`` 与 ``return_attribution``，以反映 **C 侧 shift + D 侧 target_lag_bars**
的合成滞后（与 ``single_asset_backtest/README.md`` **§17.4** 一致）。仅使用 D 侧时请直接调 runner，勿经本 bridge。

依赖：需安装 ``factor-engine[backtest]``（Backtrader），且 ``PYTHONPATH`` 同时包含
``backtest_layer`` 与 ``factor_layer/factor_engine``（见 ``single_asset_backtest/README.md`` 文首）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from single_asset_backtest.config import BacktestConfig  # 仅配置数据类，不触发 backtrader 导入
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
    cols = ["timestamp", "target_position", *extra]  # D 侧 validate 只依赖前两列，其余便于审计/排错
    return df[cols].copy()


def _extract_position_mapper_shift_bars(pipeline: StrategyPipeline) -> int:
    mapper = getattr(pipeline, "position_mapper", None)
    params = getattr(mapper, "params", None)

    if isinstance(params, dict):
        raw = params.get("shift_bars", 1)
    elif params is not None and hasattr(params, "shift_bars"):
        raw = getattr(params, "shift_bars")
    else:
        return 0

    if raw is None:
        return 1
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


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
    # runner 内会 import backtrader，故放在函数体，避免仅 import 本模块就依赖 bt
    from single_asset_backtest.runner import run_single_asset_backtest

    tp_df = pipeline.run(
        market_data=market_data,
        save_full_timeseries=pipeline_save_outputs,  # False 时仍可能写 run_meta.json，见 pipeline 实现
        save_debounced=pipeline_save_outputs,
        **pipeline_run_kwargs,
    )
    tp_df = target_position_dataframe_to_backtest_input(tp_df)
    cfg = backtest_config if backtest_config is not None else BacktestConfig()
    c_shift_bars = _extract_position_mapper_shift_bars(pipeline)
    d_target_lag_bars = int(cfg.target_lag_bars)
    if c_shift_bars > 0 and d_target_lag_bars > 0:
        raise ValueError(
            "Detected double lag: "
            f"pipeline.position_mapper.params.shift_bars={c_shift_bars}, "
            f"BacktestConfig.target_lag_bars={d_target_lag_bars}. "
            "Please enable lag on only one side (C mapper shift OR D target_lag_bars)."
        )
    report = run_single_asset_backtest(
        ohlcv=market_data,  # 须与 C 计算信号时用的行情为同一时间轴（索引对齐）
        target_position=tp_df,
        config=cfg,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        strategy_params=strategy_params,
    )
    effective_lag_bars = max(0, c_shift_bars) + max(0, d_target_lag_bars)
    summary = report.get("summary") if isinstance(report, dict) else None
    if isinstance(summary, dict):
        summary["execution_effective_lag_bars"] = effective_lag_bars
        summary["return_attribution"] = f"weights(t-{effective_lag_bars}) * returns(t)"
    return report
