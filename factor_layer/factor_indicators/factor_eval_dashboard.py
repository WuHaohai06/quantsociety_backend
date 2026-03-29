from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

from factor_evaluation_framework import EvalConfig, run_evaluation


HORIZONS: Tuple[int, ...] = (1, 5, 10, 20)


_CACHE_VERSION = "v9"  # bump whenever evaluation module outputs change


@st.cache_data(show_spinner=True)
def run_all_metrics(base_dir_str: str, _cache_version: str = _CACHE_VERSION) -> Dict[int, Dict[str, object]]:
    base_dir = Path(base_dir_str)
    cfg = EvalConfig(
        factor_path=base_dir / "factor_output.parquet",
        vwap_path=base_dir / "NQ_vwap.parquet",
        horizons=HORIZONS,
        zscore_window=200,
        winsor_quantile=0.01,
        n_quantiles=10,
        min_obs_per_day=30,
    )
    return run_evaluation(cfg)


def build_summary_df(results: Dict[int, Dict[str, object]]) -> pd.DataFrame:
    summary_df = pd.DataFrame([payload["summary"] for payload in results.values()])
    summary_df = summary_df.sort_values("horizon").reset_index(drop=True)
    return summary_df


def build_layered_df(results: Dict[int, Dict[str, object]]) -> pd.DataFrame:
    rows = []
    for n, payload in sorted(results.items()):
        layered = payload["layered_single_period"]
        for group, value in layered.items():
            rows.append(
                {
                    "horizon": int(n),
                    "group": int(group),
                    "single_period_ret": float(value),
                }
            )
    return pd.DataFrame(rows)


def build_long_short_df(layered_df: pd.DataFrame) -> pd.DataFrame:
    records = []
    if layered_df.empty:
        return pd.DataFrame(columns=["horizon", "long_short_ret"])

    for n, g in layered_df.groupby("horizon", sort=True):
        g = g.sort_values("group")
        first = g.iloc[0]["single_period_ret"]
        last = g.iloc[-1]["single_period_ret"]
        # Long-short defined as Group10 - Group1
        records.append({"horizon": int(n), "long_short_ret": float(last - first)})

    return pd.DataFrame(records).sort_values("horizon")


def build_holding_pnl_curve_df(results: Dict[int, Dict[str, object]], payload_key: str = "holding_pnl") -> pd.DataFrame:
    frames = []
    for n, payload in sorted(results.items()):
        pnl_df = payload.get(payload_key)
        if pnl_df is None or pnl_df.empty:
            continue
        # Downsample to daily: take the last cum_pnl value of each calendar day
        daily = (
            pnl_df[["cum_pnl"]]
            .dropna()
            .resample("D")
            .last()
            .dropna()
            .reset_index()
            .rename(columns={"timestamp": "timestamp"})
        )
        daily["horizon"] = int(n)
        frames.append(daily[["timestamp", "horizon", "cum_pnl"]])
    if not frames:
        return pd.DataFrame(columns=["timestamp", "horizon", "cum_pnl"])
    out = pd.concat(frames, ignore_index=True).sort_values(["timestamp", "horizon"])
    return out


def build_holding_stats_df(
    results: Dict[int, Dict[str, object]],
    stats_key: str = "holding_stats",
    stat_cols: list[str] | None = None,
) -> pd.DataFrame:
    rows = []
    if stat_cols is None:
        stat_cols = [
            "holding_sharpe",
            "holding_max_drawdown",
            "holding_annual_return",
            "holding_turnover",
            "holding_avg_daily_trades",
            "holding_win_rate",
            "holding_profit_loss_ratio",
        ]
    for n, payload in sorted(results.items()):
        # Pull stats from dedicated key first; fall back to summary dict for robustness
        stats = payload.get(stats_key) or {}
        if not stats:
            stats = payload.get("summary", {})
        row = {"horizon": int(n)}
        for c in stat_cols:
            v = stats.get(c)
            row[c] = float(v) if v is not None and not (isinstance(v, float) and v != v) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def render_holding_stats_grid(holding_stats_df: pd.DataFrame, stat_cols: list[str], metric_name_map: Dict[str, str]) -> None:
    if holding_stats_df.empty:
        st.warning("Holding stats data is empty.")
        return

    for i in range(0, len(holding_stats_df), 2):
        chunk = holding_stats_df.iloc[i : i + 2]
        cols = st.columns(2)
        for j, (_, row) in enumerate(chunk.iterrows()):
            with cols[j]:
                st.markdown(f"### N={int(row['horizon'])}")
                metric_rows = []
                for c in stat_cols:
                    val = row.get(c, float("nan"))
                    if pd.isna(val):
                        disp = "NaN"
                    elif "max_drawdown" in c or "annual_return" in c or "win_rate" in c:
                        disp = f"{val:.2%}"
                    else:
                        disp = f"{val:.4f}"
                    metric_rows.append({"Metric": metric_name_map[c], "Value": disp})
                st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, height=250)


