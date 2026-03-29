"""向量场算子 API（Pandas 后端尚未实现）。"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.vector import VecAvg, VecSum


def vec_avg(x: Expr) -> Expr:
    return VecAvg(ensure_expr(x))


def vec_sum(x: Expr) -> Expr:
    return VecSum(ensure_expr(x))
