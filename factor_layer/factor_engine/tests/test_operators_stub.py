import pytest

pd = pytest.importorskip("pandas")

import api.operators as ops
from api.columns import col
from api.factor import Factor
from api.operator_registry import STUB_IR_OPS
from backend.pandas_backend import PandasBackend
from ir.analyzer import Analyzer
from planner.lowerer import Lowerer
from runtime.engine import FactorEngine
from tests.helpers import InMemorySeriesSource


@pytest.mark.parametrize("op", sorted(STUB_IR_OPS))
def test_stub_compile(op):
    fn = getattr(ops, op)
    expr = fn(col("x"))
    ar = Analyzer().lower(expr)
    plan = Lowerer().to_logical_plan(ar.ir)
    assert plan.op == op


@pytest.mark.parametrize("op", sorted(STUB_IR_OPS))
def test_stub_execute_raises(op):
    fn = getattr(ops, op)
    expr = fn(col("x"))
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-01"]), ["A"]],
        names=["timestamp", "instrument"],
    )
    x = pd.Series([1.0], index=idx)
    src = InMemorySeriesSource(data={"x": x})
    eng = FactorEngine(backend=PandasBackend(), data_source=src)
    with pytest.raises(NotImplementedError):
        eng.run(Factor(name="v", expr=expr))
