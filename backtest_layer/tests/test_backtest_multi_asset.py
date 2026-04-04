from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_multi_asset_backtest
from runtime.perf_config import PerfConfig


def _build_multi_inputs():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    ohlcv_by_symbol = {
        "XAU": pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "high": [101.0, 102.0, 103.0, 104.0],
                "low": [99.5, 100.5, 101.5, 102.5],
                "close": [100.0, 101.0, 102.0, 103.0],
                "volume": [10, 11, 12, 13],
            },
            index=idx,
        ),
        "XAG": pd.DataFrame(
            {
                "open": [20.0, 19.0, 19.5, 20.5],
                "high": [20.2, 19.3, 19.8, 20.8],
                "low": [19.8, 18.8, 19.2, 20.2],
                "close": [20.0, 19.0, 19.5, 20.5],
                "volume": [100, 110, 120, 130],
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


def test_run_multi_asset_backtest_output_shape_and_metadata():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(initial_cash=100_000.0, portfolio_mode="multi", portfolio_commission_bps=10.0),
        symbols=["XAU", "XAG"],
    )

    assert set(report.keys()) == {"returns", "metrics", "summary"}
    assert "portfolio_turnover" in report["returns"]
    assert "portfolio_cost" in report["returns"]
    assert "portfolio_participation" in report["returns"]
    assert report["summary"]["mode"] == "multi"
    assert report["summary"]["strategy_name"] == "portfolio_target_weights"
    assert report["summary"]["signal_timestamp"] == "bar_close_t"
    assert report["summary"]["decision_timestamp"] == "bar_close_t"
    assert report["summary"]["execution_effective_lag_bars"] >= 1
    assert "weights(t-" in report["summary"]["return_attribution"]
    assert report["summary"]["execution_engine_requested"] in {"python", "numpy", "numba", "auto"}
    assert report["summary"]["execution_engine_resolved"] in {"python", "numpy", "numba"}
    assert report["summary"]["strategy_params"]["portfolio_execution_engine"] == "python"
    assert report["metrics"]["portfolio_turnover_total"] >= 0.0
    assert report["metrics"]["portfolio_cost_total"] >= 0.0
    assert report["metrics"]["portfolio_participation_max"] >= 0.0


def test_multi_asset_execution_engine_from_config_is_exposed_in_summary():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_execution_engine="numba"),
        symbols=["XAU", "XAG"],
    )

    assert report["summary"]["execution_engine_requested"] == "numba"
    assert report["summary"]["execution_engine_resolved"] in {"numpy", "numba"}


def test_multi_asset_execution_engine_from_env(monkeypatch):
    ohlcv_by_symbol, target_weights = _build_multi_inputs()
    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "auto")

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_execution_engine="python"),
        symbols=["XAU", "XAG"],
    )

    assert report["summary"]["execution_engine_requested"] == "auto"
    assert report["summary"]["execution_engine_resolved"] in {"numpy", "numba"}


def test_multi_asset_execution_engine_auto_prefers_accelerated_kernel(monkeypatch):
    ohlcv_by_symbol, target_weights = _build_multi_inputs()
    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "auto")

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_execution_engine="python"),
        symbols=["XAU", "XAG"],
    )

    assert report["summary"]["execution_engine_requested"] == "auto"
    assert report["summary"]["execution_engine_resolved"] in {"numpy", "numba"}


def test_multi_asset_execution_engine_invalid_value_falls_back_to_python(monkeypatch):
    ohlcv_by_symbol, target_weights = _build_multi_inputs()
    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "invalid_engine")

    report = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_execution_engine="python"),
        symbols=["XAU", "XAG"],
    )

    assert report["summary"]["execution_engine_requested"] == "python"
    assert report["summary"]["execution_engine_resolved"] == "python"


def test_run_multi_asset_backtest_half_turnover_flag_changes_cost():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    half = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_commission_bps=10.0, portfolio_half_turnover=True),
        symbols=["XAU", "XAG"],
    )
    full = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_commission_bps=10.0, portfolio_half_turnover=False),
        symbols=["XAU", "XAG"],
    )

    assert half["metrics"]["portfolio_turnover_total"] <= full["metrics"]["portfolio_turnover_total"] + 1e-12
    assert half["metrics"]["portfolio_cost_total"] <= full["metrics"]["portfolio_cost_total"] + 1e-12


