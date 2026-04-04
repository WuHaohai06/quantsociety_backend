"""
时序算子表达式（WorldQuant BRAIN — Time Series）。

所有窗口参数 ``window`` / ``d`` 表示 **每个标的上的连续 bar 条数**，不是自然日。
执行时在 Pandas 中按 ``instrument`` 分组后做 ``rolling`` / ``shift``。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class TsMean(Expr):
    """滚动简单平均（每标的 ``window`` 根 bar）。

    **华泰对照**：图表 9 ``TS_Mean`` 在研报中为「d **季度**」窗口；此处为 bar 窗口。
    """

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsStdDev(Expr):
    """滚动标准差（WQ：ts_std_dev）。"""

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsStd(TsStdDev):
    """与 :class:`TsStdDev` 相同，旧名 ``ts_std`` 兼容。"""

    pass


@dataclass(frozen=True)
class TsMax(Expr):
    """滚动最大值。"""

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsMin(Expr):
    """滚动最小值。"""

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsDelay(Expr):
    """滞后 d 根 bar：x(t-d)。

    **华泰对照**：图表 9 ``Delay`` 为「第 d **季度**」；此处为 bar 轴。
    """

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class Delay(Expr):
    """旧 API 滞后；IR 与 :class:`TsDelay` 一致，``periods`` 映射为 d。"""

    child: Expr
    periods: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsSum(Expr):
    """滚动求和。"""

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsProduct(Expr):
    """滚动连乘。"""

    child: Expr
    window: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsDelta(Expr):
    """x - ts_delay(x, d)。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsAvDiff(Expr):
    """x - ts_mean(x, d)（均值对 NaN 按 pandas 规则忽略）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsZscore(Expr):
    """时序 Z 分数：(x - 滚动均值) / 滚动标准差。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsRank(Expr):
    """当前值在窗口内的分位排名，可加 ``constant`` 平移。"""

    child: Expr
    d: int
    constant: float = 0.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsScale(Expr):
    """窗口内 min-max 缩放到约 [0,1]，再加 ``constant``。"""

    child: Expr
    d: int
    constant: float = 0.0

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsCountNans(Expr):
    """窗口内 NaN 个数。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsBackfill(Expr):
    """在滚动窗口内，若当前为 NaN，则用窗口内「从当前往过去数第 k 个**有限**观测」替换。

    ``k=1`` 即最常见的「用上一有效值前填」；更大的 k 表示跳过若干有效历史点再取。
    若窗口内有效点不足 k 个，则当前位置仍为 NaN。实现依赖 pandas 后端对窗口与 NaN 的具体规则。
    """

    child: Expr
    lookback: int
    k: int = 1

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsArgMax(Expr):
    """距今几根 bar 前出现窗口内最大值（0=当前根）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsArgMin(Expr):
    """距今几根 bar 前出现窗口内最小值。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsDecayLinear(Expr):
    """滚动 **线性衰减加权** 平均：窗口内越近的 bar 权重越大（三角形权重），远端权重线性变小。

    用于强调近期信息、同时比单点 ``ts_delay`` 更平滑。**dense=True** 时窗口内 NaN 不参与加权，
    并对剩余有效点的权重重新归一化（具体归一化以后端为准）；**False** 时 NaN 会污染加权和，
    行为更接近「稀疏窗口」语义。挖掘时若对缺失敏感，可先 ``pasteurize`` / ``ts_backfill``。
    """

    child: Expr
    d: int
    dense: bool = False

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsCorr(Expr):
    """x 与 y 的滚动皮尔逊相关系数。"""

    left: Expr
    right: Expr
    d: int

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class TsCovariance(Expr):
    """滚动协方差；WQ 参数顺序为 (y, x, d)，此处 left=y、right=x。"""

    left: Expr
    right: Expr
    d: int

    def children(self) -> tuple[Expr, Expr]:
        return (self.left, self.right)


@dataclass(frozen=True)
class TsRegression(Expr):
    """滚动窗口内 **y 对 x 的一元 OLS 回归**（每个 instrument 独立滚动）。

    在每个窗口内估计 ``y ≈ alpha + beta * x``；``rettype`` 整数编码 **返回哪一个统计量**
    （截距、斜率、残差、R² 等），与 WorldQuant BRAIN 文档中的 ``ts_regression`` 表一致，
    写因子前请查 WQ 表或本仓库 ``operators_semantics`` / 测试中的约定，避免 rettype 用错。

    ``lag`` 将自变量 x **再滞后** 若干 bar，用于对齐「用过去 x 解释当前 y」的因果顺序。
    窗口过短或 x 无变异时，后端通常返回 NaN。
    """

    y: Expr
    x: Expr
    d: int
    lag: int = 0
    rettype: int = 0

    def children(self) -> tuple[Expr, Expr]:
        return (self.y, self.x)


@dataclass(frozen=True)
class TsQuantile(Expr):
    """滚动窗口内：先把当前值放在窗口经验分位 ``q∈[0,1]`` 上，再经 **driver** 变到目标分布。

    **默认 driver=gaussian**：用分位 q 当作标准正态的 **CDF 逆**（需 scipy），输出近似 N(0,1)，
    便于在不同时序波动尺度间可比。与 **截面** ``quantile``（每个 timestamp 横截面上变分位）不同：
    这里是 **每个标的自己的时间窗** 内的相对位置。

    窗口内有效点过少时输出常为 NaN；与 ``ts_rank``（仅 rank）相比，本算子多了「分位 → 分布」一步。
    """

    child: Expr
    d: int
    driver: str = "gaussian"

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class DaysFromLastChange(Expr):
    """自上次取值变化以来经过的 bar 数。"""

    child: Expr

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class KthElement(Expr):
    """滚动窗口内取 **排序后的第 k 个值**（顺序统计量），类似「窗口内第 k 小/大」。

    k 的计数方式与 WQ 约定一致（实现见 pandas 后端）：通常 k=1 表示窗口内最小一侧，
    大 k 表示更靠大值一侧。**ignore** 控制 NaN 是否参与排序（如 ``"NaN"`` 表示跳过 NaN）；
    若跳过 NaN 后有效点不足 k，输出 NaN。用于稳健估计、非参位置度量等，比 ``ts_min``/``ts_max``
    对极端值更不敏感（取中间次序统计量时）。
    """

    child: Expr
    d: int
    k: int
    ignore: str = "NaN"

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class LastDiffValue(Expr):
    """在当前 bar 之前的窗口内，找 **最近一根** 满足「历史值 ≠ 当前值」的 bar 上的 **那个历史值**。

    用于刻画「上一次发生变化时旧值是多少」、状态切换前的水平等；与 ``ts_delay``（固定滞后）
    不同，这里是 **事件驱动** 的回望。若窗口内没有与当前不同的有限值，输出 NaN。具体相等判定
    为浮点相等，接近相等的抖动可能被当成「未变化」。
    """

    child: Expr
    d: int

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsSkew(Expr):
    """滚动样本偏度（pandas ``rolling().skew()``）；窗口 ``d``。"""

    child: Expr
    d: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsKurt(Expr):
    """滚动峰度（pandas Fisher 定义，超额峰度）；窗口 ``d``。"""

    child: Expr
    d: int
    min_periods: int | None = None

    def children(self) -> tuple[Expr]:
        return (self.child,)


@dataclass(frozen=True)
class TsStep(Expr):
    """**周期性阶梯**：在每个标的自己的时间轴上，第 i 根 bar（从 0 计数）输出 ``float(i % d)``。

    **anchor 参数**：表达式树里必须带一个 ``anchor`` 子表达式，**仅用于提供与结果相同的
    MultiIndex 形状**（例如 ``col("close")``）；**anchor 的数值不参与计算**。这样即使没有
    其他列依赖，也能唯一确定面板上有哪些 (timestamp, instrument)。

    **与「全局交易日 step」的差异**：此处 i 是 **该标的可见 bar 的连续下标**，停牌日无 bar 则
    不推进计数，故不同标的的 ``ts_step`` 可能在同一日历日 **不同步**。若策略要求全市场统一
    交易日编号，需要在数据层对齐 bar 或使用别的算子。详见 ``docs/adr_ts_step_hump.md``。
    """

    d: int
    anchor: Expr

    def children(self) -> tuple[Expr, ...]:
        return (self.anchor,)


@dataclass(frozen=True)
class Hump(Expr):
    """**带记忆的单边限幅**：输出序列满足每步相对 **上一根输出** 的变化不超过 ``hump``。

    对每个 instrument 按时间升序：记上一根 **已输出** 为 ``out_{t-1}``。当前输入 ``x_t`` 有限时，
    ``out_t = clip(x_t, out_{t-1} - h, out_{t-1} + h)``。第一根 **有限** 输入前无历史输出时，
    输出取当前输入。输入 NaN 时输出 NaN，且 **不更新** 内部记忆（下一根有限输入仍相对
    **上一次有效输出** 裁剪），避免缺失把状态冲没。

    用途：限制因子单期跳变、平滑换手代理、风控上「每期调整不超过 h」等。详见
    ``docs/adr_ts_step_hump.md``。
    """

    child: Expr
    hump: float = 0.01

    def children(self) -> tuple[Expr]:
        return (self.child,)
