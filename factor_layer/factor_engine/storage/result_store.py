"""因子读取器：从分区 Parquet 加载因子数据，支持多因子拼接与跨频对齐。

提供两种后端实现
-----------------
- **PolarsResultStore**（推荐）：利用 ``pl.scan_parquet()`` 实现惰性分区剪枝，
  由 Rust I/O 层跳过不需要的年份文件。
- **PandasResultStore**（兜底）：纯 Pandas 实现，适配未安装 Polars 的环境。

自动选择逻辑
-------------
``build_result_store()`` 工厂函数优先尝试 Polars 后端；进口失败时退化为
Pandas 后端并输出 WARNING 日志。
"""

from __future__ import annotations

import logging
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .catalog import FactorCatalog
from .exceptions import FactorNotFoundError

logger = logging.getLogger(__name__)


class ResultStore(ABC):
    """结果存储抽象基类。"""

    @abstractmethod
    def write(self, factor_name: str, result) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_factor(
        self,
        factor_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> Any:
        """加载单因子数据。"""
        raise NotImplementedError

    @abstractmethod
    def load_factors(
        self,
        factor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        align_method: str = "forward_fill",
    ) -> Any:
        """加载并拼接多因子数据。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _factor_parquet_paths(
    lake_root: Path, factor_id: str, start: str | None, end: str | None
) -> list[Path]:
    """返回因子分区 Parquet 路径列表，按年份做粗粒度剪枝。"""
    factor_dir = lake_root / "factors" / factor_id
    if not factor_dir.exists():
        return []

    start_year = int(start[:4]) if start else 0
    end_year = int(end[:4]) if end else 9999

    paths: list[Path] = []
    for partition_dir in sorted(factor_dir.iterdir()):
        if not partition_dir.is_dir() or not partition_dir.name.startswith("year="):
            # 兼容无分区的单文件因子
            pq = factor_dir / "data.parquet"
            if pq.exists() and pq not in paths:
                paths.append(pq)
            continue
        try:
            year = int(partition_dir.name.split("=")[1])
        except (IndexError, ValueError):
            continue
        if start_year <= year <= end_year:
            pq = partition_dir / "data.parquet"
            if pq.exists():
                paths.append(pq)
    return paths


# ---------------------------------------------------------------------------
# Polars 后端
# ---------------------------------------------------------------------------

class PolarsResultStore(ResultStore):
    """Polars LazyFrame 惰性读取后端（推荐）。

    Parameters
    ----------
    lake_root : str | Path
        落盘根目录。
    catalog : FactorCatalog
        元数据目录（用于查询频率信息做跨频对齐）。
    """

    def __init__(self, lake_root: str | Path, catalog: FactorCatalog) -> None:
        import polars as pl  # 延迟导入：不强制依赖

        self._lake_root = Path(lake_root)
        self._catalog = catalog
        self._pl = pl

    def write(self, factor_name: str, result) -> None:
        """ResultStore 抽象方法；写入应通过 ParquetMaterializer 完成。"""
        raise NotImplementedError(
            "写入请使用 ParquetMaterializer.materialize()，"
            "ResultStore 仅负责读取。"
        )

    def load_factor(
        self,
        factor_id: str,
        start: str | None = None,
        end: str | None = None,
    ):
        """加载单因子为 ``pl.LazyFrame[datetime, asset, value]``。

        利用分区剪枝跳过不需要的年份文件。
        """
        pl = self._pl
        paths = _factor_parquet_paths(self._lake_root, factor_id, start, end)
        if not paths:
            raise FactorNotFoundError(
                f"因子 '{factor_id}' 无可用 Parquet 文件"
                f"（区间: {start or '…'} ~ {end or '…'}）。"
            )

        lf = pl.scan_parquet(paths)

        # 精确时间过滤（分区仅做粗粒度年份剪枝）
        if start:
            lf = lf.filter(pl.col("datetime") >= pl.lit(start).str.to_datetime())
        if end:
            lf = lf.filter(pl.col("datetime") <= pl.lit(end).str.to_datetime())

        return lf

    def load_factors(
        self,
        factor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        align_method: str = "forward_fill",
    ):
        """加载多因子并自动拼接为宽表 ``pl.LazyFrame[datetime, asset, f1, f2, ...]``。

        Parameters
        ----------
        factor_ids : list[str]
            要加载的因子 ID 列表。
        start, end : str | None
            时间过滤范围（ISO 格式）。
        align_method : str
            跨频对齐策略：``'forward_fill'`` 或 ``'asof'``。
        """
        pl = self._pl

        if not factor_ids:
            raise ValueError("factor_ids 不能为空。")

        # 加载第一个因子作为基底
        base = self.load_factor(factor_ids[0], start, end).rename(
            {"value": factor_ids[0]}
        )

        for fid in factor_ids[1:]:
            other = self.load_factor(fid, start, end).rename({"value": fid})

            # 查询频率信息以决定对齐策略
            base_info = self._catalog.get_factor_info(factor_ids[0])
            other_info = self._catalog.get_factor_info(fid)

            # 同频或无法判断频率 → 直接 outer join
            if (
                base_info is None
                or other_info is None
                or base_info.get("frequency") == other_info.get("frequency")
            ):
                base = base.join(other, on=["datetime", "asset"], how="full", coalesce=True)
            elif align_method == "asof":
                # ASOF Join：需要预排序
                base = base.sort("datetime")
                other = other.sort("datetime")
                base = base.join_asof(
                    other.drop("asset"),
                    on="datetime",
                    strategy="backward",
                )
            else:
                # forward_fill：先 outer join，再前向填充
                base = base.join(other, on=["datetime", "asset"], how="full", coalesce=True)
                base = base.sort(["asset", "datetime"])
                base = base.with_columns(
                    pl.col(fid).forward_fill().over("asset")
                )

        return base

    def to_pandas(
        self,
        factor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        align_method: str = "forward_fill",
    ):
        """加载多因子并直接返回 ``pd.DataFrame``。"""
        lf = self.load_factors(factor_ids, start, end, align_method)
        return lf.collect().to_pandas()


# ---------------------------------------------------------------------------
# Pandas 兜底后端
# ---------------------------------------------------------------------------

class PandasResultStore(ResultStore):
    """纯 Pandas 读取后端（兜底，未安装 Polars 时使用）。

    .. warning::

        Pandas 后端不支持惰性加载，大数据量时性能不如 Polars。
    """

    def __init__(self, lake_root: str | Path, catalog: FactorCatalog) -> None:
        self._lake_root = Path(lake_root)
        self._catalog = catalog

    def write(self, factor_name: str, result) -> None:
        raise NotImplementedError(
            "写入请使用 ParquetMaterializer.materialize()，"
            "ResultStore 仅负责读取。"
        )

    def load_factor(
        self,
        factor_id: str,
        start: str | None = None,
        end: str | None = None,
    ):
        """加载单因子为 ``pd.DataFrame[datetime, asset, value]``。"""
        import pandas as pd

        paths = _factor_parquet_paths(self._lake_root, factor_id, start, end)
        if not paths:
            raise FactorNotFoundError(
                f"因子 '{factor_id}' 无可用 Parquet 文件"
                f"（区间: {start or '…'} ~ {end or '…'}）。"
            )

        frames = [pd.read_parquet(p) for p in paths]
        df = pd.concat(frames, ignore_index=True)

        if start:
            df = df[df["datetime"] >= pd.Timestamp(start)]
        if end:
            df = df[df["datetime"] <= pd.Timestamp(end)]

        return df.sort_values(["asset", "datetime"]).reset_index(drop=True)

    def load_factors(
        self,
        factor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        align_method: str = "forward_fill",
    ):
        """加载多因子并拼接为宽表 ``pd.DataFrame``。"""
        import pandas as pd

        if not factor_ids:
            raise ValueError("factor_ids 不能为空。")

        base = self.load_factor(factor_ids[0], start, end).rename(
            columns={"value": factor_ids[0]}
        )

        for fid in factor_ids[1:]:
            other = self.load_factor(fid, start, end).rename(
                columns={"value": fid}
            )
            base = base.merge(other, on=["datetime", "asset"], how="outer")

        base = base.sort_values(["asset", "datetime"]).reset_index(drop=True)

        # 跨频对齐
        if align_method == "forward_fill":
            for fid in factor_ids:
                if fid in base.columns:
                    base[fid] = base.groupby("asset")[fid].ffill()

        return base

    def to_pandas(
        self,
        factor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        align_method: str = "forward_fill",
    ):
        """直接返回 ``pd.DataFrame``（本身就是 Pandas）。"""
        return self.load_factors(factor_ids, start, end, align_method)


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def build_result_store(
    lake_root: str | Path,
    catalog: FactorCatalog | None = None,
) -> ResultStore:
    """自动选择最佳后端：优先 Polars，退化 Pandas。

    Parameters
    ----------
    lake_root : str | Path
        落盘根目录。
    catalog : FactorCatalog | None
        元数据目录。``None`` 时自动从 ``lake_root/_catalog.sqlite`` 创建。
    """
    lake_root = Path(lake_root)
    if catalog is None:
        catalog = FactorCatalog(lake_root / "_catalog.sqlite")

    try:
        import polars  # noqa: F401

        return PolarsResultStore(lake_root, catalog)
    except ImportError:
        warnings.warn(
            "未安装 polars，ResultStore 退化为 Pandas 后端。"
            "大数据量场景建议 `pip install polars>=0.20` 以获得显著性能提升。",
            stacklevel=2,
        )
        return PandasResultStore(lake_root, catalog)
