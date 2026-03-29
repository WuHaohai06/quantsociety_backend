import pytest

pd = pytest.importorskip("pandas")

from api.columns import col
from api.factor import Factor
from api.operators import ts_delay, ts_max, ts_mean, ts_min, ts_std_dev, ts_sum
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


def _panel():
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            ["A", "B"],
        ],
        names=["timestamp", "instrument"],
    )
    close = pd.Series([10.0, 20.0, 11.0, 21.0, 12.0, 22.0], index=idx)
    return InMemorySeriesSource(data={"close": close})


def test_ts_max_min_std():
    src = _panel()
    f = Factor(name="mx", expr=ts_max(col("close"), 2))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.notna().sum() >= 1

    f2 = Factor(name="mn", expr=ts_min(col("close"), 2))
    out2 = FactorEngine(backend=PandasBackend(), data_source=src).run(f2)["result"]
    assert out2.notna().sum() >= 1

    f3 = Factor(name="sd", expr=ts_std_dev(col("close"), 2))
    out3 = FactorEngine(backend=PandasBackend(), data_source=src).run(f3)["result"]
    assert out3.loc[(pd.Timestamp("2024-01-03"), "A")] > 0


def test_ts_sum_delay():
    src = _panel()
    f = Factor(name="s", expr=ts_sum(col("close"), 2))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-02"), "A")] == pytest.approx(21.0)

    f2 = Factor(name="d", expr=ts_delay(col("close"), 1))
    out2 = FactorEngine(backend=PandasBackend(), data_source=src).run(f2)["result"]
    assert out2.loc[(pd.Timestamp("2024-01-02"), "A")] == 10.0


def test_ts_mean_uses_d_param():
    src = _panel()
    f = Factor(name="m", expr=ts_mean(col("close"), 2))
    out = FactorEngine(backend=PandasBackend(), data_source=src).run(f)["result"]
    assert out.loc[(pd.Timestamp("2024-01-02"), "A")] == pytest.approx(10.5)
