from __future__ import annotations

from pathlib import Path

from .parquet_source import ParquetSource


class KlineParquetSource(ParquetSource):
    """K 线 parquet 数据源，默认对齐 Massive bar 数据字段。"""

    def __init__(
        self,
        root: str | Path,
        *,
        instrument_column: str | None = None,
        instrument_col: str | None = None,
        timestamp_column: str | None = None,
        timestamp_col: str | None = None,
        fields: dict[str, str] | None = None,
        max_files: int | None = None,
        timestamp_unit: str | None = "ns",
        start_date: str | None = None,
        end_date: str | None = None,
        recursive: bool = True,
    ) -> None:
        super().__init__(
            root=root,
            timestamp_column=timestamp_col or timestamp_column or "window_start",
            instrument_column=instrument_col or instrument_column or "ticker",
            fields=fields,
            max_files=max_files,
            timestamp_unit=timestamp_unit,
            start_date=start_date,
            end_date=end_date,
            recursive=recursive,
        )
