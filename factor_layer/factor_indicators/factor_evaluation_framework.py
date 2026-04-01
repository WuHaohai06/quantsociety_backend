from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Market Status Label
# ---------------------------------------------------------------------------
class MarketStatusLabel:
    """
    Creates market status classification labels for factor analysis.

    All labels are computed strictly using data up to (and including) time t,
    with no look-ahead bias.

    Parameters
    ----------
    market_df : pd.DataFrame
        1-minute OHLCV bar data (e.g., NQ.parquet).
    timestamp_col : str
        Column name for the bar timestamp.
    close_col : str
        Column name for the close/settlement price.
    volume_col : str
        Column name for the bar volume.
    vol_window : int
        Number of bars used to compute rolling realized volatility.
        Default 120 = 2 hours of 1-minute bars.
    vol_rank_window : int
        Rolling window over which the realized-vol percentile rank is computed.
        Default 7200 ≈ 5 calendar days * 1440 min/day (one week of history).
    vol_low_pct : float
        Percentile threshold below which a bar is classified as 'LV'.
    vol_high_pct : float
        Percentile threshold at or above which a bar is classified as 'HV'.
    """

    # Regular Trading Hours for NQ futures (CME Globex, ET)
    # RTH open:  09:30  →  encoded as 930
    # RTH close: 16:00  →  encoded as 1600  (exclusive upper bound)
    # Open  session:  09:30–10:00  (first 30 min)
    # Midday session: 10:00–15:30
    # Close  session: 15:30–16:00  (last  30 min)
    _OPEN_START:   int = 930
    _OPEN_END:     int = 1000
    _CLOSE_START:  int = 1530
    _RTH_END:      int = 1600

    def __init__(
        self,
        market_df: pd.DataFrame,
        timestamp_col: str = "data",
        close_col: str = "close",
        volume_col: str = "volume",
        vol_window: int = 120,
        vol_rank_window: int = 7200,
        vol_low_pct: float = 1.0 / 3.0,
        vol_high_pct: float = 2.0 / 3.0,
    ) -> None:
        df = market_df[[timestamp_col, close_col, volume_col]].copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        df = df.drop_duplicates(subset=[timestamp_col]).sort_values(timestamp_col)
        df = df.set_index(timestamp_col)
        df.index.name = "timestamp"

        self._df = df
        self._close_col = close_col
        self._volume_col = volume_col
        self._vol_window = vol_window
        self._vol_rank_window = vol_rank_window
        self._vol_low_pct = vol_low_pct
        self._vol_high_pct = vol_high_pct

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_parquet(
        cls,
        path: Path,
        timestamp_col: str = "data",
        close_col: str = "close",
        volume_col: str = "volume",
        **kwargs,
    ) -> "MarketStatusLabel":
        """Load market data from a parquet file and construct the label generator."""
        df = pd.read_parquet(path, columns=[timestamp_col, close_col, volume_col])
        return cls(df, timestamp_col=timestamp_col, close_col=close_col,
                   volume_col=volume_col, **kwargs)

    # ------------------------------------------------------------------
    # Public label methods
    # ------------------------------------------------------------------
    def volatility_regime(self) -> pd.Series:
        """
        Classify each bar's volatility regime using a rolling percentile rank
        of realized volatility.

        Steps (all look-back only, no future data):
          1. Compute 1-bar log return: ln(close_t / close_{t-1}).
          2. Rolling std of log returns over ``vol_window`` bars  →  realized vol.
          3. Rolling percentile rank of realized vol over ``vol_rank_window`` bars.
          4. Classify:
               pct_rank < vol_low_pct          →  'LV'  (low volatility)
               vol_low_pct <= pct_rank < vol_high_pct  →  'MV'  (medium volatility)
               pct_rank >= vol_high_pct        →  'HV'  (high volatility)
               NaN (insufficient history)      →  pd.NA

        Returns
        -------
        pd.Series[str]
            Index matches the market data index; name = 'volatility_regime'.
        """
        close = self._df[self._close_col]
        log_ret = np.log(close / close.shift(1))

        # Rolling realized vol — uses only past vol_window bars
        realized_vol = log_ret.rolling(
            window=self._vol_window, min_periods=self._vol_window
        ).std(ddof=1)

        # Rolling percentile rank — pct=True gives rank / count ∈ (0, 1]
        # Uses only older/equal values within the window, so no look-ahead.
        pct_rank = realized_vol.rolling(
            window=self._vol_rank_window, min_periods=self._vol_rank_window
        ).rank(pct=True)

        labels = pd.array(
            ["MV"] * len(self._df), dtype=pd.StringDtype()
        )
        lv_mask = (pct_rank < self._vol_low_pct).to_numpy()
        hv_mask = (pct_rank >= self._vol_high_pct).to_numpy()
        na_mask = pct_rank.isna().to_numpy()

        labels[lv_mask] = "LV"
        labels[hv_mask] = "HV"
        labels[na_mask] = pd.NA

        result = pd.Series(labels, index=self._df.index, name="volatility_regime")
        return result

    def intraday_session(self) -> pd.Series:
        """
        Classify each bar by its intraday trading session.

        Classification is purely time-based (no computation, trivially no
        look-ahead bias):
          - 'OPEN':      09:30–10:00 ET  (first 30 min of RTH)
          - 'MIDDAY':    10:00–15:30 ET
          - 'CLOSE':     15:30–16:00 ET  (last  30 min of RTH)
          - 'OVERNIGHT': outside RTH (pre-market / after-hours / globex night)

        Returns
        -------
        pd.Series[str]
            Index matches the market data index; name = 'intraday_session'.
        """
        ts = self._df.index
        # Encode time as integer HHMM for fast vectorized comparison
        hhmm = ts.hour * 100 + ts.minute

        labels = pd.array(
            ["OVERNIGHT"] * len(ts), dtype=pd.StringDtype()
        )

        open_mask   = (hhmm >= self._OPEN_START)  & (hhmm < self._OPEN_END)
        midday_mask = (hhmm >= self._OPEN_END)    & (hhmm < self._CLOSE_START)
        close_mask  = (hhmm >= self._CLOSE_START) & (hhmm < self._RTH_END)

        labels[open_mask]   = "OPEN"
        labels[midday_mask] = "MIDDAY"
        labels[close_mask]  = "CLOSE"

        result = pd.Series(labels, index=ts, name="intraday_session")
        return result


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Data helpers (module-level utilities)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Predictivity — IC / RankIC related evaluation
# ---------------------------------------------------------------------------
class Predictivity:

    @staticmethod
    def daily_corr(
        series_x: pd.Series,
        series_y: pd.Series,
        date_index: pd.Series,
        method: str,
        min_obs: int,
    ) -> pd.Series:
        tmp = pd.DataFrame({"x": series_x, "y": series_y, "date": date_index})

        def _corr_one_day(g: pd.DataFrame) -> float:
            valid = g.dropna()
            if len(valid) < min_obs:
                return np.nan
            return valid["x"].corr(valid["y"], method=method)

        out = tmp.groupby("date", sort=True)[["x", "y"]].apply(_corr_one_day)
        out.name = f"{method}_corr"
        return out

    @staticmethod
    def summary_from_daily_series(s: pd.Series) -> Dict[str, float]:
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

    @classmethod
    def evaluate(
        cls,
        factor_eval: pd.Series,
        target_eval: pd.Series,
        date_index: pd.Series,
        min_obs: int,
    ) -> Dict[str, object]:
        daily_ic = cls.daily_corr(factor_eval, target_eval, date_index, method="pearson", min_obs=min_obs)
        daily_rank_ic = cls.daily_corr(factor_eval, target_eval, date_index, method="spearman", min_obs=min_obs)
        ic_summary = cls.summary_from_daily_series(daily_ic)
        rank_ic_summary = cls.summary_from_daily_series(daily_rank_ic)
        return {
            "daily_ic": daily_ic.rename("ic"),
            "daily_rank_ic": daily_rank_ic.rename("rank_ic"),
            "ic_summary": ic_summary,
            "rank_ic_summary": rank_ic_summary,
        }


