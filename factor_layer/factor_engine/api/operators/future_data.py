"""远期数据层算子 API：仅 **Expr 构建 + IR**，Pandas 执行统一 ``NotImplementedError``（见 ``STUB_IR_OPS``）。

这些工厂用于在 **没有 LOB / PiT / NLP 管道** 时仍能在 DSL 中出现名字；**不要**当成已有数据就能跑出因子值。
"""

from __future__ import annotations

from expr.alternative import ALTERNATIVE_STUB_OPS, AlternativeStub
from expr.base import Expr, ensure_expr
from expr.fundamental import FUNDAMENTAL_STUB_OPS, FundamentalStub
from expr.microstructure import MICROSTRUCTURE_STUB_OPS, MicrostructureStub

__all__ = tuple(
    sorted(FUNDAMENTAL_STUB_OPS | ALTERNATIVE_STUB_OPS | MICROSTRUCTURE_STUB_OPS)
)


def lob_ofi_stub(child: Expr) -> Expr:
    """订单流失衡（OFI）占位；需 LOB/tick。"""
    return MicrostructureStub(op="lob_ofi_stub", child=ensure_expr(child))


def micro_mid_return_stub(child: Expr) -> Expr:
    """mid 收益占位。"""
    return MicrostructureStub(op="micro_mid_return_stub", child=ensure_expr(child))


def micro_spread_stub(child: Expr) -> Expr:
    """买卖价差占位。"""
    return MicrostructureStub(op="micro_spread_stub", child=ensure_expr(child))


def micro_effective_spread_stub(child: Expr) -> Expr:
    """有效价差占位。"""
    return MicrostructureStub(op="micro_effective_spread_stub", child=ensure_expr(child))


def micro_depth_imbalance_stub(child: Expr) -> Expr:
    """多档深度不平衡占位。"""
    return MicrostructureStub(op="micro_depth_imbalance_stub", child=ensure_expr(child))


def micro_book_slope_stub(child: Expr) -> Expr:
    """订单簿斜率/弹性占位。"""
    return MicrostructureStub(op="micro_book_slope_stub", child=ensure_expr(child))


def micro_quote_update_rate_stub(child: Expr) -> Expr:
    """报价更新频率占位。"""
    return MicrostructureStub(op="micro_quote_update_rate_stub", child=ensure_expr(child))


def micro_cancel_trade_ratio_stub(child: Expr) -> Expr:
    """撤单/成交比占位。"""
    return MicrostructureStub(op="micro_cancel_trade_ratio_stub", child=ensure_expr(child))


def micro_vpin_stub(child: Expr) -> Expr:
    """VPIN 类桶失衡占位。"""
    return MicrostructureStub(op="micro_vpin_stub", child=ensure_expr(child))


def micro_trade_imbalance_stub(child: Expr) -> Expr:
    """主动买卖失衡占位。"""
    return MicrostructureStub(op="micro_trade_imbalance_stub", child=ensure_expr(child))


def micro_kyle_lambda_stub(child: Expr) -> Expr:
    """价格冲击（Kyle λ）占位。"""
    return MicrostructureStub(op="micro_kyle_lambda_stub", child=ensure_expr(child))


def micro_amihud_hf_stub(child: Expr) -> Expr:
    """高频非流动性占位。"""
    return MicrostructureStub(op="micro_amihud_hf_stub", child=ensure_expr(child))


def micro_realized_vol_stub(child: Expr) -> Expr:
    """已实现波动占位。"""
    return MicrostructureStub(op="micro_realized_vol_stub", child=ensure_expr(child))


def micro_bipower_var_stub(child: Expr) -> Expr:
    """双幂变差占位。"""
    return MicrostructureStub(op="micro_bipower_var_stub", child=ensure_expr(child))


def micro_jump_indicator_stub(child: Expr) -> Expr:
    """跳跃统计占位。"""
    return MicrostructureStub(op="micro_jump_indicator_stub", child=ensure_expr(child))


