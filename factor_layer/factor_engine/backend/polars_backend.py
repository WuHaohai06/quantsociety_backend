"""Polars 长表后端（**子集**）：仅支持由 ``column`` / ``literal`` / 四则 / ``rank`` / ``ts_mean`` 组成的计划树。

其余算子会 ``NotImplementedError``。结果统一转回 ``(timestamp, instrument)`` MultiIndex 的 pandas ``Series``，
与 ``PandasBackend`` 形态一致。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from planner.logical_plan import PlanNode

from .base import Backend
from .context import ExecutionContext

_SCALAR = "scalar"


def _ts(ctx: ExecutionContext) -> str:
    return ctx.timestamp_col


def _inst(ctx: ExecutionContext) -> str:
    return ctx.instrument_col


def _series_to_long(s: pd.Series, ctx: ExecutionContext, pl: Any) -> Any:
    df = s.rename("v").reset_index()
    tsn, isn = _ts(ctx), _inst(ctx)
    cols = list(df.columns)
    if len(cols) >= 3:
        df = df.rename(columns={cols[0]: tsn, cols[1]: isn, cols[2]: "v"})
    return pl.DataFrame(df[[tsn, isn, "v"]])


def _long_to_series(df: Any, ctx: ExecutionContext) -> pd.Series:
    p = df.to_pandas()
    tsn, isn = _ts(ctx), _inst(ctx)
    return pd.Series(
        p["v"].to_numpy(),
        index=pd.MultiIndex.from_arrays(
            [p[tsn].values, p[isn].values],
            names=[tsn, isn],
        ),
    )


class PolarsBackend(Backend):
    """子集后端；安装 ``polars`` 后可通过 ``build_backend("polars")`` 使用。"""

    _OPS = frozenset(
        {
            "column",
            "literal",
            "add",
            "sub",
            "mul",
            "div",
            "rank",
            "ts_mean",
            "sin",
            "cos",
        }
    )

    def execute(self, plan: PlanNode, ctx: ExecutionContext):
        import polars as pl

        self._assert_supported(plan)
        out = self._eval(plan, ctx, pl)
        return _long_to_series(out, ctx)

    def _assert_supported(self, node: PlanNode) -> None:
        if node.op not in self._OPS:
            raise NotImplementedError(
                f"PolarsBackend subset: op '{node.op}' is not supported. "
                f"Allowed: {sorted(self._OPS)}."
            )
        for ch in node.inputs:
            self._assert_supported(ch)

    def _eval(self, node: PlanNode, ctx: ExecutionContext, pl: Any) -> Any:
        op = node.op
        tsn, isn = _ts(ctx), _inst(ctx)

        if op == "column":
            s = ctx.data_source.load_column(node.attrs["name"])
            return _series_to_long(s, ctx, pl)

        if op == "literal":
            return (_SCALAR, float(node.attrs["value"]))

        if op in ("add", "sub", "mul", "div"):
            a = self._eval(node.inputs[0], ctx, pl)
            b = self._eval(node.inputs[1], ctx, pl)
            ops = {
                "add": lambda x, y: x + y,
                "sub": lambda x, y: x - y,
                "mul": lambda x, y: x * y,
                "div": lambda x, y: x / y,
            }
            fn = ops[op]

            if isinstance(a, tuple) and a[0] == _SCALAR:
                lf = b
                return lf.with_columns(fn(pl.lit(a[1]), pl.col("v")).alias("v"))
            if isinstance(b, tuple) and b[0] == _SCALAR:
                lf = a
                return lf.with_columns(fn(pl.col("v"), pl.lit(b[1])).alias("v"))
            return (
                a.join(b, on=[tsn, isn], how="inner", suffix="_r")
                .with_columns(fn(pl.col("v"), pl.col("v_r")).alias("v"))
                .drop("v_r")
            )

        if op == "rank":
            lf = self._eval(node.inputs[0], ctx, pl)
            cnt = pl.col("v").count().over(tsn)
            rk = pl.col("v").rank(method="average").over(tsn)
            return lf.with_columns(
                pl.when(cnt > 0).then(rk / cnt).otherwise(None).alias("v")
            )

        if op == "ts_mean":
            lf = self._eval(node.inputs[0], ctx, pl).sort([isn, tsn])
            d = max(1, int(node.attrs.get("d", node.attrs.get("window", 1))))
            mp = node.attrs.get("min_periods")
            minp = d if mp is None else max(1, int(mp))
            v = pl.col("v")
            try:
                rolled = v.rolling_mean(window_size=d, min_samples=minp)
            except TypeError:
                rolled = v.rolling_mean(window_size=d, min_periods=minp)
            return lf.with_columns(rolled.over(isn).alias("v"))

        if op == "sin":
            lf = self._eval(node.inputs[0], ctx, pl)
            return lf.with_columns(pl.col("v").sin().alias("v"))

        if op == "cos":
            lf = self._eval(node.inputs[0], ctx, pl)
            return lf.with_columns(pl.col("v").cos().alias("v"))

        raise NotImplementedError(op)
