"""清洗、技术指标、上下文与 group_* 算子的 Pandas 后端单测。"""

from __future__ import annotations

import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import (
    change_instrument,
    group_neutralize,
    group_rank,
    group_zscore,
    neutralize,
    orthogonalize,
    pasteurize,
    protected_div,
    ts_ad,
    ts_adosc,
    ts_adx,
    ts_adxr,
    ts_apo,
    ts_aroon,
    ts_atr,
    ts_bop,
    ts_cmo,
    ts_donchian,
    ts_dx,
    ts_linearreg_angle,
    ts_linearreg_slope,
    ts_macd,
    ts_mean,
    ts_mom,
    ts_ppo,
    ts_rocr100,
    ts_rocr,
    ts_sar,
    ts_skew,
    ts_sma,
    ts_stochf,
    ts_stochrsi,
    ts_t3,
    ts_tema,
    ts_trima,
    ts_trix,
    ts_ultosc,
)
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from storage.cache import CacheManager
from tests.helpers import InMemorySeriesSource


def _panel_2x2():
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "A"),
            (pd.Timestamp("2024-01-01"), "B"),
            (pd.Timestamp("2024-01-02"), "A"),
            (pd.Timestamp("2024-01-02"), "B"),
        ],
        names=["timestamp", "instrument"],
    )
    return idx


def test_group_rank_and_neutralize():
    idx = _panel_2x2()
    x = pd.Series([1.0, 3.0, 2.0, 4.0], index=idx)
    g = pd.Series([1, 1, 1, 2], index=idx)
    src = InMemorySeriesSource(data={"x": x, "g": g})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(Factor(name="t", expr=group_rank(col("x"), col("g"))))["result"]
    # 同日同组内：A,B 在 g=1 上 rank 0.5,1.0
    assert r.loc[(pd.Timestamp("2024-01-01"), "A")] == pytest.approx(0.5)
    n = eng.run(Factor(name="n", expr=group_neutralize(col("x"), col("g"))))[
        "result"
    ]
    assert n.loc[(pd.Timestamp("2024-01-01"), "A")] == pytest.approx(-1.0)


def test_group_zscore():
    idx = _panel_2x2()
    # 同一日截面内至少两点且方差非零，避免组内 std=0 → NaN
    x = pd.Series([1.0, 3.0, 2.0, 4.0], index=idx)
    g = pd.Series([1, 1, 1, 1], index=idx)
    src = InMemorySeriesSource(data={"x": x, "g": g})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    z = eng.run(Factor(name="z", expr=group_zscore(col("x"), col("g"))))["result"]
    assert np.isfinite(z.loc[(pd.Timestamp("2024-01-01"), "A")]).item()


def test_pasteurize_and_protected_div():
    idx = _panel_2x2()
    x = pd.Series([1.0, np.inf, 3.0, 4.0], index=idx)
    y = pd.Series([2.0, 1e-15, 0.0, 2.0], index=idx)
    src = InMemorySeriesSource(data={"x": x, "y": y})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    p = eng.run(Factor(name="p", expr=pasteurize(col("x"), fill_value=0.0)))[
        "result"
    ]
    assert np.isfinite(p).all()
    d = eng.run(
        Factor(name="d", expr=protected_div(col("x"), col("y"), default=99.0))
    )["result"]
    assert d.loc[(idx[1])] == pytest.approx(99.0)


def test_ts_sma_runs():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 3.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    m = eng.run(Factor(name="m", expr=ts_sma(col("x"), 2)))["result"]
    assert m.notna().sum() >= 1


def test_orthogonalize_change_instrument():
    idx = _panel_2x2()
    x = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    y = pd.Series([1.0, 1.0, 1.0, 1.0], index=idx)
    bench = pd.Series([2.0, 2.0, 2.0, 2.0], index=idx)
    src = InMemorySeriesSource(data={"x": x, "y": y, "b": bench})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    o = eng.run(Factor(name="o", expr=orthogonalize(col("x"), col("y"))))["result"]
    assert o.notna().any()
    c = eng.run(
        Factor(name="c", expr=change_instrument(col("x"), "b"))
    )["result"]
    assert (c == x / 2.0).all()


def test_ts_donchian_and_atr_hlc():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    high = pd.Series([10.0, 11.0, 12.0], index=idx)
    low = pd.Series([9.0, 10.0, 11.0], index=idx)
    close = pd.Series([9.5, 10.5, 11.5], index=idx)
    src = InMemorySeriesSource(
        data={"high": high, "low": low, "close": close}
    )
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    dc = eng.run(
        Factor(
            name="d",
            expr=ts_donchian(col("high"), col("low"), 2, band="upper"),
        )
    )["result"]
    assert dc.notna().any()
    atr = eng.run(
        Factor(name="a", expr=ts_atr(col("high"), col("low"), col("close"), 2))
    )["result"]
    assert atr.notna().any()


