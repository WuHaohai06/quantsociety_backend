from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.io import load_ohlcv_from_config
from single_asset_backtest.runner import run_single_asset_backtest, run_single_asset_backtest_batch


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
    assert "pandas" in report["summary"]["dependency_versions"]
    assert "numpy" in report["summary"]["dependency_versions"]
    assert "backtrader" in report["summary"]["dependency_versions"]
    assert "git_sha" in report["summary"]
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


def test_run_single_asset_backtest_can_load_aggregate_bars_from_config(tmp_path):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    aggregate_root = tmp_path / "aggregate_bars"
    dataset_dir = aggregate_root / "daily_market_summary"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2024-01-01", periods=6, freq="B", tz="UTC")
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"] * len(dates),
            "align_time": dates,
            "o": [10.0, 10.2, 10.3, 10.5, 10.6, 10.8],
            "h": [10.4, 10.5, 10.7, 10.8, 10.9, 11.1],
            "l": [9.8, 10.0, 10.1, 10.2, 10.4, 10.5],
            "c": [10.2, 10.3, 10.6, 10.7, 10.8, 11.0],
            "v": [1000, 1100, 1200, 1300, 1250, 1400],
        }
    )
    frame.to_parquet(dataset_dir / "daily_market_summary_2024.parquet", index=False)

    target = pd.DataFrame(
        {
            "timestamp": [dates[0].tz_convert(None), dates[2].tz_convert(None), dates[4].tz_convert(None)],
            "target_position": [0.0, 0.8, 0.2],
        }
    )
    cfg = BacktestConfig(
        market_data_mode="aggregate_bars_daily_summary",
        aggregate_bars_root=str(aggregate_root),
        symbol="AAA",
        frequency="1d",
        initial_cash=100_000.0,
        commission=0.001,
    )

    report = run_single_asset_backtest(target_position=target, config=cfg)

    assert report["summary"]["bars"] == 6
    assert report["summary"]["strategy_name"] == "target_position"


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
    assert r1["summary"]["execution_effective_lag_bars"] == 1
    assert r1["summary"]["return_attribution"] == "weights(t-1) * returns(t)"


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

def test_fast_profile_forces_trade_ledger_off_even_when_config_enabled():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    report = run_single_asset_backtest(
        ohlcv=ohlcv,
        target_position=target,
        config=BacktestConfig(
            initial_cash=100_000.0,
            include_trade_ledger=True,
            metrics_profile="fast",
        ),
    )

    # fast profile 只保留核心指标计算，不应携带 trade ledger 工件。
    assert report["summary"]["strategy_params"]["include_trade_ledger"] is False
    assert "artifacts" not in report



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

    core_cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.0,
        include_trade_ledger=False,
        metrics_profile="core",
    )
    fast_cfg = BacktestConfig(
        initial_cash=100_000.0,
        commission=0.0,
        include_trade_ledger=False,
        metrics_profile="fast",
    )

    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=core_cfg)
    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=fast_cfg)

    t0 = time.perf_counter()
    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=core_cfg)
    core_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    run_single_asset_backtest(ohlcv=ohlcv, target_position=target, config=fast_cfg)
    fast_elapsed_ms = (time.perf_counter() - t1) * 1000.0

    assert core_elapsed_ms <= 1200.0
    # 机器噪声下用宽松相对断言：fast 至少不应显著慢于 core。
    assert fast_elapsed_ms <= core_elapsed_ms * 1.10


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


def test_run_single_asset_backtest_batch_workers_1_keeps_order_and_matches_single():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    base_ohlcv, base_target = _build_inputs()
    task0 = {
        "ohlcv": base_ohlcv,
        "target_position": base_target,
        "config": BacktestConfig(initial_cash=100_000.0, commission=0.0, metrics_profile="core"),
    }

    ohlcv2 = base_ohlcv.copy()
    ohlcv2["close"] = ohlcv2["close"] * 1.01
    target2 = base_target.copy()
    target2["target_position"] = [0.0, 0.5, 0.1]
    task1 = {
        "ohlcv": ohlcv2,
        "target_position": target2,
        "config": BacktestConfig(initial_cash=120_000.0, commission=0.0, metrics_profile="fast"),
    }

    single0 = run_single_asset_backtest(**task0)
    single1 = run_single_asset_backtest(**task1)
    batch_reports = run_single_asset_backtest_batch(tasks=[task0, task1], max_workers=1)

    assert len(batch_reports) == 2
    assert batch_reports[0]["summary"]["final_equity"] == pytest.approx(single0["summary"]["final_equity"])
    assert batch_reports[1]["summary"]["final_equity"] == pytest.approx(single1["summary"]["final_equity"])



def test_run_single_asset_backtest_batch_invalid_workers_and_unknown_keys_rejected():
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    ohlcv, target = _build_inputs()
    with pytest.raises(ValueError, match="max_workers"):
        run_single_asset_backtest_batch(
            tasks=[{"ohlcv": ohlcv, "target_position": target}],
            max_workers=0,
        )

    with pytest.raises(ValueError, match="unknown keys"):
        run_single_asset_backtest_batch(
            tasks=[{"ohlcv": ohlcv, "target_position": target, "bad_key": 1}],
            max_workers=1,
        )
