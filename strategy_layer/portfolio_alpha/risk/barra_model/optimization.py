from __future__ import annotations

from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd


DEFAULT_LAMBDA = 2.0
MAX_WEIGHT = 0.08


def _load_latest_cross_section(factor_exposure_path: str | Path) -> tuple[pd.DataFrame, object]:
    exposures = pd.read_parquet(factor_exposure_path).copy()
    exposures["date"] = pd.to_datetime(exposures["date"], errors="coerce").dt.date
    latest_date = exposures["date"].max()
    latest = exposures.loc[exposures["date"] == latest_date].copy()
    return latest, latest_date


def run_portfolio_optimization(
    work_dir: str | Path,
    lambda_reg: float = DEFAULT_LAMBDA,
) -> pd.DataFrame:
    work_dir = Path(work_dir)
    alpha_path = work_dir / "alpha_vector.parquet"
    factor_covariance_path = work_dir / "factor_covariance.parquet"
    specific_risk_path = work_dir / "specific_risk.parquet"
    factor_exposure_path = work_dir / "cleaned_factors.parquet"
    output_path = work_dir / "optimal_weights.parquet"

    required_paths = {
        "alpha_vector": alpha_path,
        "factor_covariance": factor_covariance_path,
        "specific_risk": specific_risk_path,
        "cleaned_factors": factor_exposure_path,
    }
    missing_files = [f"{name}: {path}" for name, path in required_paths.items() if not path.exists()]
    if missing_files:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing_files))

    alpha = pd.read_parquet(alpha_path).copy()
    factor_covariance = pd.read_parquet(factor_covariance_path).copy()
    specific_risk = pd.read_parquet(specific_risk_path).copy()
    exposures, latest_date = _load_latest_cross_section(factor_exposure_path)

    alpha["asset"] = alpha["asset"].astype("string").str.strip().str.upper()
    specific_risk["asset"] = specific_risk["asset"].astype("string").str.strip().str.upper()
    exposures["asset"] = exposures["asset"].astype("string").str.strip().str.upper()

    market_median_risk = pd.to_numeric(
        specific_risk["specific_var_annual"],
        errors="coerce",
    ).median()
    if not np.isfinite(market_median_risk):
        raise ValueError("Specific risk median is invalid for the latest cross-section.")

    factor_cols = factor_covariance.columns.tolist()
    missing_factor_cols = [column for column in factor_cols if column not in exposures.columns]
    if missing_factor_cols:
        raise KeyError(f"Missing factor exposure columns required by covariance matrix: {missing_factor_cols}")

    optimizer_frame = exposures.loc[:, ["asset", *factor_cols]].merge(
        alpha.loc[:, ["asset", "expected_ret"]],
        on="asset",
        how="inner",
        validate="one_to_one",
    )
    optimizer_frame = optimizer_frame.merge(
        specific_risk.loc[:, ["asset", "specific_var_annual"]],
        on="asset",
        how="left",
        validate="one_to_one",
    )
    optimizer_frame["specific_var_annual"] = pd.to_numeric(
        optimizer_frame["specific_var_annual"], errors="coerce"
    ).fillna(market_median_risk)

    if optimizer_frame.empty:
        raise ValueError("Optimizer universe is empty after joining alpha, exposures, and specific risk.")

    assets = optimizer_frame["asset"].to_numpy()
    alpha_vec = pd.to_numeric(optimizer_frame["expected_ret"], errors="coerce").to_numpy(dtype=np.float64)
    X = optimizer_frame.loc[:, factor_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    F = factor_covariance.loc[factor_cols, factor_cols].to_numpy(dtype=np.float64)
    delta = optimizer_frame["specific_var_annual"].to_numpy(dtype=np.float64)

    n_assets = len(assets)
    w = cp.Variable(n_assets)

    factor_risk = cp.quad_form(X.T @ w, cp.psd_wrap(F))
    specific_risk_term = cp.sum(cp.multiply(cp.square(w), delta))
    total_variance = factor_risk + specific_risk_term
    utility = alpha_vec @ w - 0.5 * lambda_reg * total_variance

    constraints = [
        cp.sum(w) == 1.0,
        w >= 0.0,
        w <= MAX_WEIGHT,
    ]

    problem = cp.Problem(cp.Maximize(utility), constraints)
    problem.solve(solver=cp.SCS, verbose=False)

    if problem.status not in {"optimal", "optimal_inaccurate"}:
        raise ValueError(f"Optimization failed with status: {problem.status}")

    optimal_weights = pd.DataFrame(
        {
            "asset": assets,
            "weight": np.asarray(w.value, dtype=np.float64).astype("float32"),
        }
    )
    optimal_weights = optimal_weights.sort_values("weight", ascending=False, kind="stable", ignore_index=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimal_weights.to_parquet(output_path, index=False)

    print(f"latest_date={latest_date}")
    print(f"status={problem.status}")
    print(f"utility={float(problem.value):.10f}")
    print(f"optimal_weights_path={output_path}")
    return optimal_weights


def main() -> None:
    run_portfolio_optimization(work_dir=r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx")


if __name__ == "__main__":
    main()
