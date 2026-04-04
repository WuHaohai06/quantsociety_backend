from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.contracts import REQUIRED_SUMMARY_KEYS
from single_asset_backtest.report import build_backtest_report


def test_report_schema_keys_are_stable():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    equity = pd.Series([100.0, 101.0, 100.5, 103.0], index=idx)
    realized = pd.Series([0.0, 0.3, 0.3, 0.0], index=idx)
    target = pd.Series([0.0, 0.5, 0.5, 0.0], index=idx)

    report = build_backtest_report(
        equity_curve=equity,
        realized_position=realized,
        target_position=target,
        commission_paid=1.23,
        trades=2,
        config=BacktestConfig(initial_cash=100.0),
    )

    assert set(report.keys()) == {"returns", "metrics", "summary"}
    assert set(report["returns"].keys()) == {"equity_curve", "period_return", "realized_position"}
    assert "total_return" in report["metrics"]
    assert set(REQUIRED_SUMMARY_KEYS).issubset(set(report["summary"].keys()))
    assert "strategy_name" not in report["summary"]


def test_report_summary_accepts_strategy_metadata_extension():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    equity = pd.Series([100.0, 101.0, 100.5, 103.0], index=idx)
    realized = pd.Series([0.0, 0.3, 0.3, 0.0], index=idx)
    target = pd.Series([0.0, 0.5, 0.5, 0.0], index=idx)

    report = build_backtest_report(
        equity_curve=equity,
        realized_position=realized,
        target_position=target,
        commission_paid=1.23,
        trades=2,
        config=BacktestConfig(initial_cash=100.0),
        strategy_metadata={
            "strategy_name": "target_position",
            "strategy_version": "1.0",
            "strategy_params": {"rebalance_threshold": 0.01},
            "strategy_instance_id": "abc123",
        },
    )

    assert report["summary"]["strategy_name"] == "target_position"
    assert report["summary"]["strategy_version"] == "1.0"


def test_report_summary_accepts_reproducibility_metadata_extension():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    equity = pd.Series([100.0, 101.0, 100.5, 103.0], index=idx)
    realized = pd.Series([0.0, 0.3, 0.3, 0.0], index=idx)
    target = pd.Series([0.0, 0.5, 0.5, 0.0], index=idx)

    report = build_backtest_report(
        equity_curve=equity,
        realized_position=realized,
        target_position=target,
        commission_paid=1.23,
        trades=2,
        config=BacktestConfig(initial_cash=100.0),
        reproducibility_metadata={
            "mode": "single",
            "run_id": "run-123",
            "data_fingerprint": "fp-abc",
            "dependency_versions": {"python": "3.12.0", "pandas": "2.2.0"},
            "git_sha": None,
        },
    )

    assert report["summary"]["mode"] == "single"
    assert report["summary"]["run_id"] == "run-123"
    assert report["summary"]["data_fingerprint"] == "fp-abc"