# ---------------------------------------------------------------------------
# Backtest — layered / long-short holding backtest
# ---------------------------------------------------------------------------
class Backtest:

    @staticmethod
    def _assign_quantile_groups(
        factor_for_eval: pd.Series,
        n_quantiles: int,
        lookback: int = 1000,
    ) -> pd.Series:
        groups_all = pd.Series(np.nan, index=factor_for_eval.index, dtype=float)
        valid = factor_for_eval.dropna()
        if valid.empty:
            return groups_all.rename("group")

        values = valid.to_numpy()
        n = len(values)
        grp_arr = np.full(n, np.nan)

        for i in range(lookback - 1, n):
            window = values[i - lookback + 1 : i + 1]
            breaks = np.quantile(window, np.linspace(0, 1, n_quantiles + 1))
            grp_arr[i] = np.searchsorted(breaks[1:-1], values[i], side="right") + 1

        groups_all.loc[valid.index] = grp_arr
        return groups_all.rename("group")

    @staticmethod
    def _capped_position_signal(
        long_trigger: pd.Series,
        short_trigger: pd.Series,
        horizon: int,
    ) -> pd.Series:
        n = len(long_trigger)
        lt = long_trigger.to_numpy(dtype=bool)
        st = short_trigger.to_numpy(dtype=bool)

        long_events  = [(int(i),  1) for i in np.where(lt)[0]]
        short_events = [(int(i), -1) for i in np.where(st)[0]]
        events = sorted(long_events + short_events, key=lambda x: x[0])

        pos = np.zeros(n, dtype=np.float64)
        hold_until = -1

        for idx, direction in events:
            if idx <= hold_until:
                continue
            end = min(idx + horizon, n)
            pos[idx:end] = direction
            hold_until = end - 1

        return pd.Series(pos, index=long_trigger.index, name="net_position")

    @staticmethod
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

    @classmethod
    def layered_single_period_return(
        cls,
        factor_for_eval: pd.Series,
        target_return_n: pd.Series,
        n_quantiles: int,
        horizon: int,
        lookback: int = 1000,
    ) -> pd.Series:
        tmp = pd.DataFrame({"factor": factor_for_eval, "ret_n": target_return_n}).dropna()
        if tmp.empty:
            return pd.Series(dtype=float, name="avg_single_period_ret")

        factors = tmp["factor"].to_numpy()
        n = len(factors)
        groups = np.full(n, np.nan)

        for i in range(lookback - 1, n):
            window = factors[i - lookback + 1 : i + 1]
            breaks = np.quantile(window, np.linspace(0, 1, n_quantiles + 1))
            groups[i] = np.searchsorted(breaks[1:-1], factors[i], side="right") + 1

        tmp["group"] = groups
        valid = tmp.dropna(subset=["group"])

        grp_mean_n = valid.groupby("group")["ret_n"].mean()
        grp_mean_single = np.power(1.0 + grp_mean_n, 1.0 / horizon) - 1.0
        grp_mean_single.index = grp_mean_single.index.astype(int)
        grp_mean_single.index.name = "group"
        grp_mean_single.name = "avg_single_period_ret"
        return grp_mean_single

    @classmethod
    def long_short_holding_pnl(
        cls,
        factor_for_eval: pd.Series,
        vwap: pd.Series,
        n_quantiles: int,
        horizon: int,
    ) -> pd.DataFrame:
        groups = cls._assign_quantile_groups(factor_for_eval, n_quantiles=n_quantiles)

        long_trigger  = (groups == n_quantiles).shift(1).fillna(0.0)
        short_trigger = (groups == 1).shift(1).fillna(0.0)

        net_position = cls._capped_position_signal(long_trigger, short_trigger, horizon)

        one_period_ret = vwap.shift(-1) / vwap - 1.0
        pnl = (net_position * one_period_ret).rename("pnl")
        cum_pnl = (1.0 + pnl.fillna(0.0)).cumprod().rename("cum_pnl")

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

    @staticmethod
    def apply_transaction_cost(holding_pnl: pd.DataFrame, fee_rate: float) -> pd.DataFrame:
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

    @classmethod
    def holding_stats(cls, holding_pnl: pd.DataFrame) -> Dict[str, float]:
        _empty = {
            "holding_sharpe": np.nan,
            "holding_max_drawdown": np.nan,
            "holding_annual_return": np.nan,
            "holding_turnover": np.nan,
            "holding_avg_daily_trades": np.nan,
            "holding_win_rate": np.nan,
            "holding_profit_loss_ratio": np.nan,
        }
        if holding_pnl is None or holding_pnl.empty:
            return _empty

        pnl = holding_pnl["pnl"].dropna()
        equity = holding_pnl["cum_pnl"].reindex(pnl.index).dropna()
        net_pos = holding_pnl["net_position"].reindex(pnl.index).fillna(0.0)
        if pnl.empty:
            return _empty

        periods_per_year = cls._infer_periods_per_year(pnl.index)
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

    @classmethod
    def evaluate(
        cls,
        factor_eval: pd.Series,
        target_eval: pd.Series,
        vwap: pd.Series,
        n_quantiles: int,
        horizon: int,
        fee_rate: float,
    ) -> Dict[str, object]:
        layered = cls.layered_single_period_return(
            factor_for_eval=factor_eval,
            target_return_n=target_eval,
            n_quantiles=n_quantiles,
            horizon=horizon,
        )
        holding_pnl = cls.long_short_holding_pnl(
            factor_for_eval=factor_eval,
            vwap=vwap,
            n_quantiles=n_quantiles,
            horizon=horizon,
        )
        holding_pnl_with_cost = cls.apply_transaction_cost(holding_pnl, fee_rate)
        h_stats = cls.holding_stats(holding_pnl)
        h_stats_with_cost = cls.holding_stats(holding_pnl_with_cost)
        holding_total_ret = float(holding_pnl["cum_pnl"].iloc[-1] - 1.0) if not holding_pnl.empty else np.nan
        holding_total_ret_with_cost = (
            float(holding_pnl_with_cost["cum_pnl"].iloc[-1] - 1.0) if not holding_pnl_with_cost.empty else np.nan
        )
        return {
            "layered_single_period": layered,
            "holding_pnl": holding_pnl,
            "holding_stats": h_stats,
            "holding_pnl_with_cost": holding_pnl_with_cost,
            "holding_stats_with_cost": h_stats_with_cost,
            "holding_total_return": holding_total_ret,
            "holding_total_return_with_cost": holding_total_ret_with_cost,
        }