def micro_trade_count_intensity_stub(child: Expr) -> Expr:
    """成交笔数强度占位。"""
    return MicrostructureStub(op="micro_trade_count_intensity_stub", child=ensure_expr(child))


def micro_avg_trade_size_stub(child: Expr) -> Expr:
    """均笔规模占位。"""
    return MicrostructureStub(op="micro_avg_trade_size_stub", child=ensure_expr(child))


def micro_large_trade_ratio_stub(child: Expr) -> Expr:
    """大单占比占位。"""
    return MicrostructureStub(op="micro_large_trade_ratio_stub", child=ensure_expr(child))


def micro_tick_rule_agreement_stub(child: Expr) -> Expr:
    """tick rule 与报价方向一致性占位。"""
    return MicrostructureStub(op="micro_tick_rule_agreement_stub", child=ensure_expr(child))


def event_window_mask_stub(child: Expr) -> Expr:
    """事件窗 dummy 占位（并购、拆股等）。"""
    return MicrostructureStub(op="event_window_mask_stub", child=ensure_expr(child))


def universe_reit_stub(child: Expr) -> Expr:
    """板块/universe 掩码示例占位。"""
    return MicrostructureStub(op="universe_reit_stub", child=ensure_expr(child))


def fundamental_ttm_stub(child: Expr) -> Expr:
    """TTM 等占位；需披露日与 asof。"""
    return FundamentalStub(op="fundamental_ttm_stub", child=ensure_expr(child))


def fundamental_yoy_stub(child: Expr) -> Expr:
    """同比占位。"""
    return FundamentalStub(op="fundamental_yoy_stub", child=ensure_expr(child))


def fundamental_qoq_stub(child: Expr) -> Expr:
    """环比占位。"""
    return FundamentalStub(op="fundamental_qoq_stub", child=ensure_expr(child))


def fundamental_cagr_stub(child: Expr) -> Expr:
    """复合增长占位。"""
    return FundamentalStub(op="fundamental_cagr_stub", child=ensure_expr(child))


def fundamental_lag_quarter_stub(child: Expr) -> Expr:
    """滞后 N 季占位（滞后阶数由数据层或后续 attrs 扩展约定）。"""
    return FundamentalStub(op="fundamental_lag_quarter_stub", child=ensure_expr(child))


def days_since_filing_stub(child: Expr) -> Expr:
    """距最近公告日 bar 数占位。"""
    return FundamentalStub(op="days_since_filing_stub", child=ensure_expr(child))


def days_since_forecast_stub(child: Expr) -> Expr:
    """距指引/预告占位。"""
    return FundamentalStub(op="days_since_forecast_stub", child=ensure_expr(child))


def fundamental_revision_stub(child: Expr) -> Expr:
    """一致预期修订占位。"""
    return FundamentalStub(op="fundamental_revision_stub", child=ensure_expr(child))


def fundamental_surprise_stub(child: Expr) -> Expr:
    """盈利惊喜占位。"""
    return FundamentalStub(op="fundamental_surprise_stub", child=ensure_expr(child))


def fundamental_report_delay_stub(child: Expr) -> Expr:
    """披露滞后占位。"""
    return FundamentalStub(op="fundamental_report_delay_stub", child=ensure_expr(child))


def fundamental_accruals_stub(child: Expr) -> Expr:
    """应计/盈利质量占位。"""
    return FundamentalStub(op="fundamental_accruals_stub", child=ensure_expr(child))


def fundamental_cf_accruals_stub(child: Expr) -> Expr:
    """现金流应计占位。"""
    return FundamentalStub(op="fundamental_cf_accruals_stub", child=ensure_expr(child))


def fundamental_asset_growth_stub(child: Expr) -> Expr:
    """资产增长占位。"""
    return FundamentalStub(op="fundamental_asset_growth_stub", child=ensure_expr(child))


def fundamental_inv_growth_stub(child: Expr) -> Expr:
    """存货增长异常占位。"""
    return FundamentalStub(op="fundamental_inv_growth_stub", child=ensure_expr(child))


