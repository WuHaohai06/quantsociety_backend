from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.report import build_backtest_report


def _build_report(profile: str) -> dict:
    idx = pd.date_range("2026-01-01", periods=8, freq="D")
    equity = pd.Series([100, 102, 101, 104, 103, 106, 105, 107], index=idx, dtype=float)
    realized = pd.Series([0.0, 0.2, 0.2, 0.5, 0.3, 0.7, 0.4, 0.1], index=idx, dtype=float)
    target = realized.copy()

    return build_backtest_report(
        equity_curve=equity,
        realized_position=realized,
        target_position=target,
        commission_paid=1.5,
        trades=4,
        config=BacktestConfig(initial_cash=100.0, metrics_profile=profile),
    )


def test_core_profile_outputs_only_required_metrics():
    report = _build_report("core")

    assert set(report["metrics"].keys()) == {
        "total_return",
        "annual_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "turnover",
        "trades",
        "commission_paid",
    }


def test_fast_profile_outputs_only_required_metrics_and_matches_core_values():
    fast_report = _build_report("fast")
    core_report = _build_report("core")

    required_keys = {
        "total_return",
        "annual_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "turnover",
        "trades",
        "commission_paid",
    }
    assert set(fast_report["metrics"].keys()) == required_keys
    assert set(core_report["metrics"].keys()) == required_keys

    # fast 与 core 在必需字段上语义一致；fast 仅通过跳过扩展指标来提速。
    for key in sorted(required_keys):
        assert fast_report["metrics"][key] == core_report["metrics"][key]


    report = _build_report("standard")

    assert "sortino" in report["metrics"]
    assert "calmar" in report["metrics"]
    assert "downside_volatility" in report["metrics"]
    assert "hit_rate_bar" in report["metrics"]


def test_industrial_profile_outputs_tail_and_drawdown_metrics():
    report = _build_report("industrial")

    assert "var_95" in report["metrics"]
    assert "cvar_95" in report["metrics"]
    assert "max_drawdown_duration_bars" in report["metrics"]
    assert "avg_drawdown" in report["metrics"]
    assert "commission_to_turnover" in report["metrics"]
    assert "turnover_annualized" in report["metrics"]
