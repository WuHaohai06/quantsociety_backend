from api.columns import col
from expr.arithmetic import Sub
from expr.cs import Rank
from expr.ts import TsMean


def test_expr_composition():
    expr = rank(ts_mean(col("close"), 20) - ts_mean(col("close"), 5))
    assert isinstance(expr, Rank)
    assert isinstance(expr.child, Sub)
    assert isinstance(expr.child.left, TsMean)
    assert isinstance(expr.child.right, TsMean)


def ts_mean(x, window):
    return TsMean(x, window)


def rank(x):
    return Rank(x)
