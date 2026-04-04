from __future__ import annotations

"""回测输入契约与冻结 schema：单标的 ``target_position``、多标的 ``target_weights`` 的校验与对齐。

输出报告必须包含 ``REQUIRED_*_KEYS`` 所列键；具体报告组装见 ``report.py``。
"""

from collections.abc import Iterable

import pandas as pd

BACKTEST_SCHEMA_VERSION = "1.0"

REQUIRED_RETURNS_KEYS = (
    "equity_curve",
    "period_return",
    "realized_position",
)

REQUIRED_METRICS_KEYS = (
    "total_return",
    "annual_return",
    "volatility",
    "sharpe",
    "max_drawdown",
    "turnover",
    "trades",
    "commission_paid",
)

REQUIRED_SUMMARY_KEYS = (
    "schema_version",
    "start",
    "end",
    "bars",
    "initial_cash",
    "final_equity",
)


def _to_timestamp_index(frame: pd.DataFrame) -> pd.DataFrame:
    """将 DataFrame 规范为无时区 DatetimeIndex（列或索引含 timestamp）。"""
    if isinstance(frame.index, pd.DatetimeIndex):
        out = frame.copy()
        out.index = pd.to_datetime(out.index, utc=True, errors="raise").tz_convert(None)
        return out

    if "timestamp" not in frame.columns:
        raise ValueError("target_position input must include DatetimeIndex or 'timestamp' column")

    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise").dt.tz_convert(None)
    out = out.set_index("timestamp")
    return out


def validate_target_position(
    target: pd.Series | pd.DataFrame,
    *,
    strict: bool = True,
    enforce_bounds: bool = True,
) -> pd.Series:
    """校验单标的目标仓位：时间索引、ffill、缺失填 0，可选严格限制在 [-1, 1]。"""
    if isinstance(target, pd.Series):
        frame = target.to_frame(name="target_position")
    else:
        frame = target.copy()

    frame = _to_timestamp_index(frame)

    if "target_position" not in frame.columns:
        raise ValueError("target_position column is required")

    if frame.index.has_duplicates:
        raise ValueError("target_position index has duplicate timestamps")

    if not frame.index.is_monotonic_increasing:
        frame = frame.sort_index()

    series = pd.to_numeric(frame["target_position"], errors="coerce")
    series = series.ffill().fillna(0.0)

    if series.isna().any():
        raise ValueError("target_position contains NaN after forward-fill")

    if enforce_bounds:
        out_of_range = (series < -1.0) | (series > 1.0)
        if out_of_range.any() and strict:
            first_bad = series[out_of_range].iloc[0]
            raise ValueError(f"target_position out of bounds [-1,1]: {first_bad}")
        if out_of_range.any() and not strict:
            series = series.clip(-1.0, 1.0)

    return series.astype(float)


def align_target_position_to_index(
    target: pd.Series,
    index: pd.DatetimeIndex | Iterable[pd.Timestamp],
) -> pd.Series:
    """将目标序列重索引到行情时间轴，ffill 后空缺补 0（与单标的回测 feed 对齐）。"""
    dt_index = pd.DatetimeIndex(index)
    dt_index = pd.to_datetime(dt_index, utc=True, errors="raise").tz_convert(None)
    aligned = target.reindex(dt_index).ffill().fillna(0.0)
    aligned.index = dt_index
    return aligned.astype(float)