def test_portfolio_weight_lag_bars_zero_raises():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    with pytest.raises(ValueError, match="portfolio_weight_lag_bars"):
        run_multi_asset_backtest(
            ohlcv_by_symbol=ohlcv_by_symbol,
            target_weights=target_weights,
            config=BacktestConfig(portfolio_mode="multi", portfolio_weight_lag_bars=0),
            symbols=["XAU", "XAG"],
        )


def test_portfolio_min_trade_weight_filters_small_rebalances():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    base = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_commission_bps=10.0, portfolio_min_trade_weight=0.0),
        symbols=["XAU", "XAG"],
    )
    filtered = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(portfolio_mode="multi", portfolio_commission_bps=10.0, portfolio_min_trade_weight=1.0),
        symbols=["XAU", "XAG"],
    )

    assert filtered["metrics"]["portfolio_turnover_total"] <= base["metrics"]["portfolio_turnover_total"] + 1e-12
    assert filtered["metrics"]["portfolio_cost_total"] <= base["metrics"]["portfolio_cost_total"] + 1e-12


def test_portfolio_cost_models_add_impact_cost_when_adv_cap_enabled():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    cfg_simple = BacktestConfig(
        initial_cash=10_000.0,
        portfolio_mode="multi",
        portfolio_cost_model="simple_bps",
        portfolio_commission_bps=5.0,
        portfolio_spread_bps=2.0,
        portfolio_adv_participation_cap=0.1,
        portfolio_impact_coeff=0.5,
    )
    cfg_linear = BacktestConfig(
        initial_cash=10_000.0,
        portfolio_mode="multi",
        portfolio_cost_model="linear_impact",
        portfolio_commission_bps=5.0,
        portfolio_spread_bps=2.0,
        portfolio_adv_participation_cap=0.1,
        portfolio_impact_coeff=0.5,
    )
    cfg_square = BacktestConfig(
        initial_cash=10_000.0,
        portfolio_mode="multi",
        portfolio_cost_model="square_impact",
        portfolio_commission_bps=5.0,
        portfolio_spread_bps=2.0,
        portfolio_adv_participation_cap=0.1,
        portfolio_impact_coeff=0.5,
    )

    simple = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg_simple,
        symbols=["XAU", "XAG"],
    )
    linear = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg_linear,
        symbols=["XAU", "XAG"],
    )
    square = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg_square,
        symbols=["XAU", "XAG"],
    )

    assert linear["metrics"]["portfolio_cost_total"] >= simple["metrics"]["portfolio_cost_total"] - 1e-12
    assert square["metrics"]["portfolio_cost_total"] >= simple["metrics"]["portfolio_cost_total"] - 1e-12
    assert linear["metrics"]["portfolio_cost_total"] >= square["metrics"]["portfolio_cost_total"] - 1e-12




def test_backtest_execution_engine_env_parser_accepts_valid_values(monkeypatch):
    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "numpy")
    perf = PerfConfig.from_env()
    assert perf.backtest_execution_engine == "numpy"


def test_backtest_execution_engine_env_parser_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "definitely_invalid")
    perf = PerfConfig.from_env()
    assert perf.backtest_execution_engine == "python"


def test_multi_asset_strict_real_data_rejects_inline_ohlcv():
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    with pytest.raises(ValueError, match="strict_real_data=True"):
        run_multi_asset_backtest(
            ohlcv_by_symbol=ohlcv_by_symbol,
            target_weights=target_weights,
            config=BacktestConfig(
                portfolio_mode="multi",
                strict_real_data=True,
                data_root="/tmp/not-used",
                frequency="1h",
            ),
            symbols=["XAU", "XAG"],
        )




def test_multi_asset_execution_engine_python_numpy_parity(monkeypatch):
    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "python")
    report_python = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(
            initial_cash=100_000.0,
            portfolio_mode="multi",
            portfolio_execution_engine="python",
            portfolio_cost_model="linear_impact",
            portfolio_commission_bps=8.0,
            portfolio_spread_bps=2.0,
            portfolio_impact_coeff=0.25,
            portfolio_adv_participation_cap=0.2,
            portfolio_min_trade_weight=0.01,
            portfolio_half_turnover=True,
        ),
        symbols=["XAU", "XAG"],
    )

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "numpy")
    report_numpy = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(
            initial_cash=100_000.0,
            portfolio_mode="multi",
            portfolio_execution_engine="python",
            portfolio_cost_model="linear_impact",
            portfolio_commission_bps=8.0,
            portfolio_spread_bps=2.0,
            portfolio_impact_coeff=0.25,
            portfolio_adv_participation_cap=0.2,
            portfolio_min_trade_weight=0.01,
            portfolio_half_turnover=True,
        ),
        symbols=["XAU", "XAG"],
    )

    pd.testing.assert_series_equal(
        report_python["returns"]["equity_curve"],
        report_numpy["returns"]["equity_curve"],
        rtol=1e-12,
        atol=1e-12,
    )
    pd.testing.assert_series_equal(
        report_python["returns"]["portfolio_turnover"],
        report_numpy["returns"]["portfolio_turnover"],
        rtol=1e-12,
        atol=1e-12,
    )
    pd.testing.assert_series_equal(
        report_python["returns"]["portfolio_cost"],
        report_numpy["returns"]["portfolio_cost"],
        rtol=1e-12,
        atol=1e-12,
    )




