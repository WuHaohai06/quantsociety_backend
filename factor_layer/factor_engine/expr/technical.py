"""
技术指标类时序算子（重叠研究 / TA-Lib 族）。

优先在运行时使用 TA-Lib（若安装）；否则用 pandas/numpy 退化实现，保证无 TA-Lib 环境可测。
按标的 ``instrument`` 分组后在时间轴上计算，索引仍为 ``(timestamp, instrument)`` MultiIndex。

**动机**：研究报告将 SMA/EMA/布林带/RSI 等列为因子挖掘常用前置滤波；TA-Lib C 实现可降低延迟。

**后续**：已扩展 ATR/唐奇安/Keltner/MACD/CCI/Stochastic/Williams %R/ROC/OBV/MFI、DEMA/WMA/KAMA、
ADX/Aroon/AD/ADOSC/SAR、CMO/PPO/APO/UltOsc/StochRSI、TEMA/TRIMA/T3、
BOP/MOM/STOCHF/TRIX/ADXR/DX/ROCR/线性回归斜率与倾角 等；优先 TA-Lib，缺省走 pandas/numpy 退化。
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Expr


@dataclass(frozen=True)
class TsSma(Expr):
    """简单移动平均 ``SMA(x, d)``。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsEma(Expr):
    """指数移动平均；与 TA-Lib 一致时 ``alpha = 2/(d+1)``（由库实现）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsRsi(Expr):
    """相对强弱指标 RSI（Wilder 平滑，周期 ``d``）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsBbands(Expr):
    """布林带：返回上轨/中轨/下轨之一（由 ``band`` 指定）。

    中轨为 SMA(x,d)；上下轨为中轨 ± nbdev * 滚动标准差。
    """

    child: Expr
    d: int
    nbdev: float = 2.0
    band: str = "middle"

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- 波动 / 真实波幅（需 HLC 三列） ---


@dataclass(frozen=True)
class TsTrange(Expr):
    """单根 bar 真实波幅 TR = max(H-L, |H-PC|, |L-PC|)；``PC`` 为上一根收盘价。"""

    high: Expr
    low: Expr
    close: Expr

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsAtr(Expr):
    """平均真实波幅 ATR：Wilder 平滑 TR，周期 ``d``。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsNatr(Expr):
    """归一化 ATR（NATR），近似百分比尺度。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


# --- 通道 / 包络 ---


@dataclass(frozen=True)
class TsDonchian(Expr):
    """唐奇安通道：``d`` 根内高/低与中轨；``band`` = upper | lower | middle。"""

    high: Expr
    low: Expr
    d: int
    band: str = "middle"

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low)


@dataclass(frozen=True)
class TsKeltner(Expr):
    """Keltner：典型价 EMA 中轨 ± ``mult`` * ATR(``atr_d``)。"""

    high: Expr
    low: Expr
    close: Expr
    d: int
    mult: float = 2.0
    band: str = "middle"
    atr_d: int | None = None

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsMaEnvelope(Expr):
    """均线包络：SMA/EMA 中轨 × (1±pct)；``use_ema`` 为真则用 EMA。"""

    child: Expr
    d: int
    pct: float = 0.025
    band: str = "middle"
    use_ema: bool = False

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- 动量 ---


