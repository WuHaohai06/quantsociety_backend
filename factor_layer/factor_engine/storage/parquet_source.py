from __future__ import annotations

import gc
import re
import time
from pathlib import Path
from typing import Any

from .datasource import DataSource
from logging_utils import ProgressLogger, get_logger


logger = get_logger("storage.parquet_source")


class ParquetSource(DataSource):
    """通用 parquet 单数据源实现。

    约定每次按需读取一列，将其整理成 `(timestamp, instrument)` MultiIndex Series。
    该类既可用于 fundamentals 这类多文件目录，也可用于单文件 parquet。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        timestamp_column: str,
        instrument_column: str,
        fields: dict[str, str] | None = None,
        max_files: int | None = None,
        timestamp_unit: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        recursive: bool = True,
    ) -> None:
        self.root = Path(root)
        self.timestamp_column = timestamp_column
        self.instrument_column = instrument_column
        self.fields = dict(fields or {})
        self.max_files = max_files
        self.timestamp_unit = timestamp_unit
        self.start_date = self._normalize_bound(start_date)
        self.end_date = self._normalize_bound(end_date)
        self.recursive = recursive
        self._column_cache: dict[str, Any] = {}

    @staticmethod
    def _normalize_instrument(value: Any) -> str | None:
        import pandas as pd

        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            value = value[0]
        if pd.isna(value):
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _normalize_bound(value: str | None):
        if value is None:
            return None

        import pandas as pd

        bound = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(bound):
            raise ValueError(f"Invalid datetime boundary: {value}")
        if getattr(bound, "tz", None) is not None:
            bound = bound.tz_convert(None)
        return bound

    def _selected_files(self) -> list[Path]:
        if self.root.is_file():
            files = [self.root]
        else:
            if not self.root.exists():
                raise FileNotFoundError(f"Parquet source root not found: {self.root}")
            iterator = self.root.rglob("*.parquet") if self.recursive else self.root.glob("*.parquet")
            files = sorted(path for path in iterator if path.is_file())
        total_files = len(files)
        if self.start_date is not None or self.end_date is not None:
            files = [path for path in files if self._path_matches_requested_range(path)]
            logger.info(
                "按日期范围筛选 parquet 文件: before=%d, after=%d, start=%s, end=%s",
                total_files,
                len(files),
                self.start_date,
                self.end_date,
            )
        if self.max_files is not None:
            files = files[: self.max_files]
        logger.info("发现 parquet 文件 %d 个: root=%s", len(files), self.root)
        return files

    @staticmethod
    def _extract_partition_value(path: Path, key: str) -> int | None:
        pattern = re.compile(rf"{re.escape(key)}=(\d{{1,4}})$")
        for part in reversed(path.parts):
            match = pattern.fullmatch(part)
            if match is not None:
                return int(match.group(1))
        return None

    @classmethod
    def _infer_path_time_window(cls, path: Path):
        import pandas as pd

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
        if date_match is not None:
            day = pd.Timestamp(date_match.group(1))
            return day, day + pd.Timedelta(days=1)

        year = cls._extract_partition_value(path, "year")
        month = cls._extract_partition_value(path, "month")
        day = cls._extract_partition_value(path, "day")
        if year is None:
            return None

        if month is not None and day is not None:
            start = pd.Timestamp(year=year, month=month, day=day)
            return start, start + pd.Timedelta(days=1)
        if month is not None:
            start = pd.Timestamp(year=year, month=month, day=1)
            if month == 12:
                end = pd.Timestamp(year=year + 1, month=1, day=1)
            else:
                end = pd.Timestamp(year=year, month=month + 1, day=1)
            return start, end

        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year + 1, month=1, day=1)
        return start, end

    def _path_matches_requested_range(self, path: Path) -> bool:
        time_window = self._infer_path_time_window(path)
        if time_window is None:
            return True

        file_start, file_end = time_window
        if self.end_date is not None and file_start > self.end_date:
            return False
        if self.start_date is not None and file_end <= self.start_date:
            return False
        return True

    def _read_column_frame(self, path: Path, requested_columns: list[str]):
        import pandas as pd
        import pyarrow.parquet as pq

        last_error: Exception | None = None
        for attempt in range(1, 3):
            try:
                return pd.read_parquet(path, columns=requested_columns)
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    break
                gc.collect()
                time.sleep(0.05)

        # Some parquet files intermittently fail through pandas/pyarrow in long scans.
        # Fall back to a direct single-threaded pyarrow read before giving up.
        try:
            table = pq.read_table(
                path,
                columns=requested_columns,
                use_threads=False,
                memory_map=False,
            )
            return table.to_pandas()
        except Exception as exc:
            if last_error is not None:
                raise exc from last_error
            raise

    def _coerce_timestamp(self, series):
        import pandas as pd

        if self.timestamp_unit:
            numeric = pd.to_numeric(series, errors="coerce")
            timestamps = pd.to_datetime(
                numeric,
                unit=self.timestamp_unit,
                utc=True,
                errors="coerce",
            )
        else:
            timestamps = pd.to_datetime(series, utc=True, errors="coerce")

        if getattr(timestamps.dt, "tz", None) is not None:
            timestamps = timestamps.dt.tz_convert(None)
        return timestamps

    def load_column(self, name: str):
        import pandas as pd

        if name in self._column_cache:
            logger.debug("命中列缓存: %s", name)
            return self._column_cache[name]

        actual_name = self.fields.get(name, name)
        selected_files = self._selected_files()
        if not selected_files:
            raise FileNotFoundError(f"No parquet files found under {self.root}")

        logger.info(
            "开始加载列 '%s' (实际列 '%s')，文件数=%d，root=%s",
            name,
            actual_name,
            len(selected_files),
            self.root,
        )

        requested_columns = list(
            dict.fromkeys([self.timestamp_column, self.instrument_column, actual_name])
        )
        frames: list[pd.DataFrame] = []
        read_errors: list[str] = []
        progress = ProgressLogger(
            logger,
            desc=f"读取列 {name}",
            total=len(selected_files),
            unit="file",
        )
        for path in selected_files:
            try:
                frames.append(self._read_column_frame(path, requested_columns))
            except Exception as exc:  # pragma: no cover - depends on raw file quality
                read_errors.append(f"{path}: {exc}")
                logger.warning("读取 parquet 失败: %s - %s", path, exc)
            progress.advance(detail=path.name)

        if not frames:
            preview = "\n".join(read_errors[:5])
            raise RuntimeError(
                f"No readable parquet file for column '{name}' under {self.root}. Errors:\n{preview}"
            )

        frame = pd.concat(frames, ignore_index=True)
        timestamps = self._coerce_timestamp(frame[self.timestamp_column])
        normalized = pd.DataFrame(
            {
                "timestamp": timestamps,
                "instrument": frame[self.instrument_column].map(self._normalize_instrument),
                name: frame[actual_name],
            }
        )
        normalized = normalized[
            normalized["timestamp"].notna() & normalized["instrument"].notna()
        ].copy()

        if self.start_date is not None:
            normalized = normalized[normalized["timestamp"] >= self.start_date]
        if self.end_date is not None:
            normalized = normalized[normalized["timestamp"] <= self.end_date]

        normalized = normalized.drop_duplicates(
            subset=["timestamp", "instrument"], keep="last"
        )
        series = normalized.set_index(["timestamp", "instrument"])[name].sort_index()
        series.index = series.index.set_names(["timestamp", "instrument"])
        self._column_cache[name] = series
        logger.info(
            "完成加载列 '%s'：有效文件=%d/%d，结果行数=%d，读取失败=%d",
            name,
            len(frames),
            len(selected_files),
            len(series),
            len(read_errors),
        )
        return series
