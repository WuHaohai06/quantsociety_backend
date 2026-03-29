"""
算术类表达式（WorldQuant BRAIN — Arithmetic）。

包含：二元 ``+ - * /``、一元函数（abs/log 等）、多元 ``add``/``max`` 等对应的 AST 节点。
编译后 IR 的 ``op`` 多为 ``add``/``nary_add``/``abs`` 等字符串，由 PandasBackend 分派执行。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class BinaryExpr(Expr):
    """左右子表达式上的二元运算基类。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class Add(BinaryExpr):
    """加法：也可用 ``expr_a + expr_b`` 构造。"""


@dataclass(frozen=True)
class Sub(BinaryExpr):
    """减法。"""


@dataclass(frozen=True)
class Mul(BinaryExpr):
    """乘法。"""


@dataclass(frozen=True)
class Div(BinaryExpr):
    """除法。"""


@dataclass(frozen=True)
class UnaryExpr(Expr):
    """单输入算术/变换的基类。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Abs(UnaryExpr):
    """绝对值 |x|。"""


@dataclass(frozen=True)
class Log(UnaryExpr):
    """自然对数 ln(x)。"""


@dataclass(frozen=True)
class Sqrt(UnaryExpr):
    """非负平方根。"""


@dataclass(frozen=True)
class Sin(UnaryExpr):
    """正弦；用于周期/谐波类特征（遗传规划常用扩展）。"""


@dataclass(frozen=True)
class Cos(UnaryExpr):
    """余弦。"""


@dataclass(frozen=True)
class Sign(UnaryExpr):
    """符号函数：正 1、负 -1、零 0、NaN 仍为 NaN。"""


@dataclass(frozen=True)
class Reverse(UnaryExpr):
    """取负：-x（WQ 名 reverse）。"""


@dataclass(frozen=True)
class Inverse(UnaryExpr):
    """倒数 1/x。"""


@dataclass(frozen=True)
class Pow(Expr):
    """幂：x ** y。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class SignedPow(Expr):
    """带符号幂：sign(x) * |x|**y。"""

    left: Expr
    right: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class NaryAdd(Expr):
    """多元加法；``filter_nan`` 为 True 时 NaN 当 0 再相加（WQ add 语义）。"""

    operands: tuple[Expr, ...]
    filter_nan: bool = False

    def children(self) -> tuple[Expr, ...]:
        return self.operands


@dataclass(frozen=True)
class NaryMul(Expr):
    """多元乘法；``filter_nan`` 为 True 时 NaN 当 1。"""

    operands: tuple[Expr, ...]
    filter_nan: bool = False

    def children(self) -> tuple[Expr, ...]:
        return self.operands


@dataclass(frozen=True)
class NarySub(Expr):
    """从左到右连减：a - b - c；可选 filter_nan。"""

    operands: tuple[Expr, ...]
    filter_nan: bool = False

    def children(self) -> tuple[Expr, ...]:
        return self.operands


@dataclass(frozen=True)
class NaryMax(Expr):
    """多元逐元素取最大。"""

    operands: tuple[Expr, ...]

    def children(self) -> tuple[Expr, ...]:
        return self.operands


@dataclass(frozen=True)
class NaryMin(Expr):
    """多元逐元素取最小。"""

    operands: tuple[Expr, ...]

    def children(self) -> tuple[Expr, ...]:
        return self.operands


@dataclass(frozen=True)
class Densify(UnaryExpr):
    """截面稠密化：每个时间截面上对取值做 factorize，减少稀疏类别编码空间。"""
