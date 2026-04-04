from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy_layer.data import FactorRef
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline
from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import ThresholdPositionMapper
from strategy_layer.single_asset_alpha.strategies.signals.factor_threshold_signal import FactorThresholdSignal


def _write_factor(lake_root: Path, factor_id: str, rows: list[tuple[pd.Timestamp, str, float]]) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def test_data_fetcher_loads_factor_lake_for_single_symbol(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    dates = pd.date_range("2024-01-01", periods=3, freq="D")

    _write_factor(
        lake_root,
        "factor_a",
        [
            (dates[0], "AAA", 1.0),
            (dates[1], "AAA", 2.0),
            (dates[2], "AAA", 3.0),
            (dates[0], "BBB", 999.0),
        ],
    )
    _write_factor(
        lake_root,
        "factor_b",
        [
            (dates[0], "AAA", 10.0),
            (dates[1], "AAA", 20.0),
            (dates[2], "AAA", 30.0),
        ],
    )

    fetcher = DataFetcher(
        factor_lake_root=lake_root,
        factor_refs=[FactorRef("factor_a", "alpha"), "factor_b"],
    )

    factor_data = fetcher.load_factor_data(symbol="AAA")

    assert list(factor_data.columns) == ["alpha", "factor_b"]
    assert factor_data.index.tolist() == list(dates)
    assert factor_data.loc[dates[0], "alpha"] == 1.0
    assert factor_data.loc[dates[0], "factor_b"] == 10.0
    assert factor_data["alpha"].max() < 999.0

    only_alpha = fetcher.load_factor_data(symbol="AAA", factor_names=["alpha"])
    assert list(only_alpha.columns) == ["alpha"]


def test_pipeline_auto_loads_factor_lake(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    output_dir = tmp_path / "outputs"
    market_data = DataFetcher.generate_sample_data(
        symbol="AAA",
        periods=6,
        start_date="2024-01-01",
        seed=7,
    )

    _write_factor(
        lake_root,
        "timing_factor",
        [(timestamp, "AAA", 1.0) for timestamp in market_data.index],
    )

    pipeline = StrategyPipeline(
        symbol="AAA",
        signal_generator=FactorThresholdSignal(
            params={
                "factor_names": ["timing_factor"],
                "normalize": False,
            }
        ),
        position_mapper=ThresholdPositionMapper(
            params={
                "long_entry_threshold": 0.1,
                "shift_bars": 0,
            }
        ),
        data_fetcher=DataFetcher(
            factor_lake_root=lake_root,
            factor_refs=["timing_factor"],
        ),
        output_dir=output_dir,
    )

    output = pipeline.run(
        market_data=market_data,
        factor_data=None,
        save_full_timeseries=False,
        save_debounced=False,
    )

    assert not output.empty
    assert (output["target_position"] == 1.0).all()
    assert (output["signal_value"] > 0.7).all()
    assert output["action_name"].iloc[0] == "ENTRY_LONG"
    assert (output_dir / "AAA_run_meta.json").exists()