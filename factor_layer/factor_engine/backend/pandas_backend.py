"""Pandas 执行后端：按 ``PlanNode.op`` 分派 kernel，递归求值整棵计划树。

数据形态：中间结果一般为 ``(timestamp, instrument)`` MultiIndex 的 ``Series``。
- **时序**：``groupby(instrument)`` + ``rolling`` / ``shift``
- **截面**：``groupby(timestamp)`` + ``rank`` / ``transform``
"""

from __future__ import annotations

import os
from typing import Any, Callable, Literal

import numpy as np

from .pandas_compat import pd

from api.operator_registry import STUB_IR_OPS

from planner.logical_plan import PlanNode
from planner.plan_hash import plan_cache_key

from .base import Backend
from .context import ExecutionContext
from .kernels import KernelRegistry


def _ts_d(node: PlanNode) -> int:
    """从节点属性取窗口长度：优先 ``d``，兼容旧字段 ``window``。"""
    return int(node.attrs.get("d", node.attrs.get("window", 0)))


def _talib_mod():
    """可选 TA-Lib C 库；未安装时返回 None，由 pandas/numpy 退化实现。"""
    try:
        import talib  # type: ignore

        return talib
    except ImportError:
        return None


def _wilder_tr_arr(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """1D 真实波幅 TR；``close`` 与 H/L 等长。"""
    n = len(close)
    tr = np.full(n, np.nan, dtype=float)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    pc = np.empty(n, dtype=float)
    pc[0] = close[0]
    pc[1:] = close[:-1]
    hl = high - low
    hpc = np.abs(high - pc)
    lpc = np.abs(low - pc)
    tr[1:] = np.maximum.reduce([hl[1:], hpc[1:], lpc[1:]])
    return tr


def _wilder_atr_arr(high: np.ndarray, low: np.ndarray, close: np.ndarray, d: int) -> np.ndarray:
    """1D Wilder ATR，与 TA-Lib 常见定义一致。"""
    tr = _wilder_tr_arr(high, low, close)
    n = len(tr)
    out = np.full(n, np.nan, dtype=float)
    if d < 1 or n < d:
        return out
    out[d - 1] = np.nanmean(tr[:d])
    for i in range(d, n):
        if np.isfinite(tr[i]) and np.isfinite(out[i - 1]):
            out[i] = (out[i - 1] * (d - 1) + tr[i]) / d
        else:
            out[i] = np.nan
    return out


def _eval_hlc_series(
    h: pd.Series,
    l: pd.Series,
    c: pd.Series,
    ctx: ExecutionContext,
    talib_triple: Callable[..., Any] | None,
    pandas_fn: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
) -> pd.Series:
    """按 instrument 对齐 HLC，优先 TA-Lib 三参函数，否则 ``pandas_fn(h_arr,l_arr,c_arr)``。"""
    ta = _talib_mod()
    inst = ctx.instrument_col
    tcol = ctx.timestamp_col

    def _one_instr(grp_h: pd.Series) -> pd.Series:
        hh = grp_h.sort_index(level=tcol).astype(float)
        ll = l.reindex(hh.index).astype(float)
        cc = c.reindex(hh.index).astype(float)
        arrh = hh.to_numpy(dtype=float)
        arrl = ll.to_numpy(dtype=float)
        arrc = cc.to_numpy(dtype=float)
        if ta is not None and talib_triple is not None:
            res = np.asarray(talib_triple(arrh, arrl, arrc), dtype=float)
        else:
            res = pandas_fn(arrh, arrl, arrc)
        return pd.Series(res, index=hh.index)

    out = h.groupby(level=inst, group_keys=False).apply(_one_instr)
    return out.reindex(h.index)


def _dmi_wilder_di_dx(
    arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray, d: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wilder 平滑后的 +DI、-DI、DX。"""
    n = len(arrc)
    nan3 = (
        np.full(n, np.nan, dtype=float),
        np.full(n, np.nan, dtype=float),
        np.full(n, np.nan, dtype=float),
    )
    if d < 1 or n < d + 1:
        return nan3
    tr = _wilder_tr_arr(arrh, arrl, arrc)
    pdm = np.zeros(n, dtype=float)
    mdm = np.zeros(n, dtype=float)
    for i in range(1, n):
        up = arrh[i] - arrh[i - 1]
        dn = arrl[i - 1] - arrl[i]
        if up > dn and up > 0:
            pdm[i] = up
        if dn > up and dn > 0:
            mdm[i] = dn
    tr_s = np.full(n, np.nan, dtype=float)
    ps = np.full(n, np.nan, dtype=float)
    ms = np.full(n, np.nan, dtype=float)
    tr_s[d - 1] = np.nanmean(tr[:d])
    ps[d - 1] = np.nanmean(pdm[:d])
    ms[d - 1] = np.nanmean(mdm[:d])
    for i in range(d, n):
        tr_s[i] = (tr_s[i - 1] * (d - 1) + tr[i]) / d
        ps[i] = (ps[i - 1] * (d - 1) + pdm[i]) / d
        ms[i] = (ms[i - 1] * (d - 1) + mdm[i]) / d
    plus_di = np.where(tr_s > 1e-12, 100.0 * ps / tr_s, np.nan)
    minus_di = np.where(tr_s > 1e-12, 100.0 * ms / tr_s, np.nan)
    den = plus_di + minus_di
    dx = np.where(den > 1e-12, 100.0 * np.abs(plus_di - minus_di) / den, np.nan)
    return plus_di, minus_di, dx


def _numpy_adx_line(
    arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray, d: int, line: str
) -> np.ndarray:
    """Wilder 风格 DMI/ADX 退化，与 TA-Lib 近似对齐。"""
    n = len(arrc)
    out = np.full(n, np.nan, dtype=float)
    if d < 1 or n < d + 1:
        return out
    plus_di, minus_di, dx = _dmi_wilder_di_dx(arrh, arrl, arrc, d)
    ln = line.lower()
    if ln == "plus_di":
        return plus_di
    if ln == "minus_di":
        return minus_di
    adx = np.full(n, np.nan, dtype=float)
    start = 2 * d - 2
    if start < n:
        adx[start] = np.nanmean(dx[d - 1 : start + 1])
        for i in range(start + 1, n):
            if np.isfinite(dx[i]) and np.isfinite(adx[i - 1]):
                adx[i] = (adx[i - 1] * (d - 1) + dx[i]) / d
    return adx


def _numpy_adxr(arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray, d: int) -> np.ndarray:
    """ADXR ≈ (ADX + ADX.shift(d)) / 2（退化路径）。"""
    adx = _numpy_adx_line(arrh, arrl, arrc, d, "adx")
    n = len(adx)
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        if i >= d and np.isfinite(adx[i]) and np.isfinite(adx[i - d]):
            out[i] = (adx[i] + adx[i - d]) / 2.0
    return out


def _numpy_rolling_linreg_slope(arr: np.ndarray, d: int) -> np.ndarray:
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    if d < 2:
        return out
    x = np.arange(d, dtype=float)
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom < 1e-18:
        return out
    for i in range(d - 1, n):
        yy = arr[i - d + 1 : i + 1]
        if not np.all(np.isfinite(yy)):
            continue
        yc = yy - yy.mean()
        out[i] = float(np.dot(x, yc) / denom)
    return out


def _numpy_rolling_linreg_angle(arr: np.ndarray, d: int) -> np.ndarray:
    slope = _numpy_rolling_linreg_slope(arr, d)
    return np.degrees(np.arctan(slope))


def _numpy_aroon(arrh: np.ndarray, arrl: np.ndarray, d: int, line: str) -> np.ndarray:
    """Aroon Up/Down：``periods_since_extreme = (d-1) - idx``；输出 0–100。"""
    n = len(arrh)
    up = np.full(n, np.nan, dtype=float)
    dn = np.full(n, np.nan, dtype=float)
    for i in range(d - 1, n):
        w = slice(i - d + 1, i + 1)
        hh = arrh[w]
        ll = arrl[w]
        idx_hi = int(np.argmax(hh))
        idx_lo = int(np.argmin(ll))
        ps_hi = (d - 1) - idx_hi
        ps_lo = (d - 1) - idx_lo
        up[i] = 100.0 * (d - ps_hi) / d
        dn[i] = 100.0 * (d - ps_lo) / d
    ln = line.lower()
    if ln == "down":
        return dn
    if ln == "osc":
        return up - dn
    return up


def _chaikin_ad_from_hlcv(
    arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray, arrv: np.ndarray
) -> np.ndarray:
    n = len(arrc)
    ad = np.zeros(n, dtype=float)
    for i in range(n):
        h, lo, c, v = arrh[i], arrl[i], arrc[i], arrv[i]
        rng = h - lo
        if rng > 1e-12 and np.isfinite(v):
            mfm = ((c - lo) - (h - c)) / rng
            ad[i] = mfm * v
        else:
            ad[i] = 0.0
    return np.cumsum(ad)


def _numpy_sar(
    high: np.ndarray, low: np.ndarray, af_start: float, af_max: float
) -> np.ndarray:
    """抛物线 SAR（简化迭代，与 TA-Lib 数值可能略有差异）。"""
    n = len(high)
    sar = np.full(n, np.nan, dtype=float)
    if n < 2:
        return sar
    af0 = float(af_start)
    afmx = float(af_max)
    long = high[1] + low[1] > high[0] + low[0]
    if long:
        sar[0] = low[0]
        ep = float(high[0])
    else:
        sar[0] = high[0]
        ep = float(low[0])
    af = af0
    for i in range(1, n):
        h, lo = float(high[i]), float(low[i])
        prev_sar = sar[i - 1]
        if not np.isfinite(prev_sar):
            sar[i] = np.nan
            continue
        if long:
            sar_i = prev_sar + af * (ep - prev_sar)
            sar_i = min(sar_i, low[i - 1], lo)
            if h > ep:
                ep = h
                af = min(af + af0, afmx)
            if lo < sar_i:
                long = False
                sar_i = ep
                ep = lo
                af = af0
        else:
            sar_i = prev_sar + af * (ep - prev_sar)
            sar_i = max(sar_i, high[i - 1], h)
            if lo < ep:
                ep = lo
                af = min(af + af0, afmx)
            if h > sar_i:
                long = True
                sar_i = ep
                ep = h
                af = af0
        sar[i] = sar_i
    return sar


def _numpy_ultosc(
    arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray, p1: int, p2: int, p3: int
) -> np.ndarray:
    n = len(arrc)
    pc = np.empty(n, dtype=float)
    pc[0] = arrc[0]
    pc[1:] = arrc[:-1]
    bp = arrc - np.minimum(arrl, pc)
    tr_u = np.maximum(arrh, pc) - np.minimum(arrl, pc)

    def avg_ratio(p: int) -> np.ndarray:
        bpsum = pd.Series(bp).rolling(p, min_periods=1).sum().to_numpy(dtype=float)
        trsum = pd.Series(tr_u).rolling(p, min_periods=1).sum().to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(trsum > 1e-12, bpsum / trsum, np.nan)

    a1, a2, a3 = avg_ratio(p1), avg_ratio(p2), avg_ratio(p3)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * (4 * a1 + 2 * a2 + a3) / 7.0


def _numpy_t3_close(arr: np.ndarray, d: int, vfactor: float) -> np.ndarray:
    s = pd.Series(arr, dtype=float)
    e1 = s.ewm(span=max(d, 1), adjust=False).mean()
    e2 = e1.ewm(span=max(d, 1), adjust=False).mean()
    e3 = e2.ewm(span=max(d, 1), adjust=False).mean()
    e4 = e3.ewm(span=max(d, 1), adjust=False).mean()
    e5 = e4.ewm(span=max(d, 1), adjust=False).mean()
    e6 = e5.ewm(span=max(d, 1), adjust=False).mean()
    v = float(vfactor)
    c1 = -v**3
    c2 = 3 * v**2 + 3 * v**3
    c3 = -3 * v**2 - 2 * v - 3 * v**3
    c4 = 1 + 2 * v + 3 * v**2 + v**3
    t3 = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3
    return t3.to_numpy(dtype=float)


def _bottleneck_mod():
    """可选 Bottleneck C 滚动加速；可用环境变量 ``FACTOR_ENGINE_DISABLE_BOTTLENECK=1`` 强制关闭。"""
    if os.environ.get("FACTOR_ENGINE_DISABLE_BOTTLENECK", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return None
    try:
        import bottleneck as bn  # type: ignore

        return bn
    except ImportError:
        return None


def _ts_roll_via_bottleneck(
    s: pd.Series,
    ctx: ExecutionContext,
    d: int,
    min_periods: Any,
    kind: Literal["mean", "max", "min"],
) -> pd.Series | None:
    """若已安装 Bottleneck，按标的内顺序做 ``move_*``，结果与 ``groupby+rolling`` 对齐后 reindex。"""
    bn = _bottleneck_mod()
    if bn is None or d < 1:
        return None
    fn = getattr(bn, f"move_{kind}", None)
    if fn is None:
        return None
    mc = d if min_periods is None else max(1, min(int(min_periods), d))
    inst = ctx.instrument_col

    def one(grp: pd.Series) -> pd.Series:
        arr = np.asarray(grp.to_numpy(dtype=float), dtype=np.float64)
        out = fn(arr, window=d, min_count=mc)
        return pd.Series(out, index=grp.index)

    try:
        out = s.groupby(level=inst, group_keys=False).apply(one)
        return out.reindex(s.index)
    except Exception:
        return None


def _numba_ts_roll_wanted(ctx: ExecutionContext) -> bool:
    if os.environ.get("FACTOR_ENGINE_USE_NUMBA", "").lower() in ("1", "true", "yes"):
        return True
    perf = getattr(ctx, "perf", None)
    return perf is not None and getattr(perf, "use_numba_rolling", False)


def _ts_roll_via_numba(
    s: pd.Series,
    ctx: ExecutionContext,
    d: int,
    min_periods: Any,
) -> pd.Series | None:
    """可选 Numba 滑动均值；需 ``FACTOR_ENGINE_USE_NUMBA=1`` 或 ``PerfConfig.use_numba_rolling``。"""
    from .numba_kernels import rolling_mean_1d

    if not _numba_ts_roll_wanted(ctx):
        return None
    inst = ctx.instrument_col
    mc = d if min_periods is None else max(1, min(int(min_periods), d))

    def one(grp: pd.Series) -> pd.Series:
        arr = np.asarray(grp.to_numpy(dtype=float), dtype=np.float64)
        out = rolling_mean_1d(arr, d, mc)
        if out is None:
            return pd.Series(np.nan, index=grp.index)
        return pd.Series(out, index=grp.index)

    try:
        out = s.groupby(level=inst, group_keys=False).apply(one)
        return out.reindex(s.index)
    except Exception:
        return None


def _stub(node: PlanNode, ctx: ExecutionContext) -> Any:
    _ = ctx
    raise NotImplementedError(
        f"Operator '{node.op}' is registered but not yet implemented on PandasBackend "
        f"(vector columns, group fields, or stateful semantics may be required). "
        f"See api/operator_registry.STUB_IR_OPS."
    )


def _as_bool_mask(cond: pd.Series) -> pd.Series:
    """把浮点条件列变成布尔掩码，与 ``trade_when`` / 逻辑算子 **判真规则** 对齐。

    NaN 先填 0，再视为假；**真** 当且仅当 ``value > 0.5`` 或 ``value == 1.0``（与 WQ 风格
    0/1 与连续概率门限混用一致）。这样 ``trigger`` 写成 ``rank(x) > 0.8`` 一类时行为稳定。
    """
    s = cond.fillna(0.0)
    return (s > 0.5) | (s == 1.0)


def _as_bool_mask_scalar(v: Any) -> bool:
    """标量版判真：与 :func:`_as_bool_mask` 一致，用于 ``trade_when`` 按 bar 扫描。

    None、NaN、非有限浮点 → 假；否则 ``>0.5`` 或 ``==1.0`` → 真。非数字类型尝试转 float，
    失败则假。
    """
    if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
        return False
    if pd.isna(v):
        return False
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return False
    return (fv > 0.5) or (fv == 1.0)


class PandasBackend(Backend):
    """主力数值后端：初始化时将全部支持的 ``op`` 注册进 :class:`KernelRegistry`。"""

    def __init__(self) -> None:
        self._registry = KernelRegistry()
        self._register_kernels()

    def execute(self, plan: PlanNode, ctx: ExecutionContext):
        """从根节点递归求值。"""
        return self._eval(plan, ctx)

    def _eval(self, node: PlanNode, ctx: ExecutionContext):
        """后序：先算子节点，再在当前节点调用对应 kernel；可选子树结果缓存。"""
        if node.op == "plan_ref":
            sc = getattr(ctx, "shared_result_cache", None)
            if sc is None:
                raise RuntimeError(
                    "plan_ref requires ExecutionContext.shared_result_cache; "
                    "use FactorEngine.run_many() after compile_many CSE."
                )
            sid = node.attrs["sid"]
            if sid not in sc:
                raise KeyError(f"missing shared subplan result for sid prefix={sid[:64]!r}...")
            return sc[sid]
        cache = getattr(ctx, "cache", None)
        cache_key: str | None = None
        if cache is not None:
            cache_key = plan_cache_key(node)
            hit = cache.get(cache_key)
            if hit is not None:
                return hit
        try:
            kernel = self._registry.get(node.op)
        except KeyError as exc:
            raise NotImplementedError(f"Unsupported op: {node.op}") from exc
        out = kernel(node, ctx)
        if cache is not None and cache_key is not None:
            cache.set(cache_key, out)
        return out

    def _register_kernels(self) -> None:
        """登记所有算子实现；未在阶段一实现的 op 指向 ``_stub``。"""
        reg = self._registry.register
        # 叶子
        reg("column", self._op_column)
        reg("literal", self._op_literal)
        reg("add", self._op_add)
        reg("sub", self._op_sub)
        reg("mul", self._op_mul)
        reg("div", self._op_div)
        reg("nary_add", self._op_nary_add)
        reg("nary_mul", self._op_nary_mul)
        reg("nary_sub", self._op_nary_sub)
        reg("nary_max", self._op_nary_max)
        reg("nary_min", self._op_nary_min)
        reg("abs", self._wrap_unary(np.abs))
        reg("log", self._wrap_unary(np.log))
        reg("exp", self._wrap_unary(np.exp))
        reg("sqrt", self._wrap_unary(np.sqrt))
        reg("sin", self._wrap_unary(np.sin))
        reg("cos", self._wrap_unary(np.cos))
        reg("sign", self._wrap_unary(np.sign))
        reg("reverse", self._wrap_unary(lambda s: -s))
        reg("inverse", self._wrap_unary(lambda s: 1.0 / s))
        reg("power", self._op_power)
        reg("signed_power", self._op_signed_power)
        reg("densify", self._op_densify)
        # 逻辑与比较（结果为 0.0/1.0）
        reg("not", self._op_not)
        reg("and", self._op_and)
        reg("or", self._op_or)
        reg("if_else", self._op_if_else)
        reg("is_nan", self._op_is_nan)
        reg("lt", self._op_cmp(lambda a, b: a < b))
        reg("le", self._op_cmp(lambda a, b: a <= b))
        reg("eq", self._op_cmp(lambda a, b: a == b))
        reg("gt", self._op_cmp(lambda a, b: a > b))
        reg("ge", self._op_cmp(lambda a, b: a >= b))
        reg("ne", self._op_cmp(lambda a, b: a != b))
        # 时序（按 instrument 分组）
        reg("ts_mean", self._op_ts_mean)
        reg("ts_std_dev", self._op_ts_std_dev)
        reg("ts_std", self._op_ts_std_dev)
        reg("ts_max", self._op_ts_max)
        reg("ts_min", self._op_ts_min)
        reg("ts_delay", self._op_ts_delay)
        reg("delay", self._op_ts_delay_legacy)
        reg("ts_sum", self._op_ts_sum)
        reg("ts_product", self._op_ts_product)
        reg("ts_delta", self._op_ts_delta)
        reg("ts_av_diff", self._op_ts_av_diff)
        reg("ts_zscore", self._op_ts_zscore)
        reg("ts_rank", self._op_ts_rank)
        reg("ts_scale", self._op_ts_scale)
        reg("ts_count_nans", self._op_ts_count_nans)
        reg("ts_backfill", self._op_ts_backfill)
        reg("ts_arg_max", self._op_ts_arg_max)
        reg("ts_arg_min", self._op_ts_arg_min)
        reg("ts_decay_linear", self._op_ts_decay_linear)
        reg("ts_corr", self._op_ts_corr)
        reg("ts_covariance", self._op_ts_covariance)
        reg("ts_regression", self._op_ts_regression)
        reg("ts_quantile", self._op_ts_quantile)
        reg("days_from_last_change", self._op_days_from_last_change)
        reg("kth_element", self._op_kth_element)
        reg("last_diff_value", self._op_last_diff_value)
        reg("ts_skew", self._op_ts_skew)
        reg("ts_kurt", self._op_ts_kurt)
        # 横截面（按 timestamp 分组）
        reg("rank", self._op_rank)
        reg("zscore", self._op_zscore)
        reg("normalize", self._op_normalize)
        reg("quantile", self._op_cs_quantile)
        reg("scale", self._op_scale)
        reg("winsorize", self._op_winsorize)
        reg("neutralize", self._op_neutralize)
        reg("bucket", self._op_bucket)
        reg("trade_when", self._op_trade_when)
        reg("ts_step", self._op_ts_step)
        reg("hump", self._op_hump)
        # 数据清洗 / 技术指标 / 工程上下文
        reg("pasteurize", self._op_pasteurize)
        reg("tail", self._op_tail)
        reg("protected_div", self._op_protected_div)
        reg("protected_log", self._op_protected_log)
        reg("protected_sqrt", self._op_protected_sqrt)
        reg("ts_sma", self._op_ts_sma)
        reg("ts_ema", self._op_ts_ema)
        reg("ts_rsi", self._op_ts_rsi)
        reg("ts_bbands", self._op_ts_bbands)
        reg("ts_trange", self._op_ts_trange)
        reg("ts_atr", self._op_ts_atr)
        reg("ts_natr", self._op_ts_natr)
        reg("ts_donchian", self._op_ts_donchian)
        reg("ts_keltner", self._op_ts_keltner)
        reg("ts_ma_envelope", self._op_ts_ma_envelope)
        reg("ts_macd", self._op_ts_macd)
        reg("ts_cci", self._op_ts_cci)
        reg("ts_stoch", self._op_ts_stoch)
        reg("ts_willr", self._op_ts_willr)
        reg("ts_roc", self._op_ts_roc)
        reg("ts_obv", self._op_ts_obv)
        reg("ts_mfi", self._op_ts_mfi)
        reg("ts_dema", self._op_ts_dema)
        reg("ts_wma", self._op_ts_wma)
        reg("ts_kama", self._op_ts_kama)
        reg("ts_adx", self._op_ts_adx)
        reg("ts_aroon", self._op_ts_aroon)
        reg("ts_ad", self._op_ts_ad)
        reg("ts_adosc", self._op_ts_adosc)
        reg("ts_sar", self._op_ts_sar)
        reg("ts_cmo", self._op_ts_cmo)
        reg("ts_ppo", self._op_ts_ppo)
        reg("ts_apo", self._op_ts_apo)
        reg("ts_ultosc", self._op_ts_ultosc)
        reg("ts_stochrsi", self._op_ts_stochrsi)
        reg("ts_tema", self._op_ts_tema)
        reg("ts_trima", self._op_ts_trima)
        reg("ts_t3", self._op_ts_t3)
        reg("ts_bop", self._op_ts_bop)
        reg("ts_mom", self._op_ts_mom)
        reg("ts_stochf", self._op_ts_stochf)
        reg("ts_trix", self._op_ts_trix)
        reg("ts_adxr", self._op_ts_adxr)
        reg("ts_dx", self._op_ts_dx)
        reg("ts_rocr", self._op_ts_rocr)
        reg("ts_rocr100", self._op_ts_rocr100)
        reg("ts_linearreg_slope", self._op_ts_linearreg_slope)
        reg("ts_linearreg_angle", self._op_ts_linearreg_angle)
        reg("orthogonalize", self._op_orthogonalize)
        reg("change_instrument", self._op_change_instrument)
        # 分组（WQ group_*）
        reg("group_backfill", self._op_group_backfill)
        reg("group_mean", self._op_group_mean)
        reg("group_neutralize", self._op_group_neutralize)
        reg("group_rank", self._op_group_rank)
        reg("group_scale", self._op_group_scale)
        reg("group_zscore", self._op_group_zscore)
        # 向量 / 远期数据层：与 STUB_IR_OPS 一致，统一占位
        for op in STUB_IR_OPS:
            reg(op, _stub)

    def _wrap_unary(self, fn: Callable[[Any], Any]):
        """把 ``np.*`` 一元函数包装成 (node, ctx) kernel。"""

        def _k(node: PlanNode, ctx: ExecutionContext):
            s = self._eval(node.inputs[0], ctx)
            return fn(s)

        return _k

    def _op_column(self, node: PlanNode, ctx: ExecutionContext):
        """从数据源加载一列 MultiIndex Series。"""
        return ctx.data_source.load_column(node.attrs["name"])

    def _op_literal(self, node: PlanNode, ctx: ExecutionContext):
        """返回常量。"""
        _ = ctx
        return node.attrs["value"]

    def _binary_op(self, node: PlanNode, ctx: ExecutionContext, op):
        """递归求两子节点再逐元素 ``op``。"""
        left = self._eval(node.inputs[0], ctx)
        right = self._eval(node.inputs[1], ctx)
        return op(left, right)

    def _op_add(self, node: PlanNode, ctx: ExecutionContext):
        return self._binary_op(node, ctx, lambda a, b: a + b)

    def _op_sub(self, node: PlanNode, ctx: ExecutionContext):
        return self._binary_op(node, ctx, lambda a, b: a - b)

    def _op_mul(self, node: PlanNode, ctx: ExecutionContext):
        return self._binary_op(node, ctx, lambda a, b: a * b)

    def _op_div(self, node: PlanNode, ctx: ExecutionContext):
        return self._binary_op(node, ctx, lambda a, b: a / b)

    def _op_power(self, node: PlanNode, ctx: ExecutionContext):
        return self._binary_op(node, ctx, lambda a, b: np.power(a, b))

    def _op_signed_power(self, node: PlanNode, ctx: ExecutionContext):
        a = self._eval(node.inputs[0], ctx)
        b = self._eval(node.inputs[1], ctx)
        return np.sign(a) * np.power(np.abs(a), b)

    def _fold_nary(
        self, node: PlanNode, ctx: ExecutionContext, start: Any, combine: Callable
    ):
        acc = self._eval(node.inputs[0], ctx)
        for i in range(1, len(node.inputs)):
            acc = combine(acc, self._eval(node.inputs[i], ctx))
        return acc

    def _op_nary_add(self, node: PlanNode, ctx: ExecutionContext):
        filt = bool(node.attrs.get("filter", False))

        def combine(a, b):
            if filt:
                return a.fillna(0.0) + b.fillna(0.0)
            return a + b

        acc = self._eval(node.inputs[0], ctx)
        for i in range(1, len(node.inputs)):
            acc = combine(acc, self._eval(node.inputs[i], ctx))
        return acc

    def _op_nary_mul(self, node: PlanNode, ctx: ExecutionContext):
        filt = bool(node.attrs.get("filter", False))

        def combine(a, b):
            if filt:
                return a.fillna(1.0) * b.fillna(1.0)
            return a * b

        acc = self._eval(node.inputs[0], ctx)
        for i in range(1, len(node.inputs)):
            acc = combine(acc, self._eval(node.inputs[i], ctx))
        return acc

    def _op_nary_sub(self, node: PlanNode, ctx: ExecutionContext):
        filt = bool(node.attrs.get("filter", False))
        acc = self._eval(node.inputs[0], ctx)
        if filt:
            acc = acc.fillna(0.0)
        for i in range(1, len(node.inputs)):
            b = self._eval(node.inputs[i], ctx)
            if filt:
                b = b.fillna(0.0)
            acc = acc - b
        return acc

    def _op_nary_max(self, node: PlanNode, ctx: ExecutionContext):
        acc = self._eval(node.inputs[0], ctx)
        for i in range(1, len(node.inputs)):
            acc = np.maximum(acc, self._eval(node.inputs[i], ctx))
        return acc

    def _op_nary_min(self, node: PlanNode, ctx: ExecutionContext):
        acc = self._eval(node.inputs[0], ctx)
        for i in range(1, len(node.inputs)):
            acc = np.minimum(acc, self._eval(node.inputs[i], ctx))
        return acc

    def _op_densify(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        ts = ctx.timestamp_col

        def dense_one(g: pd.Series) -> pd.Series:
            codes, _ = pd.factorize(g.values, use_na_sentinel=True)
            return pd.Series(codes.astype(float), index=g.index)

        return s.groupby(level=ts, group_keys=False).apply(dense_one)

    def _op_not(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        out = x.astype(float).copy()
        m = x.notna()
        out[m] = (~_as_bool_mask(x[m])).astype(float)
        return out

    def _op_and(self, node: PlanNode, ctx: ExecutionContext):
        a = self._eval(node.inputs[0], ctx).fillna(0.0)
        b = self._eval(node.inputs[1], ctx).fillna(0.0)
        return ((a > 0.5) & (b > 0.5)).astype(float)

    def _op_or(self, node: PlanNode, ctx: ExecutionContext):
        a = self._eval(node.inputs[0], ctx).fillna(0.0)
        b = self._eval(node.inputs[1], ctx).fillna(0.0)
        return ((a > 0.5) | (b > 0.5)).astype(float)

    def _op_if_else(self, node: PlanNode, ctx: ExecutionContext):
        c = self._eval(node.inputs[0], ctx)
        t = self._eval(node.inputs[1], ctx)
        f = self._eval(node.inputs[2], ctx)
        return t.where(_as_bool_mask(c), f)

    def _op_is_nan(self, node: PlanNode, ctx: ExecutionContext):
        return self._eval(node.inputs[0], ctx).isna().astype(float)

    def _op_cmp(self, pred: Callable[[Any, Any], Any]):
        def _k(node: PlanNode, ctx: ExecutionContext):
            a = self._eval(node.inputs[0], ctx)
            b = self._eval(node.inputs[1], ctx)
            return pred(a, b).astype(float)

        return _k

    def _by_inst_roll(self, s: pd.Series, ctx: ExecutionContext):
        """按标的分组，供 rolling 使用。"""
        return s.groupby(level=ctx.instrument_col)

    def _op_ts_mean(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")
        bn_out = _ts_roll_via_bottleneck(s, ctx, d, mp, "mean")
        if bn_out is not None:
            return bn_out
        nb_out = _ts_roll_via_numba(s, ctx, d, mp)
        if nb_out is not None:
            return nb_out
        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .mean()
            .droplevel(0)
        )

    def _op_ts_std_dev(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")
        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .std()
            .droplevel(0)
        )

    def _op_ts_max(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")
        bn_out = _ts_roll_via_bottleneck(s, ctx, d, mp, "max")
        if bn_out is not None:
            return bn_out
        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .max()
            .droplevel(0)
        )

    def _op_ts_min(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")
        bn_out = _ts_roll_via_bottleneck(s, ctx, d, mp, "min")
        if bn_out is not None:
            return bn_out
        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .min()
            .droplevel(0)
        )

    def _op_ts_delay(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        return s.groupby(level=ctx.instrument_col).shift(d)

    def _op_ts_delay_legacy(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        periods = int(node.attrs["d"])
        return s.groupby(level=ctx.instrument_col).shift(periods)

    def _op_ts_sum(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")
        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .sum()
            .droplevel(0)
        )

    def _op_ts_product(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = _ts_d(node)
        mp = node.attrs.get("min_periods")

        def prod_window(x: pd.Series) -> float:
            return float(np.nanprod(x.to_numpy()))

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=mp)
            .apply(prod_window, raw=False)
            .droplevel(0)
        )

    def _op_ts_delta(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        delayed = s.groupby(level=ctx.instrument_col).shift(d)
        return s - delayed

    def _op_ts_av_diff(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        m = (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=None)
            .mean()
            .droplevel(0)
        )
        return s - m

    def _op_ts_zscore(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        g = self._by_inst_roll(s, ctx)
        mu = g.rolling(window=d, min_periods=2).mean().droplevel(0)
        sig = g.rolling(window=d, min_periods=2).std().droplevel(0)
        return (s - mu) / sig.replace(0.0, np.nan)

    def _op_ts_rank(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        cst = float(node.attrs.get("constant", 0.0))

        def win_rank(x: pd.Series) -> float:
            if len(x) == 0 or pd.isna(x.iloc[-1]):
                return np.nan
            cur = x.iloc[-1]
            valid = x.dropna()
            if valid.empty:
                return np.nan
            return (valid <= cur).sum() / len(valid) + cst

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(win_rank, raw=False)
            .droplevel(0)
        )

    def _op_ts_scale(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        cst = float(node.attrs.get("constant", 0.0))
        g = self._by_inst_roll(s, ctx)
        lo = g.rolling(window=d, min_periods=1).min().droplevel(0)
        hi = g.rolling(window=d, min_periods=1).max().droplevel(0)
        denom = (hi - lo).replace(0.0, np.nan)
        return (s - lo) / denom + cst

    def _op_ts_count_nans(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])

        def cnt_nan(x: pd.Series) -> float:
            return float(x.isna().sum())

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(cnt_nan, raw=False)
            .droplevel(0)
        )

    def _op_ts_backfill(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        lb = int(node.attrs["lookback"])
        k = int(node.attrs.get("k", 1))

        def backfill_series(x: pd.Series) -> pd.Series:
            arr = x.to_numpy()
            out = np.full(len(arr), np.nan)
            for i in range(len(arr)):
                start = max(0, i - lb + 1)
                window = arr[start : i + 1]
                valid = window[~pd.isna(window)]
                if len(valid) >= k:
                    out[i] = valid[-k]
                elif len(valid) > 0:
                    out[i] = valid[0]
            return pd.Series(out, index=x.index)

        return s.groupby(level=ctx.instrument_col, group_keys=False).apply(
            backfill_series
        )

    def _op_ts_arg_max(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])

        def argmax_bars_ago(x: pd.Series) -> float:
            if x.empty or x.isna().all():
                return np.nan
            w = x.dropna()
            if w.empty:
                return np.nan
            rel = len(x) - 1 - int(np.nanargmax(x.to_numpy()))
            return float(rel)

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(argmax_bars_ago, raw=False)
            .droplevel(0)
        )

    def _op_ts_arg_min(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])

        def argmin_bars_ago(x: pd.Series) -> float:
            if x.empty or x.isna().all():
                return np.nan
            rel = len(x) - 1 - int(np.nanargmin(x.to_numpy()))
            return float(rel)

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(argmin_bars_ago, raw=False)
            .droplevel(0)
        )

    def _op_ts_decay_linear(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        dense = bool(node.attrs.get("dense", False))

        def decay_mean(x: pd.Series) -> float:
            vals = x.to_numpy(dtype=float)
            if dense:
                m = ~np.isnan(vals)
                vals = vals[m]
            if len(vals) == 0:
                return np.nan
            w = np.arange(1, len(vals) + 1, dtype=float)
            return float(np.dot(vals, w) / w.sum())

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(decay_mean, raw=False)
            .droplevel(0)
        )

    def _op_ts_corr(self, node: PlanNode, ctx: ExecutionContext):
        a = self._eval(node.inputs[0], ctx)
        b = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        df = pd.DataFrame({"a": a, "b": b})

        def grp_roll_corr(g: pd.DataFrame) -> pd.Series:
            out = []
            idx = g.index
            va = g["a"].to_numpy()
            vb = g["b"].to_numpy()
            for i in range(len(va)):
                sl = slice(max(0, i - d + 1), i + 1)
                xa = va[sl]
                xb = vb[sl]
                m = ~np.isnan(xa) & ~np.isnan(xb)
                if m.sum() < 2:
                    out.append(np.nan)
                else:
                    out.append(np.corrcoef(xa[m], xb[m])[0, 1])
            return pd.Series(out, index=idx)

        return df.groupby(level=ctx.instrument_col, group_keys=False).apply(
            grp_roll_corr
        )

    def _op_ts_covariance(self, node: PlanNode, ctx: ExecutionContext):
        y = self._eval(node.inputs[0], ctx)
        x = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        df = pd.DataFrame({"y": y, "x": x})

        def grp_roll_cov(g: pd.DataFrame) -> pd.Series:
            out = []
            idx = g.index
            vy = g["y"].to_numpy()
            vx = g["x"].to_numpy()
            for i in range(len(vy)):
                sl = slice(max(0, i - d + 1), i + 1)
                ya = vy[sl]
                xa = vx[sl]
                m = ~np.isnan(ya) & ~np.isnan(xa)
                if m.sum() < 2:
                    out.append(np.nan)
                else:
                    out.append(np.cov(ya[m], xa[m], ddof=1)[0, 1])
            return pd.Series(out, index=idx)

        return df.groupby(level=ctx.instrument_col, group_keys=False).apply(
            grp_roll_cov
        )

    def _op_ts_regression(self, node: PlanNode, ctx: ExecutionContext):
        y = self._eval(node.inputs[0], ctx)
        x = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        lag = int(node.attrs.get("lag", 0))
        rt = int(node.attrs.get("rettype", 0))
        df = pd.DataFrame({"y": y, "x": x})

        def ols_on_pair(
            yy: np.ndarray, xx: np.ndarray
        ) -> tuple[float, float, float, float, float, float]:
            """Returns alpha, beta, y_hat_i, sse, sst, n_eff for last row of window."""
            m = ~np.isnan(yy) & ~np.isnan(xx)
            n_eff = int(m.sum())
            if n_eff < 2:
                return (np.nan,) * 6
            yy = yy[m]
            xx = xx[m]
            x_mean = float(xx.mean())
            y_mean = float(yy.mean())
            sxx = float(np.sum((xx - x_mean) ** 2))
            if sxx == 0:
                return (np.nan,) * 6
            beta = float(np.sum((xx - x_mean) * (yy - y_mean)) / sxx)
            alpha = float(y_mean - beta * x_mean)
            y_hat_all = alpha + beta * xx
            resid = yy - y_hat_all
            sse = float(np.sum(resid**2))
            sst = float(np.sum((yy - yy.mean()) ** 2))
            y_i = yy[-1]
            x_i = xx[-1]
            y_hat_i = alpha + beta * x_i
            return alpha, beta, y_hat_i, sse, sst, float(n_eff)

        def grp_reg(g: pd.DataFrame) -> pd.Series:
            vy = g["y"].to_numpy(dtype=float)
            vx = g["x"].to_numpy(dtype=float)
            idx = g.index
            out: list[float] = []
            for i in range(len(vy)):
                sl = slice(max(0, i - d + 1), i + 1)
                ya = vy[sl].copy()
                xa = vx[sl].copy()
                if lag > 0 and len(xa) > lag:
                    xa = np.roll(xa, lag)
                    xa[:lag] = np.nan
                alpha, beta, y_hat_i, sse, sst, n_eff = ols_on_pair(ya, xa)
                err = vy[i] - (alpha + beta * vx[i]) if pd.notna(alpha) else np.nan
                r2 = 1.0 - sse / sst if sst > 0 else np.nan
                s2 = sse / (n_eff - 2) if n_eff > 2 else np.nan
                val_map: dict[int, float] = {
                    0: float(err) if pd.notna(err) else np.nan,
                    1: alpha,
                    2: beta,
                    3: float(alpha + beta * vx[i]) if pd.notna(alpha) else np.nan,
                    4: sse,
                    5: sst,
                    6: r2,
                    7: s2,
                }
                out.append(float(val_map.get(rt, err if pd.notna(err) else np.nan)))
            return pd.Series(out, index=idx)

        return df.groupby(level=ctx.instrument_col, group_keys=False).apply(grp_reg)

    def _op_ts_quantile(self, node: PlanNode, ctx: ExecutionContext):
        try:
            from scipy import stats
        except ImportError:
            raise NotImplementedError(
                "ts_quantile requires scipy (install factor-engine[pandas] with scipy)."
            ) from None
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        driver = str(node.attrs.get("driver", "gaussian")).lower()
        if driver != "gaussian":
            raise NotImplementedError(
                f"ts_quantile driver '{driver}' is not implemented (only 'gaussian')."
            )

        def win_q(x: pd.Series) -> float:
            if x.empty or pd.isna(x.iloc[-1]):
                return np.nan
            cur = x.iloc[-1]
            valid = x.dropna()
            if valid.empty:
                return np.nan
            r = (valid <= cur).sum() / len(valid)
            r = min(max(r, 1e-12), 1 - 1e-12)
            return float(stats.norm.ppf(r))

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=2)
            .apply(win_q, raw=False)
            .droplevel(0)
        )

    def _op_days_from_last_change(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)

        def bars_since_change(x: pd.Series) -> pd.Series:
            out = np.zeros(len(x))
            last = 0
            for i in range(len(x)):
                if i == 0:
                    last = 0
                else:
                    a, b = x.iloc[i], x.iloc[i - 1]
                    changed = (pd.isna(a) ^ pd.isna(b)) or (
                        pd.notna(a) and pd.notna(b) and a != b
                    )
                    if changed:
                        last = i
                out[i] = i - last
            return pd.Series(out, index=x.index)

        return s.groupby(level=ctx.instrument_col, group_keys=False).apply(
            bars_since_change
        )

    def _op_kth_element(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        k = int(node.attrs["k"])
        ignore = str(node.attrs.get("ignore", "NaN"))

        def kth(x: pd.Series) -> float:
            w = x.dropna() if ignore == "NaN" else x
            if len(w) < k or k < 1:
                return np.nan
            return float(np.sort(w.to_numpy())[k - 1])

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(kth, raw=False)
            .droplevel(0)
        )

    def _op_last_diff_value(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])

        def last_diff(x: pd.Series) -> float:
            cur = x.iloc[-1]
            past = x.iloc[:-1]
            if past.empty:
                return np.nan
            for j in range(len(past) - 1, -1, -1):
                v = past.iloc[j]
                if pd.isna(cur) and pd.isna(v):
                    continue
                if v != cur:
                    return float(v)
            return np.nan

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .apply(last_diff, raw=False)
            .droplevel(0)
        )

    def _op_rank(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        _rate = int(node.attrs.get("rate", 2))
        return s.groupby(level=ctx.timestamp_col).rank(pct=True, method="average")

    def _op_zscore(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        grouped = s.groupby(level=ctx.timestamp_col)
        mean = grouped.transform("mean")
        std = grouped.transform("std")
        return (s - mean) / std.replace(0.0, np.nan)

    def _op_normalize(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        use_std = bool(node.attrs.get("useStd", False))
        limit = float(node.attrs.get("limit", 0.0))
        g = s.groupby(level=ctx.timestamp_col)
        m = g.transform("mean")
        out = s - m
        if use_std:
            sig = g.transform("std").replace(0.0, np.nan)
            out = out / sig
        if limit > 0:
            out = out.clip(lower=-limit, upper=limit)
        return out

    def _op_cs_quantile(self, node: PlanNode, ctx: ExecutionContext):
        try:
            from scipy import stats
        except ImportError:
            raise NotImplementedError(
                "quantile (cross-sectional) requires scipy; pip install scipy"
            ) from None
        s = self._eval(node.inputs[0], ctx)
        driver = str(node.attrs.get("driver", "gaussian")).lower()
        sigma = float(node.attrs.get("sigma", 1.0))
        if driver != "gaussian":
            raise NotImplementedError(
                f"cross-sectional quantile driver '{driver}' not implemented."
            )

        def rank_to_gauss(g: pd.Series) -> pd.Series:
            r = g.rank(pct=True, method="average")
            r = r.clip(1e-12, 1 - 1e-12)
            return r.apply(lambda x: stats.norm.ppf(x) * sigma)

        return s.groupby(level=ctx.timestamp_col, group_keys=False).transform(
            lambda x: rank_to_gauss(x)
        )

    def _op_scale(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        sc = float(node.attrs.get("scale", 1.0))
        longscale = float(node.attrs.get("longscale", 1.0))
        shortscale = float(node.attrs.get("shortscale", 1.0))

        def scale_cs(g: pd.Series) -> pd.Series:
            pos = g.where(g > 0, 0.0)
            neg = g.where(g < 0, 0.0)
            sp = pos.abs().sum()
            sn = neg.abs().sum()
            out = g.copy()
            if sp > 0:
                out = out.where(g <= 0, pos / sp * sc * longscale)
            if sn > 0:
                out = out.where(g >= 0, neg / sn * sc * shortscale)
            return out

        return s.groupby(level=ctx.timestamp_col, group_keys=False).transform(
            scale_cs
        )

    def _op_winsorize(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        std_mult = float(node.attrs.get("std", 4.0))

        def win(g: pd.Series) -> pd.Series:
            m = g.mean()
            sig = g.std()
            if sig == 0 or pd.isna(sig):
                return g
            lo = m - std_mult * sig
            hi = m + std_mult * sig
            return g.clip(lower=lo, upper=hi)

        return s.groupby(level=ctx.timestamp_col, group_keys=False).transform(win)

    def _op_bucket(self, node: PlanNode, ctx: ExecutionContext):
        """截面分桶（``bucket``）：按 ``timestamp`` groupby，组内 ``rank(pct=True)`` 再映射桶 id。

        优先读 ``attrs["buckets"]``（等频 N 档）；否则 ``attrs["range"]`` 切分点；``skipBoth`` 去掉
        最低/最高档有效点；``NaNGroup`` 把输入 NaN 标为 -1。与 **时序** 分位无关。
        """
        s = self._eval(node.inputs[0], ctx)
        ts = ctx.timestamp_col
        range_spec = node.attrs.get("range")
        buckets_spec = node.attrs.get("buckets")
        skip_both = bool(node.attrs.get("skipBoth", False))
        nan_group = bool(node.attrs.get("NaNGroup", False))

        def map_cs(g: pd.Series) -> pd.Series:
            r = g.rank(pct=True, method="average")
            valid = g.notna().to_numpy()
            rv = r.to_numpy(dtype=float)
            n = len(g)
            if buckets_spec is not None and str(buckets_spec).strip() != "":
                try:
                    n_bins = max(1, int(str(buckets_spec).strip()))
                except ValueError:
                    n_bins = 0
                if n_bins >= 1:
                    oid = np.full(n, np.nan)
                    oid[valid] = np.floor(
                        np.clip(rv[valid], 0.0, 1.0 - 1e-15) * n_bins
                    )
                    oid[valid] = np.clip(oid[valid], 0.0, float(n_bins - 1))
                    if nan_group:
                        oid[~valid] = -1.0
                    out = pd.Series(oid, index=g.index)
                    if skip_both and n_bins >= 3:
                        last_b = float(n_bins - 1)
                        vn = pd.Series(valid, index=g.index)
                        extreme = (out == 0) | (out == last_b)
                        out = out.where(~(extreme & vn), np.nan)
                    return out
            if range_spec is not None and str(range_spec).strip() != "":
                cuts: list[float] = []
                for part in str(range_spec).split(","):
                    p = part.strip()
                    if p:
                        cuts.append(float(p))
                cuts = sorted({c for c in cuts if 0.0 < c < 1.0})
                if cuts:
                    bid = np.full(n, np.nan)
                    bid[valid] = np.searchsorted(cuts, rv[valid], side="right").astype(
                        float
                    )
                    if nan_group:
                        bid[~valid] = -1.0
                    out = pd.Series(bid, index=g.index)
                    if skip_both and len(cuts) >= 1:
                        max_b = float(len(cuts))
                        vn = pd.Series(valid, index=g.index)
                        extreme = (out == 0.0) | (out == max_b)
                        out = out.where(~(extreme & vn), np.nan)
                    return out
            return pd.Series(np.nan, index=g.index, dtype=float)

        return s.groupby(level=ts, group_keys=False).transform(map_cs)

    def _op_trade_when(self, node: PlanNode, ctx: ExecutionContext):
        """``trade_when``：逐 instrument、时间升序单遍扫描，维护输出状态（详见 ``adr_trade_when.md``）。

        每 bar：exit 真 → 输出 NaN 且状态清空；否则 trigger 真 → 状态=当前 alpha；否则输出=上一 bar 状态。
        标量判真用 :func:`_as_bool_mask_scalar`（NaN 当假）。
        """
        trig = self._eval(node.inputs[0], ctx)
        alpha = self._eval(node.inputs[1], ctx)
        ex = self._eval(node.inputs[2], ctx)
        inst = ctx.instrument_col
        ts = ctx.timestamp_col
        out = pd.Series(np.nan, index=trig.index, dtype=float)
        for instr in trig.index.get_level_values(inst).unique():
            m = trig.index.get_level_values(inst) == instr
            ix = trig.index[m]
            sub_t = trig.loc[ix].sort_index(level=ts)
            da = alpha.reindex(sub_t.index)
            de = ex.reindex(sub_t.index)
            prev = np.nan
            for ts_ix in sub_t.index:
                t_raw = sub_t.loc[ts_ix]
                e_raw = de.loc[ts_ix]
                if _as_bool_mask_scalar(e_raw):
                    prev = np.nan
                elif _as_bool_mask_scalar(t_raw):
                    a = da.loc[ts_ix]
                    prev = float(a) if pd.notna(a) else np.nan
                out.loc[ts_ix] = prev
        return out

    def _op_ts_step(self, node: PlanNode, ctx: ExecutionContext):
        """``ts_step``：inputs[0] 为 anchor 仅定形；``attrs["d"]`` 为周期；每标的独立枚举 bar 下标取模。

        停牌导致不同标的 bar 计数不同步；非全市场统一交易日 step。
        """
        template = self._eval(node.inputs[0], ctx)
        d = max(1, int(node.attrs.get("d", 1)))
        inst = ctx.instrument_col
        ts = ctx.timestamp_col
        out = pd.Series(np.nan, index=template.index, dtype=float)
        for instr in template.index.get_level_values(inst).unique():
            m = template.index.get_level_values(inst) == instr
            ix = template.index[m]
            sub = template.loc[ix].sort_index(level=ts)
            for i, ts_ix in enumerate(sub.index):
                out.loc[ts_ix] = float(i % d)
        return out

    def _op_hump(self, node: PlanNode, ctx: ExecutionContext):
        """``hump``：带记忆的逐 bar 裁剪；``attrs["hump"]`` 为最大单步变化。

        输入 NaN → 输出 NaN 且 **不更新** prev，下一有效 bar 仍相对上次有效输出裁剪。
        首根有限输入：输出=输入。
        """
        s = self._eval(node.inputs[0], ctx)
        h = float(node.attrs.get("hump", 0.01))
        inst = ctx.instrument_col
        ts = ctx.timestamp_col
        out = pd.Series(np.nan, index=s.index, dtype=float)
        for instr in s.index.get_level_values(inst).unique():
            m = s.index.get_level_values(inst) == instr
            ix = s.index[m]
            sub = s.loc[ix].sort_index(level=ts)
            prev = np.nan
            for ts_ix in sub.index:
                v_raw = sub.loc[ts_ix]
                if not pd.notna(v_raw):
                    out.loc[ts_ix] = np.nan
                    continue
                v = float(v_raw)
                if not np.isfinite(prev):
                    prev = v
                else:
                    prev = float(np.clip(v, prev - h, prev + h))
                out.loc[ts_ix] = prev
        return out

    def _op_pasteurize(self, node: PlanNode, ctx: ExecutionContext):
        """Inf→NaN，可选常数填充；对应研究报告「安全锁」式清洗。"""
        s = self._eval(node.inputs[0], ctx)
        out = s.replace([np.inf, -np.inf], np.nan)
        fv = node.attrs.get("fill_value", None)
        if fv is not None and np.isfinite(float(fv)):
            out = out.fillna(float(fv))
        return out

    def _op_tail(self, node: PlanNode, ctx: ExecutionContext):
        """各时间截面上按分位数裁剪长尾。"""
        s = self._eval(node.inputs[0], ctx)
        lo = float(node.attrs.get("lower", 0.01))
        hi = float(node.attrs.get("upper", 0.99))

        def clip_cs(g: pd.Series) -> pd.Series:
            if g.count() == 0:
                return g
            ql = float(g.quantile(lo))
            qh = float(g.quantile(hi))
            return g.clip(lower=ql, upper=qh)

        return s.groupby(level=ctx.timestamp_col, group_keys=False).transform(
            clip_cs
        )

    def _op_protected_div(self, node: PlanNode, ctx: ExecutionContext):
        a = self._eval(node.inputs[0], ctx)
        b = self._eval(node.inputs[1], ctx)
        eps = float(node.attrs.get("epsilon", 1e-12))
        default = float(node.attrs.get("default", 0.0))
        out = a / b
        bad = (
            ~np.isfinite(a.to_numpy())
            | ~np.isfinite(b.to_numpy())
            | (b.abs() < eps)
        )
        return out.where(~bad, default)

    def _op_protected_log(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        eps = float(node.attrs.get("epsilon", 1e-12))
        x = s.astype(float)
        m = np.maximum(np.abs(x.to_numpy()), eps)
        out = np.log(m)
        out[~np.isfinite(x.to_numpy())] = np.nan
        return pd.Series(out, index=s.index)

    def _op_protected_sqrt(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        x = s.astype(float)
        out = np.sqrt(np.abs(x.to_numpy()))
        out[~np.isfinite(x.to_numpy())] = np.nan
        return pd.Series(out, index=s.index)

    def _op_ts_sma(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        if ta is not None:

            def one(ser: pd.Series) -> pd.Series:
                arr = ser.to_numpy(dtype=float)
                return pd.Series(ta.SMA(arr, timeperiod=d), index=ser.index)

            return s.groupby(level=ctx.instrument_col, group_keys=False).apply(one)

        return (
            self._by_inst_roll(s, ctx)
            .rolling(window=d, min_periods=1)
            .mean()
            .droplevel(0)
        )

    def _op_ts_ema(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        if ta is not None:

            def one(ser: pd.Series) -> pd.Series:
                arr = ser.to_numpy(dtype=float)
                return pd.Series(ta.EMA(arr, timeperiod=d), index=ser.index)

            return s.groupby(level=ctx.instrument_col, group_keys=False).apply(one)

        span = max(d, 1)
        return (
            s.groupby(level=ctx.instrument_col)
            .ewm(span=span, adjust=False)
            .mean()
            .droplevel(0)
        )

    def _op_ts_rsi(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        if ta is not None:

            def one(ser: pd.Series) -> pd.Series:
                arr = ser.to_numpy(dtype=float)
                return pd.Series(ta.RSI(arr, timeperiod=d), index=ser.index)

            return s.groupby(level=ctx.instrument_col, group_keys=False).apply(one)

        def rsi_ewm(x: pd.Series) -> pd.Series:
            delta = x.diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            ag = gain.ewm(alpha=1.0 / d, adjust=False).mean()
            al = loss.ewm(alpha=1.0 / d, adjust=False).mean()
            rs = ag / al.replace(0.0, np.nan)
            return 100.0 - (100.0 / (1.0 + rs))

        return s.groupby(level=ctx.instrument_col, group_keys=False).apply(rsi_ewm)

    def _op_ts_bbands(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        nbdev = float(node.attrs.get("nbdev", 2.0))
        band = str(node.attrs.get("band", "middle")).lower()
        ta = _talib_mod()
        if ta is not None:

            def one(ser: pd.Series) -> pd.Series:
                arr = ser.to_numpy(dtype=float)
                u, m, l = ta.BBANDS(arr, timeperiod=d, nbdevup=nbdev, nbdevdn=nbdev)
                if band == "upper":
                    out = u
                elif band == "lower":
                    out = l
                else:
                    out = m
                return pd.Series(out, index=ser.index)

            return s.groupby(level=ctx.instrument_col, group_keys=False).apply(one)

        g = self._by_inst_roll(s, ctx)
        mid = g.rolling(window=d, min_periods=1).mean().droplevel(0)
        sig = g.rolling(window=d, min_periods=1).std().droplevel(0)
        upper = mid + nbdev * sig
        lower = mid - nbdev * sig
        if band == "upper":
            return upper
        if band == "lower":
            return lower
        return mid

    def _op_ts_trange(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        ta = _talib_mod()

        def pd_tr(arrh, arrl, arrc):
            return _wilder_tr_arr(arrh, arrl, arrc)

        fn = (lambda hh, ll, cc: ta.TRANGE(hh, ll, cc)) if ta is not None else None
        return _eval_hlc_series(h, l, c, ctx, fn, pd_tr)

    def _op_ts_atr(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_atr(arrh, arrl, arrc):
            return _wilder_atr_arr(arrh, arrl, arrc, d)

        fn = (
            (lambda hh, ll, cc: ta.ATR(hh, ll, cc, timeperiod=d)) if ta is not None else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_atr)

    def _op_ts_natr(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_natr(arrh, arrl, arrc):
            atr = _wilder_atr_arr(arrh, arrl, arrc, d)
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(np.abs(arrc) > 1e-18, 100.0 * atr / arrc, np.nan)

        fn = (
            (lambda hh, ll, cc: ta.NATR(hh, ll, cc, timeperiod=d)) if ta is not None else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_natr)

    def _op_ts_donchian(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        band = str(node.attrs.get("band", "middle")).lower()
        hi = (
            self._by_inst_roll(h, ctx)
            .rolling(window=d, min_periods=1)
            .max()
            .droplevel(0)
        )
        lo = (
            self._by_inst_roll(l, ctx)
            .rolling(window=d, min_periods=1)
            .min()
            .droplevel(0)
        )
        mid = (hi + lo) / 2.0
        if band == "upper":
            return hi
        if band == "lower":
            return lo
        return mid

    def _op_ts_keltner(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        mult = float(node.attrs.get("mult", 2.0))
        ad = int(node.attrs.get("atr_d", d))
        band = str(node.attrs.get("band", "middle")).lower()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            tp = (arrh + arrl + arrc) / 3.0
            mid = pd.Series(tp, index=hh.index).ewm(span=max(d, 1), adjust=False).mean()
            atr = _wilder_atr_arr(arrh, arrl, arrc, max(ad, 1))
            atr_s = pd.Series(atr, index=hh.index)
            upper = mid + mult * atr_s
            lower = mid - mult * atr_s
            if band == "upper":
                out.loc[hh.index] = upper
            elif band == "lower":
                out.loc[hh.index] = lower
            else:
                out.loc[hh.index] = mid
        return out.reindex(h.index)

    def _op_ts_ma_envelope(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        pct = float(node.attrs.get("pct", 0.025))
        band = str(node.attrs.get("band", "middle")).lower()
        use_ema = bool(node.attrs.get("use_ema", False))
        g = self._by_inst_roll(s, ctx)
        if use_ema:
            mid = g.ewm(span=max(d, 1), adjust=False).mean().droplevel(0)
        else:
            mid = g.rolling(window=d, min_periods=1).mean().droplevel(0)
        upper = mid * (1.0 + pct)
        lower = mid * (1.0 - pct)
        if band == "upper":
            return upper
        if band == "lower":
            return lower
        return mid

    def _op_ts_macd(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        fast = int(node.attrs.get("fast", 12))
        slow = int(node.attrs.get("slow", 26))
        sigp = int(node.attrs.get("signal", 9))
        line = str(node.attrs.get("line", "macd")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                macd, sig, hist = ta.MACD(
                    arr,
                    fastperiod=fast,
                    slowperiod=slow,
                    signalperiod=sigp,
                )
                if line == "signal":
                    return pd.Series(sig, index=ser.index)
                if line == "hist":
                    return pd.Series(hist, index=ser.index)
                return pd.Series(macd, index=ser.index)
            ef = pd.Series(arr, index=ser.index).ewm(span=fast, adjust=False).mean()
            es = pd.Series(arr, index=ser.index).ewm(span=slow, adjust=False).mean()
            macd = ef - es
            sig = macd.ewm(span=sigp, adjust=False).mean()
            hist = macd - sig
            if line == "signal":
                return sig
            if line == "hist":
                return hist
            return macd

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_cci(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_cci(arrh, arrl, arrc):
            tp = (arrh + arrl + arrc) / 3.0
            s_tp = pd.Series(tp)
            sma = s_tp.rolling(d, min_periods=1).mean().to_numpy(dtype=float)
            mad = (
                s_tp.rolling(d, min_periods=1)
                .apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
                .to_numpy(dtype=float)
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                return (tp - sma) / (0.015 * np.where(mad > 0, mad, np.nan))

        fn = (
            (lambda hh, ll, cc: ta.CCI(hh, ll, cc, timeperiod=d)) if ta is not None else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_cci)

    def _op_ts_stoch(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        fk = int(node.attrs.get("fastk_period", 5))
        sk = int(node.attrs.get("slowk_period", 3))
        sd = int(node.attrs.get("slowd_period", 3))
        line = str(node.attrs.get("line", "slowk")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            if ta is not None:
                slowk, slowd = ta.STOCH(
                    arrh,
                    arrl,
                    arrc,
                    fastk_period=fk,
                    slowk_period=sk,
                    slowk_matype=0,
                    slowd_period=sd,
                    slowd_matype=0,
                )
                arr_out = slowd if line == "slowd" else slowk
            else:
                ll_n = pd.Series(arrl).rolling(fk, min_periods=1).min().to_numpy()
                hh_n = pd.Series(arrh).rolling(fk, min_periods=1).max().to_numpy()
                den = hh_n - ll_n
                fastk_a = np.where(den > 0, 100.0 * (arrc - ll_n) / den, np.nan)
                slowk_a = (
                    pd.Series(fastk_a)
                    .rolling(sk, min_periods=1)
                    .mean()
                    .to_numpy(dtype=float)
                )
                slowd_a = (
                    pd.Series(slowk_a)
                    .rolling(sd, min_periods=1)
                    .mean()
                    .to_numpy(dtype=float)
                )
                arr_out = slowd_a if line == "slowd" else slowk_a
            out.loc[hh.index] = arr_out
        return out.reindex(h.index)

    def _op_ts_willr(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_willr(arrh, arrl, arrc):
            hh = pd.Series(arrh).rolling(d, min_periods=1).max().to_numpy(dtype=float)
            ll = pd.Series(arrl).rolling(d, min_periods=1).min().to_numpy(dtype=float)
            den = hh - ll
            return np.where(den > 0, -100.0 * (hh - arrc) / den, np.nan)

        fn = (
            (lambda hh, ll, cc: ta.WILLR(hh, ll, cc, timeperiod=d))
            if ta is not None
            else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_willr)

    def _op_ts_roc(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            ps = pd.Series(arr, index=ser.index)
            if ta is not None:
                return pd.Series(ta.ROC(arr, timeperiod=d), index=ser.index)
            prev = ps.shift(d)
            with np.errstate(divide="ignore", invalid="ignore"):
                return (ps - prev) / prev * 100.0

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_obv(self, node: PlanNode, ctx: ExecutionContext):
        c = self._eval(node.inputs[0], ctx)
        v = self._eval(node.inputs[1], ctx)
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        ta = _talib_mod()
        out = pd.Series(np.nan, index=c.index, dtype=float)
        for instr in c.index.get_level_values(inst).unique():
            m = c.index.get_level_values(inst) == instr
            ix = c.index[m]
            cc = c.loc[ix].sort_index(level=tcol).astype(float)
            vv = v.reindex(cc.index).astype(float)
            arrc = cc.to_numpy(dtype=float)
            arrv = vv.to_numpy(dtype=float)
            if ta is not None:
                obv = ta.OBV(arrc, arrv)
            else:
                ch = np.diff(arrc, prepend=arrc[0])
                sgn = np.sign(ch)
                sgn[0] = 0.0
                obv = np.cumsum(sgn * arrv)
            out.loc[cc.index] = obv
        return out.reindex(c.index)

    def _op_ts_mfi(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        v = self._eval(node.inputs[3], ctx)
        d = int(node.attrs["d"])
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        ta = _talib_mod()
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            vv = v.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            arrv = vv.to_numpy(dtype=float)
            if ta is not None:
                res = ta.MFI(arrh, arrl, arrc, arrv, timeperiod=d)
            else:
                tp = (arrh + arrl + arrc) / 3.0
                raw = tp * arrv
                pos = np.zeros_like(tp)
                neg = np.zeros_like(tp)
                pos[1:] = np.where(tp[1:] > tp[:-1], raw[1:], 0.0)
                neg[1:] = np.where(tp[1:] < tp[:-1], raw[1:], 0.0)
                psum = pd.Series(pos).rolling(d, min_periods=1).sum().to_numpy()
                nsum = pd.Series(neg).rolling(d, min_periods=1).sum().to_numpy()
                with np.errstate(divide="ignore", invalid="ignore"):
                    ratio = np.where(nsum > 0, psum / nsum, np.nan)
                    res = 100.0 - 100.0 / (1.0 + ratio)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_dema(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.DEMA(arr, timeperiod=d), index=ser.index)
            e1 = pd.Series(arr, index=ser.index).ewm(span=d, adjust=False).mean()
            e2 = e1.ewm(span=d, adjust=False).mean()
            return 2.0 * e1 - e2

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_wma(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.WMA(arr, timeperiod=d), index=ser.index)
            w = np.arange(1, d + 1, dtype=float)

            def wma_window(x):
                if len(x) < d or np.any(~np.isfinite(x[-d:])):
                    return np.nan
                return float(np.dot(x[-d:], w) / w.sum())

            return ser.rolling(d, min_periods=d).apply(wma_window, raw=True)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_kama(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        fp = int(node.attrs.get("fast_period", 2))
        sp = int(node.attrs.get("slow_period", 30))
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                try:
                    res = ta.KAMA(
                        arr, timeperiod=d, fastperiod=fp, slowperiod=sp
                    )
                except TypeError:
                    res = ta.KAMA(arr, timeperiod=d)
                return pd.Series(res, index=ser.index)
            return ser.ewm(span=max(d, 1), adjust=False).mean()

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_adx(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        line = str(node.attrs.get("line", "adx")).lower()
        ta = _talib_mod()

        def pd_adx(arrh, arrl, arrc):
            return _numpy_adx_line(arrh, arrl, arrc, d, line)

        if ta is not None:

            def fn(hh, ll, cc):
                if line == "plus_di":
                    return ta.PLUS_DI(hh, ll, cc, timeperiod=d)
                if line == "minus_di":
                    return ta.MINUS_DI(hh, ll, cc, timeperiod=d)
                return ta.ADX(hh, ll, cc, timeperiod=d)

            talib_fn = fn
        else:
            talib_fn = None
        return _eval_hlc_series(h, l, c, ctx, talib_fn, pd_adx)

    def _op_ts_aroon(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        line = str(node.attrs.get("line", "up")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            if ta is not None:
                if line == "osc":
                    res = np.asarray(
                        ta.AROONOSC(arrh, arrl, timeperiod=d), dtype=float
                    )
                else:
                    aroondown, aroonup = ta.AROON(arrh, arrl, timeperiod=d)
                    res = np.asarray(
                        aroonup if line == "up" else aroondown, dtype=float
                    )
            else:
                res = _numpy_aroon(arrh, arrl, d, line)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_ad(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        v = self._eval(node.inputs[3], ctx)
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            vv = v.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            arrv = vv.to_numpy(dtype=float)
            if ta is not None:
                res = np.asarray(ta.AD(arrh, arrl, arrc, arrv), dtype=float)
            else:
                res = _chaikin_ad_from_hlcv(arrh, arrl, arrc, arrv)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_adosc(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        v = self._eval(node.inputs[3], ctx)
        fast = int(node.attrs.get("fast", 3))
        slow = int(node.attrs.get("slow", 10))
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            vv = v.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            arrv = vv.to_numpy(dtype=float)
            if ta is not None:
                res = np.asarray(
                    ta.ADOSC(
                        arrh,
                        arrl,
                        arrc,
                        arrv,
                        fastperiod=fast,
                        slowperiod=slow,
                    ),
                    dtype=float,
                )
            else:
                ad = _chaikin_ad_from_hlcv(arrh, arrl, arrc, arrv)
                s_ad = pd.Series(ad, index=hh.index)
                ef = s_ad.ewm(span=max(fast, 1), adjust=False).mean()
                es = s_ad.ewm(span=max(slow, 1), adjust=False).mean()
                res = (ef - es).to_numpy(dtype=float)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_sar(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        af = float(node.attrs.get("acceleration", 0.02))
        mx = float(node.attrs.get("maximum", 0.2))
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            if ta is not None:
                res = np.asarray(
                    ta.SAR(arrh, arrl, acceleration=af, maximum=mx), dtype=float
                )
            else:
                res = _numpy_sar(arrh, arrl, af, mx)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_cmo(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.CMO(arr, timeperiod=d), index=ser.index)
            delta = np.diff(arr, prepend=arr[0])
            up = np.where(delta > 0, delta, 0.0)
            dn = np.where(delta < 0, -delta, 0.0)
            su = pd.Series(up, index=ser.index).rolling(d, min_periods=1).sum()
            sd = pd.Series(dn, index=ser.index).rolling(d, min_periods=1).sum()
            with np.errstate(divide="ignore", invalid="ignore"):
                den = su + sd
                return 100.0 * (su - sd) / den.replace(0.0, np.nan)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_ppo(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        fast = int(node.attrs.get("fast", 12))
        slow = int(node.attrs.get("slow", 26))
        sigp = int(node.attrs.get("signal", 9))
        line = str(node.attrs.get("line", "ppo")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                ppo, sig, hist = ta.PPO(
                    arr,
                    fastperiod=fast,
                    slowperiod=slow,
                    signalperiod=sigp,
                )
                if line == "signal":
                    return pd.Series(sig, index=ser.index)
                if line == "hist":
                    return pd.Series(hist, index=ser.index)
                return pd.Series(ppo, index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            ef = ps.ewm(span=fast, adjust=False).mean()
            es = ps.ewm(span=slow, adjust=False).mean()
            with np.errstate(divide="ignore", invalid="ignore"):
                ppo = 100.0 * (ef - es) / es.replace(0.0, np.nan)
            sig = ppo.ewm(span=sigp, adjust=False).mean()
            hist = ppo - sig
            if line == "signal":
                return sig
            if line == "hist":
                return hist
            return ppo

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_apo(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        fast = int(node.attrs.get("fast", 12))
        slow = int(node.attrs.get("slow", 26))
        sigp = int(node.attrs.get("signal", 9))
        line = str(node.attrs.get("line", "apo")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                apo, sig, hist = ta.APO(
                    arr,
                    fastperiod=fast,
                    slowperiod=slow,
                    signalperiod=sigp,
                )
                if line == "signal":
                    return pd.Series(sig, index=ser.index)
                if line == "hist":
                    return pd.Series(hist, index=ser.index)
                return pd.Series(apo, index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            ef = ps.ewm(span=fast, adjust=False).mean()
            es = ps.ewm(span=slow, adjust=False).mean()
            apo = ef - es
            sig = apo.ewm(span=sigp, adjust=False).mean()
            hist = apo - sig
            if line == "signal":
                return sig
            if line == "hist":
                return hist
            return apo

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_ultosc(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        p1 = int(node.attrs.get("timeperiod1", 7))
        p2 = int(node.attrs.get("timeperiod2", 14))
        p3 = int(node.attrs.get("timeperiod3", 28))
        ta = _talib_mod()

        def pd_uo(arrh, arrl, arrc):
            return _numpy_ultosc(arrh, arrl, arrc, p1, p2, p3)

        fn = (
            (
                lambda hh, ll, cc: ta.ULTOSC(
                    hh,
                    ll,
                    cc,
                    timeperiod1=p1,
                    timeperiod2=p2,
                    timeperiod3=p3,
                )
            )
            if ta is not None
            else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_uo)

    def _op_ts_stochrsi(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        tp = int(node.attrs.get("timeperiod", 14))
        fk = int(node.attrs.get("fastk_period", 5))
        fd = int(node.attrs.get("fastd_period", 3))
        line = str(node.attrs.get("line", "fastk")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                fastk, fastd = ta.STOCHRSI(
                    arr,
                    timeperiod=tp,
                    fastk_period=fk,
                    fastd_period=fd,
                    fastd_matype=0,
                )
                out_a = fastd if line == "fastd" else fastk
                return pd.Series(out_a, index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            delta = ps.diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            ag = gain.ewm(alpha=1.0 / tp, adjust=False).mean()
            al = loss.ewm(alpha=1.0 / tp, adjust=False).mean()
            rs = ag / al.replace(0.0, np.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rmin = rsi.rolling(fk, min_periods=1).min()
            rmax = rsi.rolling(fk, min_periods=1).max()
            den = (rmax - rmin).replace(0.0, np.nan)
            fastk_sr = 100.0 * (rsi - rmin) / den
            fastd_s = fastk_sr.rolling(fd, min_periods=1).mean()
            return fastd_s if line == "fastd" else fastk_sr

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_tema(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.TEMA(arr, timeperiod=d), index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            e1 = ps.ewm(span=max(d, 1), adjust=False).mean()
            e2 = e1.ewm(span=max(d, 1), adjust=False).mean()
            e3 = e2.ewm(span=max(d, 1), adjust=False).mean()
            return 3.0 * e1 - 3.0 * e2 + e3

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_trima(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.TRIMA(arr, timeperiod=d), index=ser.index)
            w1 = max(1, int(np.ceil((d + 1) / 2.0)))
            w2 = max(1, int(np.floor((d + 1) / 2.0)) + 1)
            ps = pd.Series(arr, index=ser.index)
            return ps.rolling(w1, min_periods=1).mean().rolling(w2, min_periods=1).mean()

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_t3(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        vf = float(node.attrs.get("vfactor", 0.7))
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(
                    ta.T3(arr, timeperiod=d, vfactor=vf), index=ser.index
                )
            return pd.Series(_numpy_t3_close(arr, d, vf), index=ser.index)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_bop(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            n = len(arrc)
            opn = np.empty(n, dtype=float)
            opn[0] = arrc[0]
            if n > 1:
                opn[1:] = arrc[:-1]
            if ta is not None:
                res = np.asarray(ta.BOP(opn, arrh, arrl, arrc), dtype=float)
            else:
                den = arrh - arrl
                res = np.where(den > 1e-12, (arrc - opn) / den, np.nan)
            out.loc[hh.index] = res
        return out.reindex(h.index)

    def _op_ts_mom(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.MOM(arr, timeperiod=d), index=ser.index)
            return pd.Series(arr, index=ser.index).diff(d)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_stochf(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        fk = int(node.attrs.get("fastk_period", 5))
        fd = int(node.attrs.get("fastd_period", 3))
        line = str(node.attrs.get("line", "fastk")).lower()
        ta = _talib_mod()
        inst = ctx.instrument_col
        tcol = ctx.timestamp_col
        out = pd.Series(np.nan, index=h.index, dtype=float)
        for instr in h.index.get_level_values(inst).unique():
            m = h.index.get_level_values(inst) == instr
            ix = h.index[m]
            hh = h.loc[ix].sort_index(level=tcol).astype(float)
            ll = l.reindex(hh.index).astype(float)
            cc = c.reindex(hh.index).astype(float)
            arrh = hh.to_numpy(dtype=float)
            arrl = ll.to_numpy(dtype=float)
            arrc = cc.to_numpy(dtype=float)
            if ta is not None:
                fastk, fastd = ta.STOCHF(
                    arrh,
                    arrl,
                    arrc,
                    fastk_period=fk,
                    fastd_period=fd,
                    fastd_matype=0,
                )
                arr_out = fastd if line == "fastd" else fastk
            else:
                ll_n = pd.Series(arrl).rolling(fk, min_periods=1).min().to_numpy()
                hh_n = pd.Series(arrh).rolling(fk, min_periods=1).max().to_numpy()
                den = hh_n - ll_n
                fastk_a = np.where(den > 0, 100.0 * (arrc - ll_n) / den, np.nan)
                fastd_a = (
                    pd.Series(fastk_a)
                    .rolling(fd, min_periods=1)
                    .mean()
                    .to_numpy(dtype=float)
                )
                arr_out = fastd_a if line == "fastd" else fastk_a
            out.loc[hh.index] = arr_out
        return out.reindex(h.index)

    def _op_ts_trix(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.TRIX(arr, timeperiod=d), index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            sp = max(d, 1)
            e1 = ps.ewm(span=sp, adjust=False).mean()
            e2 = e1.ewm(span=sp, adjust=False).mean()
            e3 = e2.ewm(span=sp, adjust=False).mean()
            prev = e3.shift(1)
            with np.errstate(divide="ignore", invalid="ignore"):
                trix = (e3 - prev) / prev.replace(0.0, np.nan) * 100.0
            return trix

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_adxr(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_adxr(arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray) -> np.ndarray:
            return _numpy_adxr(arrh, arrl, arrc, d)

        fn = (
            (lambda hh, ll, cc: ta.ADXR(hh, ll, cc, timeperiod=d))
            if ta is not None
            else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_adxr)

    def _op_ts_dx(self, node: PlanNode, ctx: ExecutionContext):
        h = self._eval(node.inputs[0], ctx)
        l = self._eval(node.inputs[1], ctx)
        c = self._eval(node.inputs[2], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()

        def pd_dx(arrh: np.ndarray, arrl: np.ndarray, arrc: np.ndarray) -> np.ndarray:
            _, _, dx = _dmi_wilder_di_dx(arrh, arrl, arrc, d)
            return dx

        fn = (
            (lambda hh, ll, cc: ta.DX(hh, ll, cc, timeperiod=d))
            if ta is not None
            else None
        )
        return _eval_hlc_series(h, l, c, ctx, fn, pd_dx)

    def _op_ts_rocr(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.ROCR(arr, timeperiod=d), index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            prev = ps.shift(d)
            with np.errstate(divide="ignore", invalid="ignore"):
                return ps / prev.replace(0.0, np.nan)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_rocr100(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(ta.ROCR100(arr, timeperiod=d), index=ser.index)
            ps = pd.Series(arr, index=ser.index)
            prev = ps.shift(d)
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = ps / prev.replace(0.0, np.nan)
                return (ratio - 1.0) * 100.0

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_linearreg_slope(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(
                    ta.LINEARREG_SLOPE(arr, timeperiod=d), index=ser.index
                )
            return pd.Series(_numpy_rolling_linreg_slope(arr, d), index=ser.index)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_linearreg_angle(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        ta = _talib_mod()
        inst = ctx.instrument_col

        def one(ser: pd.Series) -> pd.Series:
            arr = ser.to_numpy(dtype=float)
            if ta is not None:
                return pd.Series(
                    ta.LINEARREG_ANGLE(arr, timeperiod=d), index=ser.index
                )
            return pd.Series(_numpy_rolling_linreg_angle(arr, d), index=ser.index)

        return s.groupby(level=inst, group_keys=False).apply(one)

    def _op_ts_skew(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        mp = int(node.attrs.get("min_periods", d))
        g = self._by_inst_roll(s, ctx)
        return g.rolling(window=d, min_periods=min(mp, d)).skew().droplevel(0)

    def _op_ts_kurt(self, node: PlanNode, ctx: ExecutionContext):
        s = self._eval(node.inputs[0], ctx)
        d = int(node.attrs["d"])
        mp = int(node.attrs.get("min_periods", d))
        g = self._by_inst_roll(s, ctx)
        return g.rolling(window=d, min_periods=min(mp, d)).kurt().droplevel(0)

    def _op_neutralize(self, node: PlanNode, ctx: ExecutionContext):
        """截面 OLS 残差：x ~ 1 + y（每个 timestamp）。"""
        x = self._eval(node.inputs[0], ctx)
        y = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "y": y})
        out = pd.Series(np.nan, index=x.index, dtype=float)
        for _, g in df.groupby(level=ts):
            sx = g["x"].astype(float)
            sy = g["y"].astype(float)
            m = sx.notna() & sy.notna()
            if m.sum() < 2:
                continue
            xv = sx[m]
            yv = sy[m]
            yc = yv - yv.mean()
            var = float((yc**2).sum())
            if var < 1e-18:
                continue
            beta = float(((xv - xv.mean()) * yc).sum() / var)
            alpha = float(xv.mean() - beta * yv.mean())
            pred = alpha + beta * sy
            out.loc[g.index] = sx - pred
        return out

    def _op_orthogonalize(self, node: PlanNode, ctx: ExecutionContext):
        """截面 Gram-Schmidt：x 对 y 去投影（每个 timestamp 一组）。"""
        x = self._eval(node.inputs[0], ctx)
        y = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "y": y})
        out = pd.Series(np.nan, index=x.index, dtype=float)
        for _, g in df.groupby(level=ts):
            xv = g["x"].to_numpy(dtype=float)
            yv = g["y"].to_numpy(dtype=float)
            res = np.full_like(xv, np.nan, dtype=float)
            m = np.isfinite(xv) & np.isfinite(yv)
            if m.sum() >= 2:
                xvm = xv[m]
                yvm = yv[m]
                yy = float(np.dot(yvm, yvm))
                if yy > 0.0 and np.isfinite(yy):
                    beta = float(np.dot(xvm, yvm) / yy)
                    res[m] = xv[m] - beta * yv[m]
            out.loc[g.index] = res
        return out

    def _op_change_instrument(self, node: PlanNode, ctx: ExecutionContext):
        """child 除以基准列按时间聚合后的广播序列（默认截面均值）。"""
        feat = self._eval(node.inputs[0], ctx)
        name = str(node.attrs["benchmark"])
        bench = ctx.data_source.load_column(name)
        ts = ctx.timestamp_col
        if isinstance(bench.index, pd.MultiIndex):
            b_scalar = bench.groupby(level=ts).mean()
        else:
            b_scalar = bench
        ts_level = feat.index.get_level_values(ts)
        aligned = b_scalar.reindex(ts_level)
        denom = pd.Series(aligned.to_numpy(), index=feat.index).replace(0.0, np.nan)
        return feat / denom

    def _op_group_rank(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        g = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "g": g})
        df["_ts"] = df.index.get_level_values(ts)
        r = df.groupby(["_ts", "g"], group_keys=False)["x"].transform(
            lambda s: s.rank(pct=True, method="average")
        )
        return pd.Series(r.to_numpy(), index=x.index)

    def _op_group_neutralize(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        g = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "g": g})
        df["_ts"] = df.index.get_level_values(ts)
        m = df.groupby(["_ts", "g"], group_keys=False)["x"].transform("mean")
        return x - pd.Series(m.to_numpy(), index=x.index)

    def _op_group_zscore(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        g = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "g": g})
        df["_ts"] = df.index.get_level_values(ts)
        m = df.groupby(["_ts", "g"], group_keys=False)["x"].transform("mean")
        s = df.groupby(["_ts", "g"], group_keys=False)["x"].transform("std").replace(
            0.0, np.nan
        )
        xm = pd.Series(m.to_numpy(), index=x.index)
        xs = pd.Series(s.to_numpy(), index=x.index)
        return (x - xm) / xs

    def _op_group_scale(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        g = self._eval(node.inputs[1], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "g": g})
        df["_ts"] = df.index.get_level_values(ts)
        lo = df.groupby(["_ts", "g"], group_keys=False)["x"].transform("min")
        hi = df.groupby(["_ts", "g"], group_keys=False)["x"].transform("max")
        lo_s = pd.Series(lo.to_numpy(), index=x.index)
        hi_s = pd.Series(hi.to_numpy(), index=x.index)
        denom = (hi_s - lo_s).replace(0.0, np.nan)
        return (x - lo_s) / denom

    def _op_group_mean(self, node: PlanNode, ctx: ExecutionContext):
        x = self._eval(node.inputs[0], ctx)
        w = self._eval(node.inputs[1], ctx)
        g = self._eval(node.inputs[2], ctx)
        ts = ctx.timestamp_col
        df = pd.DataFrame({"x": x, "w": w, "g": g})
        df["_ts"] = df.index.get_level_values(ts)
        df["wx"] = df["x"] * df["w"]
        sum_wx = df.groupby(["_ts", "g"], group_keys=False)["wx"].transform("sum")
        sum_w = df.groupby(["_ts", "g"], group_keys=False)["w"].transform("sum")
        return pd.Series(sum_wx.to_numpy(), index=x.index) / pd.Series(
            sum_w.to_numpy(), index=x.index
        ).replace(0.0, np.nan)

    def _op_group_backfill(self, node: PlanNode, ctx: ExecutionContext):
        """标的维上回溯 d 根 bar，同组内 winsor 均值填 NaN。"""
        x = self._eval(node.inputs[0], ctx)
        g = self._eval(node.inputs[1], ctx)
        d = int(node.attrs["d"])
        std_mult = float(node.attrs.get("std", 4.0))
        inst_col = ctx.instrument_col
        ts_col = ctx.timestamp_col
        out = x.copy()
        for inst in x.index.get_level_values(inst_col).unique():
            mask = x.index.get_level_values(inst_col) == inst
            sub_ix = x.index[mask]
            sub_x = x.loc[sub_ix]
            sub_g = g.loc[sub_ix]
            order = np.argsort(sub_x.index.get_level_values(ts_col).values)
            xs = sub_x.iloc[order].to_numpy(dtype=float)
            gs = sub_g.iloc[order].to_numpy()
            orig_index = sub_x.index[order]
            filled = np.array(xs, copy=True)
            for i in range(len(xs)):
                if not pd.isna(xs[i]):
                    continue
                gi = gs[i]
                vals: list[float] = []
                for j in range(max(0, i - d), i):
                    if gs[j] == gi and not pd.isna(xs[j]):
                        vals.append(float(xs[j]))
                if not vals:
                    continue
                arr = np.array(vals, dtype=float)
                m = float(np.nanmean(arr))
                sig = float(np.nanstd(arr))
                if sig > 0.0 and np.isfinite(sig):
                    arr = np.clip(arr, m - std_mult * sig, m + std_mult * sig)
                filled[i] = float(np.nanmean(arr))
            out.loc[orig_index] = filled
        return out
