"""
数据获取器 (Data Fetcher)
=========================

封装对上游数据底座的访问接口。
上游数据源:
  - 陆殷世杰提供的标准化 parquet 数据目录 (raw_data_layer)
  - 因子计算结果 (factor_layer/factor_engine 落盘文件)

本模块屏蔽底层存储细节，向信号生成层提供统一的 DataFrame 接口。
"""

from __future__ import annotations

from collections.abc import Sequence
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Any

from strategy_layer.data import (
    FactorRef,
    build_factor_panel,
    load_single_asset_ohlcv,
    project_single_asset,
)


class DataFetcher:
    """单标的数据获取器。

    Parameters
    ----------
    data_root : str or Path
        标准化 parquet 数据根目录。
    factor_root : str or Path, optional
        旧版单标因子宽表根目录。
    factor_lake_root : str or Path, optional
        公共 factor lake 根目录。
    factor_refs : list[str | FactorRef], optional
        factor lake 读取配置。若使用 factor lake，这里建议显式给出。
    aggregate_bars_root : str or Path, optional
        aggregate_bars 原始目录根，例如 massive_parquet 的 aggregate_bars。
    aggregate_dataset : str
        aggregate_bars 子数据集名称，默认 `daily_market_summary`。
    aggregate_symbol_column : str
        aggregate_bars 中的标的列名，默认 `ticker`。
    aggregate_timestamp_column : str
        aggregate_bars 中的时间列名，默认 `align_time`。
    aggregate_columns : dict[str, str], optional
        aggregate_bars 的 OHLCV 列映射，例如 `{"open": "o", ...}`。
    market_data_cache_root : str or Path, optional
        公共标准化行情缓存目录；aggregate_bars 模式下会优先读写这里。
    """

    AGGREGATE_BARS_DEFAULT_COLUMNS = {
        "open": "o",
        "high": "h",
        "low": "l",
        "close": "c",
        "volume": "v",
    }

    # 标准化字段映射 (源列名 → 内部列名)
    COLUMN_MAP = {
        # 如果上游字段名不一致，在这里统一映射
        "timestamp": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }

    def __init__(
        self,
        data_root: str | Path | None = None,
        factor_root: str | Path | None = None,
        factor_lake_root: str | Path | None = None,
        factor_refs: Sequence[str | FactorRef] | None = None,
        factor_lake_align_method: str = "outer",
        aggregate_bars_root: str | Path | None = None,
        aggregate_dataset: str = "daily_market_summary",
        aggregate_symbol_column: str = "ticker",
        aggregate_timestamp_column: str = "align_time",
        aggregate_columns: dict[str, str] | None = None,
        market_data_cache_root: str | Path | None = None,
    ):
        self.data_root = Path(data_root) if data_root else None
        self.factor_root = Path(factor_root) if factor_root else None
        self.factor_lake_root = Path(factor_lake_root) if factor_lake_root else None
        self.factor_refs = self._normalize_factor_refs(factor_refs)
        self.factor_lake_align_method = factor_lake_align_method
        self.aggregate_bars_root = Path(aggregate_bars_root) if aggregate_bars_root else None
        self.aggregate_dataset = str(aggregate_dataset).strip() or "daily_market_summary"
        self.aggregate_symbol_column = str(aggregate_symbol_column).strip() or "ticker"
        self.aggregate_timestamp_column = str(aggregate_timestamp_column).strip() or "align_time"
        self.aggregate_columns = dict(self.AGGREGATE_BARS_DEFAULT_COLUMNS)
        if aggregate_columns:
            self.aggregate_columns.update({str(key): str(value) for key, value in aggregate_columns.items()})
        self.market_data_cache_root = Path(market_data_cache_root) if market_data_cache_root else None

    @property
    def has_factor_source(self) -> bool:
        return self.factor_root is not None or self.factor_lake_root is not None

    def load_market_data(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        freq: str = "1d",
        source_path: str | Path | None = None,
    ) -> pd.DataFrame:
        """加载单标的行情 OHLCV 数据。

        Parameters
        ----------
        symbol : str
            标的代码。
        start_date : str, optional
            起始日期 (含)。
        end_date : str, optional
            结束日期 (含)。
        freq : str
            数据频率: "1d" (日频) 或 "1min" (分钟频)。
        source_path : str or Path, optional
            直接指定数据文件路径（覆盖自动查找逻辑）。

        Returns
        -------
        pd.DataFrame
            索引为 DatetimeIndex 的标准 OHLCV 数据。
        """
        mode: str
        if source_path is not None:
            mode = "source_path"
        elif self.aggregate_bars_root is not None:
            mode = "aggregate_bars_daily_summary"
        elif self.data_root is not None:
            mode = "data_root"
        else:
            raise ValueError("必须指定 data_root、aggregate_bars_root 或 source_path 之一")

        return load_single_asset_ohlcv(
            symbol=symbol,
            mode=mode,
            data_root=self.data_root,
            source_path=source_path,
            freq=freq,
            start_date=start_date,
            end_date=end_date,
            aggregate_bars_root=self.aggregate_bars_root,
            aggregate_dataset=self.aggregate_dataset,
            aggregate_symbol_column=self.aggregate_symbol_column,
            aggregate_timestamp_column=self.aggregate_timestamp_column,
            aggregate_columns=self.aggregate_columns,
            cache_root=self.market_data_cache_root,
        )

    def load_factor_data(
        self,
        symbol: str,
        factor_names: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        source_path: str | Path | None = None,
        factor_refs: Sequence[str | FactorRef] | None = None,
    ) -> pd.DataFrame | None:
        """加载因子数据。

        Parameters
        ----------
        symbol : str
            标的代码。
        factor_names : list[str], optional
            需要加载的因子名列表，为 None 时加载全部。
        start_date, end_date : str, optional
            时间范围。
        source_path : str or Path, optional
            直接指定因子数据文件路径。
        factor_refs : list[str | FactorRef], optional
            当使用 factor lake 时，指定要读取的因子及别名。

        Returns
        -------
        pd.DataFrame or None
            索引为 DatetimeIndex 的因子数据，列名为因子名。
            若找不到因子数据，返回 None。
        """
        if source_path is not None:
            path = Path(source_path)
        elif self.factor_root is not None:
            path = self.factor_root / f"{symbol}_factors.parquet"
            if not path.exists():
                # 兼容「按标的分子目录」的落盘方式
                path = self.factor_root / symbol / "factors.parquet"
                if not path.exists():
                    return None
        elif self.factor_lake_root is not None:
            refs = self._resolve_factor_refs(
                factor_names=factor_names,
                factor_refs=factor_refs,
            )
            if not refs:
                return None
            panel = build_factor_panel(
                self.factor_lake_root,
                refs,
                start=start_date,
                end=end_date,
                symbols=[symbol],
                align_method=self.factor_lake_align_method,
            )
            projected = project_single_asset(panel, symbol)
            if factor_names:
                available = [name for name in factor_names if name in projected.columns]
                if not available:
                    return None
                projected = projected[available]
            if projected.empty:
                return None
            return projected
        else:
            return None

        if not path.exists():
            return None

        df = self._read_parquet(path)
        df = self._ensure_datetime_index(df)
        df = df.sort_index()

        if factor_names:
            available = [f for f in factor_names if f in df.columns]
            if not available:
                return None
            df = df[available]

        if start_date:
            df = df.loc[start_date:]
        if end_date:
            df = df.loc[:end_date]

        return df

    def _resolve_factor_refs(
        self,
        *,
        factor_names: list[str] | None,
        factor_refs: Sequence[str | FactorRef] | None,
    ) -> tuple[FactorRef, ...]:
        if factor_refs is not None:
            return self._normalize_factor_refs(factor_refs)
        if factor_names:
            if self.factor_refs:
                configured_by_name = {ref.name: ref for ref in self.factor_refs}
                return tuple(
                    configured_by_name.get(
                        name,
                        FactorRef(factor_id=name, column_name=name),
                    )
                    for name in factor_names
                )
            return tuple(FactorRef(factor_id=name, column_name=name) for name in factor_names)
        return self.factor_refs

    @staticmethod
    def _normalize_factor_refs(
        factor_refs: Sequence[str | FactorRef] | None,
    ) -> tuple[FactorRef, ...]:
        if factor_refs is None:
            return ()
        normalized: list[FactorRef] = []
        for item in factor_refs:
            if isinstance(item, FactorRef):
                normalized.append(item)
            else:
                normalized.append(FactorRef(factor_id=str(item), column_name=str(item)))
        return tuple(normalized)

    @staticmethod
    def generate_sample_data(
        symbol: str = "000001.SZ",
        periods: int = 500,
        start_date: str = "2023-01-01",
        seed: int = 42,
    ) -> pd.DataFrame:
        """生成模拟行情数据（用于开发测试和 Mock 交付）。

        Parameters
        ----------
        symbol : str
            标的代码。
        periods : int
            生成天数。
        start_date : str
            起始日期。
        seed : int
            随机种子，确保可复现。

        Returns
        -------
        pd.DataFrame
            模拟的 OHLCV 数据。
        """
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range(start=start_date, periods=periods, freq="B")

        # 几何布朗运动：仅用于开发/单测，不代表真实行情统计特性
        initial_price = 10.0
        daily_returns = rng.normal(loc=0.0003, scale=0.02, size=periods)
        prices = initial_price * np.exp(np.cumsum(daily_returns))

        # 用噪声拉开 high/low，使 rolling 类指标有足够截面变化
        intraday_noise = rng.uniform(0.005, 0.025, size=periods)
        df = pd.DataFrame(
            {
                "open": prices * (1 + rng.uniform(-0.01, 0.01, size=periods)),
                "high": prices * (1 + intraday_noise),
                "low": prices * (1 - intraday_noise),
                "close": prices,
                "volume": rng.integers(100_000, 10_000_000, size=periods).astype(float),
            },
            index=dates,
        )
        df.index.name = "timestamp"
        return df

    # ── 内部方法 ──────────────────────────────────────────────

    @staticmethod
    def _read_parquet(path: Path) -> pd.DataFrame:
        """读取 parquet 文件。"""
        return pd.read_parquet(path)

    def _load_aggregate_bars_daily_summary(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        symbol_text = str(symbol).strip()
        dataset_dir = self._get_aggregate_dataset_dir()
        paths = self._collect_aggregate_bars_paths(
            dataset_dir,
            start_date=start_date,
            end_date=end_date,
        )

        frames = [self._read_aggregate_bars_partition(path, symbol_text) for path in paths]
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if frame.empty:
            raise FileNotFoundError(
                f"aggregate_bars 中找不到标的 {symbol_text} 的数据。"
                f" dataset={self.aggregate_dataset}, years={self._describe_year_window(start_date, end_date)}"
            )

        frame["symbol"] = frame["symbol"].astype("string").str.strip()
        frame = frame.loc[frame["symbol"] == symbol_text].copy()
        if frame.empty:
            raise FileNotFoundError(
                f"aggregate_bars 中找不到标的 {symbol_text} 的数据。"
                f" dataset={self.aggregate_dataset}, years={self._describe_year_window(start_date, end_date)}"
            )

        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if isinstance(timestamps.dtype, pd.DatetimeTZDtype):
            timestamps = timestamps.dt.tz_convert(None)
        frame["timestamp"] = timestamps

        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
        frame["volume"] = frame["volume"].fillna(0.0)

        if frame["timestamp"].duplicated().any():
            duplicated = frame.loc[frame["timestamp"].duplicated(keep=False), ["timestamp"]].head(3)
            raise ValueError(
                f"aggregate_bars 中同一标的存在重复 timestamp: symbol={symbol_text}, sample={duplicated['timestamp'].astype(str).tolist()}"
            )

        return frame[["timestamp", "open", "high", "low", "close", "volume"]]

    def _get_aggregate_dataset_dir(self) -> Path:
        if self.aggregate_bars_root is None:
            raise ValueError("aggregate_bars_root 未配置")
        dataset_dir = self.aggregate_bars_root / self.aggregate_dataset
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            raise FileNotFoundError(f"aggregate_bars dataset 目录不存在: {dataset_dir}")
        return dataset_dir

    def _collect_aggregate_bars_paths(
        self,
        dataset_dir: Path,
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> list[Path]:
        paths = sorted(dataset_dir.glob(f"{self.aggregate_dataset}_*.parquet"))
        if not paths:
            raise FileNotFoundError(f"aggregate_bars dataset 下没有 parquet 文件: {dataset_dir}")

        start_year = self._boundary_year(start_date, 0)
        end_year = self._boundary_year(end_date, 9999)
        filtered = []
        for path in paths:
            year = self._extract_aggregate_partition_year(path)
            if year is None or start_year <= year <= end_year:
                filtered.append(path)
        if not filtered:
            raise FileNotFoundError(
                f"aggregate_bars 在指定年份窗口内没有 parquet 文件: dataset={dataset_dir}, years={start_year}-{end_year}"
            )
        return filtered

    def _read_aggregate_bars_partition(self, path: Path, symbol: str) -> pd.DataFrame:
        rename_map = {
            self.aggregate_symbol_column: "symbol",
            self.aggregate_timestamp_column: "timestamp",
            self.aggregate_columns["open"]: "open",
            self.aggregate_columns["high"]: "high",
            self.aggregate_columns["low"]: "low",
            self.aggregate_columns["close"]: "close",
            self.aggregate_columns["volume"]: "volume",
        }
        read_columns = list(dict.fromkeys(rename_map.keys()))
        try:
            frame = pd.read_parquet(
                path,
                columns=read_columns,
                filters=[(self.aggregate_symbol_column, "==", symbol)],
            )
        except Exception:
            frame = pd.read_parquet(path, columns=read_columns)
        if self.aggregate_symbol_column in frame.columns:
            symbols = frame[self.aggregate_symbol_column].astype("string").str.strip()
            frame = frame.loc[symbols == symbol].copy()
        return frame.rename(columns=rename_map)

    @staticmethod
    def _extract_aggregate_partition_year(path: Path) -> int | None:
        stem = path.stem
        year_text = stem.rsplit("_", 1)[-1]
        if year_text.isdigit() and len(year_text) == 4:
            return int(year_text)
        return None

    @staticmethod
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

    @staticmethod
    def _describe_year_window(start_date: str | None, end_date: str | None) -> str:
        start_year = DataFetcher._boundary_year(start_date, 0)
        end_year = DataFetcher._boundary_year(end_date, 9999)
        return f"{start_year}-{end_year}"

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一列名到内部标准（大小写不敏感匹配，避免上游 CSV 列名漂移）。"""
        rename_map = {}
        lower_cols = {c.lower(): c for c in df.columns}
        for standard, _ in self.COLUMN_MAP.items():
            if standard not in df.columns and standard.lower() in lower_cols:
                rename_map[lower_cols[standard.lower()]] = standard
        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    @staticmethod
    def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
        """确保 DataFrame 具有 DatetimeIndex。"""
        if isinstance(df.index, pd.DatetimeIndex):
            return df

        # 尝试从常见时间列名构建
        for col in ("timestamp", "datetime", "date", "time", "dt"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                df = df.set_index(col)
                return df

        # 最后手段：尝试将索引转为 datetime
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            raise ValueError("无法自动识别时间列或索引")

        return df