def _to_weight_frame(target: pd.Series | pd.DataFrame) -> pd.DataFrame:
    """长表规范化：列 timestamp / symbol / target_weight，去重排序。"""
    if isinstance(target, pd.Series):
        if not isinstance(target.index, pd.MultiIndex) or list(target.index.names) != ["timestamp", "symbol"]:
            raise ValueError("target_weights Series must use MultiIndex ['timestamp', 'symbol']")
        frame = target.rename("target_weight").reset_index()
    else:
        frame = target.copy()

    required = {"timestamp", "symbol", "target_weight"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"target_weights missing required columns: {sorted(missing)}")

    out = frame[["timestamp", "symbol", "target_weight"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise").dt.tz_convert(None)
    out["symbol"] = out["symbol"].astype(str)
    out["target_weight"] = pd.to_numeric(out["target_weight"], errors="coerce")
    out = out.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    if out[["timestamp", "symbol"]].duplicated().any():
        raise ValueError("target_weights has duplicate (timestamp, symbol)")
    if out["target_weight"].isna().any():
        raise ValueError("target_weights contains NaN target_weight")
    return out


def validate_target_weights(
    target: pd.Series | pd.DataFrame,
    *,
    strict: bool = True,
    enforce_bounds: bool = True,
    max_gross_leverage: float = 1.0,
) -> pd.Series:
    """校验多标的权重：每 (timestamp, symbol) 一行，可选单标的 [-1,1] 与截面总杠杆上界。"""
    frame = _to_weight_frame(target)

    if enforce_bounds:
        out_of_range = (frame["target_weight"] < -1.0) | (frame["target_weight"] > 1.0)
        if out_of_range.any() and strict:
            first_bad = float(frame.loc[out_of_range, "target_weight"].iloc[0])
            raise ValueError(f"target_weight out of bounds [-1,1]: {first_bad}")
        if out_of_range.any() and not strict:
            frame["target_weight"] = frame["target_weight"].clip(-1.0, 1.0)

    gross = frame.groupby("timestamp")["target_weight"].apply(lambda x: float(x.abs().sum()))
    gross_bad = gross > float(max_gross_leverage) + 1e-12
    if gross_bad.any() and strict:
        ts = gross[gross_bad].index[0]
        val = float(gross.loc[ts])
        raise ValueError(f"target_weights gross leverage exceeds {max_gross_leverage}: timestamp={ts}, gross={val}")

    series = frame.set_index(["timestamp", "symbol"])["target_weight"].sort_index().astype(float)
    series.index = series.index.set_names(["timestamp", "symbol"])
    return series


def align_target_weights_to_index(
    target_weights: pd.Series,
    index: pd.DatetimeIndex | Iterable[pd.Timestamp],
    symbols: Iterable[str],
) -> pd.Series:
    """展开为 (timestamp × symbol) 完整网格，缺失权重 ffill 后补 0，供矩阵化回测。"""
    if not isinstance(target_weights.index, pd.MultiIndex) or list(target_weights.index.names) != ["timestamp", "symbol"]:
        raise ValueError("target_weights must use MultiIndex ['timestamp', 'symbol']")

    dt_index = pd.DatetimeIndex(index)
    dt_index = pd.to_datetime(dt_index, utc=True, errors="raise").tz_convert(None)
    symbols_list = [str(s) for s in symbols]
    full_index = pd.MultiIndex.from_product([dt_index, symbols_list], names=["timestamp", "symbol"])

    pivot = target_weights.unstack("symbol")
    pivot = pivot.reindex(index=dt_index, columns=symbols_list)
    pivot = pivot.ffill().fillna(0.0)

    long = pivot.reset_index(names="timestamp").melt(
        id_vars="timestamp",
        var_name="symbol",
        value_name="target_weight",
    )
    aligned = long.set_index(["timestamp", "symbol"])["target_weight"].reindex(full_index).fillna(0.0).astype(float)
    aligned.index = full_index
    return aligned


def validate_temporal_integrity(frame: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    """可选：检查 event_time / arrival_time 因果及 timestamp 重复（用于更严格的数据管线）。"""
    out = frame.copy()

    if "event_time" in out.columns and "arrival_time" in out.columns:
        out["event_time"] = pd.to_datetime(out["event_time"], utc=True, errors="raise").dt.tz_convert(None)
        out["arrival_time"] = pd.to_datetime(out["arrival_time"], utc=True, errors="raise").dt.tz_convert(None)
        invalid = out["arrival_time"] < out["event_time"]
        if invalid.any() and strict:
            first = out.loc[invalid, ["event_time", "arrival_time"]].iloc[0]
            raise ValueError(
                "temporal integrity violated: arrival_time earlier than event_time: "
                f"event_time={first['event_time']}, arrival_time={first['arrival_time']}"
            )

    if "timestamp" in out.columns:
        ts = pd.to_datetime(out["timestamp"], utc=True, errors="raise").dt.tz_convert(None)
        if strict and ts.duplicated().any():
            raise ValueError("ohlcv timestamp has duplicate rows")
        out["timestamp"] = ts

    return out
