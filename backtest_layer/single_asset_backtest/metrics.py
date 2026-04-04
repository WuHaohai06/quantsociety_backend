from __future__ import annotations

"""回测指标：按 ``metrics_profile`` 分层扩展（core/standard/industrial）；年化因子由时间索引推断 bar 频率。"""
import numpy as np
import pandas as pd


def _safe_float(value: float) -> float:
    out = float(value)
    if not np.isfinite(out):
        return 0.0
    return out


def annualization_factor(index: pd.DatetimeIndex) -> float:
    """用相邻 bar 时间差的中位数估计「每年多少根 bar」，再乘 252 日；异常时回退 252。"""
    if len(index) < 2:
        return 252.0
    delta = np.median(np.diff(index.view("i8")))
    if delta <= 0:
        return 252.0
    one_day = 24 * 60 * 60 * 1_000_000_000
    bars_per_day = one_day / float(delta)
    return max(1.0, 252.0 * bars_per_day)


def _max_drawdown_duration(drawdown: pd.Series) -> int:
    max_len = 0
    cur = 0
    for v in drawdown.to_numpy():
        if v < 0:
            cur += 1
            max_len = max(max_len, cur)
        else:
            cur = 0
    return int(max_len)


def _drawdown_depths(drawdown: pd.Series) -> list[float]:
    depths: list[float] = []
    cur_min = 0.0
    in_dd = False
    for v in drawdown.to_numpy(dtype=float):
        if v < 0.0:
            cur_min = min(cur_min, float(v))
            in_dd = True
        elif in_dd:
            depths.append(abs(cur_min))
            cur_min = 0.0
            in_dd = False
    if in_dd:
        depths.append(abs(cur_min))
    return depths


def _alpha_beta(period_return: pd.Series, benchmark_return: pd.Series | None, ann: float) -> tuple[float, float]:
    if benchmark_return is None:
        return 0.0, 0.0

    aligned = pd.concat([period_return, benchmark_return], axis=1, join="inner").dropna()
    if aligned.empty:
        return 0.0, 0.0

    strat = aligned.iloc[:, 0].astype(float)
    bench = aligned.iloc[:, 1].astype(float)
    var_bench = float(bench.var(ddof=0))
    if var_bench <= 1e-12:
        return 0.0, 0.0

    cov = float(np.cov(strat.to_numpy(), bench.to_numpy(), ddof=0)[0, 1])
    beta = cov / var_bench
    alpha_period = float(strat.mean()) - beta * float(bench.mean())
    alpha = alpha_period * ann
    return _safe_float(alpha), _safe_float(beta)


def _capacity_estimate(avg_daily_volume: float | None, turnover_annualized: float) -> float:
    if avg_daily_volume is None or avg_daily_volume <= 0:
        return 0.0
    participation = 0.02
    annual_adv_capacity = float(avg_daily_volume) * participation * 252.0
    if turnover_annualized <= 1e-12:
        return _safe_float(annual_adv_capacity)
    return _safe_float(annual_adv_capacity / turnover_annualized)


def _turnover_sensitivity(turnover: float, commission_paid: float) -> dict:
    if turnover <= 1e-12:
        return {"x0_5": 0.0, "x1_0": 0.0, "x1_5": 0.0}
    base_rate = float(commission_paid) / turnover
    return {
        "x0_5": _safe_float(turnover * base_rate * 0.5),
        "x1_0": _safe_float(turnover * base_rate),
        "x1_5": _safe_float(turnover * base_rate * 1.5),
    }


