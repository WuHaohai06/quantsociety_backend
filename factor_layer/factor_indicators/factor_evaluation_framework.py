from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


@dataclass
class EvalConfig:
    factor_path: Path
    vwap_path: Path
    factor_col: str = "factor"
    vwap_col: str = "vwap"
    timestamp_col: str = "timestamp"
    horizons: Tuple[int, ...] = (1, 5, 10, 20)
    zscore_window: int = 200
    winsor_quantile: float = 0.01
    n_quantiles: int = 10
    min_obs_per_day: int = 30
    holding_fee_rate: float = 0.00002


def _load_series(path: Path, ts_col: str, value_col: str) -> pd.Series:
    df = pd.read_parquet(path, columns=[ts_col, value_col])
    df = df.rename(columns={ts_col: "timestamp", value_col: "value"})
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    return pd.Series(df["value"].to_numpy(), index=df["timestamp"], name=value_col)


def align_on_overlap_reindex(factor: pd.Series, vwap: pd.Series) -> pd.DataFrame:
    if factor.empty or vwap.empty:
        raise ValueError("Input factor/vwap series is empty.")

    overlap_start = max(factor.index.min(), vwap.index.min())
    overlap_end = min(factor.index.max(), vwap.index.max())
    if overlap_start > overlap_end:
        raise ValueError("No overlapping timestamp range between factor and vwap.")

    factor_overlap = factor.loc[(factor.index >= overlap_start) & (factor.index <= overlap_end)]
    vwap_overlap = vwap.loc[(vwap.index >= overlap_start) & (vwap.index <= overlap_end)]

    overlap_index = factor_overlap.index.union(vwap_overlap.index).sort_values()

    aligned = pd.DataFrame(index=overlap_index)
    aligned["factor_raw"] = factor_overlap.reindex(overlap_index)
    aligned["vwap"] = vwap_overlap.reindex(overlap_index)
    aligned.index.name = "timestamp"
    return aligned


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    rolling_mean = series.rolling(window=window, min_periods=window).mean()
    rolling_std = series.rolling(window=window, min_periods=window).std(ddof=0)
    z = (series - rolling_mean) / rolling_std
    return z.where(rolling_std > 0)


def make_forward_vwap_return(vwap: pd.Series, horizon: int) -> pd.Series:
    # t factor -> [t+1, t+1+N] vwap return
    return vwap.shift(-(horizon + 1)) / vwap.shift(-1) - 1.0


def _eligibility_mask_by_day(df: pd.DataFrame, horizon: int) -> pd.Series:
    pos_in_day = df.groupby("date").cumcount()
    day_size = df.groupby("date")["date"].transform("size")
    return pos_in_day < (day_size - horizon)


def _winsorize_by_day(series: pd.Series, date_index: pd.Series, q: float) -> pd.Series:
    clipped = series.copy()
    grouped = series.groupby(date_index)
    lower = grouped.transform(lambda s: s.quantile(q))
    upper = grouped.transform(lambda s: s.quantile(1.0 - q))
    clipped = clipped.clip(lower=lower, upper=upper)
    return clipped


def _daily_corr(series_x: pd.Series, series_y: pd.Series, date_index: pd.Series, method: str, min_obs: int) -> pd.Series:
    tmp = pd.DataFrame({"x": series_x, "y": series_y, "date": date_index})

    def _corr_one_day(g: pd.DataFrame) -> float:
        valid = g.dropna()
        if len(valid) < min_obs:
            return np.nan
        return valid["x"].corr(valid["y"], method=method)

    out = tmp.groupby("date", sort=True)[["x", "y"]].apply(_corr_one_day)
    out.name = f"{method}_corr"
    return out


def _summary_from_daily_series(s: pd.Series) -> Dict[str, float]:
    s = s.dropna()
    if s.empty:
        return {
            "mean": np.nan,
            "std": np.nan,
            "ir": np.nan,
            "win_rate": np.nan,
            "n_days": 0,
        }

    mean = s.mean()
    std = s.std(ddof=1)
    ir = mean / std if std and not np.isclose(std, 0.0) else np.nan
    win_rate = (s > 0).mean()
    return {
        "mean": float(mean),
        "std": float(std),
        "ir": float(ir) if pd.notna(ir) else np.nan,
        "win_rate": float(win_rate),
        "n_days": int(s.shape[0]),
    }


