from __future__ import annotations

import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from single_asset_backtest.config import BacktestConfig
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.integration.backtest_bridge import (
    run_pipeline_then_single_asset_backtest,
)
from strategy_layer.single_asset_alpha.pipeline import create_dual_ma_strategy


class _MapperParamsAttrProxy:
    def __init__(self, base: dict, shift_bars: int):
        self._base = dict(base)
        self.shift_bars = shift_bars

    def get(self, key, default=None):
        if key == "shift_bars":
            return self.shift_bars
        return self._base.get(key, default)


@pytest.fixture
def c_pipeline():
    return create_dual_ma_strategy(symbol="C_D_E2E", allow_short=False, output_dir="outputs")


@pytest.fixture
def market_data():
    return DataFetcher.generate_sample_data(symbol="C_D_E2E", periods=220, seed=11)


def _assert_frozen_output_contract(result: dict) -> None:
    assert set(result.keys()) == {"returns", "metrics", "summary"}

    summary = result["summary"]
    for k in ("strategy_name", "strategy_version", "strategy_params", "strategy_instance_id"):
        assert k in summary

    for k in (
        "signal_timestamp",
        "decision_timestamp",
        "execution_effective_lag_bars",
        "return_attribution",
    ):
        assert k in summary


def _with_mapper_shift_bars(pipeline, shift_bars):
    pipeline.position_mapper.params = _MapperParamsAttrProxy(pipeline.position_mapper.params, shift_bars)
    return pipeline


@pytest.mark.integration
def test_c_to_d_e2e_pipeline_to_single_asset_backtest_contract_regression(c_pipeline, market_data):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    report = run_pipeline_then_single_asset_backtest(
        c_pipeline,
        market_data=market_data,
        backtest_config=BacktestConfig(initial_cash=100_000.0, commission=0.001, target_lag_bars=0),
        pipeline_save_outputs=False,
    )

    _assert_frozen_output_contract(report)
    assert report["summary"]["strategy_name"] == "target_position"
    assert report["summary"]["execution_effective_lag_bars"] == 1
    assert report["summary"]["return_attribution"] == "weights(t-1) * returns(t)"


@pytest.mark.integration
def test_c_to_d_e2e_pipeline_output_with_extra_columns_keeps_d_side_stable(c_pipeline, market_data):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    report = run_pipeline_then_single_asset_backtest(
        c_pipeline,
        market_data=market_data,
        backtest_config=BacktestConfig(initial_cash=100_000.0, commission=0.0, target_lag_bars=0),
        pipeline_save_outputs=False,
    )

    _assert_frozen_output_contract(report)
    assert report["summary"]["bars"] > 0


@pytest.mark.integration
def test_c_to_d_e2e_when_c_shift_zero_d_lag_one_records_effective_lag_one(market_data):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    pipeline = create_dual_ma_strategy(symbol="C_D_E2E", allow_short=False, output_dir="outputs", shift_bars=0)
    report = run_pipeline_then_single_asset_backtest(
        pipeline,
        market_data=market_data,
        backtest_config=BacktestConfig(initial_cash=100_000.0, commission=0.0, target_lag_bars=1),
        pipeline_save_outputs=False,
    )

    _assert_frozen_output_contract(report)
    assert report["summary"]["execution_effective_lag_bars"] == 1
    assert report["summary"]["return_attribution"] == "weights(t-1) * returns(t)"


@pytest.mark.integration
def test_c_to_d_bridge_reads_shift_bars_from_attribute_style_params(c_pipeline, market_data):
    bt = pytest.importorskip("backtrader")
    assert bt is not None

    pipeline = _with_mapper_shift_bars(c_pipeline, 1)
    with pytest.raises(ValueError, match="Detected double lag"):
        run_pipeline_then_single_asset_backtest(
            pipeline,
            market_data=market_data,
            backtest_config=BacktestConfig(initial_cash=100_000.0, target_lag_bars=1),
            pipeline_save_outputs=False,
        )

