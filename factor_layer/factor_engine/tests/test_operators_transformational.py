"""Transformational：bucket 等（trade_when 见单独用例）。"""

from __future__ import annotations

import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import bucket
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def test_bucket_equal_freq_three_bins():
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "A"),
            (pd.Timestamp("2024-01-01"), "B"),
            (pd.Timestamp("2024-01-01"), "C"),
        ],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 3.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(Factor(name="b", expr=bucket(col("x"), buckets="3")))[
        "result"
    ]
    assert set(r.dropna().unique()) <= {0.0, 1.0, 2.0}
    assert len(r) == 3


def test_bucket_range_cutpoints():
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "A"),
            (pd.Timestamp("2024-01-01"), "B"),
            (pd.Timestamp("2024-01-01"), "C"),
            (pd.Timestamp("2024-01-01"), "D"),
        ],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(
        Factor(name="b", expr=bucket(col("x"), range="0.25,0.5,0.75"))
    )["result"]
    assert r.notna().all()
    assert r.min() >= 0
    assert r.max() <= 3


def test_bucket_nan_group_negative_one():
    idx = pd.MultiIndex.from_product(
        [[pd.Timestamp("2024-01-01")], ["A", "B"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, np.nan], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(
        Factor(
            name="b",
            expr=bucket(col("x"), buckets="2", NaNGroup=True),
        )
    )["result"]
    assert r.loc[(pd.Timestamp("2024-01-01"), "B")] == -1.0