def metric_decay_figure(summary_df: pd.DataFrame, metric_col: str, title: str) -> px.line:
    fig = px.line(
        summary_df,
        x="horizon",
        y=metric_col,
        markers=True,
        title=title,
    )
    fig.update_layout(xaxis_title="N", yaxis_title="Value", hovermode="x unified")
    fig.update_layout(height=250, margin=dict(l=20, r=10, t=40, b=20))
    return fig


def main() -> None:
    st.set_page_config(page_title="Factor Evaluation Dashboard", layout="wide")
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 0.8rem;
                padding-bottom: 0.6rem;
                padding-left: 1.0rem;
                padding-right: 1.0rem;
                max-width: 98%;
            }
            div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stPlotlyChart"]) {
                margin-bottom: 0.3rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Factor Evaluation Dashboard")
    st.caption("N = 1, 5, 10, 20 | Rolling z-score(200) | Winsorize 1%")

    base_dir = Path(__file__).parent

    with st.spinner("Running evaluation metrics..."):
        results = run_all_metrics(str(base_dir), _cache_version=_CACHE_VERSION)

    summary_df = build_summary_df(results)
    layered_df = build_layered_df(results)
    long_short_df = build_long_short_df(layered_df)
    holding_pnl_curve_df = build_holding_pnl_curve_df(results)
    holding_stats_df = build_holding_stats_df(results)
    holding_pnl_curve_with_cost_df = build_holding_pnl_curve_df(results, payload_key="holding_pnl_with_cost")
    holding_stats_with_cost_df = build_holding_stats_df(
        results,
        stats_key="holding_stats_with_cost",
        stat_cols=[
            "holding_sharpe",
            "holding_max_drawdown",
            "holding_annual_return",
            "holding_turnover",
            "holding_avg_daily_trades",
            "holding_win_rate",
            "holding_profit_loss_ratio",
        ],
    )

    stat_cols = [
        "holding_sharpe",
        "holding_max_drawdown",
        "holding_annual_return",
        "holding_turnover",
        "holding_avg_daily_trades",
        "holding_win_rate",
        "holding_profit_loss_ratio",
    ]
    metric_name_map = {
        "holding_sharpe": "Annualized Sharpe",
        "holding_max_drawdown": "Max Drawdown",
        "holding_annual_return": "Annualized Return",
        "holding_turnover": "Turnover",
        "holding_avg_daily_trades": "Avg Daily Trades",
        "holding_win_rate": "Win Rate",
        "holding_profit_loss_ratio": "Profit/Loss Ratio",
    }

    st.subheader("1) Metrics Decay by N")
    metric_specs = [
        ("ic_mean", "IC vs N"),
        ("rank_ic_mean", "RankIC vs N"),
        ("icir", "ICIR vs N"),
        ("rank_icir", "RankICIR vs N"),
        ("ic_win_rate", "IC Win Rate vs N"),
    ]

    cols_top = st.columns(3)
    for i, (metric_col, title) in enumerate(metric_specs):
        fig = metric_decay_figure(summary_df, metric_col, title)
        cols_top[i % 3].plotly_chart(fig, use_container_width=True)

    st.subheader("2) Layered Backtest: Single-Period Return")
    if layered_df.empty:
        st.warning("Layered backtest data is empty.")
    else:
        layered_df["horizon"] = layered_df["horizon"].astype(str)
        layered_df["group"] = layered_df["group"].astype(str)
        bar_fig = px.bar(
            layered_df,
            x="horizon",
            y="single_period_ret",
            color="group",
            barmode="group",
            title="10-Group Layered Single-Period Returns by N",
        )
        bar_fig.update_layout(
            xaxis_title="N",
            yaxis_title="Single-Period Return",
            height=320,
            margin=dict(l=20, r=10, t=40, b=20),
            legend_title_text="Group",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
        )
        st.plotly_chart(bar_fig, use_container_width=True)

    st.subheader("3) Long-Short Return Decay by N")
    st.caption("Long-Short = Group10 - Group1")
    if long_short_df.empty:
        st.warning("Long-short data is empty.")
    else:
        ls_fig = px.line(
            long_short_df,
            x="horizon",
            y="long_short_ret",
            markers=True,
            title="Long-Short Return vs N",
        )
        ls_fig.update_layout(
            xaxis_title="N",
            yaxis_title="Long-Short Return",
            hovermode="x unified",
            height=260,
            margin=dict(l=20, r=10, t=40, b=20),
        )
        st.plotly_chart(ls_fig, use_container_width=True)

    st.subheader("4) Layered Long-Short Holding PnL Curve")
    st.caption("Rule: Group10 opens long, Group1 opens short, each signal holds N periods")
    if holding_pnl_curve_df.empty:
        st.warning("Holding PnL curve data is empty.")
    else:
        holding_pnl_curve_df["horizon"] = holding_pnl_curve_df["horizon"].astype(str)
        pnl_curve_fig = px.line(
            holding_pnl_curve_df,
            x="timestamp",
            y="cum_pnl",
            color="horizon",
            title="Holding PnL Curves (N=1,5,10,20)",
        )
        pnl_curve_fig.update_layout(
            xaxis_title="Timestamp",
            yaxis_title="Equity (Base = 1)",
            height=320,
            margin=dict(l=20, r=10, t=40, b=20),
            legend_title_text="N",
            hovermode="x unified",
        )
        st.plotly_chart(pnl_curve_fig, use_container_width=True)

    st.caption("Holding Backtest Stats by N")
    render_holding_stats_grid(holding_stats_df, stat_cols, metric_name_map)

    st.subheader("5) Layered Long-Short Holding PnL Curve After Fee")
    st.caption("One-way fee = 0.002%; charged on every position change, including open, close, and flip")
    if holding_pnl_curve_with_cost_df.empty:
        st.warning("Holding PnL curve with fee data is empty.")
    else:
        holding_pnl_curve_with_cost_df["horizon"] = holding_pnl_curve_with_cost_df["horizon"].astype(str)
        pnl_curve_fee_fig = px.line(
            holding_pnl_curve_with_cost_df,
            x="timestamp",
            y="cum_pnl",
            color="horizon",
            title="Holding PnL Curves After 0.002% One-Way Fee (N=1,5,10,20)",
        )
        pnl_curve_fee_fig.update_layout(
            xaxis_title="Timestamp",
            yaxis_title="Equity (Base = 1)",
            height=320,
            margin=dict(l=20, r=10, t=40, b=20),
            legend_title_text="N",
            hovermode="x unified",
        )
        st.plotly_chart(pnl_curve_fee_fig, use_container_width=True)

    st.caption("Holding Backtest Stats by N After Fee")
    render_holding_stats_grid(holding_stats_with_cost_df, stat_cols, metric_name_map)

    st.subheader("Data Tables")
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "Summary",
        "Layered",
        "Long-Short",
        "Holding PnL",
        "Holding Stats",
        "Holding PnL After Fee",
        "Holding Stats After Fee",
    ])
    with t1:
        st.dataframe(summary_df, use_container_width=True, height=220)
    with t2:
        if not layered_df.empty:
            st.dataframe(layered_df.sort_values(["horizon", "group"]), use_container_width=True, height=260)
    with t3:
        if not long_short_df.empty:
            st.dataframe(long_short_df, use_container_width=True, height=180)
    with t4:
        if not holding_pnl_curve_df.empty:
            st.dataframe(holding_pnl_curve_df, use_container_width=True, height=260)
    with t5:
        if not holding_stats_df.empty:
            st.dataframe(holding_stats_df, use_container_width=True, height=220)
    with t6:
        if not holding_pnl_curve_with_cost_df.empty:
            st.dataframe(holding_pnl_curve_with_cost_df, use_container_width=True, height=260)
    with t7:
        if not holding_stats_with_cost_df.empty:
            st.dataframe(holding_stats_with_cost_df, use_container_width=True, height=220)


if __name__ == "__main__":
    main()
