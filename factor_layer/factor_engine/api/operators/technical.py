"""技术指标算子 API（可选 TA-Lib；HLC 类需数据源含 high/low/close）。"""

from __future__ import annotations

from expr.base import Expr, ensure_expr
from expr.technical import (
    TsAd,
    TsAdosc,
    TsAdxr,
    TsAdx,
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


def ts_sma(child: Expr, d: int) -> Expr:
    return TsSma(child=ensure_expr(child), d=int(d))


def ts_ema(child: Expr, d: int) -> Expr:
    return TsEma(child=ensure_expr(child), d=int(d))


def ts_rsi(child: Expr, d: int) -> Expr:
    return TsRsi(child=ensure_expr(child), d=int(d))


def ts_bbands(
    child: Expr, d: int, nbdev: float = 2.0, band: str = "middle"
) -> Expr:
    return TsBbands(
        child=ensure_expr(child),
        d=int(d),
        nbdev=float(nbdev),
        band=str(band),
    )


def ts_trange(high: Expr, low: Expr, close: Expr) -> Expr:
    """单 bar 真实波幅 TR；需 HLC。"""
    return TsTrange(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
    )


def ts_atr(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    """ATR(HLC, d)；Wilder 平滑。"""
    return TsAtr(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_natr(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    """归一化 ATR。"""
    return TsNatr(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_donchian(high: Expr, low: Expr, d: int, band: str = "middle") -> Expr:
    """唐奇安通道；``band`` = upper | lower | middle。"""
    return TsDonchian(
        high=ensure_expr(high),
        low=ensure_expr(low),
        d=int(d),
        band=str(band),
    )


def ts_keltner(
    high: Expr,
    low: Expr,
    close: Expr,
    d: int,
    mult: float = 2.0,
    band: str = "middle",
    atr_d: int | None = None,
) -> Expr:
    """Keltner 通道；``atr_d`` 默认与 ``d`` 相同。"""
    return TsKeltner(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
        mult=float(mult),
        band=str(band),
        atr_d=atr_d,
    )


def ts_ma_envelope(
    child: Expr,
    d: int,
    pct: float = 0.025,
    band: str = "middle",
    use_ema: bool = False,
) -> Expr:
    """均线百分比包络；``use_ema`` 为真则用 EMA 中轨。"""
    return TsMaEnvelope(
        child=ensure_expr(child),
        d=int(d),
        pct=float(pct),
        band=str(band),
        use_ema=bool(use_ema),
    )


def ts_macd(
    child: Expr,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    line: str = "macd",
) -> Expr:
    """MACD；``line`` = macd | signal | hist。"""
    return TsMacd(
        child=ensure_expr(child),
        fast=int(fast),
        slow=int(slow),
        signal=int(signal),
        line=str(line),
    )


def ts_cci(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    return TsCci(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_stoch(
    high: Expr,
    low: Expr,
    close: Expr,
    fastk_period: int = 5,
    slowk_period: int = 3,
    slowd_period: int = 3,
    line: str = "slowk",
) -> Expr:
    """随机指标；``line`` = slowk | slowd。"""
    return TsStoch(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        fastk_period=int(fastk_period),
        slowk_period=int(slowk_period),
        slowd_period=int(slowd_period),
        line=str(line),
    )


def ts_willr(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    return TsWillr(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_roc(child: Expr, d: int) -> Expr:
    return TsRoc(child=ensure_expr(child), d=int(d))


def ts_obv(close: Expr, volume: Expr) -> Expr:
    return TsObv(close=ensure_expr(close), volume=ensure_expr(volume))


def ts_mfi(high: Expr, low: Expr, close: Expr, volume: Expr, d: int) -> Expr:
    return TsMfi(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        volume=ensure_expr(volume),
        d=int(d),
    )


def ts_dema(child: Expr, d: int) -> Expr:
    return TsDema(child=ensure_expr(child), d=int(d))


def ts_wma(child: Expr, d: int) -> Expr:
    return TsWma(child=ensure_expr(child), d=int(d))


def ts_kama(
    child: Expr, d: int, fast_period: int = 2, slow_period: int = 30
) -> Expr:
    return TsKama(
        child=ensure_expr(child),
        d=int(d),
        fast_period=int(fast_period),
        slow_period=int(slow_period),
    )


def ts_adx(
    high: Expr,
    low: Expr,
    close: Expr,
    d: int,
    line: str = "adx",
) -> Expr:
    return TsAdx(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
        line=str(line),
    )


def ts_aroon(high: Expr, low: Expr, d: int, line: str = "up") -> Expr:
    return TsAroon(
        high=ensure_expr(high),
        low=ensure_expr(low),
        d=int(d),
        line=str(line),
    )


def ts_ad(high: Expr, low: Expr, close: Expr, volume: Expr) -> Expr:
    return TsAd(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        volume=ensure_expr(volume),
    )


def ts_adosc(
    high: Expr,
    low: Expr,
    close: Expr,
    volume: Expr,
    fast: int = 3,
    slow: int = 10,
) -> Expr:
    return TsAdosc(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        volume=ensure_expr(volume),
        fast=int(fast),
        slow=int(slow),
    )


def ts_sar(
    high: Expr,
    low: Expr,
    acceleration: float = 0.02,
    maximum: float = 0.2,
) -> Expr:
    return TsSar(
        high=ensure_expr(high),
        low=ensure_expr(low),
        acceleration=float(acceleration),
        maximum=float(maximum),
    )


def ts_cmo(child: Expr, d: int) -> Expr:
    return TsCmo(child=ensure_expr(child), d=int(d))


def ts_ppo(
    child: Expr,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    line: str = "ppo",
) -> Expr:
    return TsPpo(
        child=ensure_expr(child),
        fast=int(fast),
        slow=int(slow),
        signal=int(signal),
        line=str(line),
    )


def ts_apo(
    child: Expr,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    line: str = "apo",
) -> Expr:
    return TsApo(
        child=ensure_expr(child),
        fast=int(fast),
        slow=int(slow),
        signal=int(signal),
        line=str(line),
    )


def ts_ultosc(
    high: Expr,
    low: Expr,
    close: Expr,
    timeperiod1: int = 7,
    timeperiod2: int = 14,
    timeperiod3: int = 28,
) -> Expr:
    return TsUltosc(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        timeperiod1=int(timeperiod1),
        timeperiod2=int(timeperiod2),
        timeperiod3=int(timeperiod3),
    )


def ts_stochrsi(
    child: Expr,
    timeperiod: int = 14,
    fastk_period: int = 5,
    fastd_period: int = 3,
    line: str = "fastk",
) -> Expr:
    return TsStochrsi(
        child=ensure_expr(child),
        timeperiod=int(timeperiod),
        fastk_period=int(fastk_period),
        fastd_period=int(fastd_period),
        line=str(line),
    )


def ts_tema(child: Expr, d: int) -> Expr:
    return TsTema(child=ensure_expr(child), d=int(d))


def ts_trima(child: Expr, d: int) -> Expr:
    return TsTrima(child=ensure_expr(child), d=int(d))


def ts_t3(child: Expr, d: int, vfactor: float = 0.7) -> Expr:
    return TsT3(
        child=ensure_expr(child), d=int(d), vfactor=float(vfactor)
    )


def ts_bop(high: Expr, low: Expr, close: Expr) -> Expr:
    return TsBop(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
    )


def ts_mom(child: Expr, d: int) -> Expr:
    return TsMom(child=ensure_expr(child), d=int(d))


def ts_stochf(
    high: Expr,
    low: Expr,
    close: Expr,
    fastk_period: int = 5,
    fastd_period: int = 3,
    line: str = "fastk",
) -> Expr:
    return TsStochf(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        fastk_period=int(fastk_period),
        fastd_period=int(fastd_period),
        line=str(line),
    )


def ts_trix(child: Expr, d: int) -> Expr:
    return TsTrix(child=ensure_expr(child), d=int(d))


def ts_adxr(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    return TsAdxr(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_dx(high: Expr, low: Expr, close: Expr, d: int) -> Expr:
    return TsDx(
        high=ensure_expr(high),
        low=ensure_expr(low),
        close=ensure_expr(close),
        d=int(d),
    )


def ts_rocr(child: Expr, d: int) -> Expr:
    return TsRocr(child=ensure_expr(child), d=int(d))


def ts_rocr100(child: Expr, d: int) -> Expr:
    return TsRocr100(child=ensure_expr(child), d=int(d))


def ts_linearreg_slope(child: Expr, d: int) -> Expr:
    return TsLinearregSlope(child=ensure_expr(child), d=int(d))


def ts_linearreg_angle(child: Expr, d: int) -> Expr:
    return TsLinearregAngle(child=ensure_expr(child), d=int(d))
