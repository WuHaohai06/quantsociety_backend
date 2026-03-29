"""因子 DSL 解析：把字符串公式解析成 ``Expr`` 树（受限 Python 表达式子集）。"""

from __future__ import annotations

import ast
from typing import Any

from api.factor import Factor
from api.operator_registry import build_dsl_allowlist
from expr.base import Expr


class DSLParseError(ValueError):
    """公式语法不合法、或使用了未白名单的函数/结构。"""


class _ExprBuilder:
    """遍历 ``ast``，把调用/比较/四则运算还原为 ``api.operators`` 构建的 ``Expr``。"""

    def __init__(self) -> None:
        # 允许出现的函数名 → 工厂函数（来自 operator_registry）
        self._allowed = build_dsl_allowlist()

    def build(self, text: str) -> Expr:
        try:
            parsed = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise DSLParseError(f"Invalid expression syntax: {text}") from exc

        expr = self._visit(parsed.body)
        if not isinstance(expr, Expr):
            raise DSLParseError("Expression must evaluate to an Expr object.")
        return expr

    def _visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Call):
            return self._visit_call(node)

        if isinstance(node, ast.Compare):
            return self._visit_compare(node)

        if isinstance(node, ast.BinOp):
            return self._visit_binop(node)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._visit(node.operand)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, int, float, bool)) or node.value is None:
                return node.value
            raise DSLParseError(f"Unsupported literal: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id in self._allowed:
                return self._allowed[node.id]
            raise DSLParseError(f"Unsupported name: {node.id}")

        raise DSLParseError(f"Unsupported syntax node: {type(node).__name__}")

    def _visit_call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in self._allowed:
                raise DSLParseError(f"Unsupported function: {name}")
            func = self._allowed[name]
        else:
            func = self._visit(node.func)

        args = [self._visit(arg) for arg in node.args]
        kwargs = {}
        for kw in node.keywords:
            if kw.arg is None:
                raise DSLParseError("Keyword-only **kwargs are not supported.")
            kwargs[kw.arg] = self._visit(kw.value)

        if not callable(func):
            raise DSLParseError("Call target is not callable.")
        return func(*args, **kwargs)

    def _visit_compare(self, node: ast.Compare) -> Expr:
        """Single comparison only: ``left op right`` (no chained compares)."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise DSLParseError(
                "Chained comparisons are not supported; use one comparison only."
            )
        left = self._visit(node.left)
        right = self._visit(node.comparators[0])
        op = node.ops[0]
        from api.operators import logical as lg

        if isinstance(op, ast.Lt):
            return lg.lt(left, right)
        if isinstance(op, ast.LtE):
            return lg.le(left, right)
        if isinstance(op, ast.Eq):
            return lg.eq(left, right)
        if isinstance(op, ast.Gt):
            return lg.gt(left, right)
        if isinstance(op, ast.GtE):
            return lg.ge(left, right)
        if isinstance(op, ast.NotEq):
            return lg.ne(left, right)
        raise DSLParseError(f"Unsupported comparison: {type(op).__name__}")

    def _visit_binop(self, node: ast.BinOp) -> Any:
        left = self._visit(node.left)
        right = self._visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right

        raise DSLParseError(f"Unsupported binary operator: {type(node.op).__name__}")


def parse_expr(text: str) -> Expr:
    """解析单条表达式字符串为 ``Expr``。"""
    return _ExprBuilder().build(text)


def parse_factor(
    text: str,
    *,
    name: str = "factor",
    freq: str = "1d",
    universe: str | None = None,
    description: str | None = None,
) -> Factor:
    """解析表达式并包成带元数据的 :class:`api.factor.Factor`。"""
    return Factor(
        name=name,
        expr=parse_expr(text),
        freq=freq,
        universe=universe,
        description=description,
    )
