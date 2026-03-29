"""分组算子 API：同一 ``timestamp``、同一 ``group`` 标签（如行业）内变换；与截面 ``rank`` 不同。

**``group_neutralize``** ≈ 组内去均值，接近行业中性 **indneutralize** 思想。详见 ``expr.group``。
"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.group import (
    GroupBackfill,
    GroupMean,
    GroupNeutralize,
    GroupRank,
    GroupScale,
    GroupZscore,
)


def group_backfill(x: Expr, group: Expr, d: int, std: float = 4.0) -> Expr:
    """组内历史 winsor 均值填当前 NaN（非全截面 ts_backfill）。"""
    return GroupBackfill(x=ensure_expr(x), group=ensure_expr(group), d=d, std=std)


def group_mean(x: Expr, weight: Expr, group: Expr) -> Expr:
    """组内加权平均再广播到成员。"""
    return GroupMean(
        x=ensure_expr(x), weight=ensure_expr(weight), group=ensure_expr(group)
    )


def group_neutralize(x: Expr, group: Expr) -> Expr:
    """``x - 组内均值``；剥离组内共同水平，非全截面 zscore。"""
    return GroupNeutralize(x=ensure_expr(x), group=ensure_expr(group))


def group_rank(x: Expr, group: Expr) -> Expr:
    """组内 [0,1] 分位排名。"""
    return GroupRank(x=ensure_expr(x), group=ensure_expr(group))


def group_scale(x: Expr, group: Expr) -> Expr:
    """组内 min-max 到 [0,1]。"""
    return GroupScale(x=ensure_expr(x), group=ensure_expr(group))


def group_zscore(x: Expr, group: Expr) -> Expr:
    """组内标准化 (x-μ)/σ。"""
    return GroupZscore(x=ensure_expr(x), group=ensure_expr(group))
