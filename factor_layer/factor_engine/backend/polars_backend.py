"""Polars 长表后端：在 ``(timestamp, instrument, v)`` 长表上执行计划树。

- **eager**（默认）：每步物化为 ``DataFrame``。
- **lazy**（``FACTOR_ENGINE_POLARS_LAZY=1`` 或 ``PolarsBackend(use_lazy=True)``）：在 ``LazyFrame`` 上链式构图，根上 ``collect()`` 一次，便于 Polars 做查询级优化。

结果统一转回 ``(timestamp, instrument)`` MultiIndex 的 pandas ``Series``（与 Modin/纯 pandas 后端形态一致，便于对比）。
"""

from __future__ import annotations

import os
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


def _series_to_long(
    s: pd.Series, ctx: ExecutionContext, pl: Any, *, lazy: bool
) -> Any:
    df = s.rename("v").reset_index()
    tsn, isn = _ts(ctx), _inst(ctx)
    cols = list(df.columns)
    if len(cols) >= 3:
        df = df.rename(columns={cols[0]: tsn, cols[1]: isn, cols[2]: "v"})
    out = pl.DataFrame(df[[tsn, isn, "v"]])
    return out.lazy() if lazy else out


def _long_to_series(df: Any, ctx: ExecutionContext) -> pd.Series:
    p = df.to_pandas() if hasattr(df, "to_pandas") else df
    tsn, isn = _ts(ctx), _inst(ctx)
    return pd.Series(
        p["v"].to_numpy(),
        index=pd.MultiIndex.from_arrays(
            [p[tsn].values, p[isn].values],
            names=[tsn, isn],
        ),
    )


class PolarsBackend(Backend):
    """安装 ``polars`` 后 ``build_backend(\"polars\")`` 使用。

    Parameters
    ----------
    use_lazy
        ``True``：LazyFrame 路径；``False``：eager；``None``：读环境变量 ``FACTOR_ENGINE_POLARS_LAZY``。
    """

    _OPS = frozenset(
        {
            "column",
            "literal",
            "plan_ref",
            "add",
            "sub",
            "mul",
            "div",
            "rank",
            "zscore",
            "ts_mean",
            "ts_delay",
            "ts_std_dev",
            "ts_std",
            "ts_sum",
            "abs",
            "log",
            "sqrt",
            "sign",
            "sin",
            "cos",
            "exp",
        }
    )

    def __init__(self, use_lazy: bool | None = None) -> None:
        self._use_lazy = use_lazy

    def execute(self, plan: PlanNode, ctx: ExecutionContext):
        import polars as pl

        self._assert_supported(plan)
        lazy = self._use_lazy
        if lazy is None:
            lazy = os.environ.get("FACTOR_ENGINE_POLARS_LAZY", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
        out = self._eval(plan, ctx, pl, lazy=lazy)
        if lazy and isinstance(out, pl.LazyFrame):
            out = out.collect()
        return _long_to_series(out, ctx)

    def _assert_supported(self, node: PlanNode) -> None:
        if node.op not in self._OPS:
            raise NotImplementedError(
                f"PolarsBackend subset: op '{node.op}' is not supported. "
                f"Allowed: {sorted(self._OPS)}."
            )
        for ch in node.inputs:
            self._assert_supported(ch)

    def _eval(self, node: PlanNode, ctx: ExecutionContext, pl: Any, *, lazy: bool) -> Any:
        op = node.op
        tsn, isn = _ts(ctx), _inst(ctx)

        if op == "plan_ref":
            cache = getattr(ctx, "shared_result_cache", None)
            if cache is None:
                raise RuntimeError(
                    "plan_ref requires ExecutionContext.shared_result_cache; "
                    "use FactorEngine.run_many() after multi-factor CSE."
                )
            sid = node.attrs["sid"]
            s = cache[sid]
            return _series_to_long(s, ctx, pl, lazy=lazy)

        if op == "column":
            s = ctx.data_source.load_column(node.attrs["name"])
            return _series_to_long(s, ctx, pl, lazy=lazy)

        if op == "literal":
            return (_SCALAR, float(node.attrs["value"]))

        if op in ("add", "sub", "mul", "div"):
            a = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            b = self._eval(node.inputs[1], ctx, pl, lazy=lazy)
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
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            cnt = pl.col("v").count().over(tsn)
            rk = pl.col("v").rank(method="average").over(tsn)
            return lf.with_columns(
                pl.when(cnt > 0).then(rk / cnt).otherwise(None).alias("v")
            )

        if op == "zscore":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            m = pl.col("v").mean().over(tsn)
            sd = pl.col("v").std().over(tsn)
            return lf.with_columns(
                pl.when(sd > 1e-18)
                .then((pl.col("v") - m) / sd)
                .otherwise(None)
                .alias("v")
            )

        if op == "ts_mean":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy).sort([isn, tsn])
            d = max(1, int(node.attrs.get("d", node.attrs.get("window", 1))))
            mp = node.attrs.get("min_periods")
            minp = d if mp is None else max(1, int(mp))
            v = pl.col("v")
            try:
                rolled = v.rolling_mean(window_size=d, min_samples=minp)
            except TypeError:
                rolled = v.rolling_mean(window_size=d, min_periods=minp)
            return lf.with_columns(rolled.over(isn).alias("v"))

        if op == "ts_delay":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy).sort([isn, tsn])
            periods = max(1, int(node.attrs.get("d", node.attrs.get("periods", 1))))
            return lf.with_columns(pl.col("v").shift(periods).over(isn).alias("v"))

        if op in ("ts_std_dev", "ts_std"):
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy).sort([isn, tsn])
            d = max(2, int(node.attrs.get("d", node.attrs.get("window", 2))))
            mp = node.attrs.get("min_periods")
            minp = d if mp is None else max(2, int(mp))
            v = pl.col("v")
            try:
                rolled = v.rolling_std(window_size=d, min_samples=minp)
            except TypeError:
                rolled = v.rolling_std(window_size=d, min_periods=minp)
            return lf.with_columns(rolled.over(isn).alias("v"))

        if op == "ts_sum":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy).sort([isn, tsn])
            d = max(1, int(node.attrs.get("d", node.attrs.get("window", 1))))
            mp = node.attrs.get("min_periods")
            minp = d if mp is None else max(1, int(mp))
            v = pl.col("v")
            try:
                rolled = v.rolling_sum(window_size=d, min_samples=minp)
            except TypeError:
                rolled = v.rolling_sum(window_size=d, min_periods=minp)
            return lf.with_columns(rolled.over(isn).alias("v"))

        if op == "abs":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").abs().alias("v"))

        if op == "log":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").log().alias("v"))

        if op == "sqrt":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").sqrt().alias("v"))

        if op == "sign":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").sign().alias("v"))

        if op == "sin":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").sin().alias("v"))

        if op == "cos":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").cos().alias("v"))

        if op == "exp":
            lf = self._eval(node.inputs[0], ctx, pl, lazy=lazy)
            return lf.with_columns(pl.col("v").exp().alias("v"))

        raise NotImplementedError(op)
