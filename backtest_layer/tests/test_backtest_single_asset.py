from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.io import load_ohlcv_from_config
from single_asset_backtest.runner import run_single_asset_backtest


def _build_inputs():
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


def test_run_single_asset_backtest_output_shape():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.001),
    )

    assert set(report.keys()) == {"returns", "metrics", "summary"}
    assert len(report["returns"]["equity_curve"]) == len(ohlcv)
    assert report["summary"]["bars"] == len(ohlcv)
    assert report["summary"]["strategy_name"] == "target_position"
    assert report["summary"]["strategy_version"] == "1.0"
    assert report["summary"]["strategy_params"]["rebalance_threshold"] == pytest.approx(1e-8)
    assert report["summary"]["strategy_params"]["target_lag_bars"] == 0
    assert isinstance(report["summary"]["strategy_instance_id"], str)
    assert len(report["summary"]["strategy_instance_id"]) >= 8
    assert report["summary"]["mode"] == "single"
    assert isinstance(report["summary"]["run_id"], str)
    assert len(report["summary"]["run_id"]) >= 8
    assert isinstance(report["summary"]["data_fingerprint"], str)
    assert len(report["summary"]["data_fingerprint"]) == 64
    assert isinstance(report["summary"]["dependency_versions"], dict)
    assert "python" in report["summary"]["dependency_versions"]
    assert report["summary"]["signal_timestamp"] == "bar_close_t"
    assert report["summary"]["decision_timestamp"] == "bar_close_t"
    assert report["summary"]["execution_effective_lag_bars"] == 0
    assert report["summary"]["return_attribution"] == "weights(t-0) * returns(t)"


def test_commission_impacts_total_return():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    no_cost = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0),
    )
    with_cost = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.003),
    )

    assert with_cost["metrics"]["total_return"] <= no_cost["metrics"]["total_return"] + 1e-12
    assert with_cost["metrics"]["commission_paid"] >= 0.0
    assert with_cost["metrics"]["trades"] >= 1


def test_unknown_strategy_rejected():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    with pytest.raises(ValueError, match="Unknown strategy"):
        run_single_asset_backtest(
            ohlcv=ohlcv,
            target_position=target,
            strategy_name="not_exists",
        )


def test_strategy_params_override_default_threshold():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        strategy_params={"rebalance_threshold": 0.02},
    )

    assert report["summary"]["strategy_params"]["rebalance_threshold"] == pytest.approx(0.02)


def test_strict_real_data_rejects_inline_ohlcv():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    with pytest.raises(ValueError, match="strict_real_data=True"):
        run_single_asset_backtest(
            ohlcv=ohlcv,
            target_position=target,
            config=BacktestConfig(strict_real_data=True, symbol="XAU", frequency="1h"),
        )


def test_strict_real_data_loads_from_gold_data_root(tmp_path):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    root = tmp_path / "ibkr"
    gold_dir = root / "gold"
    gold_dir.mkdir(parents=True)

    data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=6, freq="h"),
            "open": [100.0, 100.2, 100.5, 100.7, 100.6, 100.9],
            "high": [100.3, 100.6, 100.8, 100.9, 101.0, 101.3],
            "low": [99.9, 100.0, 100.3, 100.5, 100.4, 100.7],
            "close": [100.2, 100.4, 100.7, 100.6, 100.9, 101.1],
            "volume": [10, 11, 12, 13, 14, 15],
        }
    )
    data.to_parquet(gold_dir / "XAU_1_hour_30_D.parquet", index=False)

    target = pd.DataFrame(
        {
            "timestamp": [data["timestamp"].iloc[0], data["timestamp"].iloc[2], data["timestamp"].iloc[4]],
            "target_position": [0.0, 0.6, 0.1],
        }
    )

    cfg = BacktestConfig(
        strict_real_data=True,
        data_root=str(root),
        symbol="XAUUSD",
        frequency="1h",
        initial_cash=100_000.0,
        commission=0.001,
    )

    loaded = load_ohlcv_from_config(cfg)
    assert len(loaded) == 6

    report = run_single_asset_backtest(target_position=target, config=cfg)
    assert report["summary"]["bars"] == 6


def test_target_lag_bars_changes_fingerprint_and_is_recorded():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    r0 = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0, target_lag_bars=0),
    )
    r1 = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0, target_lag_bars=1),
    )
    assert r0["summary"]["data_fingerprint"] != r1["summary"]["data_fingerprint"]
    assert r1["summary"]["strategy_params"]["target_lag_bars"] == 1