def layered_backtest_single_period_return(
    factor_for_eval: pd.Series,
    target_return_n: pd.Series,
    n_quantiles: int,
    horizon: int,
) -> pd.Series:
    tmp = pd.DataFrame({"factor": factor_for_eval, "ret_n": target_return_n}).dropna()
    if tmp.empty:
        return pd.Series(dtype=float, name="avg_single_period_ret")

    q_rank = tmp["factor"].rank(method="first")
    groups = pd.qcut(q_rank, q=n_quantiles, labels=False, duplicates="drop") + 1

    grp_mean_n = tmp.groupby(groups)["ret_n"].mean()
    grp_mean_single = np.power(1.0 + grp_mean_n, 1.0 / horizon) - 1.0
    grp_mean_single.index.name = "group"
    grp_mean_single.name = "avg_single_period_ret"
    return grp_mean_single


def _assign_quantile_groups(factor_for_eval: pd.Series, n_quantiles: int) -> pd.Series:
    groups_all = pd.Series(np.nan, index=factor_for_eval.index, dtype=float)
    valid = factor_for_eval.dropna()
    if valid.empty:
        return groups_all.rename("group")

    rank = valid.rank(method="first")
    groups = pd.qcut(rank, q=n_quantiles, labels=False, duplicates="drop") + 1
    groups_all.loc[valid.index] = groups.astype(float)
    return groups_all.rename("group")


def _capped_position_signal(
    long_trigger: pd.Series,
    short_trigger: pd.Series,
    horizon: int,
) -> pd.Series:
    """
    State-machine position: strictly -1 / 0 / +1.
    Once a position is opened it is held for exactly `horizon` bars;
    any new signals during the hold window are ignored.
    When long and short trigger on the same bar, long takes priority.
    """
    n = len(long_trigger)
    lt = long_trigger.to_numpy(dtype=bool)
    st = short_trigger.to_numpy(dtype=bool)

    long_events  = [(int(i),  1) for i in np.where(lt)[0]]
    short_events = [(int(i), -1) for i in np.where(st)[0]]
    events = sorted(long_events + short_events, key=lambda x: x[0])

    pos = np.zeros(n, dtype=np.float64)
    hold_until = -1  # inclusive last bar index of current hold

    for idx, direction in events:
        if idx <= hold_until:
            continue  # inside an active hold — ignore new signal
        end = min(idx + horizon, n)
        pos[idx:end] = direction
        hold_until = end - 1

    return pd.Series(pos, index=long_trigger.index, name="net_position")


def layered_long_short_holding_pnl(
    factor_for_eval: pd.Series,
    vwap: pd.Series,
    n_quantiles: int,
    horizon: int,
) -> pd.DataFrame:
    groups = _assign_quantile_groups(factor_for_eval, n_quantiles=n_quantiles)

    # Causality: signal at t fires entry trigger at t+1
    long_trigger  = (groups == n_quantiles).shift(1).fillna(0.0)
    short_trigger = (groups == 1).shift(1).fillna(0.0)

    # Strictly ±1 position; new signals ignored during active hold
    net_position = _capped_position_signal(long_trigger, short_trigger, horizon)

    # Single-period return at bar k: vwap[k+1]/vwap[k] - 1
    # Position entered at t+1 earns vwap[t+2]/vwap[t+1]-1 on that bar ✓
    one_period_ret = vwap.shift(-1) / vwap - 1.0
    pnl = (net_position * one_period_ret).rename("pnl")
    cum_pnl = (1.0 + pnl.fillna(0.0)).cumprod().rename("cum_pnl")  # equity curve, starts at 1

    out = pd.DataFrame(
        {
            "pnl": pnl,
            "cum_pnl": cum_pnl,
            "net_position": net_position,
            "long_active": (net_position > 0).astype(float),
            "short_active": (net_position < 0).astype(float),
        },
        index=factor_for_eval.index,
    )
    out.index.name = "timestamp"
    return out


def apply_holding_transaction_cost(holding_pnl: pd.DataFrame, fee_rate: float) -> pd.DataFrame:
    if holding_pnl is None or holding_pnl.empty:
        return pd.DataFrame(columns=["pnl", "cum_pnl", "net_position", "long_active", "short_active", "transaction_cost"])

    out = holding_pnl.copy()
    net_pos = out["net_position"].fillna(0.0)
    pos_change = net_pos.diff().abs().fillna(net_pos.abs())
    transaction_cost = (pos_change * fee_rate).rename("transaction_cost")
    pnl_after_cost = (out["pnl"].fillna(0.0) - transaction_cost).rename("pnl")
    cum_pnl_after_cost = (1.0 + pnl_after_cost).cumprod().rename("cum_pnl")

    out["transaction_cost"] = transaction_cost
    out["pnl"] = pnl_after_cost
    out["cum_pnl"] = cum_pnl_after_cost
    return out


def _infer_periods_per_year(index: pd.Index) -> float:
    ts = pd.Series(pd.to_datetime(index)).dropna().sort_values()
    if ts.shape[0] < 3:
        return 252.0

    sec = ts.diff().dt.total_seconds().dropna()
    sec = sec[sec > 0]
    if sec.empty:
        return 252.0

    median_sec = float(sec.median())
    if median_sec <= 0:
        return 252.0
    return (365.25 * 24 * 3600) / median_sec


