"""日内 / 分钟序列类算子 API：仅 Expr + IR；执行见 ``STUB_IR_OPS`` 统一 stub。

华泰《GPT 因子工厂 2.0》**图表 11**（高频算子）中 ``Agg_*`` / ``Agg_Explode_*`` / ``Tp_Sample``
等与本引擎蛇形名之对应关系，见各工厂函数 docstring 与 ``expr.intraday.INTRADAY_STUB_OPS``。
"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.intraday import INTRADAY_STUB_OPS, IntradayStub


def _make_stub(name: str):
    htsc = _HTSC_CHART11.get(name, "")

    def _stub(child: Expr) -> Expr:
        return IntradayStub(op=name, child=ensure_expr(child))

    _stub.__name__ = name
    _stub.__doc__ = (
        f"日内序列占位 IR=`{name}`。"
        + (f" 华泰对照：图表11 {htsc}。" if htsc else "")
        + " 需分钟/逐笔数据契约；当前 NotImplementedError。"
    )
    return _stub


# 工厂名 → 研报图表11原文（节选，便于 docstring 溯源）
_HTSC_CHART11: dict[str, str] = {
    "intraday_agg_std_stub": "`Agg_Std`",
    "intraday_agg_var_stub": "`Agg_Var`",
    "intraday_agg_mean_stub": "`Agg_Mean`",
    "intraday_agg_median_stub": "`Agg_Median`",
    "intraday_agg_sum_stub": "`Agg_Sum`",
    "intraday_agg_max_stub": "`Agg_Max`",
    "intraday_agg_min_stub": "`Agg_Min`",
    "intraday_agg_argmax_stub": "`Agg_Argmax`",
    "intraday_agg_argmin_stub": "`Agg_Argmin`",
    "intraday_agg_skew_stub": "`Agg_Skew`",
    "intraday_agg_kurt_stub": "`Agg_Kurt`",
    "intraday_agg_corr_stub": "`Agg_Corr`",
    "intraday_agg_cov_stub": "`Agg_Cov`",
    "intraday_agg_quantile_stub": "`Agg_Quantile`",
    "intraday_explode_return_stub": "`Agg_Explode_Return`",
    "intraday_explode_cumsum_stub": "`Agg_Explode_Cumsum`",
    "intraday_explode_cumprod_stub": "`Agg_Explode_Cumprod`",
    "intraday_explode_cummin_stub": "`Agg_Explode_Cummin`",
    "intraday_explode_cummax_stub": "`Agg_Explode_Cummax`",
    "intraday_explode_ewmmean_stub": "`Agg_Explode_Ewmmean`",
    "intraday_explode_ewmstd_stub": "`Agg_Explode_Ewmstd`",
    "intraday_explode_ewmvar_stub": "`Agg_Explode_Ewmvar`",
    "intraday_explode_rollingmean_stub": "`Agg_Explode_Rollingmean`",
    "intraday_explode_rollingstd_stub": "`Agg_Explode_Rollingstd`",
    "intraday_explode_rollingvar_stub": "`Agg_Explode_Rollingvar`",
    "intraday_explode_rollingskew_stub": "`Agg_Explode_Rollingskew`",
    "intraday_explode_rollingmin_stub": "`Agg_Explode_Rollingmin`",
    "intraday_explode_rollingmax_stub": "`Agg_Explode_Rollingmax`",
    "intraday_explode_rollingsum_stub": "`Agg_Explode_Rollingsum`",
    "intraday_explode_rollingquantile_stub": "`Agg_Explode_Rollingquantile`",
    "intraday_tp_sample_stub": "`Tp_Sample`",
}

for _name in sorted(INTRADAY_STUB_OPS):
    globals()[_name] = _make_stub(_name)
del _name

__all__ = tuple(sorted(INTRADAY_STUB_OPS))
