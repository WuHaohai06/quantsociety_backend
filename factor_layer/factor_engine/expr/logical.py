"""
逻辑与比较表达式（WorldQuant BRAIN — Logical）。

输出一般为 **0.0 / 1.0 浮点**（或比较/条件链的中间结果），供 ``if_else``、``trade_when`` 的
trigger/exit 等使用。**判真规则**与后端一致：通常 ``> 0.5`` 或 ``== 1.0`` 视为真，**NaN 视为假**
（避免缺失被当成强信号）。DSL 里不能写 ``and(x,y)``（Python 关键字），须用 ``and_(x,y)`` 等。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class Not(Expr):
    """逻辑非：真变假、假变真（基于 >0.5 判真）。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class And(Expr):
    """逻辑与：两路均为真则 1，否则 0。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Or(Expr):
    """逻辑或：任一为真则 1。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class IfElse(Expr):
    """**无状态**条件选择：每个 (t, i) 上独立判断 ``condition`` 真假，为真取 ``then_``，否则取 ``else_``。

    与 ``trade_when`` 不同：**不记忆**上一 bar 选了哪一支；每期都重新计算两支路的值再选。
    适合纯截面或纯当期逻辑；需要「触发后保持直到下次触发」请用 ``trade_when``。
    """

    condition: Expr
    then_: Expr
    else_: Expr

    def children(self) -> tuple[Expr, Expr, Expr]:
        return (self.condition, self.then_, self.else_)


@dataclass(frozen=True)
class IsNan(Expr):
    """为 NaN 则 1，否则 0。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Lt(Expr):
    """小于比较，结果 0/1。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Le(Expr):
    """小于等于。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Eq(Expr):
    """相等。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Gt(Expr):
    """大于。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Ge(Expr):
    """大于等于。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Ne(Expr):
    """不等。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)