def holding_backtest_stats(holding_pnl: pd.DataFrame) -> Dict[str, float]:
    if holding_pnl is None or holding_pnl.empty:
        return {
            "holding_sharpe": np.nan,
            "holding_max_drawdown": np.nan,
            "holding_annual_return": np.nan,
            "holding_turnover": np.nan,
            "holding_avg_daily_trades": np.nan,
            "holding_win_rate": np.nan,
            "holding_profit_loss_ratio": np.nan,
        }

    pnl = holding_pnl["pnl"].dropna()
    equity = holding_pnl["cum_pnl"].reindex(pnl.index).dropna()
    net_pos = holding_pnl["net_position"].reindex(pnl.index).fillna(0.0)
    if pnl.empty:
        return {
            "holding_sharpe": np.nan,
            "holding_max_drawdown": np.nan,
            "holding_annual_return": np.nan,
            "holding_turnover": np.nan,
            "holding_avg_daily_trades": np.nan,
            "holding_win_rate": np.nan,
            "holding_profit_loss_ratio": np.nan,
        }

    periods_per_year = _infer_periods_per_year(pnl.index)
    pnl_std = float(pnl.std(ddof=1))
    sharpe = np.nan
    if pnl_std > 0 and not np.isclose(pnl_std, 0.0):
        sharpe = float((pnl.mean() / pnl_std) * np.sqrt(periods_per_year))

    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else np.nan

    total_return = float(equity.iloc[-1] - 1.0)
    span_days = (pd.to_datetime(pnl.index[-1]) - pd.to_datetime(pnl.index[0])).total_seconds() / (24 * 3600)
    if span_days > 0:
        years = span_days / 365.25
        annual_return = float((1.0 + total_return) ** (1.0 / years) - 1.0)
    else:
        annual_return = np.nan

    pos_change = net_pos.diff().abs().fillna(net_pos.abs())
    exposure = net_pos.abs().sum()
    turnover = float(pos_change.sum() / exposure) if exposure > 0 else np.nan
    trade_count_by_bar = pos_change
    avg_daily_trades = float(trade_count_by_bar.groupby(pd.to_datetime(trade_count_by_bar.index).date).sum().mean())

    active_mask = net_pos != 0
    active_pnl = pnl[active_mask]
    win_rate = float((active_pnl > 0).mean()) if not active_pnl.empty else np.nan

    profit_sum = float(active_pnl[active_pnl > 0].sum())
    loss_sum = float(-active_pnl[active_pnl < 0].sum())
    profit_loss_ratio = float(profit_sum / loss_sum) if loss_sum > 0 else np.nan

    return {
        "holding_sharpe": sharpe,
        "holding_max_drawdown": max_drawdown,
        "holding_annual_return": annual_return,
        "holding_turnover": turnover,
        "holding_avg_daily_trades": avg_daily_trades,
        "holding_win_rate": win_rate,
        "holding_profit_loss_ratio": profit_loss_ratio,
    }


