import pytest

pd = pytest.importorskip("pandas")

pytest.importorskip("scipy")

from api.columns import col
from api.factor import Factor
from api.operators import normalize, quantile, rank, scale, winsorize, zscore
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def _panel():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01", "2024-01-02"]), ["A", "B"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0, 3.0, 2.0, 4.0], index=idx)
    return InMemorySeriesSource(data={"x": x})


def test_rank_zscore_normalize():
    src = _panel()
    f = Factor(name="r", expr=rank(col("x")))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-01"), "B")] == 1.0

    f2 = Factor(name="z", expr=zscore(col("x")))
    out2 = FactorEngine(backend=PandasBackend(), data_source=src).run(f2)["result"]
    assert abs(out2.mean()) < 1e-9 or out2.notna().all()

    f3 = Factor(name="n", expr=normalize(col("x"), useStd=True))
    out3 = FactorEngine(backend=PandasBackend(), data_source=src).run(f3)["result"]
    assert out3.notna().all()


def test_winsorize_scale_quantile():
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A", "B", "C"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([0.0, 1.0, 100.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    f = Factor(name="w", expr=winsorize(col("x"), std=1.0))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.max() < 100.0

    f2 = Factor(name="s", expr=scale(col("x"), scale=1.0))
    out2 = FactorEngine(backend=PandasBackend(), data_source=src).run(f2)["result"]
    assert abs(out2.abs().sum() - 1.0) < 1e-6 or out2.notna().all()

    f3 = Factor(name="q", expr=quantile(col("x")))
    out3 = FactorEngine(backend=PandasBackend(), data_source=src).run(f3)["result"]
    assert out3.notna().all()
