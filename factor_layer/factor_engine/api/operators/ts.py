"""时序算子 API。

**窗口含义**：参数 ``d`` / ``window`` 表示 **每个标的上连续的 bar 条数**，不是自然日历日；
停牌日若无 bar，窗口内点数会少于日历长度。

**难懂算子入口**：``ts_regression``（滚动 OLS + ``rettype`` 编码）、``ts_quantile``（时序分位
再映射分布）、``ts_decay_linear``（三角权重）、``kth_element`` / ``last_diff_value``（顺序统计 /
事件回望）、``ts_step`` / ``hump``（周期阶梯 / 带记忆限幅）——详细见对应 ``expr.ts`` 类 docstring
与 ``docs/adr_ts_step_hump.md``、``operators_semantics.md``。
"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.ts import (
    DaysFromLastChange,
    Delay,
    Hump,
    KthElement,
    LastDiffValue,
    TsArgMax,
    TsArgMin,
    TsAvDiff,
    TsBackfill,
    TsCorr,
    TsCountNans,
    TsCovariance,
    TsDecayLinear,
    TsDelay,
    TsDelta,
    TsMax,
    TsKurt,
    TsMean,
    TsMin,
    TsProduct,
    TsQuantile,
    TsRank,
    TsRegression,
    TsScale,
    TsStd,
    TsSkew,
    TsStdDev,
    TsStep,
    TsSum,
    TsZscore,
)


def ts_mean(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    """过去 ``d`` 根 **bar** 上均值（每标的内滚动）。

    **华泰对照**：图表 9 ``TS_Mean`` 在研报中为「过去 d **季度**」；本引擎为 bar 轴，非自动季频。
    """
    return TsMean(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_std_dev(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsStdDev(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_std(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsStd(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_max(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsMax(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_min(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsMin(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_delay(x: Expr, d: int) -> Expr:
    """滞后 ``d`` 根 bar。

    **华泰对照**：图表 9 ``Delay(X,d)`` 为「过去第 d **季度**」；本引擎为 bar 滞后。
    """
    return TsDelay(child=ensure_expr(x), d=d)


def delay(x: Expr, periods: int) -> Expr:
    """``delay`` 别名（WQ 兼容）。

    **华泰对照**：同 ``ts_delay`` 与图表 9 ``Delay`` 之差异说明。
    """
    return Delay(child=ensure_expr(x), periods=periods)


def ts_delta(x: Expr, d: int) -> Expr:
    return TsDelta(child=ensure_expr(x), d=d)


def ts_sum(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsSum(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_product(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    return TsProduct(child=ensure_expr(x), window=d, min_periods=min_periods)


def ts_av_diff(x: Expr, d: int) -> Expr:
    return TsAvDiff(child=ensure_expr(x), d=d)


def ts_zscore(x: Expr, d: int) -> Expr:
    return TsZscore(child=ensure_expr(x), d=d)


def ts_rank(x: Expr, d: int, constant: float = 0.0) -> Expr:
    return TsRank(child=ensure_expr(x), d=d, constant=constant)


def ts_scale(x: Expr, d: int, constant: float = 0.0) -> Expr:
    return TsScale(child=ensure_expr(x), d=d, constant=constant)


def ts_count_nans(x: Expr, d: int) -> Expr:
    return TsCountNans(child=ensure_expr(x), d=d)


def ts_backfill(x: Expr, lookback: int, k: int = 1) -> Expr:
    """NaN 时用窗口内从当前往过去第 k 个有限值填充（k=1 即最近有效历史）。"""
    return TsBackfill(child=ensure_expr(x), lookback=lookback, k=k)


def ts_arg_max(x: Expr, d: int) -> Expr:
    return TsArgMax(child=ensure_expr(x), d=d)


def ts_arg_min(x: Expr, d: int) -> Expr:
    return TsArgMin(child=ensure_expr(x), d=d)


def ts_decay_linear(x: Expr, d: int, dense: bool = False) -> Expr:
    """线性衰减加权滚动均值；近端权重大。``dense=True`` 时 NaN 不参与且权重重归一。"""
    return TsDecayLinear(child=ensure_expr(x), d=d, dense=dense)


def ts_corr(x: Expr, y: Expr, d: int) -> Expr:
    return TsCorr(left=ensure_expr(x), right=ensure_expr(y), d=d)


def ts_covariance(y: Expr, x: Expr, d: int) -> Expr:
    return TsCovariance(left=ensure_expr(y), right=ensure_expr(x), d=d)


def ts_regression(
    y: Expr, x: Expr, d: int, lag: int = 0, rettype: int = 0
) -> Expr:
    """滚动一元回归 ``y ~ x``；``rettype`` 选择返回截距/斜率/残差/R² 等（见 WQ 文档表）。

    ``lag`` 对 x 再滞后若干 bar。窗口太短或 x 无变异时多为 NaN。
    """
    return TsRegression(
        y=ensure_expr(y), x=ensure_expr(x), d=d, lag=lag, rettype=rettype
    )


def ts_quantile(x: Expr, d: int, driver: str = "gaussian") -> Expr:
    """滚动窗口内经验分位再经 ``driver`` 变换；默认 gaussian 需 scipy，输出近似标准正态。

    与截面 ``quantile`` 不同：这是 **每标的自己的时间窗** 内相对位置再映射。
    """
    return TsQuantile(child=ensure_expr(x), d=d, driver=driver)


def days_from_last_change(x: Expr) -> Expr:
    return DaysFromLastChange(child=ensure_expr(x))


def kth_element(x: Expr, d: int, k: int, ignore: str = "NaN") -> Expr:
    """窗口内排序后的第 k 个值（顺序统计量）；``ignore`` 控制是否跳过 NaN。"""
    return KthElement(child=ensure_expr(x), d=d, k=k, ignore=ignore)


def last_diff_value(x: Expr, d: int) -> Expr:
    """窗口内（不含当前）最近一根「值≠当前」的历史 bar 上的那个历史值。"""
    return LastDiffValue(child=ensure_expr(x), d=d)


def ts_step(d: int, anchor: Expr) -> Expr:
    """各标的内时间序第 i 根 bar 输出 ``i % d``；``anchor`` 只用来对齐 MultiIndex，不参与计算。

    i 为 **该标的可见 bar 连续下标**，非全市场统一交易日计数；详见 ``docs/adr_ts_step_hump.md``。
    """
    return TsStep(d=int(d), anchor=ensure_expr(anchor))


def hump(x: Expr, hump: float = 0.01) -> Expr:
    """相对上一根 **输出** 限幅：单步变化不超过 ``hump``；输入 NaN 不更新内部状态。"""
    return Hump(child=ensure_expr(x), hump=hump)


def ts_skew(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    """滚动偏度。"""
    return TsSkew(
        child=ensure_expr(x), d=int(d), min_periods=min_periods
    )


def ts_kurt(x: Expr, d: int, min_periods: int | None = None) -> Expr:
    """滚动峰度（pandas Fisher 超额峰度）。"""
    return TsKurt(
        child=ensure_expr(x), d=int(d), min_periods=min_periods
    )
