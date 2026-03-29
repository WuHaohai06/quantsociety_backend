"""因子定义：名称 + 表达式树，以及频率、股票池等元信息（配置/YAML 用）。"""

from dataclasses import dataclass

from expr.base import Expr


@dataclass(frozen=True)
class Factor:
    """可编译、可执行的一条因子；核心负载是 ``expr: Expr``。"""

    name: str
    expr: Expr
    freq: str = "1d"
    universe: str | None = None
    description: str | None = None
