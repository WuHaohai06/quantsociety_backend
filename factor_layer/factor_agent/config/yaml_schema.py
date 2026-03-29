"""YAML 结构约定与基础校验工具。"""

from __future__ import annotations

import re
from typing import Any

REQUIRED_TOP_LEVEL_KEYS = ["factor", "data_source", "backend", "engine"]
REQUIRED_FACTOR_KEYS = ["name", "expr", "freq", "description"]
REQUIRED_DATASOURCE_KEYS = ["type", "root", "timestamp_col", "instrument_col", "max_files"]
REQUIRED_BACKEND_KEYS = ["type"]
REQUIRED_ENGINE_KEYS = ["enable_cache"]

ALLOWED_DATASOURCE_TYPES = {"parquet_kline", "multi_parquet", "parquet"}
ALLOWED_BACKEND_TYPES = {"pandas"}
ALLOWED_FREQ = {"1d", "1h", "1min"}
ALLOWED_OPERATORS = {"col", "rank", "zscore", "ts_mean", "ts_std", "delay"}
ALLOWED_EXPR_CHARS = re.compile(r'^[\w\s\(\)\+\-\*\/\.,"\'<>=%:]+$')


def _missing_keys(obj: dict[str, Any], required: list[str]) -> list[str]:
    return [k for k in required if k not in obj]


def _extract_function_calls(expr: str) -> list[str]:
    # 匹配函数名，如 rank(...), ts_mean(...)
    return re.findall(r"\b([A-Za-z_]\w*)\s*\(", expr)


def validate_yaml_dict(data: dict[str, Any]) -> list[str]:
    """返回结构与取值错误列表；空列表表示通过。"""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["YAML 顶层必须是 object/map"]

    top_missing = _missing_keys(data, REQUIRED_TOP_LEVEL_KEYS)
    if top_missing:
        errors.append(f"缺少顶层字段: {', '.join(top_missing)}")
        return errors

    factor = data.get("factor")
    ds = data.get("data_source")
    backend = data.get("backend")
    engine = data.get("engine")

    if not isinstance(factor, dict):
        errors.append("factor 必须是 object")
    else:
        m = _missing_keys(factor, REQUIRED_FACTOR_KEYS)
        if m:
            errors.append(f"factor 缺少字段: {', '.join(m)}")
        name = factor.get("name", "")
        expr = factor.get("expr", "")
        freq = factor.get("freq", "")
        if not isinstance(name, str) or not re.match(r"^[a-z][a-z0-9_]*$", name or ""):
            errors.append("factor.name 必须是 snake_case 且以字母开头")
        if not isinstance(expr, str) or not expr.strip():
            errors.append("factor.expr 不能为空")
        else:
            if not ALLOWED_EXPR_CHARS.match(expr):
                errors.append("factor.expr 包含非法字符")
            funcs = _extract_function_calls(expr)
            illegal = sorted({f for f in funcs if f not in ALLOWED_OPERATORS})
            if illegal:
                errors.append(f"factor.expr 使用了未允许算子: {', '.join(illegal)}")
        if freq not in ALLOWED_FREQ:
            errors.append(f"factor.freq 仅支持: {', '.join(sorted(ALLOWED_FREQ))}")

    if not isinstance(ds, dict):
        errors.append("data_source 必须是 object")
    else:
        m = _missing_keys(ds, REQUIRED_DATASOURCE_KEYS)
        if m:
            errors.append(f"data_source 缺少字段: {', '.join(m)}")
        if ds.get("type") not in ALLOWED_DATASOURCE_TYPES:
            errors.append("data_source.type 非法")
        if not isinstance(ds.get("root"), str) or not ds.get("root", "").strip():
            errors.append("data_source.root 不能为空")
        if not isinstance(ds.get("timestamp_col"), str) or not ds.get("timestamp_col", "").strip():
            errors.append("data_source.timestamp_col 不能为空")
        if not isinstance(ds.get("instrument_col"), str) or not ds.get("instrument_col", "").strip():
            errors.append("data_source.instrument_col 不能为空")
        if not isinstance(ds.get("max_files"), int) or ds.get("max_files", 0) <= 0:
            errors.append("data_source.max_files 必须是正整数")

    if not isinstance(backend, dict):
        errors.append("backend 必须是 object")
    else:
        m = _missing_keys(backend, REQUIRED_BACKEND_KEYS)
        if m:
            errors.append(f"backend 缺少字段: {', '.join(m)}")
        if backend.get("type") not in ALLOWED_BACKEND_TYPES:
            errors.append("backend.type 目前仅支持 pandas")

    if not isinstance(engine, dict):
        errors.append("engine 必须是 object")
    else:
        m = _missing_keys(engine, REQUIRED_ENGINE_KEYS)
        if m:
            errors.append(f"engine 缺少字段: {', '.join(m)}")
        if not isinstance(engine.get("enable_cache"), bool):
            errors.append("engine.enable_cache 必须是布尔值")

    return errors
