"""trade_when、ts_step、hump 状态算子。"""

from __future__ import annotations

import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import hump, trade_when, ts_step
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def test_ts_step_modulo():
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            ["A"],
        ],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 3.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(Factor(name="s", expr=ts_step(2, col("x"))))["result"]
    assert r.iloc[0] == 0 and r.iloc[1] == 1 and r.iloc[2] == 0


def test_hump_clips_delta():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([0.0, 1.0, 10.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(Factor(name="h", expr=hump(col("x"), 0.5)))["result"]
    assert r.iloc[0] == 0.0
    # 上一输出 0，输入 1 → 裁剪到 0.5
    assert r.iloc[1] == pytest.approx(0.5)
    # 上一输出 0.5，输入 10 → 裁剪到 1.0
    assert r.iloc[2] == pytest.approx(1.0)


def test_trade_when_hold_and_exit():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    trig = pd.Series([0.0, 1.0, 0.0], index=idx)
    alpha = pd.Series([5.0, 7.0, 9.0], index=idx)
    ex = pd.Series([0.0, 0.0, 1.0], index=idx)
    src = InMemorySeriesSource(data={"t": trig, "a": alpha, "e": ex})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(
        Factor(name="tw", expr=trade_when(col("t"), col("a"), col("e")))
    )["result"]
    assert pd.isna(r.iloc[0])
    assert r.iloc[1] == 7.0
    assert pd.isna(r.iloc[2])
