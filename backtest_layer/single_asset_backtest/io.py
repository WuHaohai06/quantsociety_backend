from __future__ import annotations

"""磁盘 IO：目标仓位文件、OHLCV 表；``data_root`` 下按标的/频率自动发现文件（含黄金别名与扁平命名）。"""
from pathlib import Path
import re

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.contracts import validate_target_position, validate_temporal_integrity


def load_target_position(path: str | Path, *, strict: bool = True, enforce_bounds: bool = True) -> pd.Series:
    """从 CSV/Parquet 读入目标仓位，再走 ``validate_target_position``。"""
    data_path = Path(path)
    suffix = data_path.suffix.lower()

    if suffix == ".csv":
        frame = pd.read_csv(data_path)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(data_path)
    else:
        raise ValueError(f"Unsupported target_position file type: {suffix}")

    return validate_target_position(frame, strict=strict, enforce_bounds=enforce_bounds)


def _read_table(path: Path) -> pd.DataFrame:
    """按扩展名读 CSV 或 Parquet 为 DataFrame。"""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _choose_ohlcv_file(*, data_root: str | Path, symbol: str, frequency: str, prefer_parquet: bool) -> Path:
    """在 ``data_root`` 下解析单文件：优先 ``symbol/frequency/*``，其次扁平 ``{symbol}_{freq}*``，再扫目录匹配频率别名与 XAU/黄金。"""
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


def load_ohlcv(path: str | Path, *, strict_temporal_validation: bool = True, max_rows: int | None = None) -> pd.DataFrame:
    """读单文件 OHLCV：timestamp 列 → 无时区索引，可选时间完整性校验与尾部截断。"""
    data_path = Path(path)
    frame = _read_table(data_path)

    frame = validate_temporal_integrity(frame, strict=strict_temporal_validation)

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLCV missing required columns: {sorted(missing)}")

    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise").dt.tz_convert(None)
    out = out.set_index("timestamp").sort_index()

    if "volume" not in out.columns:
        out["volume"] = 0.0

    if max_rows is not None and max_rows > 0:
        out = out.tail(int(max_rows))

    return out[["open", "high", "low", "close", "volume"]]


def load_ohlcv_from_config(config: BacktestConfig) -> pd.DataFrame:
    """根据 ``BacktestConfig.data_root/symbol/frequency`` 选文件并 ``load_ohlcv``。"""
    if not config.symbol:
        raise ValueError("BacktestConfig.symbol is required when loading OHLCV from data_root")
    if not config.frequency:
        raise ValueError("BacktestConfig.frequency is required when loading OHLCV from data_root")

    source = _choose_ohlcv_file(
        data_root=config.data_root,
        symbol=config.symbol,
        frequency=config.frequency,
        prefer_parquet=config.prefer_parquet,
    )
    return load_ohlcv(
        source,
        strict_temporal_validation=config.strict_temporal_validation,
        max_rows=config.max_rows,
    )
