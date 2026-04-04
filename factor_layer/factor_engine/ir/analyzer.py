"""表达式 → IR：遍历 ``Expr`` 树生成 ``IRNode``，并统计列名、回看 bar 数、是否含时序/截面算子。"""

from __future__ import annotations

from dataclasses import dataclass

from expr.alternative import AlternativeStub
from expr.cleaning import Pasteurize, ProtectedDiv, ProtectedLog, ProtectedSqrt, Tail
from expr.context import ChangeInstrument, Orthogonalize
from expr.fundamental import FundamentalStub
from expr.intraday import IntradayStub
from expr.arithmetic import (
    Abs,
    Add,
    Densify,
    Div,
    Exp,
    Inverse,
    Log,
    Mul,
    NaryAdd,
    NaryMax,
    NaryMin,
    NaryMul,
    NarySub,
    Pow,
    Cos,
    Reverse,
    SignedPow,
    Sign,
    Sin,
    Sqrt,
    Sub,
)
from expr.base import Expr
from expr.column import ColumnRef
from expr.cs import CsQuantile, Neutralize, Normalize, Rank, Scale, Winsorize, ZScore
from expr.group import (
    GroupBackfill,
    GroupMean,
    GroupNeutralize,
    GroupRank,
    GroupScale,
    GroupZscore,
)
from expr.literal import Literal
from expr.logical import And, Eq, Ge, Gt, IfElse, IsNan, Le, Lt, Ne, Not, Or
from expr.microstructure import MicrostructureStub
from expr.transformational import Bucket, TradeWhen
from expr.technical import (
    TsAd,
    TsAdosc,
    TsAdx,
    TsAdxr,
    TsApo,
    TsAroon,
    TsAtr,
    TsBbands,
    TsBop,
    TsCci,
    TsCmo,
    TsDema,
    TsDonchian,
    TsDx,
    TsEma,
    TsKama,
    TsKeltner,
    TsLinearregAngle,
    TsLinearregSlope,
    TsMacd,
    TsMaEnvelope,
    TsMfi,
    TsMom,
    TsNatr,
    TsObv,
    TsPpo,
    TsRoc,
    TsRocr100,
    TsRocr,
    TsRsi,
    TsSar,
    TsSma,
    TsStochf,
    TsStoch,
    TsStochrsi,
    TsT3,
    TsTema,
    TsTrange,
    TsTrima,
    TsTrix,
    TsUltosc,
    TsWillr,
    TsWma,
)
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
    TsMean,
    TsMin,
    TsProduct,
    TsQuantile,
    TsRank,
    TsRegression,
    TsScale,
    TsStd,
    TsStdDev,
    TsKurt,
    TsSkew,
    TsStep,
    TsSum,
    TsZscore,
)
from expr.vector import VecAvg, VecSum

from .nodes import IRNode


@dataclass
class AnalysisResult:
    """单次 ``lower`` 的输出：根 IR、静态分析摘要。"""

    ir: IRNode
    lookback: int
    has_ts_op: bool
    has_cs_op: bool
    referenced_columns: set[str]


def _lb_max(a: int, b: int) -> int:
    """取较大整数，用于累积所需历史 bar 长度。"""
    return max(a, b)


