import pytest

from api.dsl_parser import DSLParseError, parse_expr, parse_factor
from expr.cs import Rank


def test_parse_expr_builds_factor_expression():
    expr = parse_expr('rank(ts_mean(col("close"), 3) - delay(col("close"), 1))')

    assert isinstance(expr, Rank)


def test_parse_expr_rejects_unsafe_names():
    with pytest.raises(DSLParseError):
        parse_expr('__import__("os").system("echo unsafe")')


def test_parse_factor_wraps_expr():
    factor = parse_factor('rank(ts_mean(col("close"), 3))', name='demo')
    assert factor.name == 'demo'


def test_parse_expr_new_operators_v7():
    """DSL 白名单：第 7 版起 group / 清洗 / 技术 / 上下文算子。"""
    parse_expr('group_rank(col("x"), col("g"))')
    parse_expr('pasteurize(col("x"), fill_value=0.0)')
    parse_expr('orthogonalize(col("x"), col("y"))')
    parse_expr('change_instrument(col("ret"), "spy_ret")')
    parse_expr('ts_sma(col("close"), 5)')
    parse_expr('ts_bbands(col("close"), 20, nbdev=2.0, band="upper")')


def test_parse_expr_sin_cos_and_future_stubs():
    parse_expr('sin(col("x"))')
    parse_expr('cos(col("x"))')
    parse_expr('lob_ofi_stub(col("x"))')
    parse_expr('fundamental_ttm_stub(col("x"))')
    parse_expr('fundamental_yoy_stub(col("x"))')
    parse_expr('alt_sentiment_stub(col("x"))')
    parse_expr('alt_esg_score_stub(col("x"))')
    parse_expr('micro_vpin_stub(col("x"))')
    parse_expr('event_window_mask_stub(col("x"))')


def test_parse_expr_technical_expansion():
    parse_expr('ts_atr(col("h"), col("l"), col("c"), 14)')
    parse_expr('neutralize(col("x"), col("y"))')
    parse_expr('ts_macd(col("c"), line="hist")')
    parse_expr('ts_roc(col("c"), 5)')
    parse_expr('ts_adx(col("h"), col("l"), col("c"), 14, line="plus_di")')
    parse_expr('ts_aroon(col("h"), col("low"), 14, line="osc")')
    parse_expr('ts_ad(col("h"), col("l"), col("c"), col("v"))')
    parse_expr('ts_sar(col("h"), col("l"), acceleration=0.02, maximum=0.2)')
    parse_expr('ts_cmo(col("c"), 14)')
    parse_expr('ts_ppo(col("c"), line="signal")')
    parse_expr('ts_ultosc(col("h"), col("l"), col("c"))')
    parse_expr('ts_stochrsi(col("c"), line="fastd")')
    parse_expr('ts_tema(col("c"), 10)')
    parse_expr('ts_t3(col("c"), 5, vfactor=0.7)')
    parse_expr('ts_bop(col("h"), col("l"), col("c"))')
    parse_expr('ts_mom(col("c"), 5)')
    parse_expr('ts_stochf(col("h"), col("l"), col("c"), line="fastd")')
    parse_expr('ts_trix(col("c"), 10)')
    parse_expr('ts_adxr(col("h"), col("l"), col("c"), 14)')
    parse_expr('ts_dx(col("h"), col("l"), col("c"), 14)')
    parse_expr('ts_rocr(col("c"), 5)')
    parse_expr('ts_rocr100(col("c"), 5)')
    parse_expr('ts_linearreg_slope(col("c"), 10)')
    parse_expr('ts_linearreg_angle(col("c"), 10)')
