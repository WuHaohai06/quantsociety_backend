"""
分组算子（WorldQuant — Group）。

在 ``group`` 列定义的组内（同一时刻、同一组 id）做统计；需额外加载 group 列。
PandasBackend 已实现：在同一 ``timestamp``、同一 ``group`` 标签内做变换/排名等
（与 BRAIN ``group_*`` 及研究报告中的 ``group_rank`` / ``indneutralize`` 类语义一致：
``group_neutralize`` 等价于按组去均值，接近行业中性 ``indneutralize``）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class GroupBackfill(Expr):
    """在 **同一 timestamp、同一 group 标签** 内，用该组过去 d 根 bar 的 winsor 截断均值填当前 NaN。

    与全截面 ``ts_backfill`` 不同：这里「组」由 ``group`` 列定义（如行业），只在组内借历史；
    用于缺失在组内可比时更合理的补全。``std`` 控制 winsor 宽度。
    """

    x: Expr
    group: Expr
    d: int
    std: float = 4.0

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.group)


@dataclass(frozen=True)
class GroupMean(Expr):
    """同一时刻、同一 ``group`` 内对 ``x`` 按 ``weight`` 做加权平均，再广播回各标的。

    权重应非负；组内权重和为 0 或全 NaN 时结果多为 NaN。用于组内聚合特征再映射到成员。
    """

    x: Expr
    weight: Expr
    group: Expr

    def children(self) -> tuple[Expr, Expr, Expr]:
        return (self.x, self.weight, self.group)


@dataclass(frozen=True)
class GroupNeutralize(Expr):
    """**组内去均值**：每个时间截面上，对每个 ``group`` 标签分别算 ``x`` 的均值，再用 ``x - 组均值``。

    与截面 ``zscore``（全市场标准化）不同：这里剥离的是 **组内共同水平**（研究报告里与
    **indneutralize** / 行业中性接近：``group_neutralize(x, sector)`` ≈ 行业内相对排名前的
    去均值）。**不是** 对全截面减一个数；也不是时间序列 demean。
    """

    x: Expr
    group: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.group)


@dataclass(frozen=True)
class GroupRank(Expr):
    """同一 timestamp、同一 ``group`` 内对 ``x`` 做 **百分位排名**（与截面 ``rank`` 类似但范围缩在组内）。

    输出约在 [0,1]；组内仅一点或全 NaN 时行为由后端决定（多为 NaN 或常数）。用于行业内排序、
    组内动量分位等。

    **华泰对照**：图表 9 ``CS_Indus_Rank(X, indus_belong)``（华泰证券）。
    """

    x: Expr
    group: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.group)


@dataclass(frozen=True)
class GroupScale(Expr):
    """组内 min-max 缩放到 [0,1]（同一时刻、同一 ``group`` 内取 min/max，再对组内各点线性变换）。

    组内常数或全 NaN 时通常输出 NaN。与 ``group_zscore`` 相比，对极端值尺度敏感（未先截尾时）。
    """

    x: Expr
    group: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.group)


@dataclass(frozen=True)
class GroupZscore(Expr):
    """组内标准化：``(x - 组均值) / 组标准差``（同一 timestamp、同一 ``group``）。

    组内标准差为 0 或样本不足时多为 NaN。比 ``group_neutralize`` 多除以波动，得到无量纲组内相对偏离。
    """

    x: Expr
    group: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.x, self.group)