class Analyzer:
    """将 :class:`expr.base.Expr` 下降为 :class:`IRNode` 树。"""

    def lower(self, expr: Expr) -> AnalysisResult:
        cols: set[str] = set()  # 数据依赖列，供数据源只拉必要字段
        lookback = 0  # 引擎需向前多取的历史 bar 数（滚动窗口上界）
        has_ts = False
        has_cs = False

        def visit(node: Expr) -> IRNode:
            """后序遍历：子节点先降为 IR，再组装当前节点的 ``op``/``attrs``。"""
            nonlocal lookback, has_ts, has_cs

            if isinstance(node, ColumnRef):
                cols.add(node.name)
                return IRNode(op="column", attrs={"name": node.name})

            if isinstance(node, Literal):
                return IRNode(op="literal", attrs={"value": node.value})

            if isinstance(node, TsMean):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_mean",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsStdDev):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_std_dev",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsMax):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_max",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsMin):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_min",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsDelay):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_delay", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, Delay):
                has_ts = True
                lookback = _lb_max(lookback, node.periods)
                ch = visit(node.child)
                return IRNode(
                    op="ts_delay", inputs=(ch,), attrs={"d": node.periods}
                )

            if isinstance(node, TsSum):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_sum",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsProduct):
                has_ts = True
                lookback = _lb_max(lookback, node.window)
                ch = visit(node.child)
                return IRNode(
                    op="ts_product",
                    inputs=(ch,),
                    attrs={"d": node.window, "min_periods": node.min_periods},
                )

            if isinstance(node, TsDelta):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                ch = visit(node.child)
                return IRNode(op="ts_delta", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsAvDiff):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_av_diff", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsZscore):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_zscore", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsRank):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_rank",
                    inputs=(ch,),
                    attrs={"d": node.d, "constant": node.constant},
                )

            if isinstance(node, TsScale):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_scale",
                    inputs=(ch,),
                    attrs={"d": node.d, "constant": node.constant},
                )

            if isinstance(node, TsCountNans):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_count_nans", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsBackfill):
                has_ts = True
                lookback = _lb_max(lookback, node.lookback)
                ch = visit(node.child)
                return IRNode(
                    op="ts_backfill",
                    inputs=(ch,),
                    attrs={"lookback": node.lookback, "k": node.k},
                )

            if isinstance(node, TsArgMax):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_arg_max", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsArgMin):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_arg_min", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsDecayLinear):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_decay_linear",
                    inputs=(ch,),
                    attrs={"d": node.d, "dense": node.dense},
                )

            if isinstance(node, TsCorr):
                has_ts = True
                la = visit(node.left)
                lb = visit(node.right)
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_corr", inputs=(la, lb), attrs={"d": node.d}
                )

            if isinstance(node, TsCovariance):
                has_ts = True
                la = visit(node.left)
                lb = visit(node.right)
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_covariance", inputs=(la, lb), attrs={"d": node.d}
                )

            if isinstance(node, TsRegression):
                has_ts = True
                ya = visit(node.y)
                xb = visit(node.x)
                lookback = _lb_max(lookback, node.d + max(0, node.lag))
                return IRNode(
                    op="ts_regression",
                    inputs=(ya, xb),
                    attrs={"d": node.d, "lag": node.lag, "rettype": node.rettype},
                )

            if isinstance(node, TsQuantile):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_quantile",
                    inputs=(ch,),
                    attrs={"d": node.d, "driver": node.driver},
                )

            if isinstance(node, DaysFromLastChange):
                has_ts = True
                ch = visit(node.child)
                return IRNode(op="days_from_last_change", inputs=(ch,))

            if isinstance(node, KthElement):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="kth_element",
                    inputs=(ch,),
                    attrs={"d": node.d, "k": node.k, "ignore": node.ignore},
                )

            if isinstance(node, LastDiffValue):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="last_diff_value", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsStep):
                has_ts = True
                ch = visit(node.anchor)
                return IRNode(op="ts_step", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, Hump):
                has_ts = True
                ch = visit(node.child)
                return IRNode(
                    op="hump", inputs=(ch,), attrs={"hump": node.hump}
                )

            if isinstance(node, Rank):
                has_cs = True
                ch = visit(node.child)
                return IRNode(op="rank", inputs=(ch,), attrs={"rate": node.rate})

            if isinstance(node, ZScore):
                has_cs = True
                ch = visit(node.child)
                return IRNode(op="zscore", inputs=(ch,))

            if isinstance(node, Normalize):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="normalize",
                    inputs=(ch,),
                    attrs={"useStd": node.use_std, "limit": node.limit},
                )

            if isinstance(node, CsQuantile):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="quantile",
                    inputs=(ch,),
                    attrs={"driver": node.driver, "sigma": node.sigma},
                )

            if isinstance(node, Scale):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="scale",
                    inputs=(ch,),
                    attrs={
                        "scale": node.scale,
                        "longscale": node.longscale,
                        "shortscale": node.shortscale,
                    },
                )

            if isinstance(node, Winsorize):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="winsorize", inputs=(ch,), attrs={"std": node.std}
                )

            if isinstance(node, Add):
                return IRNode(
                    op="add", inputs=(visit(node.left), visit(node.right))
                )

            if isinstance(node, Sub):
                return IRNode(
                    op="sub", inputs=(visit(node.left), visit(node.right))
                )

            if isinstance(node, Mul):
                return IRNode(
                    op="mul", inputs=(visit(node.left), visit(node.right))
                )

            if isinstance(node, Div):
                return IRNode(
                    op="div", inputs=(visit(node.left), visit(node.right))
                )

            if isinstance(node, Abs):
                return IRNode(op="abs", inputs=(visit(node.child),))

            if isinstance(node, Log):
                return IRNode(op="log", inputs=(visit(node.child),))

            if isinstance(node, Exp):
                return IRNode(op="exp", inputs=(visit(node.child),))

            if isinstance(node, Sqrt):
                return IRNode(op="sqrt", inputs=(visit(node.child),))

            if isinstance(node, Sin):
                return IRNode(op="sin", inputs=(visit(node.child),))

            if isinstance(node, Cos):
                return IRNode(op="cos", inputs=(visit(node.child),))

            if isinstance(node, Sign):
                return IRNode(op="sign", inputs=(visit(node.child),))

            if isinstance(node, Reverse):
                return IRNode(op="reverse", inputs=(visit(node.child),))

            if isinstance(node, Inverse):
                return IRNode(op="inverse", inputs=(visit(node.child),))

            if isinstance(node, Pow):
                return IRNode(
                    op="power",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, SignedPow):
                return IRNode(
                    op="signed_power",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, NaryAdd):
                return IRNode(
                    op="nary_add",
                    inputs=tuple(visit(c) for c in node.operands),
                    attrs={"filter": node.filter_nan},
                )

            if isinstance(node, NaryMul):
                return IRNode(
                    op="nary_mul",
                    inputs=tuple(visit(c) for c in node.operands),
                    attrs={"filter": node.filter_nan},
                )

            if isinstance(node, NarySub):
                return IRNode(
                    op="nary_sub",
                    inputs=tuple(visit(c) for c in node.operands),
                    attrs={"filter": node.filter_nan},
                )

            if isinstance(node, NaryMax):
                return IRNode(
                    op="nary_max",
                    inputs=tuple(visit(c) for c in node.operands),
                )

            if isinstance(node, NaryMin):
                return IRNode(
                    op="nary_min",
                    inputs=tuple(visit(c) for c in node.operands),
                )

            if isinstance(node, Densify):
                has_cs = True
                return IRNode(op="densify", inputs=(visit(node.child),))

            if isinstance(node, Not):
                return IRNode(op="not", inputs=(visit(node.child),))

            if isinstance(node, And):
                return IRNode(
                    op="and",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Or):
                return IRNode(
                    op="or",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, IfElse):
                return IRNode(
                    op="if_else",
                    inputs=(
                        visit(node.condition),
                        visit(node.then_),
                        visit(node.else_),
                    ),
                )

            if isinstance(node, IsNan):
                return IRNode(op="is_nan", inputs=(visit(node.child),))

            if isinstance(node, Lt):
                return IRNode(
                    op="lt",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Le):
                return IRNode(
                    op="le",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Eq):
                return IRNode(
                    op="eq",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Gt):
                return IRNode(
                    op="gt",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Ge):
                return IRNode(
                    op="ge",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, Ne):
                return IRNode(
                    op="ne",
                    inputs=(visit(node.left), visit(node.right)),
                )

            if isinstance(node, VecAvg):
                return IRNode(op="vec_avg", inputs=(visit(node.child),))

            if isinstance(node, VecSum):
                return IRNode(op="vec_sum", inputs=(visit(node.child),))

            if isinstance(node, Bucket):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="bucket",
                    inputs=(ch,),
                    attrs={
                        "range": node.range_spec,
                        "buckets": node.buckets_spec,
                        "skipBoth": node.skip_both,
                        "NaNGroup": node.nan_group,
                    },
                )

            if isinstance(node, TradeWhen):
                has_ts = True
                return IRNode(
                    op="trade_when",
                    inputs=(
                        visit(node.trigger),
                        visit(node.alpha),
                        visit(node.exit_),
                    ),
                )

            if isinstance(node, GroupBackfill):
                has_ts = True
                return IRNode(
                    op="group_backfill",
                    inputs=(visit(node.x), visit(node.group)),
                    attrs={"d": node.d, "std": node.std},
                )

            if isinstance(node, GroupMean):
                has_cs = True
                return IRNode(
                    op="group_mean",
                    inputs=(
                        visit(node.x),
                        visit(node.weight),
                        visit(node.group),
                    ),
                )

            if isinstance(node, GroupNeutralize):
                has_cs = True
                return IRNode(
                    op="group_neutralize",
                    inputs=(visit(node.x), visit(node.group)),
                )

            if isinstance(node, GroupRank):
                has_cs = True
                return IRNode(
                    op="group_rank",
                    inputs=(visit(node.x), visit(node.group)),
                )

            if isinstance(node, GroupScale):
                has_cs = True
                return IRNode(
                    op="group_scale",
                    inputs=(visit(node.x), visit(node.group)),
                )

            if isinstance(node, GroupZscore):
                has_cs = True
                return IRNode(
                    op="group_zscore",
                    inputs=(visit(node.x), visit(node.group)),
                )

            if isinstance(node, Pasteurize):
                ch = visit(node.child)
                attrs: dict = {}
                if node.fill_value is not None:
                    attrs["fill_value"] = node.fill_value
                return IRNode(op="pasteurize", inputs=(ch,), attrs=attrs)

            if isinstance(node, Tail):
                has_cs = True
                ch = visit(node.child)
                return IRNode(
                    op="tail",
                    inputs=(ch,),
                    attrs={"lower": node.lower, "upper": node.upper},
                )

            if isinstance(node, ProtectedDiv):
                return IRNode(
                    op="protected_div",
                    inputs=(visit(node.left), visit(node.right)),
                    attrs={"epsilon": node.epsilon, "default": node.default},
                )

            if isinstance(node, ProtectedLog):
                return IRNode(
                    op="protected_log",
                    inputs=(visit(node.child),),
                    attrs={"epsilon": node.epsilon},
                )

            if isinstance(node, ProtectedSqrt):
                return IRNode(op="protected_sqrt", inputs=(visit(node.child),))

            if isinstance(node, TsSma):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_sma", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsEma):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_ema", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsRsi):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                ch = visit(node.child)
                return IRNode(op="ts_rsi", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsBbands):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_bbands",
                    inputs=(ch,),
                    attrs={
                        "d": node.d,
                        "nbdev": node.nbdev,
                        "band": node.band,
                    },
                )

            if isinstance(node, TsTrange):
                has_ts = True
                lookback = _lb_max(lookback, 2)
                return IRNode(
                    op="ts_trange",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={},
                )

            if isinstance(node, TsAtr):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                return IRNode(
                    op="ts_atr",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsNatr):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                return IRNode(
                    op="ts_natr",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsDonchian):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_donchian",
                    inputs=(visit(node.high), visit(node.low)),
                    attrs={"d": node.d, "band": node.band},
                )

            if isinstance(node, TsKeltner):
                has_ts = True
                ad = node.d if node.atr_d is None else int(node.atr_d)
                lookback = _lb_max(lookback, max(node.d, ad) + 1)
                return IRNode(
                    op="ts_keltner",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={
                        "d": node.d,
                        "mult": node.mult,
                        "band": node.band,
                        "atr_d": ad,
                    },
                )

            if isinstance(node, TsMaEnvelope):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_ma_envelope",
                    inputs=(ch,),
                    attrs={
                        "d": node.d,
                        "pct": node.pct,
                        "band": node.band,
                        "use_ema": node.use_ema,
                    },
                )

            if isinstance(node, TsMacd):
                has_ts = True
                lookback = _lb_max(
                    lookback, node.slow + node.signal + 2
                )
                ch = visit(node.child)
                return IRNode(
                    op="ts_macd",
                    inputs=(ch,),
                    attrs={
                        "fast": node.fast,
                        "slow": node.slow,
                        "signal": node.signal,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsCci):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_cci",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsStoch):
                has_ts = True
                lookback = _lb_max(
                    lookback,
                    node.fastk_period + node.slowk_period + node.slowd_period,
                )
                return IRNode(
                    op="ts_stoch",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={
                        "fastk_period": node.fastk_period,
                        "slowk_period": node.slowk_period,
                        "slowd_period": node.slowd_period,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsWillr):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_willr",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsRoc):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                ch = visit(node.child)
                return IRNode(op="ts_roc", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsObv):
                has_ts = True
                lookback = _lb_max(lookback, 2)
                return IRNode(
                    op="ts_obv",
                    inputs=(visit(node.close), visit(node.volume)),
                    attrs={},
                )

            if isinstance(node, TsMfi):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                return IRNode(
                    op="ts_mfi",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                        visit(node.volume),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsDema):
                has_ts = True
                lookback = _lb_max(lookback, node.d * 2)
                ch = visit(node.child)
                return IRNode(op="ts_dema", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsWma):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_wma", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsKama):
                has_ts = True
                lookback = _lb_max(lookback, node.d + node.slow_period)
                ch = visit(node.child)
                return IRNode(
                    op="ts_kama",
                    inputs=(ch,),
                    attrs={
                        "d": node.d,
                        "fast_period": node.fast_period,
                        "slow_period": node.slow_period,
                    },
                )

            if isinstance(node, TsAdx):
                has_ts = True
                lookback = _lb_max(lookback, 3 * node.d + 5)
                return IRNode(
                    op="ts_adx",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d, "line": node.line},
                )

            if isinstance(node, TsAroon):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                return IRNode(
                    op="ts_aroon",
                    inputs=(visit(node.high), visit(node.low)),
                    attrs={"d": node.d, "line": node.line},
                )

            if isinstance(node, TsAd):
                has_ts = True
                lookback = _lb_max(lookback, 2)
                return IRNode(
                    op="ts_ad",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                        visit(node.volume),
                    ),
                    attrs={},
                )

            if isinstance(node, TsAdosc):
                has_ts = True
                lookback = _lb_max(lookback, node.slow + 5)
                return IRNode(
                    op="ts_adosc",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                        visit(node.volume),
                    ),
                    attrs={"fast": node.fast, "slow": node.slow},
                )

            if isinstance(node, TsSar):
                has_ts = True
                lookback = _lb_max(lookback, 5)
                return IRNode(
                    op="ts_sar",
                    inputs=(visit(node.high), visit(node.low)),
                    attrs={
                        "acceleration": node.acceleration,
                        "maximum": node.maximum,
                    },
                )

            if isinstance(node, TsCmo):
                has_ts = True
                lookback = _lb_max(lookback, node.d + 1)
                ch = visit(node.child)
                return IRNode(op="ts_cmo", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsPpo):
                has_ts = True
                lookback = _lb_max(lookback, node.slow + node.signal + 2)
                ch = visit(node.child)
                return IRNode(
                    op="ts_ppo",
                    inputs=(ch,),
                    attrs={
                        "fast": node.fast,
                        "slow": node.slow,
                        "signal": node.signal,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsApo):
                has_ts = True
                lookback = _lb_max(lookback, node.slow + node.signal + 2)
                ch = visit(node.child)
                return IRNode(
                    op="ts_apo",
                    inputs=(ch,),
                    attrs={
                        "fast": node.fast,
                        "slow": node.slow,
                        "signal": node.signal,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsUltosc):
                has_ts = True
                lookback = _lb_max(
                    lookback,
                    max(node.timeperiod1, node.timeperiod2, node.timeperiod3)
                    + 2,
                )
                return IRNode(
                    op="ts_ultosc",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={
                        "timeperiod1": node.timeperiod1,
                        "timeperiod2": node.timeperiod2,
                        "timeperiod3": node.timeperiod3,
                    },
                )

            if isinstance(node, TsStochrsi):
                has_ts = True
                lookback = _lb_max(
                    lookback,
                    node.timeperiod + node.fastk_period + node.fastd_period + 2,
                )
                ch = visit(node.child)
                return IRNode(
                    op="ts_stochrsi",
                    inputs=(ch,),
                    attrs={
                        "timeperiod": node.timeperiod,
                        "fastk_period": node.fastk_period,
                        "fastd_period": node.fastd_period,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsTema):
                has_ts = True
                lookback = _lb_max(lookback, 3 * node.d + 2)
                ch = visit(node.child)
                return IRNode(op="ts_tema", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsTrima):
                has_ts = True
                lookback = _lb_max(lookback, 2 * node.d + 2)
                ch = visit(node.child)
                return IRNode(op="ts_trima", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsT3):
                has_ts = True
                lookback = _lb_max(lookback, 6 * node.d + 5)
                ch = visit(node.child)
                return IRNode(
                    op="ts_t3",
                    inputs=(ch,),
                    attrs={"d": node.d, "vfactor": node.vfactor},
                )

            if isinstance(node, TsBop):
                has_ts = True
                lookback = _lb_max(lookback, 2)
                return IRNode(
                    op="ts_bop",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={},
                )

            if isinstance(node, TsMom):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_mom", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsStochf):
                has_ts = True
                lookback = _lb_max(
                    lookback, node.fastk_period + node.fastd_period + 2
                )
                return IRNode(
                    op="ts_stochf",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={
                        "fastk_period": node.fastk_period,
                        "fastd_period": node.fastd_period,
                        "line": node.line,
                    },
                )

            if isinstance(node, TsTrix):
                has_ts = True
                lookback = _lb_max(lookback, 3 * node.d + 5)
                ch = visit(node.child)
                return IRNode(op="ts_trix", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsAdxr):
                has_ts = True
                lookback = _lb_max(lookback, 4 * node.d + 10)
                return IRNode(
                    op="ts_adxr",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsDx):
                has_ts = True
                lookback = _lb_max(lookback, 3 * node.d + 5)
                return IRNode(
                    op="ts_dx",
                    inputs=(
                        visit(node.high),
                        visit(node.low),
                        visit(node.close),
                    ),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsRocr):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_rocr", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsRocr100):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(op="ts_rocr100", inputs=(ch,), attrs={"d": node.d})

            if isinstance(node, TsLinearregSlope):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_linearreg_slope",
                    inputs=(ch,),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsLinearregAngle):
                has_ts = True
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_linearreg_angle",
                    inputs=(ch,),
                    attrs={"d": node.d},
                )

            if isinstance(node, TsSkew):
                has_ts = True
                mp = node.min_periods if node.min_periods is not None else node.d
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_skew",
                    inputs=(ch,),
                    attrs={"d": node.d, "min_periods": mp},
                )

            if isinstance(node, TsKurt):
                has_ts = True
                mp = node.min_periods if node.min_periods is not None else node.d
                lookback = _lb_max(lookback, node.d)
                ch = visit(node.child)
                return IRNode(
                    op="ts_kurt",
                    inputs=(ch,),
                    attrs={"d": node.d, "min_periods": mp},
                )

            if isinstance(node, Neutralize):
                has_cs = True
                return IRNode(
                    op="neutralize",
                    inputs=(visit(node.x), visit(node.y)),
                    attrs={},
                )

            if isinstance(node, Orthogonalize):
                has_cs = True
                return IRNode(
                    op="orthogonalize",
                    inputs=(visit(node.x), visit(node.y)),
                )

            if isinstance(node, ChangeInstrument):
                ch = visit(node.child)
                return IRNode(
                    op="change_instrument",
                    inputs=(ch,),
                    attrs={"benchmark": node.benchmark_column},
                )

            if isinstance(node, FundamentalStub):
                return IRNode(op=node.op, inputs=(visit(node.child),))

            if isinstance(node, IntradayStub):
                return IRNode(op=node.op, inputs=(visit(node.child),))

            if isinstance(node, AlternativeStub):
                return IRNode(op=node.op, inputs=(visit(node.child),))

            if isinstance(node, MicrostructureStub):
                return IRNode(op=node.op, inputs=(visit(node.child),))

            raise NotImplementedError(f"Unsupported expr: {type(node).__name__}")

        ir = visit(expr)
        return AnalysisResult(
            ir=ir,
            lookback=lookback,
            has_ts_op=has_ts,
            has_cs_op=has_cs,
            referenced_columns=cols,
        )
