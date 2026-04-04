from __future__ import annotations

"""统一组装回测输出协议：``returns`` / ``metrics`` / ``summary``（+ 可选 ``artifacts``）。

校验 ``REQUIRED_*_KEYS`` 齐全后才返回，避免下游消费到半残报告。"""
from dataclasses import asdict

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.contracts import BACKTEST_SCHEMA_VERSION, REQUIRED_METRICS_KEYS, REQUIRED_RETURNS_KEYS, REQUIRED_SUMMARY_KEYS
from single_asset_backtest.metrics import compute_backtest_metrics


def build_backtest_report(
    *,
    equity_curve: pd.Series,
    realized_position: pd.Series,
    target_position: pd.Series,
    commission_paid: float,
    trades: int,
    config: BacktestConfig,
    strategy_metadata: dict | None = None,
    benchmark_return: pd.Series | None = None,
    avg_daily_volume: float | None = None,
    trade_ledger: list[dict] | None = None,
    reproducibility_metadata: dict | None = None,
) -> dict:
    """由权益曲线与仓位序列计算周期收益与分层指标，合并策略元数据与可复现字段。"""
    equity_curve = equity_curve.sort_index().astype(float)
    realized_position = realized_position.sort_index().astype(float)
    target_position = target_position.sort_index().astype(float)

    # 单复利序列：周期收益用于夏普等；与多标的 runner 内 net_return 口径一致（由上游保证）
    period_return = equity_curve.pct_change().fillna(0.0)

    returns = {
        "equity_curve": equity_curve,
        "period_return": period_return,
        "realized_position": realized_position,
    }

    metrics = compute_backtest_metrics(
        equity_curve=equity_curve,
        period_return=period_return,
        realized_position=realized_position,
        commission_paid=commission_paid,
        trades=trades,
        profile=config.metrics_profile,
        benchmark_return=benchmark_return,
        avg_daily_volume=avg_daily_volume,
        trade_ledger=trade_ledger,
        risk_free_rate_annual=float(config.risk_free_rate_annual),
    )

    summary = {
        "schema_version": BACKTEST_SCHEMA_VERSION,
        "start": equity_curve.index.min() if len(equity_curve) else None,
        "end": equity_curve.index.max() if len(equity_curve) else None,
        "bars": int(len(equity_curve)),
        "initial_cash": float(config.initial_cash),
        "final_equity": float(equity_curve.iloc[-1]) if len(equity_curve) else float(config.initial_cash),
        "config": asdict(config),
        "target_position_last": float(target_position.iloc[-1]) if len(target_position) else 0.0,
    }

    if strategy_metadata:
        summary.update(strategy_metadata)

    if reproducibility_metadata:
        summary.update(reproducibility_metadata)

    payload = {"returns": returns, "metrics": metrics, "summary": summary}

    if trade_ledger is not None:
        payload["artifacts"] = {"trade_ledger": trade_ledger}

    missing_returns = set(REQUIRED_RETURNS_KEYS) - set(payload["returns"].keys())
    missing_metrics = set(REQUIRED_METRICS_KEYS) - set(payload["metrics"].keys())
    missing_summary = set(REQUIRED_SUMMARY_KEYS) - set(payload["summary"].keys())
    if missing_returns or missing_metrics or missing_summary:
        raise RuntimeError(
            "Backtest report schema incomplete: "
            f"returns={sorted(missing_returns)}, metrics={sorted(missing_metrics)}, summary={sorted(missing_summary)}"
        )

    return payload
