from typing import TYPE_CHECKING

from .kline_parquet_source import KlineParquetSource
from .parquet_source import ParquetSource

if TYPE_CHECKING:
    from runtime.config import DataSourceConfig


def build_data_source(config: "DataSourceConfig"):
    normalized = config.type.strip().lower()

    if normalized == "parquet":
        return ParquetSource(**config.options)

    if normalized == "parquet_kline":
        return KlineParquetSource(**config.options)

    if normalized == "multi_parquet":
        from runtime.real_data_factor_smoke import MultiParquetSeriesSource
        return MultiParquetSeriesSource(**config.options)

    raise ValueError(f"Unsupported data source type: {config.type}")
