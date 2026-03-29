"""数据清洗与保护算子 API。"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.cleaning import Pasteurize, ProtectedDiv, ProtectedLog, ProtectedSqrt, Tail


def pasteurize(child: Expr, fill_value: float | None = None) -> Expr:
    return Pasteurize(child=ensure_expr(child), fill_value=fill_value)


def tail(child: Expr, lower: float = 0.01, upper: float = 0.99) -> Expr:
    return Tail(child=ensure_expr(child), lower=lower, upper=upper)


def protected_div(
    left: Expr,
    right: Expr,
    epsilon: float = 1e-12,
    default: float = 0.0,
) -> Expr:
    return ProtectedDiv(
        left=ensure_expr(left),
        right=ensure_expr(right),
        epsilon=epsilon,
        default=default,
    )


def protected_log(child: Expr, epsilon: float = 1e-12) -> Expr:
    return ProtectedLog(child=ensure_expr(child), epsilon=epsilon)


def protected_sqrt(child: Expr) -> Expr:
    return ProtectedSqrt(child=ensure_expr(child))
