"""
远期：另类数据 / NLP / ESG / 网络与宏观代理算子占位（需文本、第三方序列或图特征落表）。

**动机**：情绪、新闻量、ESG、供应链等依赖预处理管道；当前仅占位接口，与 ``AlternativeStub.op`` 区分语义。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr

ALTERNATIVE_STUB_OPS: frozenset[str] = frozenset(
    {
        "alt_sentiment_stub",
        "alt_sentiment_ema_stub",
        "alt_sentiment_delta_stub",
        "alt_sentiment_vol_stub",
        "alt_news_volume_stub",
        "alt_news_sentiment_x_volume_stub",
        "alt_earnings_call_tone_stub",
        "alt_8k_item_stub",
        "alt_litigation_stub",
        "alt_esg_score_stub",
        "alt_esg_controversy_stub",
        "alt_carbon_intensity_stub",
        "alt_supply_chain_exposure_stub",
        "alt_customer_concentration_stub",
        "alt_patent_citation_stub",
        "alt_web_traffic_stub",
        "alt_job_posting_stub",
        "alt_credit_spread_stub",
        "alt_satellite_activity_stub",
        "alt_app_rating_stub",
        "alt_social_buzz_stub",
    }
)


@dataclass(frozen=True)
class AlternativeStub(Expr):
    """另类数据 **占位**：``op`` 为 IR 名；需 NLP/第三方/事件表，执行层未实现。"""

    op: str
    child: Expr

    def __post_init__(self) -> None:
        if self.op not in ALTERNATIVE_STUB_OPS:
            raise ValueError(f"unknown alternative stub op: {self.op!r}")

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