def _benchmark_metrics(
    *,
    period_return: pd.Series,
    benchmark_return: pd.Series | None,
    ann: float,
    annual_return: float,
    risk_free_rate_annual: float,
) -> dict:
    if benchmark_return is None:
        return {
            "information_ratio": 0.0,
            "tracking_error": 0.0,
            "treynor": 0.0,
            "up_market_capture": 0.0,
            "down_market_capture": 0.0,
            "r_squared": 0.0,
        }

    aligned = pd.concat([period_return, benchmark_return], axis=1, join="inner").dropna()
    if aligned.empty:
        return {
            "information_ratio": 0.0,
            "tracking_error": 0.0,
            "treynor": 0.0,
            "up_market_capture": 0.0,
            "down_market_capture": 0.0,
            "r_squared": 0.0,
        }

    strat = aligned.iloc[:, 0].astype(float)
    bench = aligned.iloc[:, 1].astype(float)
    active = strat - bench

    tracking_error = _safe_float(active.std(ddof=0) * np.sqrt(ann)) if len(active) else 0.0
    information_ratio = _safe_float((active.mean() * ann) / tracking_error) if tracking_error > 1e-12 else 0.0

    alpha, beta = _alpha_beta(period_return, benchmark_return, ann)
    _ = alpha
    treynor = _safe_float((annual_return - float(risk_free_rate_annual)) / beta) if abs(beta) > 1e-12 else 0.0

    up_mask = bench > 0.0
    down_mask = bench < 0.0

    def _capture(mask: pd.Series) -> float:
        if not mask.any():
            return 0.0
        strat_leg = strat[mask]
        bench_leg = bench[mask]
        strat_comp = float((1.0 + strat_leg).prod() - 1.0)
        bench_comp = float((1.0 + bench_leg).prod() - 1.0)
        if abs(bench_comp) <= 1e-12:
            return 0.0
        return _safe_float(strat_comp / bench_comp)

    corr = float(strat.corr(bench)) if len(strat) else 0.0
    r2 = _safe_float(corr * corr)

    return {
        "information_ratio": information_ratio,
        "tracking_error": tracking_error,
        "treynor": treynor,
        "up_market_capture": _capture(up_mask),
        "down_market_capture": _capture(down_mask),
        "r_squared": r2,
    }


def _trade_metrics(trade_ledger: list[dict] | None) -> dict:
    """从平仓事件聚合：胜率、盈亏比、Kelly、MFE/MAE 等（无 ledger 则全 0）。"""
    closed = [x for x in (trade_ledger or []) if x.get("event") == "trade_closed"]
    if not closed:
        return {
            "win_rate_trade": 0.0,
            "profit_factor": 0.0,
            "max_consecutive_losses": 0,
            "avg_holding_period_bars": 0.0,
            "expectancy": 0.0,
            "kelly_fraction": 0.0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
        }

    pnl = np.array([float(x.get("pnlcomm", 0.0) or 0.0) for x in closed], dtype=float)
    wins = pnl[pnl > 0.0]
    losses = pnl[pnl < 0.0]
    win_rate = float((pnl > 0.0).mean()) if len(pnl) else 0.0

    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    profit_factor = _safe_float(gross_profit / gross_loss) if gross_loss > 1e-12 else 0.0

    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(abs(losses.mean())) if len(losses) else 0.0
    loss_rate = 1.0 - win_rate
    expectancy = _safe_float(win_rate * avg_win - loss_rate * avg_loss)

    if avg_loss > 1e-12:
        b = avg_win / avg_loss if avg_win > 0 else 0.0
        kelly = _safe_float(win_rate - (loss_rate / b)) if b > 1e-12 else 0.0
    else:
        kelly = 0.0

    max_consec_losses = 0
    cur_losses = 0
    for p in pnl:
        if p < 0.0:
            cur_losses += 1
            max_consec_losses = max(max_consec_losses, cur_losses)
        else:
            cur_losses = 0

    holding = [float(x.get("holding_bars", 0.0) or 0.0) for x in closed]
    mfe = [float(x.get("mfe", 0.0) or 0.0) for x in closed]
    mae = [float(x.get("mae", 0.0) or 0.0) for x in closed]

    return {
        "win_rate_trade": _safe_float(win_rate),
        "profit_factor": _safe_float(profit_factor),
        "max_consecutive_losses": int(max_consec_losses),
        "avg_holding_period_bars": _safe_float(float(np.mean(holding)) if holding else 0.0),
        "expectancy": _safe_float(expectancy),
        "kelly_fraction": _safe_float(kelly),
        "avg_mfe": _safe_float(float(np.mean(mfe)) if mfe else 0.0),
        "avg_mae": _safe_float(float(np.mean(mae)) if mae else 0.0),
    }


