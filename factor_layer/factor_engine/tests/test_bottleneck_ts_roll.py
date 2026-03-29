"""Bottleneck 可选路径与 pandas rolling 数值对齐（需安装 bottleneck）。"""

from __future__ import annotations

import os

import numpy as np
import pytest

pd = pytest.importorskip("pandas")

pytest.importorskip("bottleneck")

from api.columns import col
from api.factor import Factor
from api.operators import ts_max, ts_mean, ts_min
from backend.pandas_backend import PandasBackend
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
            (pd.Timestamp("2024-01-04"), "B"),
        ],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, np.nan, 3.0, 10.0, 11.0, 12.0], index=idx)
    return x


@pytest.fixture
def source():
    return InMemorySeriesSource(data={"x": _panel()})


def _run_mean(engine: FactorEngine):
    return engine.run(Factor(name="m", expr=ts_mean(col("x"), 2)))["result"]


def test_ts_roll_bottleneck_matches_pandas_when_enabled(source):
    eng_fast = FactorEngine(backend=PandasBackend(), data_source=source)
    fast = _run_mean(eng_fast)
    os.environ["FACTOR_ENGINE_DISABLE_BOTTLENECK"] = "1"
    try:
        eng_pd = FactorEngine(backend=PandasBackend(), data_source=source)
        pure = _run_mean(eng_pd)
    finally:
        os.environ.pop("FACTOR_ENGINE_DISABLE_BOTTLENECK", None)
    pd.testing.assert_series_equal(fast, pure, check_names=False)


def test_ts_max_min_bottleneck_matches_pandas(source):
    for op_fn in (ts_max, ts_min):
        eng_fast = FactorEngine(backend=PandasBackend(), data_source=source)
        fast = eng_fast.run(Factor(name="t", expr=op_fn(col("x"), 2)))["result"]
        os.environ["FACTOR_ENGINE_DISABLE_BOTTLENECK"] = "1"
        try:
            eng_pd = FactorEngine(backend=PandasBackend(), data_source=source)
            pure = eng_pd.run(Factor(name="t", expr=op_fn(col("x"), 2)))["result"]
        finally:
            os.environ.pop("FACTOR_ENGINE_DISABLE_BOTTLENECK", None)
        pd.testing.assert_series_equal(fast, pure, check_names=False)
