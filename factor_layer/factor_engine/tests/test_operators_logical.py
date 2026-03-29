import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import and_, gt, if_else, is_nan, not_
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def test_gt_and_if_else():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A", "B"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 5.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    f = Factor(
        name="t",
        expr=if_else(gt(col("x"), 3.0), col("x"), col("x") * 0),
    )
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "A")] == 0.0
    assert out.loc[(pd.Timestamp("2024-01-01"), "B")] == 5.0


def test_is_nan():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([float("nan")], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    f = Factor(name="t", expr=is_nan(col("x")))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"].iloc[0]
    assert out == 1.0


def test_not_and():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    one = pd.Series([1.0], index=idx)
    src = InMemorySeriesSource(data={"a": one, "b": one})
    f = Factor(name="t", expr=not_(and_(col("a"), col("b"))))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"].iloc[0]
    assert out == 0.0