def test_neutralize_ols_residual():
    idx = _panel_2x2()
    # 每日截面上 y 须有方差，否则 OLS 斜率不定 → 全 NaN
    x = pd.Series([1.0, 2.0, 2.0, 4.0], index=idx)
    y = pd.Series([1.0, 2.0, 1.0, 3.0], index=idx)
    src = InMemorySeriesSource(data={"x": x, "y": y})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    r = eng.run(Factor(name="n", expr=neutralize(col("x"), col("y"))))["result"]
    assert r.notna().any()


def test_technical_wave2_indicators():
    """ADX / Aroon / AD / SAR / CMO / PPO / UltOsc / StochRSI / TEMA / TRIMA / T3（TA-Lib 优先，无库走退化）。"""
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                ]
            ),
            ["A"],
        ],
        names=["timestamp", "instrument"],
    )
    high = pd.Series([10.0, 11.0, 10.5, 11.2, 10.8], index=idx)
    low = pd.Series([9.5, 10.2, 10.0, 10.5, 10.2], index=idx)
    close = pd.Series([9.8, 10.8, 10.3, 11.0, 10.5], index=idx)
    vol = pd.Series([1e6, 1.1e6, 9e5, 1.2e6, 1e6], index=idx)
    src = InMemorySeriesSource(
        data={"high": high, "low": low, "close": close, "volume": vol}
    )
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    for expr in (
        ts_adx(col("high"), col("low"), col("close"), 3, line="adx"),
        ts_aroon(col("high"), col("low"), 3, line="up"),
        ts_ad(col("high"), col("low"), col("close"), col("volume")),
        ts_adosc(col("high"), col("low"), col("close"), col("volume")),
        ts_sar(col("high"), col("low")),
        ts_cmo(col("close"), 3),
        ts_ppo(col("close"), line="ppo"),
        ts_apo(col("close"), line="apo"),
        ts_ultosc(col("high"), col("low"), col("close")),
        ts_stochrsi(col("close"), timeperiod=4, fastk_period=3, fastd_period=2),
        ts_tema(col("close"), 3),
        ts_trima(col("close"), 4),
        ts_t3(col("close"), 3),
    ):
        r = eng.run(Factor(name="w2", expr=expr))["result"]
        assert r.notna().any(), expr


def test_technical_wave3_indicators():
    """第三批：BOP/MOM/STOCHF/TRIX/ADXR/DX/ROCR/线性回归（TA-Lib 优先，无库走退化）。"""
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                    "2024-01-07",
                    "2024-01-08",
                ]
            ),
            ["A"],
        ],
        names=["timestamp", "instrument"],
    )
    high = pd.Series(
        [10.0, 11.0, 10.5, 11.2, 10.8, 11.0, 10.9, 11.1], index=idx
    )
    low = pd.Series([9.5, 10.2, 10.0, 10.5, 10.2, 10.4, 10.3, 10.5], index=idx)
    close = pd.Series(
        [9.8, 10.8, 10.3, 11.0, 10.5, 10.9, 10.6, 10.95], index=idx
    )
    src = InMemorySeriesSource(data={"high": high, "low": low, "close": close})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    for expr in (
        ts_bop(col("high"), col("low"), col("close")),
        ts_mom(col("close"), 3),
        ts_stochf(col("high"), col("low"), col("close"), fastk_period=3, fastd_period=2),
        ts_trix(col("close"), 3),
        ts_adxr(col("high"), col("low"), col("close"), 3),
        ts_dx(col("high"), col("low"), col("close"), 3),
        ts_rocr(col("close"), 2),
        ts_rocr100(col("close"), 2),
        ts_linearreg_slope(col("close"), 3),
        ts_linearreg_angle(col("close"), 3),
    ):
        r = eng.run(Factor(name="w3", expr=expr))["result"]
        assert r.notna().any(), expr


def test_ts_skew_and_macd():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 2.0, 4.0, 2.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    sk = eng.run(Factor(name="s", expr=ts_skew(col("x"), 3)))["result"]
    assert sk.notna().any()
    m = eng.run(Factor(name="m", expr=ts_macd(col("x"), line="macd")))["result"]
    assert m.notna().any()


def test_subtree_cache_reuses_column_load():
    from backend.context import ExecutionContext

    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([5.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    cache = CacheManager()
    eng = FactorEngine(backend=PandasBackend(), data_source=src, cache=cache)
    expr = ts_mean(col("x"), 1) + ts_mean(col("x"), 1)
    plan, _ = eng.compile(Factor(name="d", expr=expr))
    ctx = ExecutionContext(data_source=src, cache=cache)
    PandasBackend().execute(plan, ctx)
    # 两棵相同子树：子树缓存 MVP 下应至少写入若干键（含重复 ``ts_mean`` 子式）。
    assert len(cache._cache) >= 1
