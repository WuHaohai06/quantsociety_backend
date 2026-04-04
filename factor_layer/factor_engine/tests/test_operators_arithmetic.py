import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import abs_, add, densify, exp, max_, multiply
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def _tiny_panel():
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2024-01-01", "2024-01-02"]),
            ["A", "B"],
        ],
        names=["timestamp", "instrument"],
    )
    close = pd.Series([1.0, -2.0, 3.0, 4.0], index=idx)
    return InMemorySeriesSource(data={"close": close})


def test_abs_and_add():
    src = _tiny_panel()
    f = Factor(name="t", expr=abs_(col("close") + col("close")))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "B")] == 4.0


def test_exp():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A", "B"]],
        names=["timestamp", "instrument"],
    )
    src = InMemorySeriesSource(data={"x": pd.Series([0.0, 1.0], index=idx)})
    f = Factor(name="t", expr=exp(col("x")))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "A")] == pytest.approx(1.0)
    assert out.loc[(pd.Timestamp("2024-01-01"), "B")] == pytest.approx(2.718281828, rel=1e-6)


def test_multiply_filter_nan():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A", "B"]],
        names=["timestamp", "instrument"],
    )
    a = pd.Series([2.0, float("nan")], index=idx)
    b = pd.Series([3.0, 5.0], index=idx)
    src = InMemorySeriesSource(data={"a": a, "b": b})
    f = Factor(name="t", expr=multiply(col("a"), col("b"), filter=True))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "B")] == 5.0


def test_densify():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02"]), ["A", "B", "C"]],
        names=["timestamp", "instrument"],
    )
    g = pd.Series([100.0, 200.0, 100.0, 300.0, 300.0, 400.0], index=idx)
    src = InMemorySeriesSource(data={"g": g})
    f = Factor(name="t", expr=densify(col("g")))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert set(out.loc[pd.Timestamp("2024-01-01")].unique()) <= {0.0, 1.0}


def test_max_binary():
    src = _tiny_panel()
    f = Factor(name="t", expr=max_(col("close"), col("close") * 0))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "A")] == 1.0
