"""
横截面算子（WorldQuant BRAIN — Cross Sectional）。

在同一 ``timestamp`` 上对所有 instrument 逐点计算；与 ``ts`` 的“按标的滚动”正交。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class Rank(Expr):
    """截面百分位排名 [0,1]；``rate`` 预留与 WQ 对齐，当前后端主要用 pct rank。"""

    child: Expr
    rate: int = 2

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class ZScore(Expr):
    """截面 Z 分数：(x - 当日均值) / 当日标准差。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Normalize(Expr):
    """去截面均值；use_std 为 True 时再除截面标准差；limit>0 时对结果 clip。"""

    child: Expr
    use_std: bool = False
    limit: float = 0.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class CsQuantile(Expr):
    """**截面** ``quantile``：在每个 ``timestamp`` 上，先把 ``child`` 变成当日横截面上的分位 ``q∈[0,1]``，
    再用 ``driver``（如 gaussian）做 **逆 CDF** 映射，得到近似目标分布的得分。

    与 ``ts_quantile``（**滚动时间窗**内算分位再映射）完全不同：一个是「同一天全市场比谁高」，
    一个是「同一标的过去 d 根 bar 比谁高」。默认 gaussian 需 scipy；``sigma`` 缩放输出尺度。
    """

    child: Expr
    driver: str = "gaussian"
    sigma: float = 1.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Scale(Expr):
    """**Book scaling**：在每个时间截面上，按多头与空头分别缩放 ``child``，使全截面加权绝对值和
    匹配 ``longscale`` / ``shortscale``（与 WQ 资金分配语义一致；细节以后端实现为准）。

    与简单 ``normalize`` 不同：这里区分多空头寸方向，常用于把 alpha 压到目标杠杆/容量。
    ``scale`` 为兼容参数，具体与 ``longscale``/``shortscale`` 组合方式见 ``operators_semantics``。
    """

    child: Expr
    scale: float = 1.0
    longscale: float = 1.0
    shortscale: float = 1.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Winsorize(Expr):
    """截面缩尾：超出 mean ± std*std_mult 的截断到边界。"""

    child: Expr
    std: float = 4.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Neutralize(Expr):
    """截面 OLS 残差：每个 ``timestamp`` 上对 ``y`` 回归 ``x``，返回 ``x - (alpha + beta * y)``。

    与 ``orthogonalize``（Gram-Schmidt 投影）不同：此处为 **带截距** 的最小二乘，Barra/风险因子
    文献里「对市值中性」常用回归残差形式。截面有效点少于 2 或 ``y`` 无方差时输出 NaN。
    """

    x: Expr
    y: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.y)
