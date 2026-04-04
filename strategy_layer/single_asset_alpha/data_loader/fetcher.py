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

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Any


class DataFetcher:
    """单标的数据获取器。

    Parameters
    ----------
    data_root : str or Path
        标准化 parquet 数据根目录。
    factor_root : str or Path, optional
        因子数据根目录。
    """

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
    ):
        self.data_root = Path(data_root) if data_root else None
        self.factor_root = Path(factor_root) if factor_root else None

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
        if source_path is not None:
            df = self._read_parquet(Path(source_path))
        elif self.data_root is not None:
            # 自动查找: data_root / {freq} / {symbol}.parquet
            candidates = [
                self.data_root / freq / f"{symbol}.parquet",
                self.data_root / f"{symbol}.parquet",
                self.data_root / f"{symbol}_{freq}.parquet",
            ]
            found = None
            for p in candidates:
                if p.exists():
                    found = p
                    break
            if found is None:
                raise FileNotFoundError(
                    f"找不到标的 {symbol} 的行情数据。\n"
                    f"已搜索路径: {[str(p) for p in candidates]}"
                )
            df = self._read_parquet(found)
        else:
            raise ValueError("必须指定 data_root 或 source_path 之一")

        # 标准化列名
        df = self._standardize_columns(df)

        # 确保 datetime 索引
        df = self._ensure_datetime_index(df)

        # 按时间排序
        df = df.sort_index()

        # 时间范围筛选
        if start_date:
            df = df.loc[start_date:]
        if end_date:
            df = df.loc[:end_date]

        return df

    def load_factor_data(
        self,
        symbol: str,
        factor_names: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        source_path: str | Path | None = None,
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
                # 尝试其他路径格式
                path = self.factor_root / symbol / "factors.parquet"
                if not path.exists():
                    return None
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

        # 模拟价格: 几何布朗运动
        initial_price = 10.0
        daily_returns = rng.normal(loc=0.0003, scale=0.02, size=periods)
        prices = initial_price * np.exp(np.cumsum(daily_returns))

        # OHLCV
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

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一列名到内部标准。"""
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
