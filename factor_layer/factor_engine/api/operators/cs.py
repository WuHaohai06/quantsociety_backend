"""横截面算子 API：每个 ``timestamp`` 上跨 **所有 instrument** 计算，与 ``ts_*`` 的按标的滚动正交。

易混：**``quantile``（本模块）** 是截面 rank 再逆 CDF；**``ts_quantile``** 是滚动时间窗内分位
再映射——二者完全不同。
"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.cs import CsQuantile, Neutralize, Normalize, Rank, Scale, Winsorize, ZScore


def rank(x: Expr, rate: int = 2) -> Expr:
    """全截面分位秩。

    **华泰对照**：《GPT 因子工厂 2.0》图表 9 ``CS_Rank(X)``（华泰证券）。
    """
    return Rank(child=ensure_expr(x), rate=rate)


def zscore(x: Expr) -> Expr:
    return ZScore(child=ensure_expr(x))


def normalize(x: Expr, useStd: bool = False, limit: float = 0.0) -> Expr:
    return Normalize(child=ensure_expr(x), use_std=useStd, limit=limit)


def quantile(x: Expr, driver: str = "gaussian", sigma: float = 1.0) -> Expr:
    """截面分位再映射分布（默认高斯）；非时序 ``ts_quantile``。需 scipy（与可选依赖一致）。"""
    return CsQuantile(child=ensure_expr(x), driver=driver, sigma=sigma)


def scale(
    x: Expr, scale: float = 1.0, longscale: float = 1.0, shortscale: float = 1.0
) -> Expr:
    """按多空侧分别缩放，使 book 绝对值和匹配目标（WQ scale 语义，细节见 ``expr.cs.Scale``）。"""
    return Scale(
        child=ensure_expr(x),
        scale=scale,
        longscale=longscale,
        shortscale=shortscale,
    )


def winsorize(x: Expr, std: float = 4.0) -> Expr:
    return Winsorize(child=ensure_expr(x), std=std)


def neutralize(x: Expr, y: Expr) -> Expr:
    """截面 OLS 残差 ``x - (alpha + beta*y)``；与 ``orthogonalize``（无截距投影）不同。"""
    return Neutralize(x=ensure_expr(x), y=ensure_expr(y))
