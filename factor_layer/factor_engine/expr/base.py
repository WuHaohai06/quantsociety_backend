"""
因子表达式基类。

所有可编译的因子公式都由 ``Expr`` 子类树组成；编译器遍历 ``children()`` 得到子节点。
支持 ``+ - * /`` 重载，自动包装为算术节点（见 ``expr.arithmetic``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(frozen=True)
class Expr:
    """表达式抽象基类；不可变（frozen），便于哈希与缓存。"""

    def children(self) -> Tuple["Expr", ...]:
        return ()

    def __add__(self, other: Any) -> "Expr":
        from .arithmetic import Add

        return Add(self, ensure_expr(other))

    def __radd__(self, other: Any) -> "Expr":
        from .arithmetic import Add

        return Add(ensure_expr(other), self)

    def __sub__(self, other: Any) -> "Expr":
        from .arithmetic import Sub

        return Sub(self, ensure_expr(other))

    def __rsub__(self, other: Any) -> "Expr":
        from .arithmetic import Sub

        return Sub(ensure_expr(other), self)

    def __mul__(self, other: Any) -> "Expr":
        from .arithmetic import Mul

        return Mul(self, ensure_expr(other))

    def __rmul__(self, other: Any) -> "Expr":
        from .arithmetic import Mul

        return Mul(ensure_expr(other), self)

    def __truediv__(self, other: Any) -> "Expr":
        from .arithmetic import Div

        return Div(self, ensure_expr(other))

    def __rtruediv__(self, other: Any) -> "Expr":
        from .arithmetic import Div

        return Div(ensure_expr(other), self)


def ensure_expr(x: Any) -> Expr:
    """标量或已是 Expr 时统一成 Expr；数字/布尔等会包成 ``Literal``。"""
    from .literal import Literal

    if isinstance(x, Expr):
        return x
    return Literal(x)
