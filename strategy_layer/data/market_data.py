from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Literal

import pandas as pd


MarketDataMode = Literal["data_root", "source_path", "aggregate_bars_daily_summary"]

STANDARD_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
DEFAULT_AGGREGATE_BARS_COLUMNS = {
    "open": "o",
    "high": "h",
    "low": "l",
    "close": "c",
    "volume": "v",
}


def _normalize_timestamp_series(series: pd.Series) -> pd.Series:
    normalized = pd.to_datetime(series, utc=True, errors="coerce")
    if isinstance(normalized.dtype, pd.DatetimeTZDtype):
        normalized = normalized.dt.tz_convert(None)
    return normalized


def validate_temporal_market_frame(frame: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    out = frame.copy()

    if "event_time" in out.columns and "arrival_time" in out.columns:
        out["event_time"] = _normalize_timestamp_series(out["event_time"])
        out["arrival_time"] = _normalize_timestamp_series(out["arrival_time"])
        invalid = out["arrival_time"] < out["event_time"]
        if invalid.any() and strict:
            first = out.loc[invalid, ["event_time", "arrival_time"]].iloc[0]
            raise ValueError(
                "temporal integrity violated: arrival_time earlier than event_time: "
                f"event_time={first['event_time']}, arrival_time={first['arrival_time']}"
            )

    if "timestamp" in out.columns:
        out["timestamp"] = _normalize_timestamp_series(out["timestamp"])
        if out["timestamp"].isna().any():
            raise ValueError("OHLCV timestamp contains invalid values")
        if out["timestamp"].duplicated().any():
            raise ValueError("OHLCV timestamp has duplicate rows")

    return out


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def load_standard_ohlcv(
    path: str | Path,
    *,
    strict_temporal_validation: bool = True,
    max_rows: int | None = None,
) -> pd.DataFrame:
    data_path = Path(path)
    frame = _read_table(data_path)
    frame = validate_temporal_market_frame(frame, strict=strict_temporal_validation)

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLCV missing required columns: {sorted(missing)}")

    out = frame.copy()
    out["timestamp"] = _normalize_timestamp_series(out["timestamp"])
    out = out.set_index("timestamp").sort_index()

    if out.index.has_duplicates:
        raise ValueError("OHLCV index has duplicate timestamps")

    if "volume" not in out.columns:
        out["volume"] = 0.0

    if max_rows is not None and max_rows > 0:
        out = out.tail(int(max_rows))

    out.index.name = "timestamp"
    return out[list(STANDARD_OHLCV_COLUMNS)]


def choose_ohlcv_file(
    *,
    data_root: str | Path,
    symbol: str,
    frequency: str,
    prefer_parquet: bool,
) -> Path:
    root = Path(data_root)
    if not root.exists():
        raise ValueError(f"data_root does not exist: {root}")

    base = root / symbol / frequency
    if base.is_file():
        return base

    candidates: list[Path] = []
    if base.is_dir():
        if prefer_parquet:
            candidates.extend(sorted(base.glob("*.parquet")))
            candidates.extend(sorted(base.glob("*.pq")))
            candidates.extend(sorted(base.glob("*.csv")))
        else:
            candidates.extend(sorted(base.glob("*.csv")))
            candidates.extend(sorted(base.glob("*.parquet")))
            candidates.extend(sorted(base.glob("*.pq")))

    if candidates:
        return candidates[0]

    flat_candidates: list[Path] = []
    stem = f"{symbol}_{frequency}"
    if prefer_parquet:
        flat_candidates.extend(sorted(root.glob(f"{stem}*.parquet")))
        flat_candidates.extend(sorted(root.glob(f"{stem}*.pq")))
        flat_candidates.extend(sorted(root.glob(f"{stem}*.csv")))
    else:
        flat_candidates.extend(sorted(root.glob(f"{stem}*.csv")))
        flat_candidates.extend(sorted(root.glob(f"{stem}*.parquet")))
        flat_candidates.extend(sorted(root.glob(f"{stem}*.pq")))

    if flat_candidates:
        return flat_candidates[0]

    freq_aliases = {
        "1min": ["1_min", "1_mins", "1min", "1m"],
        "5min": ["5_min", "5_mins", "5min", "5m"],
        "15min": ["15_min", "15_mins", "15min", "15m"],
        "30min": ["30_min", "30_mins", "30min", "30m"],
        "1h": ["1_hour", "1h", "60min", "60_min"],
        "1d": ["1_day", "1d", "1day"],
    }
    normalized_symbol = symbol.upper()
    roots_to_scan = [root]
    if normalized_symbol in {"XAU", "XAUUSD", "GOLD"}:
        roots_to_scan.append(root / "gold")

    exts = [".parquet", ".pq", ".csv"] if prefer_parquet else [".csv", ".parquet", ".pq"]
    aliases = freq_aliases.get(frequency, [frequency])
    pattern = re.compile(r"^([A-Za-z]+)[_\-]", re.IGNORECASE)

    for scan_root in roots_to_scan:
        if not scan_root.exists() or not scan_root.is_dir():
            continue
        for ext in exts:
            for file in sorted(scan_root.glob(f"*{ext}")):
                name_lower = file.stem.lower()
                prefix_match = pattern.match(file.stem)
                prefix = prefix_match.group(1).upper() if prefix_match else ""
                if normalized_symbol in {"XAU", "XAUUSD", "GOLD"}:
                    if prefix not in {"XAU", "XAUUSD", "GOLD"}:
                        continue
                elif prefix and prefix != normalized_symbol:
                    continue

                if any(alias in name_lower for alias in aliases):
                    return file

    raise ValueError(f"No OHLCV data found for symbol={symbol}, frequency={frequency} under {root}")


def _extract_partition_year(path: Path) -> int | None:
    stem = path.stem
    year_text = stem.rsplit("_", 1)[-1]
    if year_text.isdigit() and len(year_text) == 4:
        return int(year_text)
    return None


def _boundary_year(value: object | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(pd.Timestamp(value).year)
    except Exception:
        text = str(value)
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        return default


def _aggregate_dataset_dir(root: str | Path, dataset: str) -> Path:
    dataset_dir = Path(root) / dataset
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise FileNotFoundError(f"aggregate_bars dataset 目录不存在: {dataset_dir}")
    return dataset_dir


def _collect_aggregate_paths(
    dataset_dir: Path,
    *,
    dataset: str,
    start_date: str | None,
    end_date: str | None,
) -> list[Path]:
    paths = sorted(dataset_dir.glob(f"{dataset}_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"aggregate_bars dataset 下没有 parquet 文件: {dataset_dir}")

    start_year = _boundary_year(start_date, 0)
    end_year = _boundary_year(end_date, 9999)
    filtered = []
    for path in paths:
        year = _extract_partition_year(path)
        if year is None or start_year <= year <= end_year:
            filtered.append(path)
    if not filtered:
        raise FileNotFoundError(
            f"aggregate_bars 在指定年份窗口内没有 parquet 文件: dataset={dataset_dir}, years={start_year}-{end_year}"
        )
    return filtered


def _read_aggregate_partition(
    path: Path,
    *,
    symbol: str,
    symbol_column: str,
    timestamp_column: str,
    aggregate_columns: Mapping[str, str],
) -> pd.DataFrame:
    rename_map = {
        symbol_column: "symbol",
        timestamp_column: "timestamp",
        aggregate_columns["open"]: "open",
        aggregate_columns["high"]: "high",
        aggregate_columns["low"]: "low",
        aggregate_columns["close"]: "close",
        aggregate_columns["volume"]: "volume",
    }
    read_columns = list(dict.fromkeys(rename_map.keys()))
    try:
        frame = pd.read_parquet(
            path,
            columns=read_columns,
            filters=[(symbol_column, "==", symbol)],
        )
    except Exception:
        frame = pd.read_parquet(path, columns=read_columns)
    if symbol_column in frame.columns:
        symbols = frame[symbol_column].astype("string").str.strip()
        frame = frame.loc[symbols == symbol].copy()
    return frame.rename(columns=rename_map)


def _normalize_standard_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = _normalize_timestamp_series(out["timestamp"])
    for column in STANDARD_OHLCV_COLUMNS:
        if column not in out.columns:
            if column == "volume":
                out[column] = 0.0
                continue
            raise ValueError(f"aggregate_bars 标准化后缺少列: {column}")
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
    out["volume"] = out["volume"].fillna(0.0)
    if out["timestamp"].duplicated().any():
        duplicated = out.loc[out["timestamp"].duplicated(keep=False), ["timestamp"]].head(3)
        raise ValueError(
            "aggregate_bars 中同一标的存在重复 timestamp: "
            f"sample={duplicated['timestamp'].astype(str).tolist()}"
        )
    out = out.sort_values("timestamp").set_index("timestamp")
    out.index.name = "timestamp"
    return out[list(STANDARD_OHLCV_COLUMNS)]


def _sanitize_symbol_for_path(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(symbol).strip())


def _cache_file_path(cache_root: str | Path, *, dataset: str, freq: str, symbol: str) -> Path:
    return Path(cache_root) / dataset / f"freq={freq}" / f"{_sanitize_symbol_for_path(symbol)}.parquet"


def _cache_meta_path(cache_root: str | Path, *, dataset: str, freq: str, symbol: str) -> Path:
    return Path(cache_root) / dataset / f"freq={freq}" / f"{_sanitize_symbol_for_path(symbol)}.json"


def _write_cached_ohlcv(
    cache_root: str | Path,
    *,
    dataset: str,
    freq: str,
    symbol: str,
    frame: pd.DataFrame,
    source_root: str | Path | None,
    symbol_column: str,
    timestamp_column: str,
    aggregate_columns: Mapping[str, str],
) -> None:
    cache_path = _cache_file_path(cache_root, dataset=dataset, freq=freq, symbol=symbol)
    meta_path = _cache_meta_path(cache_root, dataset=dataset, freq=freq, symbol=symbol)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_parquet(cache_path, index=False)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "freq": freq,
        "symbol": symbol,
        "source_root": str(source_root) if source_root is not None else None,
        "source_symbol_column": symbol_column,
        "source_timestamp_column": timestamp_column,
        "source_aggregate_columns": dict(aggregate_columns),
        "rows": int(len(frame)),
        "start": str(frame.index.min()) if len(frame) else None,
        "end": str(frame.index.max()) if len(frame) else None,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_aggregate_bars_daily_summary(
    *,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    aggregate_bars_root: str | Path | None,
    aggregate_dataset: str,
    aggregate_symbol_column: str,
    aggregate_timestamp_column: str,
    aggregate_columns: Mapping[str, str],
    freq: str,
    cache_root: str | Path | None,
    refresh_cache: bool,
) -> pd.DataFrame:
    symbol_text = str(symbol).strip()
    if not symbol_text:
        raise ValueError("symbol 不能为空")
    if freq != "1d":
        raise ValueError("aggregate_bars_daily_summary 目前只支持 1d")

    if cache_root is not None and not refresh_cache:
        cache_path = _cache_file_path(cache_root, dataset=aggregate_dataset, freq=freq, symbol=symbol_text)
        if cache_path.exists():
            cached = load_standard_ohlcv(cache_path, strict_temporal_validation=False)
            if start_date:
                cached = cached.loc[start_date:]
            if end_date:
                cached = cached.loc[:end_date]
            return cached

    if aggregate_bars_root is None:
        raise ValueError("aggregate_bars_root 未配置")

    dataset_dir = _aggregate_dataset_dir(aggregate_bars_root, aggregate_dataset)
    read_start = None if cache_root is not None else start_date
    read_end = None if cache_root is not None else end_date
    paths = _collect_aggregate_paths(
        dataset_dir,
        dataset=aggregate_dataset,
        start_date=read_start,
        end_date=read_end,
    )
    frames = [
        _read_aggregate_partition(
            path,
            symbol=symbol_text,
            symbol_column=aggregate_symbol_column,
            timestamp_column=aggregate_timestamp_column,
            aggregate_columns=aggregate_columns,
        )
        for path in paths
    ]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if frame.empty:
        raise FileNotFoundError(
            f"aggregate_bars 中找不到标的 {symbol_text} 的数据: dataset={aggregate_dataset}"
        )

    frame["symbol"] = frame["symbol"].astype("string").str.strip()
    frame = frame.loc[frame["symbol"] == symbol_text].copy()
    if frame.empty:
        raise FileNotFoundError(
            f"aggregate_bars 中找不到标的 {symbol_text} 的数据: dataset={aggregate_dataset}"
        )

    standardized = _normalize_standard_ohlcv_frame(frame[["timestamp", *STANDARD_OHLCV_COLUMNS]])
    if cache_root is not None:
        _write_cached_ohlcv(
            cache_root,
            dataset=aggregate_dataset,
            freq=freq,
            symbol=symbol_text,
            frame=standardized,
            source_root=aggregate_bars_root,
            symbol_column=aggregate_symbol_column,
            timestamp_column=aggregate_timestamp_column,
            aggregate_columns=aggregate_columns,
        )

    if start_date:
        standardized = standardized.loc[start_date:]
    if end_date:
        standardized = standardized.loc[:end_date]
    return standardized


def load_single_asset_ohlcv(
    *,
    symbol: str | None = None,
    mode: MarketDataMode,
    data_root: str | Path | None = None,
    source_path: str | Path | None = None,
    freq: str = "1d",
    start_date: str | None = None,
    end_date: str | None = None,
    prefer_parquet: bool = True,
    strict_temporal_validation: bool = True,
    max_rows: int | None = None,
    aggregate_bars_root: str | Path | None = None,
    aggregate_dataset: str = "daily_market_summary",
    aggregate_symbol_column: str = "ticker",
    aggregate_timestamp_column: str = "align_time",
    aggregate_columns: Mapping[str, str] | None = None,
    cache_root: str | Path | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    if mode == "source_path":
        if source_path is None:
            raise ValueError("source_path mode requires source_path")
        frame = load_standard_ohlcv(
            source_path,
            strict_temporal_validation=strict_temporal_validation,
            max_rows=None,
        )
    elif mode == "data_root":
        if data_root is None:
            raise ValueError("data_root mode requires data_root")
        if not symbol:
            raise ValueError("data_root mode requires symbol")
        source = choose_ohlcv_file(
            data_root=data_root,
            symbol=str(symbol),
            frequency=freq,
            prefer_parquet=prefer_parquet,
        )
        frame = load_standard_ohlcv(
            source,
            strict_temporal_validation=strict_temporal_validation,
            max_rows=None,
        )
    elif mode == "aggregate_bars_daily_summary":
        if not symbol:
            raise ValueError("aggregate_bars_daily_summary mode requires symbol")
        frame = _load_aggregate_bars_daily_summary(
            symbol=str(symbol),
            start_date=start_date,
            end_date=end_date,
            aggregate_bars_root=aggregate_bars_root,
            aggregate_dataset=aggregate_dataset,
            aggregate_symbol_column=aggregate_symbol_column,
            aggregate_timestamp_column=aggregate_timestamp_column,
            aggregate_columns=dict(DEFAULT_AGGREGATE_BARS_COLUMNS | dict(aggregate_columns or {})),
            freq=freq,
            cache_root=cache_root,
            refresh_cache=refresh_cache,
        )
        if max_rows is not None and max_rows > 0:
            frame = frame.tail(int(max_rows))
        return frame
    else:
        raise ValueError(f"Unsupported market data mode: {mode}")

    if start_date:
        frame = frame.loc[start_date:]
    if end_date:
        frame = frame.loc[:end_date]
    if max_rows is not None and max_rows > 0:
        frame = frame.tail(int(max_rows))
    return frame