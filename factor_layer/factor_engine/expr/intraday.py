"""
分钟 / 成交子序列上的聚合与展开占位（华泰《GPT 因子工厂 2.0》图表 11 类语义）。

与 ``expr.microstructure`` 的区分：**微观结构**侧重 LOB/tick/事件掩码；**本模块**侧重
**日内序列上 Agg / Agg_Explode / 时点采样** 等，需分钟 OHLCV 或逐笔管线对齐后再实现数值核。
当前仅占位，Pandas 执行 ``NotImplementedError``（见 ``INTRADAY_STUB_OPS`` ⊆ ``STUB_IR_OPS``）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr

# IR 名全集；与 api.operator_registry.STUB_IR_OPS 中 intraday 子集一致
INTRADAY_STUB_OPS: frozenset[str] = frozenset(
    {
        # 聚合算子（研报 Agg_*）
        "intraday_agg_std_stub",
        "intraday_agg_var_stub",
        "intraday_agg_mean_stub",
        "intraday_agg_median_stub",
        "intraday_agg_sum_stub",
        "intraday_agg_max_stub",
        "intraday_agg_min_stub",
        "intraday_agg_argmax_stub",
        "intraday_agg_argmin_stub",
        "intraday_agg_skew_stub",
        "intraday_agg_kurt_stub",
        "intraday_agg_corr_stub",
        "intraday_agg_cov_stub",
        "intraday_agg_quantile_stub",
        # 聚合展开（研报 Agg_Explode_*）
        "intraday_explode_return_stub",
        "intraday_explode_cumsum_stub",
        "intraday_explode_cumprod_stub",
        "intraday_explode_cummin_stub",
        "intraday_explode_cummax_stub",
        "intraday_explode_ewmmean_stub",
        "intraday_explode_ewmstd_stub",
        "intraday_explode_ewmvar_stub",
        "intraday_explode_rollingmean_stub",
        "intraday_explode_rollingstd_stub",
        "intraday_explode_rollingvar_stub",
        "intraday_explode_rollingskew_stub",
        "intraday_explode_rollingmin_stub",
        "intraday_explode_rollingmax_stub",
        "intraday_explode_rollingsum_stub",
        "intraday_explode_rollingquantile_stub",
        # 采样
        "intraday_tp_sample_stub",
    }
)


@dataclass(frozen=True)
class IntradayStub(Expr):
    """分钟/日内序列类 **占位**：``op`` 为 DSL/IR 名；需专用 schema 后再实装。"""

    op: str
    child: Expr

    def __post_init__(self) -> None:
        if self.op not in INTRADAY_STUB_OPS:
            raise ValueError(f"unknown intraday stub op: {self.op!r}")

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