def evaluate_horizon(base_df: pd.DataFrame, horizon: int, cfg: EvalConfig) -> Dict[str, object]:
    df = base_df.copy()
    df["target_ret_n"] = make_forward_vwap_return(df["vwap"], horizon)

    eligible = _eligibility_mask_by_day(df, horizon)
    df["factor_eval"] = df["factor_z"].where(eligible)
    df["target_eval"] = df["target_ret_n"].where(eligible)

    df["factor_eval"] = _winsorize_by_day(df["factor_eval"], df["date"], cfg.winsor_quantile)

    daily_ic = _daily_corr(
        series_x=df["factor_eval"],
        series_y=df["target_eval"],
        date_index=df["date"],
        method="pearson",
        min_obs=cfg.min_obs_per_day,
    )
    daily_rank_ic = _daily_corr(
        series_x=df["factor_eval"],
        series_y=df["target_eval"],
        date_index=df["date"],
        method="spearman",
        min_obs=cfg.min_obs_per_day,
    )

    ic_summary = _summary_from_daily_series(daily_ic)
    rank_ic_summary = _summary_from_daily_series(daily_rank_ic)

    layered = layered_backtest_single_period_return(
        factor_for_eval=df["factor_eval"],
        target_return_n=df["target_eval"],
        n_quantiles=cfg.n_quantiles,
        horizon=horizon,
    )
    holding_pnl = layered_long_short_holding_pnl(
        factor_for_eval=df["factor_eval"],
        vwap=df["vwap"],
        n_quantiles=cfg.n_quantiles,
        horizon=horizon,
    )
    holding_pnl_with_cost = apply_holding_transaction_cost(holding_pnl, cfg.holding_fee_rate)
    holding_stats = holding_backtest_stats(holding_pnl)
    holding_stats_with_cost = holding_backtest_stats(holding_pnl_with_cost)
    holding_total_ret = float(holding_pnl["cum_pnl"].iloc[-1] - 1.0) if not holding_pnl.empty else np.nan
    holding_total_ret_with_cost = (
        float(holding_pnl_with_cost["cum_pnl"].iloc[-1] - 1.0) if not holding_pnl_with_cost.empty else np.nan
    )

    summary = {
        "horizon": horizon,
        "ic_mean": ic_summary["mean"],
        "ic_std": ic_summary["std"],
        "icir": ic_summary["ir"],
        "ic_win_rate": ic_summary["win_rate"],
        "ic_n_days": ic_summary["n_days"],
        "rank_ic_mean": rank_ic_summary["mean"],
        "rank_ic_std": rank_ic_summary["std"],
        "rank_icir": rank_ic_summary["ir"],
        "rank_ic_win_rate": rank_ic_summary["win_rate"],
        "rank_ic_n_days": rank_ic_summary["n_days"],
        "holding_total_return": holding_total_ret,
        **holding_stats,
        "holding_total_return_with_cost": holding_total_ret_with_cost,
        **{f"{k}_with_cost": v for k, v in holding_stats_with_cost.items()},
    }

    return {
        "summary": summary,
        "daily_ic": daily_ic.rename("ic"),
        "daily_rank_ic": daily_rank_ic.rename("rank_ic"),
        "layered_single_period": layered,
        "holding_pnl": holding_pnl,
        "holding_stats": holding_stats,
        "holding_pnl_with_cost": holding_pnl_with_cost,
        "holding_stats_with_cost": holding_stats_with_cost,
    }


def run_evaluation(cfg: EvalConfig) -> Dict[int, Dict[str, object]]:
    factor = _load_series(cfg.factor_path, cfg.timestamp_col, cfg.factor_col)
    vwap = _load_series(cfg.vwap_path, cfg.timestamp_col, cfg.vwap_col)

    aligned = align_on_overlap_reindex(factor=factor, vwap=vwap)
    aligned["factor_z"] = rolling_zscore(aligned["factor_raw"], window=cfg.zscore_window)
    aligned["date"] = aligned.index.date

    results: Dict[int, Dict[str, object]] = {}
    for horizon in cfg.horizons:
        results[horizon] = evaluate_horizon(aligned, horizon, cfg)
    return results


def save_results(results: Dict[int, Dict[str, object]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_df = pd.DataFrame([v["summary"] for v in results.values()]).sort_values("horizon")
    summary_df.to_csv(out_dir / "evaluation_summary.csv", index=False)

    for h, payload in results.items():
        payload["daily_ic"].to_frame().to_csv(out_dir / f"daily_ic_h{h}.csv")
        payload["daily_rank_ic"].to_frame().to_csv(out_dir / f"daily_rank_ic_h{h}.csv")
        payload["layered_single_period"].to_frame().to_csv(out_dir / f"layered_single_period_h{h}.csv")
        payload["holding_pnl"].to_csv(out_dir / f"holding_pnl_h{h}.csv")


def print_brief(results: Dict[int, Dict[str, object]]) -> None:
    print("=" * 88)
    print("Factor Evaluation Summary")
    print("Columns: horizon | IC mean/std/IR/win | RankIC mean/std/IR/win | HoldPnl")
    print("=" * 88)
    for h in sorted(results):
        s = results[h]["summary"]
        print(
            f"H={h:>3} | "
            f"IC {s['ic_mean']:+.6f}/{s['ic_std']:.6f}/{s['icir']:+.4f}/{s['ic_win_rate']:.2%} | "
            f"RankIC {s['rank_ic_mean']:+.6f}/{s['rank_ic_std']:.6f}/{s['rank_icir']:+.4f}/{s['rank_ic_win_rate']:.2%} | "
            f"HoldPnl {s['holding_total_return']:+.4f}"
        )
    print("=" * 88)


def main() -> None:
    base_dir = Path(__file__).parent
    cfg = EvalConfig(
        factor_path=base_dir / "factor_output.parquet",
        vwap_path=base_dir / "NQ_vwap.parquet",
        horizons=(1, 5, 10, 20),
        zscore_window=200,
        winsor_quantile=0.01,
        n_quantiles=10,
        min_obs_per_day=30,
    )

    results = run_evaluation(cfg)
    print_brief(results)
    save_results(results, out_dir=base_dir / "evaluation_output")
    print(f"Results saved to: {base_dir / 'evaluation_output'}")


if __name__ == "__main__":
    main()