def _hurst_exponent(values: pd.Series) -> float:
    x = values.to_numpy(dtype=float)
    if len(x) < 20:
        return 0.0
    lags = np.arange(2, min(20, len(x) // 2))
    tau = [np.std(x[lag:] - x[:-lag]) for lag in lags]
    tau = np.array(tau, dtype=float)
    valid = tau > 1e-12
    if valid.sum() < 3:
        return 0.0
    slope = np.polyfit(np.log(lags[valid]), np.log(tau[valid]), 1)[0]
    return _safe_float(float(slope * 2.0))


def _standard_profile_metrics(
    *,
    period_return: pd.Series,
    annual_return: float,
    max_drawdown: float,
    ann: float,
    turnover: float,
    turnover_annualized: float,
    commission_paid: float,
    benchmark_return: pd.Series | None,
    avg_daily_volume: float | None,
    risk_free_rate_annual: float,
) -> dict:
    downside = period_return[period_return < 0.0]
    downside_vol = _safe_float(downside.std(ddof=0) * np.sqrt(ann)) if len(downside) else 0.0
    sortino = _safe_float(annual_return / downside_vol) if downside_vol > 1e-12 else 0.0
    calmar = _safe_float(annual_return / abs(max_drawdown)) if abs(max_drawdown) > 1e-12 else 0.0
    hit_rate_bar = _safe_float((period_return > 0.0).mean()) if len(period_return) else 0.0

    alpha, beta = _alpha_beta(period_return, benchmark_return, ann)
    benchmark_metrics = _benchmark_metrics(
        period_return=period_return,
        benchmark_return=benchmark_return,
        ann=ann,
        annual_return=annual_return,
        risk_free_rate_annual=risk_free_rate_annual,
    )
    return {
        "downside_volatility": downside_vol,
        "sortino": sortino,
        "calmar": calmar,
        "hit_rate_bar": hit_rate_bar,
        "alpha": alpha,
        "beta": beta,
        "capacity_estimate": _capacity_estimate(avg_daily_volume, turnover_annualized),
        "turnover_sensitivity": _turnover_sensitivity(turnover, float(commission_paid)),
        **benchmark_metrics,
    }


def compute_backtest_metrics(
    *,
    equity_curve: pd.Series,
    period_return: pd.Series,
    realized_position: pd.Series,
    commission_paid: float,
    trades: int,
    profile: str,
    benchmark_return: pd.Series | None = None,
    avg_daily_volume: float | None = None,
    trade_ledger: list[dict] | None = None,
    risk_free_rate_annual: float = 0.0,
) -> dict:
    """计算核心指标并按 ``profile`` 追加 standard/industrial 扩展；换手由 ``realized_position`` 差分近似。"""
    ann = annualization_factor(equity_curve.index)
    total_return = _safe_float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0) if len(equity_curve) else 0.0
    annual_return = _safe_float((1.0 + total_return) ** (ann / max(1.0, len(equity_curve))) - 1.0) if len(equity_curve) else 0.0

    vol = _safe_float(period_return.std(ddof=0) * np.sqrt(ann)) if len(period_return) else 0.0
    sharpe = _safe_float((annual_return - float(risk_free_rate_annual)) / vol) if vol > 1e-12 else 0.0

    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    max_drawdown = _safe_float(drawdown.min()) if len(drawdown) else 0.0

    # 全样本仓位变化绝对值之和（首根用 |position|）；与多标的「bar 换手」含义不同，仅作可比近似
    turnover = _safe_float(realized_position.diff().abs().fillna(realized_position.abs()).sum())
    turnover_annualized = _safe_float(turnover / max(1.0, len(equity_curve)) * ann)

    metrics = {
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "trades": int(trades),
        "commission_paid": _safe_float(commission_paid),
    }

    if profile not in {"standard", "industrial"}:
        return metrics

    standard_metrics = _standard_profile_metrics(
        period_return=period_return,
        annual_return=annual_return,
        max_drawdown=max_drawdown,
        ann=ann,
        turnover=turnover,
        turnover_annualized=turnover_annualized,
        commission_paid=float(commission_paid),
        benchmark_return=benchmark_return,
        avg_daily_volume=avg_daily_volume,
        risk_free_rate_annual=risk_free_rate_annual,
    )
    metrics.update(standard_metrics)

    if profile != "industrial":
        return metrics

    var_95 = _safe_float(period_return.quantile(0.05)) if len(period_return) else 0.0
    tail = period_return[period_return <= var_95]

    dd_duration = _max_drawdown_duration(drawdown)
    drawdown_depths = _drawdown_depths(drawdown)
    top_depths = sorted(drawdown_depths, reverse=True)[:3]
    sterling_denom = float(np.mean(top_depths)) if top_depths else 0.0
    burke_denom = float(np.sqrt(np.sum(np.square(drawdown_depths)))) if drawdown_depths else 0.0

    ulcer = _safe_float(np.sqrt(np.mean(np.square(drawdown[drawdown < 0.0])))) if (drawdown < 0.0).any() else 0.0
    omega_threshold = float(risk_free_rate_annual) / ann if ann > 1e-12 else 0.0
    gains = period_return[period_return > omega_threshold] - omega_threshold
    losses = omega_threshold - period_return[period_return < omega_threshold]
    omega = _safe_float(float(gains.sum()) / float(losses.sum())) if float(losses.sum()) > 1e-12 else 0.0

    tail_ratio = 0.0
    if len(period_return):
        q95 = float(period_return.quantile(0.95))
        q05 = float(period_return.quantile(0.05))
        tail_ratio = _safe_float(q95 / abs(q05)) if abs(q05) > 1e-12 else 0.0

    trade_metrics = _trade_metrics(trade_ledger)

    industrial_metrics = {
        "skew": _safe_float(period_return.skew()) if len(period_return) else 0.0,
        "kurtosis": _safe_float(period_return.kurt()) if len(period_return) else 0.0,
        "var_95": var_95,
        "cvar_95": _safe_float(tail.mean()) if len(tail) else var_95,
        "max_drawdown_duration_bars": dd_duration,
        "avg_drawdown": _safe_float(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0.0,
        "commission_to_turnover": _safe_float(float(commission_paid) / turnover) if turnover > 1e-12 else 0.0,
        "turnover_annualized": turnover_annualized,
        "ulcer_index": ulcer,
        "mar_ratio": _safe_float(annual_return / abs(max_drawdown)) if abs(max_drawdown) > 1e-12 else 0.0,
        "sterling_ratio": _safe_float(annual_return / sterling_denom) if sterling_denom > 1e-12 else 0.0,
        "burke_ratio": _safe_float(annual_return / burke_denom) if burke_denom > 1e-12 else 0.0,
        "tail_ratio": tail_ratio,
        "omega_ratio": omega,
        "recovery_factor": _safe_float(total_return / abs(max_drawdown)) if abs(max_drawdown) > 1e-12 else 0.0,
        "hurst_exponent": _hurst_exponent(equity_curve.pct_change().fillna(0.0)),
        "time_in_market": _safe_float((realized_position.abs() > 1e-12).mean()) if len(realized_position) else 0.0,
        "exposure": _safe_float(realized_position.abs().mean()) if len(realized_position) else 0.0,
    }
    industrial_metrics.update(trade_metrics)
    metrics.update(industrial_metrics)

    return metrics