def test_borrow_rate_reduces_equity_and_increases_commission_paid():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, _ = _build_inputs()
    short_target = pd.DataFrame(
        {
            "timestamp": [ohlcv.index[0], ohlcv.index[2], ohlcv.index[4]],
            "target_position": [0.0, -0.7, -0.2],
        }
    )

    base = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=short_target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0, borrow_rate_annual=0.0),
    )
    with_borrow = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=short_target,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0, borrow_rate_annual=0.15),
    )

    assert with_borrow["summary"]["final_equity"] < base["summary"]["final_equity"]
    assert with_borrow["metrics"]["commission_paid"] > base["metrics"]["commission_paid"]


def test_single_asset_can_disable_data_fingerprint():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, include_data_fingerprint=False),
    )

    assert report["summary"]["data_fingerprint"] is None


def test_single_asset_strategy_params_include_trade_ledger_flag():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(initial_cash=100_000.0, include_trade_ledger=False, metrics_profile="core"),
    )

    assert report["summary"]["strategy_params"]["include_trade_ledger"] is False




def test_dual_ma_strategy_runs_without_target_position():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    close = np.concatenate([np.linspace(100, 110, 20), np.linspace(110, 95, 20)])
    ohlcv = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.full(len(idx), 1000.0),
        },
        index=idx,
    )

    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        config=BacktestConfig(initial_cash=100_000.0, commission=0.0),
        strategy_name="dual_ma",
        strategy_params={"short_window": 3, "long_window": 8, "position_size": 0.8},
    )

    assert set(report.keys()) == {"returns", "metrics", "summary"}
    assert report["summary"]["strategy_name"] == "dual_ma"
    assert report["summary"]["strategy_version"] == "1.0"
    assert report["summary"]["strategy_params"]["short_window"] == 3
    assert report["summary"]["strategy_params"]["long_window"] == 8
    assert report["summary"]["strategy_params"]["position_size"] == pytest.approx(0.8)
    expected_bars = len(ohlcv) - 8 + 1
    assert report["summary"]["bars"] == expected_bars
    realized = report["returns"]["realized_position"]
    assert float(realized.max()) > 0.0
    assert float(realized.min()) >= -1e-12


def test_dual_ma_invalid_window_raises():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, _ = _build_inputs()
    with pytest.raises(ValueError, match="short_window must be < long_window"):
        run_single_asset_backtest(
            ohlcv=ohlcv,
            config=BacktestConfig(initial_cash=100_000.0),
            strategy_name="dual_ma",
            strategy_params={"short_window": 5, "long_window": 5},
        )


def test_dual_ma_real_gold_data_strict_mode_if_available():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.001,
        strict_real_data=True,
        data_root="/home/yluel/share/data/ibkr",
        symbol="XAUUSD",
        frequency="1h",
    )

    try:
        load_ohlcv_from_config(cfg)
    except ValueError as exc:
        pytest.skip(f"gold data not available: {exc}")

    report = run_single_asset_backtest(
        config=cfg,
        strategy_name="dual_ma",
        strategy_params={"short_window": 5, "long_window": 20, "position_size": 1.0},
    )

    assert set(report.keys()) == {"returns", "metrics", "summary"}
    assert report["summary"]["strategy_name"] == "dual_ma"
    assert report["summary"]["bars"] > 0
    assert np.isfinite(float(report["summary"]["final_equity"]))


def test_single_asset_runtime_guard_python_not_extremely_slow():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    bars = 2000
    idx = pd.date_range("2026-01-01", periods=bars, freq="h")
    close = 100.0 + np.linspace(0.0, 5.0, bars)
    ohlcv = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.full(bars, 1_000.0),
        },
        index=idx,
    )
    target = pd.DataFrame(
        {
            "timestamp": idx[::25],
            "target_position": np.where(np.arange(len(idx[::25])) % 2 == 0, 0.7, -0.3),
        }
    )

    cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.0,
        include_trade_ledger=False,
        metrics_profile="core",
    )

    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=cfg)

    t0 = time.perf_counter()
    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=cfg)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms <= 1200.0


def test_target_lag_bars_negative_raises():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    with pytest.raises(ValueError, match="target_lag_bars"):
        run_single_asset_backtest(
            ohlcv=ohlcv,
            target_position=target,
            config=BacktestConfig(target_lag_bars=-1),
        )
