"""
数据清洗与数值安全算子（Deep Research：Pasteurize / Tail / Protected ops）。

与 ``arithmetic`` 区分：专注 Inf/NaN 处理、分位截断与除零安全，供 GP/RL 等自动挖掘避免
梯度爆炸与非法域错误；后续可接横截面统计前预处理与回测稳健性检查。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class Pasteurize(Expr):
    """将 Inf 置为 NaN，可选将 NaN 填为常数（「巴氏杀菌」式清洗）。

    **计算**：``result = where(isfinite(x), x, nan)``，若 ``fill_value`` 有限则 ``fillna``。

    **动机**：研究报告指出高频与自动演化管线需拦截非法浮点，避免污染后续 ``rank``/``zscore``。

    **后续**：可与 Universe 掩码结合，在挖掘引擎中对未上市标的强制置 NaN（见路线图）。
    """

    child: Expr
    fill_value: float | None = None

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class Tail(Expr):
    """按截面分位数截断长尾（各时间截面上对 ``x`` 做分位裁剪）。

    **计算**：在每个 ``timestamp`` 上，将 ``x`` 裁剪到
    ``[quantile(lower), quantile(upper)]``（线性插值分位）。

    **动机**：肥尾分布下极端值会扭曲回归与 IC；Tail 提供可组合的稳健预处理。

    **后续**：供 RL 状态标准化前级、或与 ``winsorize`` 对照做消融实验。
    """

    child: Expr
    lower: float = 0.01
    upper: float = 0.99

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class ProtectedDiv(Expr):
    """受保护除法：分母绝对值小于 ``epsilon`` 时返回 ``default``，避免 Inf。

    **计算**：``where(abs(y) >= eps, x/y, default)``（对非有限 ``x,y`` 输出 NaN）。

    **动机**：gplearn 等符号回归常用保护算子，防止自动生成的分母穿过零点。

    **后续**：可作为 DSL 中 ``divide`` 的安全替代参与遗传变异。
    """

    left: Expr
    right: Expr
    epsilon: float = 1e-12
    default: float = 0.0

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class ProtectedLog(Expr):
    """受保护对数：对 ``abs(x)`` 取 ``log``，过小模长返回 0。

    **计算**：令 ``m = max(abs(x), epsilon)``，``result = log(m)``；输入非有限则 NaN。

    **动机**：避免 ``log(0)`` 与负域错误，压缩右偏分布时保持挖掘稳定性。

    **后续**：与 ``rank`` 组合构造无量纲量价特征供 LLM 因子提案采样。
    """

    child: Expr
    epsilon: float = 1e-12

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class ProtectedSqrt(Expr):
    """受保护平方根：``sqrt(abs(x))``，避免复数域。

    **动机**：符号回归可能产生对负残差开方；保护形式保留幅度信息。

    **后续**：用于波动率类中间特征的非负参数化。
    """

    child: Expr

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
