from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import CompositionConfig, WeightingConfig
from strategy_layer.portfolio_alpha.multiple_factor_composite.panel_preprocess import standardize_panel


def _normalize_weight_map(weights: dict[str, float], factor_columns: list[str]) -> dict[str, float]:
    ordered = {column: float(weights.get(column, 0.0)) for column in factor_columns}
    scale = sum(abs(value) for value in ordered.values())
    if scale <= 1e-12:
        return {column: 1.0 / len(factor_columns) for column in factor_columns}
    return {column: value / scale for column, value in ordered.items()}


def _equal_weights(factor_columns: list[str]) -> dict[str, float]:
    weight = 1.0 / len(factor_columns)
    return {column: weight for column in factor_columns}


def _compute_ic_for_factor(
    panel: pd.DataFrame,
    *,
    factor: str,
    target_column: str,
    correlation: str,
) -> float:
    ic_values = []
    for _, group in panel.groupby("datetime", sort=False):
        mask = group[[factor, target_column]].notna().all(axis=1)
        if mask.sum() < 2:
            continue
        x = group.loc[mask, factor]
        y = group.loc[mask, target_column]
        if correlation == "spearman":
            corr = x.rank().corr(y.rank(), method="pearson")
        else:
            corr = x.corr(y, method=correlation)
        if corr is not None and np.isfinite(corr):
            ic_values.append(float(corr))
    if not ic_values:
        return float("nan")
    return float(np.nanmean(ic_values))


def compute_weight_history(
    panel: pd.DataFrame,
    factor_columns: list[str],
    config: WeightingConfig,
) -> pd.DataFrame:
    dates = sorted(pd.unique(panel["datetime"]))
    records: list[dict[str, object]] = []
    if config.method == "equal":
        weights = _equal_weights(factor_columns)
        for date in dates:
            records.append({"datetime": date, **weights})
        return pd.DataFrame(records)

    if config.method == "custom":
        weights = _normalize_weight_map(config.custom_weights, factor_columns)
        for date in dates:
            records.append({"datetime": date, **weights})
        return pd.DataFrame(records)

    if config.method != "ic":
        raise ValueError(f"Unsupported weighting method: {config.method}")
    if not config.target_column:
        raise ValueError("IC weighting 需要 target_column")

    fallback_weights = (
        _equal_weights(factor_columns)
        if config.fallback == "equal"
        else _normalize_weight_map(config.custom_weights, factor_columns)
    )
    for index, current_date in enumerate(dates):
        history_dates = dates[max(0, index - config.lookback_periods) : index]
        if len(history_dates) < config.min_history:
            records.append({"datetime": current_date, **fallback_weights})
            continue
        history = panel.loc[panel["datetime"].isin(history_dates)]
        raw_weights = {
            factor: _compute_ic_for_factor(
                history,
                factor=factor,
                target_column=config.target_column,
                correlation=config.correlation,
            )
            for factor in factor_columns
        }
        usable_weights = {
            factor: value
            for factor, value in raw_weights.items()
            if np.isfinite(value)
        }
        if not usable_weights:
            usable_weights = fallback_weights
        normalized = _normalize_weight_map(usable_weights, factor_columns)
        records.append({"datetime": current_date, **normalized})
    return pd.DataFrame(records)


def compose_signal(
    panel: pd.DataFrame,
    factor_columns: list[str],
    weight_history: pd.DataFrame,
    config: CompositionConfig,
) -> pd.DataFrame:
    merged = panel.merge(weight_history, on="datetime", suffixes=("", "__weight"), how="left")
    weight_columns = {factor: f"{factor}__weight" for factor in factor_columns}
    score = np.zeros(len(merged), dtype=float)
    for factor in factor_columns:
        score = score + merged[factor].fillna(0.0).to_numpy(dtype=float) * merged[weight_columns[factor]].fillna(0.0).to_numpy(dtype=float)
    merged[config.score_column] = score

    if config.final_transform == "zscore":
        merged = standardize_panel(merged, [config.score_column], "zscore")
    elif config.final_transform == "rank":
        merged = standardize_panel(merged, [config.score_column], "rank")
    elif config.final_transform != "none":
        raise ValueError(f"Unsupported final_transform: {config.final_transform}")

    merged["rank"] = merged.groupby("datetime")[config.score_column].rank(ascending=False, method="average")
    merged["selected_flag"] = False
    merged["side"] = "NONE"
    if config.long_top_k is not None:
        long_mask = merged.groupby("datetime")[config.score_column].rank(ascending=False, method="first") <= int(config.long_top_k)
        merged.loc[long_mask, "selected_flag"] = True
        merged.loc[long_mask, "side"] = "LONG"
    if config.short_bottom_k is not None:
        short_mask = merged.groupby("datetime")[config.score_column].rank(ascending=True, method="first") <= int(config.short_bottom_k)
        merged.loc[short_mask, "selected_flag"] = True
        merged.loc[short_mask, "side"] = "SHORT"

    output_columns = [
        "datetime",
        "asset",
        config.score_column,
        "rank",
        "selected_flag",
        "side",
    ]
    return merged[output_columns].sort_values(["datetime", "rank", "asset"]).reset_index(drop=True)