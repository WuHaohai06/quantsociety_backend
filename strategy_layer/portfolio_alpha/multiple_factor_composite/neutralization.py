from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import NeutralizationStepConfig


def _build_design_matrix(group: pd.DataFrame, control_columns: tuple[str, ...], add_intercept: bool) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for column in control_columns:
        series = group[column]
        if pd.api.types.is_numeric_dtype(series):
            pieces.append(pd.DataFrame({column: pd.to_numeric(series, errors="coerce")}))
        else:
            dummies = pd.get_dummies(series.astype("string"), prefix=column, dummy_na=False)
            if not dummies.empty:
                pieces.append(dummies.iloc[:, 1:] if dummies.shape[1] > 1 else dummies)
    if pieces:
        matrix = pd.concat(pieces, axis=1)
    else:
        matrix = pd.DataFrame(index=group.index)
    if add_intercept:
        matrix.insert(0, "intercept", 1.0)
    return matrix


def _ols_residualize_series(
    values: pd.Series,
    controls: pd.DataFrame,
) -> pd.Series:
    out = pd.Series(np.nan, index=values.index, dtype=float)
    if controls.empty:
        return values.astype(float)

    mask = values.notna() & controls.notna().all(axis=1)
    if mask.sum() <= controls.shape[1]:
        return out

    y = values.loc[mask].astype(float).to_numpy(dtype=float)
    x = controls.loc[mask].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    pred = controls.to_numpy(dtype=float) @ beta
    out.loc[controls.index] = values.astype(float) - pred
    return out


def apply_neutralization_steps(
    panel: pd.DataFrame,
    default_factors: list[str],
    steps: tuple[NeutralizationStepConfig, ...],
) -> pd.DataFrame:
    out = panel.copy()
    for step in steps:
        if step.method == "none":
            continue
        target_columns = list(step.factors) or list(default_factors)
        if step.method == "group_demean":
            if not step.group_column:
                raise ValueError("group_demean 需要 group_column")
            for column in target_columns:
                group_mean = out.groupby(["datetime", step.group_column])[column].transform("mean")
                out[column] = out[column] - group_mean
        elif step.method == "ols":
            if not step.control_columns:
                raise ValueError("ols neutralization 需要 control_columns")
            pieces = []
            for _, group in out.groupby("datetime", sort=False):
                group = group.copy()
                controls = _build_design_matrix(group, step.control_columns, step.add_intercept)
                for column in target_columns:
                    group[column] = _ols_residualize_series(group[column], controls)
                pieces.append(group)
            out = pd.concat(pieces, ignore_index=True)
        else:
            raise ValueError(f"Unsupported neutralization method: {step.method}")
    return out.sort_values(["asset", "datetime"]).reset_index(drop=True)