def fundamental_rec_growth_stub(child: Expr) -> Expr:
    """应收增长占位。"""
    return FundamentalStub(op="fundamental_rec_growth_stub", child=ensure_expr(child))


def fundamental_no_stub(child: Expr) -> Expr:
    """净发行/净举债类组合信号占位（文献变体多，输入多为预计算列）。"""
    return FundamentalStub(op="fundamental_no_stub", child=ensure_expr(child))


def fundamental_payout_stub(child: Expr) -> Expr:
    """分红+回购强度占位。"""
    return FundamentalStub(op="fundamental_payout_stub", child=ensure_expr(child))


def fundamental_rnd_intensity_stub(child: Expr) -> Expr:
    """研发强度占位。"""
    return FundamentalStub(op="fundamental_rnd_intensity_stub", child=ensure_expr(child))


def fundamental_goodwill_ratio_stub(child: Expr) -> Expr:
    """商誉占比占位。"""
    return FundamentalStub(op="fundamental_goodwill_ratio_stub", child=ensure_expr(child))


def fundamental_tax_rate_stub(child: Expr) -> Expr:
    """有效税率占位。"""
    return FundamentalStub(op="fundamental_tax_rate_stub", child=ensure_expr(child))


def fundamental_roe_stub(child: Expr) -> Expr:
    """ROE 占位。"""
    return FundamentalStub(op="fundamental_roe_stub", child=ensure_expr(child))


def fundamental_roa_stub(child: Expr) -> Expr:
    """ROA 占位。"""
    return FundamentalStub(op="fundamental_roa_stub", child=ensure_expr(child))


def fundamental_gross_margin_stub(child: Expr) -> Expr:
    """毛利率占位。"""
    return FundamentalStub(op="fundamental_gross_margin_stub", child=ensure_expr(child))


def fundamental_oper_margin_stub(child: Expr) -> Expr:
    """营业利润率占位。"""
    return FundamentalStub(op="fundamental_oper_margin_stub", child=ensure_expr(child))


def fundamental_net_margin_stub(child: Expr) -> Expr:
    """净利率占位。"""
    return FundamentalStub(op="fundamental_net_margin_stub", child=ensure_expr(child))


def fundamental_leverage_stub(child: Expr) -> Expr:
    """杠杆占位。"""
    return FundamentalStub(op="fundamental_leverage_stub", child=ensure_expr(child))


def fundamental_current_ratio_stub(child: Expr) -> Expr:
    """流动比率占位。"""
    return FundamentalStub(op="fundamental_current_ratio_stub", child=ensure_expr(child))


def fundamental_quick_ratio_stub(child: Expr) -> Expr:
    """速动比率占位。"""
    return FundamentalStub(op="fundamental_quick_ratio_stub", child=ensure_expr(child))


def fundamental_interest_coverage_stub(child: Expr) -> Expr:
    """利息保障占位。"""
    return FundamentalStub(op="fundamental_interest_coverage_stub", child=ensure_expr(child))


def fundamental_altman_z_stub(child: Expr) -> Expr:
    """Altman Z-score 简化占位。"""
    return FundamentalStub(op="fundamental_altman_z_stub", child=ensure_expr(child))


def analyst_dispersion_stub(child: Expr) -> Expr:
    """分析师预测分歧占位。"""
    return FundamentalStub(op="analyst_dispersion_stub", child=ensure_expr(child))


def analyst_revision_30d_stub(child: Expr) -> Expr:
    """30 日评级/目标价修正占位。"""
    return FundamentalStub(op="analyst_revision_30d_stub", child=ensure_expr(child))


def insider_net_buy_stub(child: Expr) -> Expr:
    """内部人净买入占位。"""
    return FundamentalStub(op="insider_net_buy_stub", child=ensure_expr(child))


def institutional_ownership_chg_stub(child: Expr) -> Expr:
    """机构持仓变化占位。"""
    return FundamentalStub(op="institutional_ownership_chg_stub", child=ensure_expr(child))


def alt_sentiment_stub(child: Expr) -> Expr:
    """另类情绪得分占位。"""
    return AlternativeStub(op="alt_sentiment_stub", child=ensure_expr(child))


