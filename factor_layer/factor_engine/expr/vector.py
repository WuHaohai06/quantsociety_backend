"""
向量场算子（WorldQuant — Vector）。

假设列值为“向量字段”；当前仅 Expr/IR/DSL 占位，PandasBackend 未实现。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class VecAvg(Expr):
    """向量分量均值（待数据源支持向量列）。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class VecSum(Expr):
    """向量分量和。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)
