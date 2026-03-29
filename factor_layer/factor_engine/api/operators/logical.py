"""逻辑与比较 API；DSL 中须用 ``and_``/``or_``/``not_``。"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.logical import And, Eq, Ge, Gt, IfElse, IsNan, Le, Lt, Ne, Not, Or


def and_(a: Expr, b: Expr) -> Expr:
    return And(ensure_expr(a), ensure_expr(b))


def or_(a: Expr, b: Expr) -> Expr:
    return Or(ensure_expr(a), ensure_expr(b))


def not_(x: Expr) -> Expr:
    return Not(ensure_expr(x))


def if_else(condition: Expr, then_: Expr, else_: Expr) -> Expr:
    return IfElse(ensure_expr(condition), ensure_expr(then_), ensure_expr(else_))


def is_nan(x: Expr) -> Expr:
    return IsNan(ensure_expr(x))


def lt(a: Expr, b: Expr) -> Expr:
    return Lt(ensure_expr(a), ensure_expr(b))


def le(a: Expr, b: Expr) -> Expr:
    return Le(ensure_expr(a), ensure_expr(b))


def eq(a: Expr, b: Expr) -> Expr:
    return Eq(ensure_expr(a), ensure_expr(b))


def gt(a: Expr, b: Expr) -> Expr:
    return Gt(ensure_expr(a), ensure_expr(b))


def ge(a: Expr, b: Expr) -> Expr:
    return Ge(ensure_expr(a), ensure_expr(b))


def ne(a: Expr, b: Expr) -> Expr:
    return Ne(ensure_expr(a), ensure_expr(b))
