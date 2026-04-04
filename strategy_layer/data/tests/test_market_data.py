from __future__ import annotations

from pathlib import Path
import sys

import pytest

pd = pytest.importorskip("pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_layer.data import load_single_asset_ohlcv  # noqa: E402


def _write_aggregate_year(
    aggregate_root: Path,
    year: int,
    rows: list[tuple[str, pd.Timestamp, float, float, float, float, float]],
) -> None:
    dataset_dir = aggregate_root / "daily_market_summary"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        rows,
        columns=["ticker", "align_time", "o", "h", "l", "c", "v"],
    )
    frame["align_time"] = pd.to_datetime(frame["align_time"], utc=True)
    frame.to_parquet(dataset_dir / f"daily_market_summary_{year}.parquet", index=False)


def test_load_single_asset_ohlcv_reads_aggregate_bars_and_reuses_cache(tmp_path: Path):
    aggregate_root = tmp_path / "aggregate_bars"
    cache_root = tmp_path / ".cache" / "market_data"
    dates = pd.bdate_range("2024-01-01", periods=6, freq="B", tz="UTC")
    rows = []
    for index, timestamp in enumerate(dates):
        rows.append(("AAA", timestamp, 10.0 + index, 11.0 + index, 9.0 + index, 10.5 + index, 1000.0 + index))
        rows.append(("BBB", timestamp, 20.0 + index, 21.0 + index, 19.0 + index, 20.5 + index, 2000.0 + index))
    _write_aggregate_year(aggregate_root, 2024, rows)

    first = load_single_asset_ohlcv(
        symbol="AAA",
        mode="aggregate_bars_daily_summary",
        aggregate_bars_root=aggregate_root,
        aggregate_dataset="daily_market_summary",
        start_date="2024-01-03",
        end_date="2024-01-08",
        freq="1d",
        cache_root=cache_root,
    )

    assert list(first.columns) == ["open", "high", "low", "close", "volume"]
    assert first.index.name == "timestamp"
    assert len(first) == 4
    assert (cache_root / "daily_market_summary" / "freq=1d" / "AAA.parquet").exists()
    assert (cache_root / "daily_market_summary" / "freq=1d" / "AAA.json").exists()

    second = load_single_asset_ohlcv(
        symbol="AAA",
        mode="aggregate_bars_daily_summary",
        aggregate_bars_root=None,
        aggregate_dataset="daily_market_summary",
        start_date="2024-01-03",
        end_date="2024-01-08",
        freq="1d",
        cache_root=cache_root,
    )

    pd.testing.assert_frame_equal(first, second)
