"""工程上下文算子 API（正交化、基准列）。"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.context import ChangeInstrument, Orthogonalize


def orthogonalize(x: Expr, y: Expr) -> Expr:
    return Orthogonalize(x=ensure_expr(x), y=ensure_expr(y))


def change_instrument(child: Expr, benchmark_column: str) -> Expr:
    return ChangeInstrument(
        child=ensure_expr(child), benchmark_column=str(benchmark_column)
    )
