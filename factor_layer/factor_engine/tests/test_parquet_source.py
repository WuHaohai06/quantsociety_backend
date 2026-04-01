from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from storage.parquet_source import ParquetSource


def _write_day_file(root: Path, day: str) -> None:
    day_ts = pd.Timestamp(day)
    target_dir = root / day_ts.strftime("%Y") / day_ts.strftime("%m")
    target_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "window_start": [pd.Timestamp(day, tz="UTC").value],
            "close": [1.0],
        }
    )
    frame.to_parquet(target_dir / f"{day}.parquet", index=False)


def test_selected_files_respects_requested_date_range(tmp_path: Path):
    root = tmp_path / "day_aggs_v1"
    for day in ["2015-12-31", "2016-01-04", "2025-12-31", "2026-01-02"]:
        _write_day_file(root, day)

    source = ParquetSource(
        root=root,
        timestamp_column="window_start",
        instrument_column="ticker",
        start_date="2016-01-01",
        end_date="2025-12-31 23:59:59",
    )

    selected = source._selected_files()

    assert [path.name for path in selected] == [
        "2016-01-04.parquet",
        "2025-12-31.parquet",
    ]


def test_load_column_retries_transient_parquet_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "day_aggs_v1"
    _write_day_file(root, "2024-01-02")

    source = ParquetSource(
        root=root,
        timestamp_column="window_start",
        instrument_column="ticker",
    )

    original_read_parquet = pd.read_parquet
    call_count = {"value": 0}

    def flaky_read_parquet(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise RuntimeError("Repetition level histogram size mismatch")
        return original_read_parquet(*args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", flaky_read_parquet)

    series = source.load_column("close")

    assert len(series) == 1
    assert call_count["value"] == 2