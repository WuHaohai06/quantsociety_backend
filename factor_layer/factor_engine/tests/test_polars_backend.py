"""PolarsBackend 子集与 PandasBackend 数值对齐（需安装 polars）。"""

from __future__ import annotations

import os

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("polars")

from api.columns import col
from api.factor import Factor
from api.operators import abs_, cos_, exp, rank, sin_, ts_delay, ts_mean, zscore
from backend.factory import build_backend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def _panel():
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "A"),
            (pd.Timestamp("2024-01-02"), "A"),
            (pd.Timestamp("2024-01-03"), "A"),
            (pd.Timestamp("2024-01-01"), "B"),
            (pd.Timestamp("2024-01-02"), "B"),
        ],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 4.0, 10.0, 20.0], index=idx)
    return x


@pytest.fixture
def source():
    return InMemorySeriesSource(data={"x": _panel()})


def _run(engine: FactorEngine, expr):
    return engine.run(Factor(name="t", expr=expr))["result"]


@pytest.mark.parametrize(
    "expr",
    [
        rank(col("x")),
        ts_mean(col("x"), 2),
        rank(ts_mean(col("x"), 2)),
        col("x") + 1.0,
        sin_(col("x")),
        cos_(col("x")),
        exp(col("x")),
        zscore(col("x")),
        ts_delay(col("x"), 1),
        abs_(col("x")),
    ],
)
def test_polars_matches_pandas(source, expr):
    os.environ["FACTOR_ENGINE_DISABLE_BOTTLENECK"] = "1"
    try:
        eng_pd = FactorEngine(backend=build_backend("pandas"), data_source=source)
        eng_pl = FactorEngine(backend=build_backend("polars"), data_source=source)
    finally:
        os.environ.pop("FACTOR_ENGINE_DISABLE_BOTTLENECK", None)

    a = _run(eng_pd, expr)
    b = _run(eng_pl, expr)
    pd.testing.assert_series_equal(a, b, check_names=False, rtol=1e-12, atol=1e-12)


def test_polars_lazy_matches_eager(source):
    """LazyFrame 路径与 eager Polars 数值一致。"""
    os.environ["FACTOR_ENGINE_DISABLE_BOTTLENECK"] = "1"
    try:
        expr = rank(ts_mean(col("x"), 2))
        eng_e = FactorEngine(backend=build_backend("polars"), data_source=source)
        eng_l = FactorEngine(backend=build_backend("polars_lazy"), data_source=source)
        a = _run(eng_e, expr)
        b = _run(eng_l, expr)
    finally:
        os.environ.pop("FACTOR_ENGINE_DISABLE_BOTTLENECK", None)

    pd.testing.assert_series_equal(a, b, check_names=False, rtol=1e-12, atol=1e-12)
