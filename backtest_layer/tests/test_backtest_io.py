from __future__ import annotations

import pandas as pd
import pytest

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.io import load_ohlcv, load_ohlcv_from_config


def _write_aggregate_year(
    aggregate_root,
    year,
    rows,
):
    dataset_dir = aggregate_root / "daily_market_summary"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        rows,
        columns=["ticker", "align_time", "o", "h", "l", "c", "v"],
    )
    frame["align_time"] = pd.to_datetime(frame["align_time"], utc=True)
    frame.to_parquet(dataset_dir / f"daily_market_summary_{year}.parquet", index=False)


def test_load_ohlcv_validates_temporal_integrity(tmp_path):
    path = tmp_path / "ohlcv.csv"
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01 09:30:00", "2026-01-01 09:35:00"],
            "event_time": ["2026-01-01 09:30:00", "2026-01-01 09:35:00"],
            "arrival_time": ["2026-01-01 09:30:00", "2026-01-01 09:34:00"],
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [100, 110],
        }
    )
    frame.to_csv(path, index=False)

    with pytest.raises(ValueError, match="arrival_time earlier than event_time"):
        load_ohlcv(path, strict_temporal_validation=True)


def test_backtest_config_defaults_ibkr_data_root():
    cfg = BacktestConfig()
    assert cfg.data_root == "/home/yluel/share/data/ibkr"


def test_load_ohlcv_from_config_matches_gold_alias_file(tmp_path):
    root = tmp_path / "ibkr"
    gold_dir = root / "gold"
    gold_dir.mkdir(parents=True)

    source = gold_dir / "XAU_1_hour_30_D.parquet"
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01 09:30:00", "2026-01-01 10:30:00"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.5, 100.5],
            "close": [100.5, 101.5],
            "volume": [10, 12],
        }
    )
    frame.to_parquet(source, index=False)

    out = load_ohlcv_from_config(
        BacktestConfig(
            data_root=str(root),
            symbol="XAUUSD",
            frequency="1h",
            prefer_parquet=True,
            strict_temporal_validation=True,
        )
    )

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert out.index.is_monotonic_increasing


def test_load_ohlcv_from_config_supports_aggregate_bars_daily_summary(tmp_path):
    aggregate_root = tmp_path / "aggregate_bars"
    dates = pd.bdate_range("2024-01-01", periods=5, freq="B", tz="UTC")
    rows = []
    for index, timestamp in enumerate(dates):
        rows.append(("AAA", timestamp, 10.0 + index, 11.0 + index, 9.0 + index, 10.5 + index, 1000.0 + index))
        rows.append(("BBB", timestamp, 30.0 + index, 31.0 + index, 29.0 + index, 30.5 + index, 2000.0 + index))
    _write_aggregate_year(aggregate_root, 2024, rows)

    out = load_ohlcv_from_config(
        BacktestConfig(
            market_data_mode="aggregate_bars_daily_summary",
            aggregate_bars_root=str(aggregate_root),
            symbol="AAA",
            frequency="1d",
        )
    )

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 5
    assert out.index.name == "timestamp"
