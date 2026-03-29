"""
远期：订单簿 / tick / 高频微观结构及事件掩码占位（需 LOB、逐笔或预聚合特征列）。

**动机**：OFI、VPIN、有效价差等依赖专用数据层；当前仅占位，避免仅用 OHLCV 假算。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr

MICROSTRUCTURE_STUB_OPS: frozenset[str] = frozenset(
    {
        "lob_ofi_stub",
        "micro_mid_return_stub",
        "micro_spread_stub",
        "micro_effective_spread_stub",
        "micro_depth_imbalance_stub",
        "micro_book_slope_stub",
        "micro_quote_update_rate_stub",
        "micro_cancel_trade_ratio_stub",
        "micro_vpin_stub",
        "micro_trade_imbalance_stub",
        "micro_kyle_lambda_stub",
        "micro_amihud_hf_stub",
        "micro_realized_vol_stub",
        "micro_bipower_var_stub",
        "micro_jump_indicator_stub",
        "micro_trade_count_intensity_stub",
        "micro_avg_trade_size_stub",
        "micro_large_trade_ratio_stub",
        "micro_tick_rule_agreement_stub",
        "event_window_mask_stub",
        "universe_reit_stub",
    }
)


@dataclass(frozen=True)
class MicrostructureStub(Expr):
    """微观结构或事件 universe **占位**：``op`` 为 IR 名；执行层未实现。"""

    op: str
    child: Expr

    def __post_init__(self) -> None:
        if self.op not in MICROSTRUCTURE_STUB_OPS:
            raise ValueError(f"unknown microstructure stub op: {self.op!r}")

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
