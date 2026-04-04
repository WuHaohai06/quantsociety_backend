from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .datasource import DataSource


@dataclass
class KlineParquetSource(DataSource):
    root: str
    instrument_column: str = "ticker"
    timestamp_column: str = "window_start"
    fields: dict[str, str] = field(default_factory=dict)
    file_pattern: str = "*.parquet"
    max_files: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    timestamp_unit: str = "ns"
    timestamp_utc: bool = True
    normalize_timestamp: bool = True
    sort_index: bool = True
    _column_cache: dict[str, object] = field(default_factory=dict, init=False, repr=False)
    _file_cache: list[Path] | None = field(default=None, init=False, repr=False)

    def load_column(self, name: str):
        import pandas as pd

        if name in self._column_cache:
            return self._column_cache[name]

        source_name = self.fields.get(name, name)
        selected_files = self._selected_files()
        if not selected_files:
            raise FileNotFoundError(f"No parquet files found under {self.root}")

        read_columns = [self.instrument_column, self.timestamp_column, source_name]
        frames = [pd.read_parquet(path, columns=list(dict.fromkeys(read_columns))) for path in selected_files]
        df = pd.concat(frames, ignore_index=True)
        df = df.rename(
            columns={
                self.instrument_column: "instrument",
                self.timestamp_column: "timestamp",
                source_name: name,
            }
        )
        df["timestamp"] = self._convert_timestamp(df["timestamp"])
        if self.start_date:
            df = df[df["timestamp"] >= self.start_date]
        if self.end_date:
            df = df[df["timestamp"] <= self.end_date]
        series = df.set_index(["timestamp", "instrument"])[name]

        if self.sort_index:
            series = series.sort_index()

        self._column_cache[name] = series
        return series

    def _selected_files(self) -> list[Path]:
        if self._file_cache is None:
            root = Path(self.root)
            self._file_cache = sorted(root.rglob(self.file_pattern))

        files = self._file_cache
        start = date.fromisoformat(self.start_date) if self.start_date else None
        end = date.fromisoformat(self.end_date) if self.end_date else None
        if start or end:
            files = [path for path in files if self._matches_date_range(path, start, end)]

        if self.max_files is not None:
            files = files[: self.max_files]

        return files

    def _matches_date_range(self, path: Path, start: date | None, end: date | None) -> bool:
        try:
            file_date = date.fromisoformat(path.stem)
        except ValueError:
            return True

        if start and file_date < start:
            return False
        if end and file_date > end:
            return False
        return True

    def _convert_timestamp(self, series):
        import pandas as pd
        from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

        if is_datetime64_any_dtype(series):
            timestamp = series
        elif is_numeric_dtype(series):
            timestamp = pd.to_datetime(series, unit=self.timestamp_unit, utc=self.timestamp_utc)
        else:
            timestamp = pd.to_datetime(series, utc=self.timestamp_utc)

        if getattr(timestamp.dt, "tz", None) is not None:
            timestamp = timestamp.dt.tz_convert(None)

        if self.normalize_timestamp:
            timestamp = timestamp.dt.normalize()

        return timestamp