# ---------------------------------------------------------------------------
# Status Analyzer — per-status factor evaluation
# ---------------------------------------------------------------------------
class StatusAnalyzer:
    """Analyze factor performance segmented by market status labels.

    Preprocessing exactly mirrors ``evaluate_horizon``:
      1. align factor & vwap on overlapping timestamps
      2. rolling z-score normalisation of the raw factor
      3. per-day winsorisation
      4. single-period forward return: ``vwap[t+1] / vwap[t] − 1``
         paired with the factor value at time *t*

    Two built-in status methods are supported via ``MarketStatusLabel``:
      - ``'volatility_regime'``  →  LV / MV / HV
      - ``'intraday_session'``   →  OPEN / MIDDAY / CLOSE / OVERNIGHT

    Parameters
    ----------
    factor : pd.Series
        Factor value series (index = timestamp).
    vwap : pd.Series
        VWAP price series (index = timestamp).
    status_labels : pd.Series
        Categorical / string label series (index = timestamp).  Must share
        timestamps with *factor* and *vwap*.
    zscore_window : int
        Rolling window for z-score normalisation.
    winsor_quantile : float
        Per-day winsorisation quantile (both tails).
    n_quantiles : int
        Number of quantile groups for the long-short backtest.
    min_obs : int
        Minimum observations per day for IC calculation.
    fee_rate : float
        One-way transaction cost rate applied to position changes.
    """

    def __init__(
        self,
        factor: pd.Series,
        vwap: pd.Series,
        status_labels: pd.Series,
        zscore_window: int = 200,
        winsor_quantile: float = 0.01,
        n_quantiles: int = 10,
        min_obs: int = 30,
        fee_rate: float = 0.00002,
    ) -> None:
        # --- align --------------------------------------------------------
        aligned = align_on_overlap_reindex(factor, vwap)
        aligned["factor_z"] = rolling_zscore(aligned["factor_raw"], window=zscore_window)
        aligned["date"] = aligned.index.date

        # single-period forward return: factor_t → ret from t+1 to t+2
        aligned["fwd_ret"] = aligned["vwap"].shift(-2) / aligned["vwap"].shift(-1) - 1.0

        # winsorise factor_z by day
        aligned["factor_eval"] = _winsorize_by_day(
            aligned["factor_z"], aligned["date"], winsor_quantile,
        )

        # join status labels (reindex to aligned timestamps)
        aligned["status"] = status_labels.reindex(aligned.index)

        self._df = aligned
        self._n_quantiles = n_quantiles
        self._min_obs = min_obs
        self._fee_rate = fee_rate

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_parquet(
        cls,
        factor_path: Path,
        vwap_path: Path,
        market_path: Path,
        status_method: str = "volatility_regime",
        factor_col: str = "factor",
        vwap_col: str = "vwap",
        timestamp_col: str = "timestamp",
        **kwargs,
    ) -> "StatusAnalyzer":
        """Build a ``StatusAnalyzer`` directly from parquet files.

        Parameters
        ----------
        factor_path, vwap_path : Path
            Parquet files with columns ``[timestamp_col, factor_col/vwap_col]``.
        market_path : Path
            Raw OHLCV parquet (e.g. NQ.parquet) used by ``MarketStatusLabel``.
        status_method : str
            ``'volatility_regime'`` or ``'intraday_session'``.
        """
        factor = _load_series(factor_path, timestamp_col, factor_col)
        vwap = _load_series(vwap_path, timestamp_col, vwap_col)

        labeler = MarketStatusLabel.from_parquet(market_path)
        if status_method == "volatility_regime":
            status_labels = labeler.volatility_regime()
        elif status_method == "intraday_session":
            status_labels = labeler.intraday_session()
        else:
            raise ValueError(
                f"Unknown status_method '{status_method}'. "
                "Use 'volatility_regime' or 'intraday_session'."
            )
        return cls(factor, vwap, status_labels, **kwargs)

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------
    def _ic_for_group(
        self,
        sub: pd.DataFrame,
    ) -> Dict[str, object]:
        """Compute daily IC / rank-IC for a single status group."""
        return Predictivity.evaluate(
            factor_eval=sub["factor_eval"],
            target_eval=sub["fwd_ret"],
            date_index=sub["date"],
            min_obs=self._min_obs,
        )

    def _backtest_for_group(
        self,
        sub: pd.DataFrame,
    ) -> Dict[str, object]:
        """Run long-short holding backtest for a single status group."""
        factor_eval = sub["factor_eval"]
        vwap = sub["vwap"]

        holding_pnl = Backtest.long_short_holding_pnl(
            factor_for_eval=factor_eval,
            vwap=vwap,
            n_quantiles=self._n_quantiles,
            horizon=1,
        )
        holding_pnl_with_cost = Backtest.apply_transaction_cost(holding_pnl, self._fee_rate)
        stats = Backtest.holding_stats(holding_pnl)
        stats_with_cost = Backtest.holding_stats(holding_pnl_with_cost)
        total_ret = float(holding_pnl["cum_pnl"].iloc[-1] - 1.0) if not holding_pnl.empty else np.nan
        total_ret_with_cost = (
            float(holding_pnl_with_cost["cum_pnl"].iloc[-1] - 1.0)
            if not holding_pnl_with_cost.empty
            else np.nan
        )
        return {
            "holding_pnl": holding_pnl,
            "holding_stats": stats,
            "holding_pnl_with_cost": holding_pnl_with_cost,
            "holding_stats_with_cost": stats_with_cost,
            "holding_total_return": total_ret,
            "holding_total_return_with_cost": total_ret_with_cost,
        }

    def analyze(self) -> Dict[str, Dict[str, object]]:
        """Run the full per-status analysis.

        Returns
        -------
        dict
            ``{ status_value: { 'ic_summary', 'rank_ic_summary',
            'daily_ic', 'daily_rank_ic', 'holding_pnl',
            'holding_stats', ... } }``
        """
        df = self._df.dropna(subset=["status"])
        groups = df.groupby("status", sort=True)
        results: Dict[str, Dict[str, object]] = {}

        for status_val, idx in groups.groups.items():
            sub = df.loc[idx].copy()
            if sub.empty:
                continue

            ic_result = self._ic_for_group(sub)
            bt_result = self._backtest_for_group(sub)

            results[str(status_val)] = {
                "n_bars": len(sub),
                "ic_summary": ic_result["ic_summary"],
                "rank_ic_summary": ic_result["rank_ic_summary"],
                "daily_ic": ic_result["daily_ic"],
                "daily_rank_ic": ic_result["daily_rank_ic"],
                **bt_result,
            }

        return results

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------
    @staticmethod
    def print_summary(results: Dict[str, Dict[str, object]]) -> None:
        """Print a compact summary table for all status groups."""
        header = (
            f"{'Status':<12} | {'#Bars':>8} | "
            f"{'IC_mean':>9} {'IC_IR':>8} {'IC_win':>7} | "
            f"{'RkIC_mean':>9} {'RkIC_IR':>8} {'RkIC_win':>8} | "
            f"{'Sharpe':>8} {'MaxDD':>8} {'WinRate':>8} {'TotalRet':>9}"
        )
        print("=" * len(header))
        print("Status Analyzer — per-status factor evaluation")
        print("=" * len(header))
        print(header)
        print("-" * len(header))

        for status_val in sorted(results):
            r = results[status_val]
            ic = r["ic_summary"]
            ric = r["rank_ic_summary"]
            hs = r["holding_stats"]
            print(
                f"{status_val:<12} | {r['n_bars']:>8d} | "
                f"{ic['mean']:>+9.6f} {ic['ir']:>+8.4f} {ic['win_rate']:>7.2%} | "
                f"{ric['mean']:>+9.6f} {ric['ir']:>+8.4f} {ric['win_rate']:>8.2%} | "
                f"{hs['holding_sharpe']:>+8.3f} {hs['holding_max_drawdown']:>8.4f} "
                f"{hs['holding_win_rate']:>8.2%} {r['holding_total_return']:>+9.4f}"
            )
        print("=" * len(header))

    def summary_dataframe(self, results: Dict[str, Dict[str, object]] | None = None) -> pd.DataFrame:
        """Return the per-status summary as a ``pd.DataFrame``."""
        if results is None:
            results = self.analyze()

        rows = []
        for status_val in sorted(results):
            r = results[status_val]
            ic = r["ic_summary"]
            ric = r["rank_ic_summary"]
            hs = r["holding_stats"]
            hs_c = r["holding_stats_with_cost"]
            rows.append(
                {
                    "status": status_val,
                    "n_bars": r["n_bars"],
                    "ic_mean": ic["mean"],
                    "ic_std": ic["std"],
                    "icir": ic["ir"],
                    "ic_win_rate": ic["win_rate"],
                    "ic_n_days": ic["n_days"],
                    "rank_ic_mean": ric["mean"],
                    "rank_ic_std": ric["std"],
                    "rank_icir": ric["ir"],
                    "rank_ic_win_rate": ric["win_rate"],
                    "rank_ic_n_days": ric["n_days"],
                    "holding_sharpe": hs["holding_sharpe"],
                    "holding_max_drawdown": hs["holding_max_drawdown"],
                    "holding_win_rate": hs["holding_win_rate"],
                    "holding_total_return": r["holding_total_return"],
                    "holding_sharpe_with_cost": hs_c["holding_sharpe"],
                    "holding_max_drawdown_with_cost": hs_c["holding_max_drawdown"],
                    "holding_win_rate_with_cost": hs_c["holding_win_rate"],
                    "holding_total_return_with_cost": r["holding_total_return_with_cost"],
                }
            )
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def evaluate_horizon(base_df: pd.DataFrame, horizon: int, cfg: EvalConfig) -> Dict[str, object]:
    df = base_df.copy()
    df["target_ret_n"] = make_forward_vwap_return(df["vwap"], horizon)

    eligible = _eligibility_mask_by_day(df, horizon)
    df["factor_eval"] = df["factor_z"].where(eligible)
    df["target_eval"] = df["target_ret_n"].where(eligible)

    df["factor_eval"] = _winsorize_by_day(df["factor_eval"], df["date"], cfg.winsor_quantile)

    pred = Predictivity.evaluate(
        factor_eval=df["factor_eval"],
        target_eval=df["target_eval"],
        date_index=df["date"],
        min_obs=cfg.min_obs_per_day,
    )
    bt = Backtest.evaluate(
        factor_eval=df["factor_eval"],
        target_eval=df["target_eval"],
        vwap=df["vwap"],
        n_quantiles=cfg.n_quantiles,
        horizon=horizon,
        fee_rate=cfg.holding_fee_rate,
    )

    ic_summary = pred["ic_summary"]
    rank_ic_summary = pred["rank_ic_summary"]

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
        "holding_total_return": bt["holding_total_return"],
        **bt["holding_stats"],
        "holding_total_return_with_cost": bt["holding_total_return_with_cost"],
        **{f"{k}_with_cost": v for k, v in bt["holding_stats_with_cost"].items()},
    }

    return {
        "summary": summary,
        "daily_ic": pred["daily_ic"],
        "daily_rank_ic": pred["daily_rank_ic"],
        "layered_single_period": bt["layered_single_period"],
        "holding_pnl": bt["holding_pnl"],
        "holding_stats": bt["holding_stats"],
        "holding_pnl_with_cost": bt["holding_pnl_with_cost"],
        "holding_stats_with_cost": bt["holding_stats_with_cost"],
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
