from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_multi_asset_backtest


def _build_multi_inputs():
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    ohlcv_by_symbol = {
        "XAU": pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.5, 100.5, 101.5, 102.5, 103.5],
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
                "volume": [10, 11, 12, 13, 14],
            },
            index=idx,
        ),
        "XAG": pd.DataFrame(
            {
                "open": [20.0, 19.0, 19.5, 20.5, 21.0],
                "high": [20.2, 19.3, 19.8, 20.8, 21.2],
                "low": [19.8, 18.8, 19.2, 20.2, 20.7],
                "close": [20.0, 19.0, 19.5, 20.5, 21.0],
                "volume": [100, 110, 120, 130, 140],
            },
            index=idx,
        ),
    }

    target_weights = pd.DataFrame(
        {
            "timestamp": [idx[0], idx[0], idx[2], idx[2]],
            "symbol": ["XAU", "XAG", "XAU", "XAG"],
            "target_weight": [0.6, 0.4, 0.3, 0.7],
        }
    )
    return ohlcv_by_symbol, target_weights


def test_multi_asset_report_contains_reproducibility_metadata():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(initial_cash=100_000.0, portfolio_mode="multi", portfolio_commission_bps=10.0),
        symbols=["XAU", "XAG"],
    )

    assert report["summary"]["mode"] == "multi"
    assert isinstance(report["summary"]["run_id"], str)
    assert len(report["summary"]["run_id"]) >= 8
    assert isinstance(report["summary"]["data_fingerprint"], str)
    assert len(report["summary"]["data_fingerprint"]) == 64
    assert isinstance(report["summary"]["dependency_versions"], dict)
    assert "python" in report["summary"]["dependency_versions"]
    assert "pandas" in report["summary"]["dependency_versions"]
    assert "numpy" in report["summary"]["dependency_versions"]
    assert "git_sha" in report["summary"]
    assert report["summary"]["signal_timestamp"] == "bar_close_t"
    assert report["summary"]["decision_timestamp"] == "bar_close_t"
    assert report["summary"]["execution_effective_lag_bars"] >= 1
    assert "weights(t-" in report["summary"]["return_attribution"]


def test_multi_asset_data_fingerprint_is_stable_for_same_input():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()
    cfg = BacktestConfig(initial_cash=100_000.0, portfolio_mode="multi", portfolio_commission_bps=10.0)

    report1 = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg,
        symbols=["XAU", "XAG"],
    )
    report2 = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg,
        symbols=["XAU", "XAG"],
    )

    assert report1["summary"]["data_fingerprint"] == report2["summary"]["data_fingerprint"]
    assert report1["summary"]["run_id"] != report2["summary"]["run_id"]
