from __future__ import annotations

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_multi_asset_backtest, run_single_asset_backtest, run_single_asset_backtest_batch


def _build_single_inputs():
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    ohlcv = pd.DataFrame(
        {
            "open": [10, 10.5, 10.7, 10.8, 11.0, 11.2],
            "high": [10.6, 10.8, 10.9, 11.1, 11.3, 11.5],
            "low": [9.9, 10.2, 10.5, 10.6, 10.8, 11.0],
            "close": [10.4, 10.7, 10.8, 11.0, 11.2, 11.4],
            "volume": [100, 120, 110, 130, 140, 150],
        },
        index=idx,
    )
    target = pd.DataFrame(
        {
            "timestamp": [idx[0], idx[2], idx[4]],
            "target_position": [0.0, 0.8, 0.2],
        }
    )
    return ohlcv, target


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


def test_single_asset_data_fingerprint_is_stable_for_same_input():
    ohlcv, target = _build_single_inputs()
    cfg = BacktestConfig(initial_cash=100_000.0, commission=0.001, target_lag_bars=0)

    report1 = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=cfg,
    )
    report2 = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=cfg,
    )

    assert report1["summary"]["data_fingerprint"] == report2["summary"]["data_fingerprint"]
    assert report1["summary"]["run_id"] != report2["summary"]["run_id"]
    assert report1["summary"]["dependency_versions"] == report2["summary"]["dependency_versions"]
    assert report1["summary"]["git_sha"] == report2["summary"]["git_sha"]


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
    assert report1["summary"]["dependency_versions"] == report2["summary"]["dependency_versions"]
    assert report1["summary"]["git_sha"] == report2["summary"]["git_sha"]


def test_single_asset_batch_workers_1_matches_sequential_fingerprints():
    ohlcv, target = _build_single_inputs()

    task0 = {
        "ohlcv": ohlcv,
        "target_position": target,
        "config": BacktestConfig(initial_cash=100_000.0, commission=0.001, target_lag_bars=0),
    }
    task1 = {
        "ohlcv": ohlcv,
        "target_position": target,
        "config": BacktestConfig(initial_cash=100_000.0, commission=0.001, target_lag_bars=1),
    }

    seq0 = run_single_asset_backtest(**task0)
    seq1 = run_single_asset_backtest(**task1)
    batched = run_single_asset_backtest_batch(tasks=[task0, task1], max_workers=1)

    assert batched[0]["summary"]["data_fingerprint"] == seq0["summary"]["data_fingerprint"]
    assert batched[1]["summary"]["data_fingerprint"] == seq1["summary"]["data_fingerprint"]