def alt_sentiment_ema_stub(child: Expr) -> Expr:
    """情绪 EWM 占位。"""
    return AlternativeStub(op="alt_sentiment_ema_stub", child=ensure_expr(child))


def alt_sentiment_delta_stub(child: Expr) -> Expr:
    """情绪一期变化占位。"""
    return AlternativeStub(op="alt_sentiment_delta_stub", child=ensure_expr(child))


def alt_sentiment_vol_stub(child: Expr) -> Expr:
    """情绪横截面分歧占位。"""
    return AlternativeStub(op="alt_sentiment_vol_stub", child=ensure_expr(child))


def alt_news_volume_stub(child: Expr) -> Expr:
    """新闻条数/热度占位。"""
    return AlternativeStub(op="alt_news_volume_stub", child=ensure_expr(child))


def alt_news_sentiment_x_volume_stub(child: Expr) -> Expr:
    """条数加权情绪占位。"""
    return AlternativeStub(op="alt_news_sentiment_x_volume_stub", child=ensure_expr(child))


def alt_earnings_call_tone_stub(child: Expr) -> Expr:
    """业绩会语气占位。"""
    return AlternativeStub(op="alt_earnings_call_tone_stub", child=ensure_expr(child))


def alt_8k_item_stub(child: Expr) -> Expr:
    """8-K 重大事件占位。"""
    return AlternativeStub(op="alt_8k_item_stub", child=ensure_expr(child))


def alt_litigation_stub(child: Expr) -> Expr:
    """诉讼/处罚占位。"""
    return AlternativeStub(op="alt_litigation_stub", child=ensure_expr(child))


def alt_esg_score_stub(child: Expr) -> Expr:
    """ESG 综合分占位。"""
    return AlternativeStub(op="alt_esg_score_stub", child=ensure_expr(child))


def alt_esg_controversy_stub(child: Expr) -> Expr:
    """ESG 争议占位。"""
    return AlternativeStub(op="alt_esg_controversy_stub", child=ensure_expr(child))


def alt_carbon_intensity_stub(child: Expr) -> Expr:
    """碳强度占位。"""
    return AlternativeStub(op="alt_carbon_intensity_stub", child=ensure_expr(child))


def alt_supply_chain_exposure_stub(child: Expr) -> Expr:
    """供应链暴露占位。"""
    return AlternativeStub(op="alt_supply_chain_exposure_stub", child=ensure_expr(child))


def alt_customer_concentration_stub(child: Expr) -> Expr:
    """客户集中度占位。"""
    return AlternativeStub(op="alt_customer_concentration_stub", child=ensure_expr(child))


def alt_patent_citation_stub(child: Expr) -> Expr:
    """专利被引占位。"""
    return AlternativeStub(op="alt_patent_citation_stub", child=ensure_expr(child))


def alt_web_traffic_stub(child: Expr) -> Expr:
    """网页/App 流量占位。"""
    return AlternativeStub(op="alt_web_traffic_stub", child=ensure_expr(child))


def alt_job_posting_stub(child: Expr) -> Expr:
    """招聘量占位。"""
    return AlternativeStub(op="alt_job_posting_stub", child=ensure_expr(child))


def alt_credit_spread_stub(child: Expr) -> Expr:
    """信用利差占位。"""
    return AlternativeStub(op="alt_credit_spread_stub", child=ensure_expr(child))


def alt_satellite_activity_stub(child: Expr) -> Expr:
    """卫星/夜光类占位。"""
    return AlternativeStub(op="alt_satellite_activity_stub", child=ensure_expr(child))


def alt_app_rating_stub(child: Expr) -> Expr:
    """App 评分/评论量占位。"""
    return AlternativeStub(op="alt_app_rating_stub", child=ensure_expr(child))


def alt_social_buzz_stub(child: Expr) -> Expr:
    """社媒提及占位。"""
    return AlternativeStub(op="alt_social_buzz_stub", child=ensure_expr(child))
