"""
算子注册表（WorldQuant BRAIN 风格）。

- ``build_dsl_allowlist()``：供 ``dsl_parser`` 使用，键为 DSL 里允许的函数名 → 返回 ``Expr`` 的可调用对象。
- 因 ``ast.parse`` 限制，逻辑函数须用 ``and_`` / ``or_`` / ``not_``，不能写成 ``and`` 调用。
- ``STUB_IR_OPS``：这些 IR 算子名在 Pandas 后端仅注册占位，执行会 ``NotImplementedError``。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from api.columns import col
from expr.alternative import ALTERNATIVE_STUB_OPS
from expr.fundamental import FUNDAMENTAL_STUB_OPS
from expr.microstructure import MICROSTRUCTURE_STUB_OPS


class BrainCategory(str, Enum):
    """与 BRAIN 文档大类一致，并扩展 Deep Research 中的清洗/技术指标/上下文等维度。"""

    ARITHMETIC = "arithmetic"
    LOGICAL = "logical"
    TIME_SERIES = "time_series"
    CROSS_SECTIONAL = "cross_sectional"
    VECTOR = "vector"
    TRANSFORMATIONAL = "transformational"
    GROUP = "group"
    # 研究报告扩展类别（注册表/文档用；DSL 白名单仍按具体函数名）
    TECHNICAL = "technical"
    CLEANING = "cleaning"
    CONTEXT = "context"
    MICROSTRUCTURE = "microstructure"
    FUNDAMENTAL = "fundamental"
    ALTERNATIVE = "alternative"


# 以下 op 字符串在 PandasBackend 中走统一 stub，不实现具体计算。
STUB_IR_OPS: frozenset[str] = frozenset({"vec_avg", "vec_sum"}).union(
    FUNDAMENTAL_STUB_OPS,
    ALTERNATIVE_STUB_OPS,
    MICROSTRUCTURE_STUB_OPS,
)


def build_dsl_allowlist() -> dict[str, Callable[..., Any]]:
    """构建 DSL 白名单：仅这些标识符可作为 ``ast.Call`` 的函数名被解析。"""
    from api.operators import arithmetic as ar
    from api.operators import cleaning as cl
    from api.operators import future_data as fd
    from api.operators import context as cx
    from api.operators import cs as cs_ops
    from api.operators import group as gr
    from api.operators import logical as lg
    from api.operators import technical as tc
    from api.operators import transformational as tr
    from api.operators import ts as ts_ops
    from api.operators import vector as vec

    _future_stub_allowlist = {
        name: getattr(fd, name)
        for name in sorted(
            FUNDAMENTAL_STUB_OPS | ALTERNATIVE_STUB_OPS | MICROSTRUCTURE_STUB_OPS
        )
    }

    return {
        "col": col,
        # Arithmetic
        "abs": ar.abs_,
        "log": ar.log,
        "sqrt": ar.sqrt,
        "sin": ar.sin_,
        "cos": ar.cos_,
        "sign": ar.sign,
        "reverse": ar.reverse,
        "inverse": ar.inverse,
        "power": ar.power,
        "signed_power": ar.signed_power,
        "add": ar.add,
        "multiply": ar.multiply,
        "subtract": ar.subtract,
        "max": ar.max_,
        "min": ar.min_,
        "densify": ar.densify,
        "divide": ar.divide,
        # Logical (WQ and/or/not → underscore names in Python)
        "and_": lg.and_,
        "or_": lg.or_,
        "not_": lg.not_,
        "if_else": lg.if_else,
        "is_nan": lg.is_nan,
        "lt": lg.lt,
        "le": lg.le,
        "eq": lg.eq,
        "gt": lg.gt,
        "ge": lg.ge,
        "ne": lg.ne,
        # Time series
        "ts_mean": ts_ops.ts_mean,
        "ts_std_dev": ts_ops.ts_std_dev,
        "ts_std": ts_ops.ts_std,
        "ts_max": ts_ops.ts_max,
        "ts_min": ts_ops.ts_min,
        "ts_delay": ts_ops.ts_delay,
        "delay": ts_ops.delay,
        "ts_delta": ts_ops.ts_delta,
        "ts_sum": ts_ops.ts_sum,
        "ts_product": ts_ops.ts_product,
        "ts_av_diff": ts_ops.ts_av_diff,
        "ts_zscore": ts_ops.ts_zscore,
        "ts_rank": ts_ops.ts_rank,
        "ts_scale": ts_ops.ts_scale,
        "ts_count_nans": ts_ops.ts_count_nans,
        "ts_backfill": ts_ops.ts_backfill,
        "ts_arg_max": ts_ops.ts_arg_max,
        "ts_arg_min": ts_ops.ts_arg_min,
        "ts_decay_linear": ts_ops.ts_decay_linear,
        "ts_corr": ts_ops.ts_corr,
        "ts_covariance": ts_ops.ts_covariance,
        "ts_regression": ts_ops.ts_regression,
        "ts_quantile": ts_ops.ts_quantile,
        "days_from_last_change": ts_ops.days_from_last_change,
        "kth_element": ts_ops.kth_element,
        "last_diff_value": ts_ops.last_diff_value,
        "ts_skew": ts_ops.ts_skew,
        "ts_kurt": ts_ops.ts_kurt,
        "ts_step": ts_ops.ts_step,
        "hump": ts_ops.hump,
        # Cross sectional
        "rank": cs_ops.rank,
        "zscore": cs_ops.zscore,
        "normalize": cs_ops.normalize,
        "quantile": cs_ops.quantile,
        "scale": cs_ops.scale,
        "winsorize": cs_ops.winsorize,
        "neutralize": cs_ops.neutralize,
        # Vector / transformational / group (compile-only + stub execute)
        "vec_avg": vec.vec_avg,
        "vec_sum": vec.vec_sum,
        "bucket": tr.bucket,
        "trade_when": tr.trade_when,
        "group_backfill": gr.group_backfill,
        "group_mean": gr.group_mean,
        "group_neutralize": gr.group_neutralize,
        "group_rank": gr.group_rank,
        "group_scale": gr.group_scale,
        "group_zscore": gr.group_zscore,
        # Cleaning / technical / context (Deep Research 扩展)
        "pasteurize": cl.pasteurize,
        "tail": cl.tail,
        "protected_div": cl.protected_div,
        "protected_log": cl.protected_log,
        "protected_sqrt": cl.protected_sqrt,
        "ts_sma": tc.ts_sma,
        "ts_ema": tc.ts_ema,
        "ts_rsi": tc.ts_rsi,
        "ts_bbands": tc.ts_bbands,
        "ts_trange": tc.ts_trange,
        "ts_atr": tc.ts_atr,
        "ts_natr": tc.ts_natr,
        "ts_donchian": tc.ts_donchian,
        "ts_keltner": tc.ts_keltner,
        "ts_ma_envelope": tc.ts_ma_envelope,
        "ts_macd": tc.ts_macd,
        "ts_cci": tc.ts_cci,
        "ts_stoch": tc.ts_stoch,
        "ts_willr": tc.ts_willr,
        "ts_roc": tc.ts_roc,
        "ts_obv": tc.ts_obv,
        "ts_mfi": tc.ts_mfi,
        "ts_dema": tc.ts_dema,
        "ts_wma": tc.ts_wma,
        "ts_kama": tc.ts_kama,
        "ts_adx": tc.ts_adx,
        "ts_aroon": tc.ts_aroon,
        "ts_ad": tc.ts_ad,
        "ts_adosc": tc.ts_adosc,
        "ts_sar": tc.ts_sar,
        "ts_cmo": tc.ts_cmo,
        "ts_ppo": tc.ts_ppo,
        "ts_apo": tc.ts_apo,
        "ts_ultosc": tc.ts_ultosc,
        "ts_stochrsi": tc.ts_stochrsi,
        "ts_tema": tc.ts_tema,
        "ts_trima": tc.ts_trima,
        "ts_t3": tc.ts_t3,
        "ts_bop": tc.ts_bop,
        "ts_mom": tc.ts_mom,
        "ts_stochf": tc.ts_stochf,
        "ts_trix": tc.ts_trix,
        "ts_adxr": tc.ts_adxr,
        "ts_dx": tc.ts_dx,
        "ts_rocr": tc.ts_rocr,
        "ts_rocr100": tc.ts_rocr100,
        "ts_linearreg_slope": tc.ts_linearreg_slope,
        "ts_linearreg_angle": tc.ts_linearreg_angle,
        "orthogonalize": cx.orthogonalize,
        "change_instrument": cx.change_instrument,
        **_future_stub_allowlist,
    }
