"""因子定义：名称 + 表达式树，以及频率、股票池等元信息（配置/YAML 用）。"""

from dataclasses import dataclass

from expr.base import Expr


@dataclass(frozen=True)
class Factor:
    """可编译、可执行的一条因子；核心负载是 ``expr: Expr``。"""

    name: str
    expr: Expr
    freq: str = "1d"  # 业务语义频率，写入 YAML/物化元数据，不参与 IR 类型推导
    universe: str | None = None  # 股票池/标签，供配置与文档；执行时以数据源为准
    description: str | None = None
