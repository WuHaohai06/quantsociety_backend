from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import PreprocessConfig


def apply_factor_directions(panel: pd.DataFrame, directions: dict[str, float]) -> pd.DataFrame:
    out = panel.copy()
    for column, direction in directions.items():
        if column in out.columns:
            out[column] = out[column].astype(float) * float(direction)
    return out


def _winsorize_series(series: pd.Series, method: str, lower: float, upper: float) -> pd.Series:
    if method == "none":
        return series
    if method != "quantile":
        raise ValueError(f"Unsupported winsorize method: {method}")
    valid = series.dropna()
    if valid.empty:
        return series
    lo = valid.quantile(lower)
    hi = valid.quantile(upper)
    return series.clip(lower=lo, upper=hi)


def _standardize_series(series: pd.Series, method: str) -> pd.Series:
    if method == "none":
        return series
    valid = series.dropna()
    if valid.empty:
        return series
    if method == "zscore":
        std = float(valid.std(ddof=0))
        if std < 1e-12:
            return pd.Series(0.0, index=series.index)
        return (series - valid.mean()) / std
    if method == "rank":
        return series.rank(pct=True)
    raise ValueError(f"Unsupported standardize method: {method}")


def _fillna_series(series: pd.Series, method: str) -> pd.Series:
    if method == "keep":
        return series
    if method == "zero":
        return series.fillna(0.0)
    if method == "median":
        return series.fillna(series.median())
    raise ValueError(f"Unsupported fillna method: {method}")


def standardize_panel(panel: pd.DataFrame, factor_columns: list[str], method: str) -> pd.DataFrame:
    out = panel.copy()
    for column in factor_columns:
        out[column] = out.groupby("datetime", group_keys=False)[column].apply(
            lambda series: _standardize_series(series.astype(float), method)
        )
    return out


def preprocess_panel(
    panel: pd.DataFrame,
    factor_columns: list[str],
    config: PreprocessConfig,
) -> pd.DataFrame:
    out = panel.copy()
    for column in factor_columns:
        out[column] = out.groupby("datetime", group_keys=False)[column].apply(
            lambda series: _winsorize_series(
                series.astype(float),
                config.winsorize.method if config.winsorize.enabled else "none",
                config.winsorize.lower,
                config.winsorize.upper,
            )
        )
        out[column] = out.groupby("datetime", group_keys=False)[column].apply(
            lambda series: _standardize_series(series.astype(float), config.standardize.method)
        )
        out[column] = out.groupby("datetime", group_keys=False)[column].apply(
            lambda series: _fillna_series(series.astype(float), config.fillna.method)
        )
    out = out.replace([np.inf, -np.inf], np.nan)
    return out