def test_multi_asset_execution_engine_numba_matches_numpy_when_available(monkeypatch):
    pytest.importorskip("numba")

    ohlcv_by_symbol, target_weights = _build_multi_inputs()

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "numba")
    report_numba = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(
            initial_cash=100_000.0,
            portfolio_mode="multi",
            portfolio_execution_engine="python",
            portfolio_cost_model="square_impact",
            portfolio_commission_bps=8.0,
            portfolio_spread_bps=2.0,
            portfolio_impact_coeff=0.25,
            portfolio_adv_participation_cap=0.2,
            portfolio_min_trade_weight=0.01,
            portfolio_half_turnover=True,
        ),
        symbols=["XAU", "XAG"],
    )

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "numpy")
    report_numpy = run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=BacktestConfig(
            initial_cash=100_000.0,
            portfolio_mode="multi",
            portfolio_execution_engine="python",
            portfolio_cost_model="square_impact",
            portfolio_commission_bps=8.0,
            portfolio_spread_bps=2.0,
            portfolio_impact_coeff=0.25,
            portfolio_adv_participation_cap=0.2,
            portfolio_min_trade_weight=0.01,
            portfolio_half_turnover=True,
        ),
        symbols=["XAU", "XAG"],
    )

    assert report_numba["summary"]["execution_engine_resolved"] == "numba"
    pd.testing.assert_series_equal(
        report_numba["returns"]["equity_curve"],
        report_numpy["returns"]["equity_curve"],
        rtol=1e-12,
        atol=1e-12,
    )
    pd.testing.assert_series_equal(
        report_numba["returns"]["portfolio_turnover"],
        report_numpy["returns"]["portfolio_turnover"],
        rtol=1e-12,
        atol=1e-12,
    )


def test_multi_asset_numpy_kernel_is_not_slower_than_python_on_medium_input(monkeypatch):
    bars = 800
    symbols = ["XAU", "XAG", "XPT", "XPD"]
    idx = pd.date_range("2026-01-01", periods=bars, freq="h")

    ohlcv_by_symbol = {}
    for i, symbol in enumerate(symbols):
        base = 100.0 + i * 10.0
        close = np.linspace(base, base + 5.0, bars)
        ohlcv_by_symbol[symbol] = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": np.full(bars, 1_000 + i * 50, dtype=float),
            },
            index=idx,
        )

    target_weights = pd.DataFrame(
        {
            "timestamp": np.repeat(idx[::20], len(symbols)),
            "symbol": symbols * len(idx[::20]),
            "target_weight": np.tile(np.array([0.4, 0.3, 0.2, 0.1]), len(idx[::20])),
        }
    )

    cfg = BacktestConfig(
        initial_cash=100_000.0,
        portfolio_mode="multi",
        portfolio_execution_engine="python",
        portfolio_cost_model="square_impact",
        portfolio_commission_bps=5.0,
        portfolio_spread_bps=1.0,
        portfolio_impact_coeff=0.2,
        portfolio_adv_participation_cap=0.3,
        portfolio_min_trade_weight=0.001,
        portfolio_half_turnover=True,
    )

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "python")
    t0 = pd.Timestamp.utcnow()
    run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg,
        symbols=symbols,
    )
    python_ms = (pd.Timestamp.utcnow() - t0).total_seconds() * 1000.0

    monkeypatch.setenv("FACTOR_BACKTEST_EXECUTION_ENGINE", "numpy")
    t1 = pd.Timestamp.utcnow()
    run_multi_asset_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        target_weights=target_weights,
        config=cfg,
        symbols=symbols,
    )
    numpy_ms = (pd.Timestamp.utcnow() - t1).total_seconds() * 1000.0

    assert numpy_ms <= python_ms * 1.20