@dataclass(frozen=True)
class TsMacd(Expr):
    """MACD；``line`` = macd | signal | hist。"""

    child: Expr
    fast: int = 12
    slow: int = 26
    signal: int = 9
    line: str = "macd"

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsCci(Expr):
    """CCI；需 HLC。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsStoch(Expr):
    """随机指标；``line`` = slowk | slowd。"""

    high: Expr
    low: Expr
    close: Expr
    fastk_period: int = 5
    slowk_period: int = 3
    slowd_period: int = 3
    line: str = "slowk"

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsWillr(Expr):
    """Williams %R（动量振荡器）。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsRoc(Expr):
    """变动率 ROC（百分比）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- 成交量 ---


@dataclass(frozen=True)
class TsObv(Expr):
    """OBV：按涨跌累加成交量。"""

    close: Expr
    volume: Expr

    def children(self) -> tuple[Expr, Expr]:
        return (self.close, self.volume)


@dataclass(frozen=True)
class TsMfi(Expr):
    """MFI；需 OHLCV。"""

    high: Expr
    low: Expr
    close: Expr
    volume: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close, self.volume)


# --- Overlap 扩展 ---


@dataclass(frozen=True)
class TsDema(Expr):
    """DEMA。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsWma(Expr):
    """WMA。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsKama(Expr):
    """KAMA 自适应均线。"""

    child: Expr
    d: int
    fast_period: int = 2
    slow_period: int = 30

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- 趋势强度 / 量价 ---


@dataclass(frozen=True)
class TsAdx(Expr):
    """ADX 族：``line`` = adx | plus_di | minus_di（Wilder 体系，需 HLC）。"""

    high: Expr
    low: Expr
    close: Expr
    d: int
    line: str = "adx"

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsAroon(Expr):
    """Aroon：``line`` = up | down | osc（osc = up - down，与 TA-Lib AROONOSC 一致）。"""

    high: Expr
    low: Expr
    d: int
    line: str = "up"

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low)


@dataclass(frozen=True)
class TsAd(Expr):
    """Chaikin A/D 累积线（HLCV）。"""

    high: Expr
    low: Expr
    close: Expr
    volume: Expr

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close, self.volume)


@dataclass(frozen=True)
class TsAdosc(Expr):
    """Chaikin A/D 振荡器：快慢 EMA(AD) 之差（默认 fast=3, slow=10）。"""

    high: Expr
    low: Expr
    close: Expr
    volume: Expr
    fast: int = 3
    slow: int = 10

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close, self.volume)


@dataclass(frozen=True)
class TsSar(Expr):
    """Parabolic SAR（抛物线止损转向）；``acceleration`` / ``maximum`` 为步长与上限。"""

    high: Expr
    low: Expr
    acceleration: float = 0.02
    maximum: float = 0.2

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low)


# --- 动量扩展 ---


@dataclass(frozen=True)
class TsCmo(Expr):
    """Chande Momentum Oscillator，[-100,100]。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsPpo(Expr):
    """PPO：快慢 EMA 百分比差；``line`` = ppo | signal | hist。"""

    child: Expr
    fast: int = 12
    slow: int = 26
    signal: int = 9
    line: str = "ppo"

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsApo(Expr):
    """APO：快慢 EMA 绝对差；``line`` = apo | signal | hist。"""

    child: Expr
    fast: int = 12
    slow: int = 26
    signal: int = 9
    line: str = "apo"

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsUltosc(Expr):
    """Ultimate Oscillator（Larry Williams），三时间窗加权。"""

    high: Expr
    low: Expr
    close: Expr
    timeperiod1: int = 7
    timeperiod2: int = 14
    timeperiod3: int = 28

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsStochrsi(Expr):
    """Stochastic RSI；``line`` = fastk | fastd。"""

    child: Expr
    timeperiod: int = 14
    fastk_period: int = 5
    fastd_period: int = 3
    line: str = "fastk"

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- Overlap 加深 ---


@dataclass(frozen=True)
class TsTema(Expr):
    """Triple EMA：3*e1 - 3*e2 + e3。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsTrima(Expr):
    """Triangular MA（双次 SMA，窗口按 TA-Lib 规则拆分）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsT3(Expr):
    """T3（Tillson）：``vfactor`` 默认 0.7；无 TA-Lib 时用 Tillson 六阶 EMA 系数近似。"""

    child: Expr
    d: int
    vfactor: float = 0.7

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


# --- 第三批：BOP / 动量 / 快随机 / TRIX / DMI 派生 / ROCR / 线性回归 ---


@dataclass(frozen=True)
class TsBop(Expr):
    """Balance of Power：TA-Lib 需 open；本引擎 **用上一根 close 近似 open**（首 bar 用自身 close）。"""

    high: Expr
    low: Expr
    close: Expr

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsMom(Expr):
    """动量 ``close - close.shift(d)``（与 ``ts_roc`` 百分比口径不同）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsStochf(Expr):
    """快速随机；``line`` = fastk | fastd。"""

    high: Expr
    low: Expr
    close: Expr
    fastk_period: int = 5
    fastd_period: int = 3
    line: str = "fastk"

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsTrix(Expr):
    """TRIX：三重 EMA 的一阶变化率（与 TA-Lib 一致）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsAdxr(Expr):
    """ADXR：ADX 的评级平滑（TA-Lib ADXR）。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsDx(Expr):
    """DX：方向运动指数（非 ADX 平滑后值）。"""

    high: Expr
    low: Expr
    close: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.high, self.low, self.close)


@dataclass(frozen=True)
class TsRocr(Expr):
    """变动率比 ``close / close.shift(d)``。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsRocr100(Expr):
    """变动率百分比 ``(close/close.shift(d)-1)*100``。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsLinearregSlope(Expr):
    """滚动线性回归斜率（对 bar 索引回归收盘价）。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)


@dataclass(frozen=True)
class TsLinearregAngle(Expr):
    """滚动线性回归倾角（度）；与 TA-Lib ``LINEARREG_ANGLE`` 对齐。"""

    child: Expr
    d: int

    def children(self) -> tuple[Expr, ...]:
        return (self.child,)
