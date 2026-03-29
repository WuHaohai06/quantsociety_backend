"""列引用工厂：``col("close")`` 生成数据源中的字段表达式。"""

from expr.column import ColumnRef


def col(name: str) -> ColumnRef:
    """按列名字符串构造 :class:`~expr.column.ColumnRef`。"""
    return ColumnRef(name=name)
