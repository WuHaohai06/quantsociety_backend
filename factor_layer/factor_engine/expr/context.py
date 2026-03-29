"""
工程上下文算子（Qlib ChangeInstrument / Barra 正交化思想）。

**动机**：多资产张量上需要对齐基准收益或剔除共线风险因子；研究报告强调 Gram-Schmidt
与基准切换可减少冗余暴露、简化跨表 Join。

**后续**：时序版正交化（滚动投影）可在本模块延伸；换基准可与指数成分数据源联动。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class Orthogonalize(Expr):
    """截面 **Gram-Schmidt 一步**：在每个 ``timestamp`` 上，用同日全截面的内积估计
    ``beta = <x,y>/<y,y>``，输出 ``x_orth = x - beta * y``（即去掉 x 在 y 方向上的线性成分）。

    **仅在 x、y 同时有限的截面上** 估计 beta；若 ``<y,y>`` 为 0 或样本不足，输出 NaN。
    这是 **线性投影** 而非分组回归残差；**未**按行业分组。若需「行业内对市值中性」应使用
    ``group_neutralize`` 或与行业虚拟变量组合。与 Barra 风格「对风格因子正交」思想一致，
    但实现为单日全截面一元投影。详见 ``operators_semantics``。
    """

    x: Expr
    y: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.y)


@dataclass(frozen=True)
class ChangeInstrument(Expr):
    """**换基准 / 相对强度**：输出近似 ``child / benchmark``，其中 benchmark 由命名列推导。

    基准列加载后：若为 **多标的** MultiIndex，则每个 ``timestamp`` 上对基准列取截面 **均值**
    得到一个标量，再广播到 ``child`` 的同索引行（表示相对「当日市场或篮子平均」）；若为
    **单序列** 则按时间对齐 reindex 后逐点相除。用于超额收益、相对指数表现等；**不等于**
    按成分权重的精确指数复制，除非数据源已构造好该基准列。完整约定见
    ``docs/adr_context_benchmark.md``。
    """

    child: Expr
    benchmark_column: str

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
