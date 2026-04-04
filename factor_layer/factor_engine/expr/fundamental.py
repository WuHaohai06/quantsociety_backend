"""
远期：基本面 / PiT / 分析师与持仓类算子占位（需双时态财报、事件表或第三方面板 asof join）。

**动机**：TTM、YoY、披露滞后、应计、杠杆等必须与 **可得日** 对齐；当前仅占位，防止前视偏差假实现。
所有具体算子共用 ``FundamentalStub``，以 ``op`` 区分 IR 名；工厂见 ``api.operators.future_data``。

华泰《GPT 因子工厂 2.0》图表 9 中 ``YOY`` / ``QOQ`` 等为矩阵语境；本处为 PiT/财报管线 **stub**，
与 ``fundamental_yoy_stub`` / ``fundamental_qoq_stub`` 对应，见 ``api/operators/future_data`` docstring
与 ``docs/huatai_factor_factory_operator_catalog.md``。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr

# IR 算子名全集（与 api.operator_registry.STUB_IR_OPS 中基本面相关子集一致）
FUNDAMENTAL_STUB_OPS: frozenset[str] = frozenset(
    {
        "fundamental_ttm_stub",
        "fundamental_yoy_stub",
        "fundamental_qoq_stub",
        "fundamental_cagr_stub",
        "fundamental_lag_quarter_stub",
        "days_since_filing_stub",
        "days_since_forecast_stub",
        "fundamental_revision_stub",
        "fundamental_surprise_stub",
        "fundamental_report_delay_stub",
        "fundamental_accruals_stub",
        "fundamental_cf_accruals_stub",
        "fundamental_asset_growth_stub",
        "fundamental_inv_growth_stub",
        "fundamental_rec_growth_stub",
        "fundamental_no_stub",
        "fundamental_payout_stub",
        "fundamental_rnd_intensity_stub",
        "fundamental_goodwill_ratio_stub",
        "fundamental_tax_rate_stub",
        "fundamental_roe_stub",
        "fundamental_roa_stub",
        "fundamental_gross_margin_stub",
        "fundamental_oper_margin_stub",
        "fundamental_net_margin_stub",
        "fundamental_leverage_stub",
        "fundamental_current_ratio_stub",
        "fundamental_quick_ratio_stub",
        "fundamental_interest_coverage_stub",
        "fundamental_altman_z_stub",
        "analyst_dispersion_stub",
        "analyst_revision_30d_stub",
        "insider_net_buy_stub",
        "institutional_ownership_chg_stub",
    }
)


@dataclass(frozen=True)
class FundamentalStub(Expr):
    """单 child 的基本面 / 事件 / 分析师类 **占位**：``op`` 为 DSL/IR 名，执行层走 ``NotImplementedError``。

    ``child`` 通常为已 PiT 对齐或预处理后的单列引用；多字段比率类建议在数据层预计算为单列后再传入。
    各 ``op`` 的数据契约见 ``docs/operators_semantics.md`` 远期表。
    """

    op: str
    child: Expr

    def __post_init__(self) -> None:
        if self.op not in FUNDAMENTAL_STUB_OPS:
            raise ValueError(f"unknown fundamental stub op: {self.op!r}")

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
