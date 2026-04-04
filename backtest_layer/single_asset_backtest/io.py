from __future__ import annotations

"""磁盘 IO：目标仓位文件、OHLCV 表；``data_root`` 下按标的/频率自动发现文件（含黄金别名与扁平命名）。"""
from pathlib import Path

import pandas as pd

from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.contracts import validate_target_position


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


def load_ohlcv(path: str | Path, *, strict_temporal_validation: bool = True, max_rows: int | None = None) -> pd.DataFrame:
    """读单文件 OHLCV：timestamp 列 → 无时区索引，可选时间完整性校验与尾部截断。"""
    from strategy_layer.data import load_standard_ohlcv

    return load_standard_ohlcv(
        path,
        strict_temporal_validation=strict_temporal_validation,
        max_rows=max_rows,
    )


def load_ohlcv_from_config(config: BacktestConfig) -> pd.DataFrame:
    """根据 ``BacktestConfig`` 统一加载标准 OHLCV。"""
    from strategy_layer.data import load_single_asset_ohlcv

    if config.market_data_mode in {"data_root", "aggregate_bars_daily_summary"} and not config.symbol:
        raise ValueError("BacktestConfig.symbol is required when loading OHLCV from configured market data source")
    if config.market_data_mode == "data_root" and not config.frequency:
        raise ValueError("BacktestConfig.frequency is required when market_data_mode=data_root")
    if config.market_data_mode == "source_path" and not config.source_path:
        raise ValueError("BacktestConfig.source_path is required when market_data_mode=source_path")

    return load_single_asset_ohlcv(
        symbol=config.symbol,
        mode=config.market_data_mode,
        data_root=config.data_root,
        source_path=config.source_path,
        freq=config.frequency or "1d",
        prefer_parquet=config.prefer_parquet,
        strict_temporal_validation=config.strict_temporal_validation,
        max_rows=config.max_rows,
        aggregate_bars_root=config.aggregate_bars_root,
        aggregate_dataset=config.aggregate_dataset,
        aggregate_symbol_column=config.aggregate_symbol_column,
        aggregate_timestamp_column=config.aggregate_timestamp_column,
        aggregate_columns=config.aggregate_columns,
        cache_root=config.market_data_cache_root,
    )
