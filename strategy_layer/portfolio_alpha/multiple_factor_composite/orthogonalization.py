from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import OrthogonalizationStepConfig
from strategy_layer.portfolio_alpha.multiple_factor_composite.panel_preprocess import standardize_panel


def _residualize_against(values: np.ndarray, design: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ beta


def _apply_sequential(group: pd.DataFrame, factors: list[str], order: list[str]) -> pd.DataFrame:
    result = group.copy()
    if not order:
        order = factors
    for idx, column in enumerate(order):
        if idx == 0:
            continue
        previous = order[:idx]
        mask = result[[column, *previous]].notna().all(axis=1)
        if mask.sum() <= len(previous):
            result.loc[:, column] = np.nan
            continue
        y = result.loc[mask, column].astype(float).to_numpy(dtype=float)
        x = result.loc[mask, previous].astype(float).to_numpy(dtype=float)
        residuals = _residualize_against(y, x)
        result.loc[mask, column] = residuals
        result.loc[~mask, column] = np.nan
    return result


def _apply_symmetric(group: pd.DataFrame, factors: list[str], shrinkage: float) -> pd.DataFrame:
    result = group.copy()
    mask = result[factors].notna().all(axis=1)
    if mask.sum() <= len(factors):
        result.loc[:, factors] = np.nan
        return result

    values = result.loc[mask, factors].astype(float)
    means = values.mean()
    stds = values.std(ddof=0).replace(0.0, np.nan)
    standardized = ((values - means) / stds).dropna(axis=0, how="any")
    if standardized.shape[0] <= len(factors):
        result.loc[:, factors] = np.nan
        return result

    corr = standardized.corr().to_numpy(dtype=float)
    corr = (1.0 - shrinkage) * corr + shrinkage * np.eye(len(factors))
    eigvals, eigvecs = np.linalg.eigh(corr)
    eigvals = np.clip(eigvals, 1e-8, None)
    inv_sqrt = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
    transformed = standardized.to_numpy(dtype=float) @ inv_sqrt
    transformed_df = pd.DataFrame(transformed, index=standardized.index, columns=factors)
    result.loc[:, factors] = np.nan
    result.loc[transformed_df.index, factors] = transformed_df.values
    return result


def apply_orthogonalization_steps(
    panel: pd.DataFrame,
    default_factors: list[str],
    steps: tuple[OrthogonalizationStepConfig, ...],
) -> pd.DataFrame:
    out = panel.copy()
    for step in steps:
        if step.method == "none":
            continue
        factors = list(step.factors) or list(default_factors)
        pieces = []
        for _, group in out.groupby("datetime", sort=False):
            group = group.copy()
            if step.method == "sequential":
                updated = _apply_sequential(group, factors, list(step.order))
            elif step.method == "symmetric":
                updated = _apply_symmetric(group, factors, step.shrinkage)
            else:
                raise ValueError(f"Unsupported orthogonalization method: {step.method}")
            pieces.append(updated)
        out = pd.concat(pieces, ignore_index=True)
        if step.renormalize:
            out = standardize_panel(out, factors, "zscore")
    return out.sort_values(["asset", "datetime"]).reset_index(drop=True)