"""算术类 API：返回 ``expr.arithmetic`` 中的表达式节点（供 DSL 白名单与代码拼式）。"""

from __future__ import annotations

from expr.arithmetic import (
    Abs,
    Cos,
    Densify,
    Inverse,
    Log,
    NaryAdd,
    NaryMax,
    NaryMin,
    NaryMul,
    NarySub,
    Pow,
    Reverse,
    SignedPow,
    Sign,
    Sin,
    Sqrt,
)
from expr.base import Expr, ensure_expr


def abs_(x: Expr) -> Expr:
    return Abs(ensure_expr(x))


def log(x: Expr) -> Expr:
    return Log(ensure_expr(x))


def sqrt(x: Expr) -> Expr:
    return Sqrt(ensure_expr(x))


def sin_(x: Expr) -> Expr:
    return Sin(ensure_expr(x))


def cos_(x: Expr) -> Expr:
    return Cos(ensure_expr(x))


def sign(x: Expr) -> Expr:
    return Sign(ensure_expr(x))


def reverse(x: Expr) -> Expr:
    return Reverse(ensure_expr(x))


def inverse(x: Expr) -> Expr:
    return Inverse(ensure_expr(x))


def power(x: Expr, y: Expr) -> Expr:
    return Pow(ensure_expr(x), ensure_expr(y))


def signed_power(x: Expr, y: Expr) -> Expr:
    return SignedPow(ensure_expr(x), ensure_expr(y))


def add(*xs: Expr, filter: bool = False) -> Expr:
    if len(xs) < 2:
        raise ValueError("add() requires at least 2 inputs")
    return NaryAdd(tuple(ensure_expr(t) for t in xs), filter_nan=filter)


def multiply(*xs: Expr, filter: bool = False) -> Expr:
    if len(xs) < 2:
        raise ValueError("multiply() requires at least 2 inputs")
    return NaryMul(tuple(ensure_expr(t) for t in xs), filter_nan=filter)


def subtract(*xs: Expr, filter: bool = False) -> Expr:
    if len(xs) < 2:
        raise ValueError("subtract() requires at least 2 inputs")
    return NarySub(tuple(ensure_expr(t) for t in xs), filter_nan=filter)


def max_(*xs: Expr) -> Expr:
    if len(xs) < 2:
        raise ValueError("max() requires at least 2 inputs")
    return NaryMax(tuple(ensure_expr(t) for t in xs))


def min_(*xs: Expr) -> Expr:
    if len(xs) < 2:
        raise ValueError("min() requires at least 2 inputs")
    return NaryMin(tuple(ensure_expr(t) for t in xs))


def densify(x: Expr) -> Expr:
    return Densify(ensure_expr(x))


def divide(x: Expr, y: Expr) -> Expr:
    return ensure_expr(x) / ensure_expr(y)
