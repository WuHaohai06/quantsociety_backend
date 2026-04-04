from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


WORK_DIR = Path(r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx")
MARKET_CAP_PATH = Path(r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\market_cap\market_cap_weights.parquet")
FACTOR_PATH = WORK_DIR / "cleaned_factors.parquet"
FACTOR_COVARIANCE_PATH = WORK_DIR / "factor_covariance.parquet"
SPECIFIC_RISK_PATH = WORK_DIR / "specific_risk.parquet"
LOG_PATH = WORK_DIR / "benchmark_total_risk.txt"


def compute_benchmark_total_risk(
    work_dir: str | Path = WORK_DIR,
    market_cap_path: str | Path = MARKET_CAP_PATH,
) -> tuple[object, float]:
    work_dir = Path(work_dir)
    market_cap_path = Path(market_cap_path)

    factor_path = work_dir / "cleaned_factors.parquet"
    factor_covariance_path = work_dir / "factor_covariance.parquet"
    specific_risk_path = work_dir / "specific_risk.parquet"
    log_path = work_dir / "benchmark_total_risk.txt"

    required_paths = {
        "cleaned_factors": factor_path,
        "factor_covariance": factor_covariance_path,
        "specific_risk": specific_risk_path,
        "market_cap_weights": market_cap_path,
    }
    missing_files = [f"{name}: {path}" for name, path in required_paths.items() if not path.exists()]
    if missing_files:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing_files))

    exposures = pd.read_parquet(factor_path).copy()
    factor_covariance = pd.read_parquet(factor_covariance_path).copy()
    specific_risk = pd.read_parquet(specific_risk_path).copy()
    market_cap = pd.read_parquet(market_cap_path).copy()

    exposures["date"] = pd.to_datetime(exposures["date"], errors="coerce").dt.date
    exposures["asset"] = exposures["asset"].astype("string").str.strip().str.upper()
    latest_date = exposures["date"].max()
    latest_exposures = exposures.loc[exposures["date"] == latest_date].copy()

    market_cap["date"] = pd.to_datetime(market_cap["datetime"], errors="coerce").dt.date
    market_cap["asset"] = market_cap["asset"].astype("string").str.strip().str.upper()
    market_cap["market_cap"] = pd.to_numeric(market_cap["market_cap"], errors="coerce")
    latest_market_cap = market_cap.loc[market_cap["date"] == latest_date, ["asset", "market_cap"]].copy()

    specific_risk["asset"] = specific_risk["asset"].astype("string").str.strip().str.upper()
    specific_risk["specific_var_annual"] = pd.to_numeric(specific_risk["specific_var_annual"], errors="coerce")

    factor_cols = factor_covariance.columns.tolist()
    missing_factor_cols = [column for column in factor_cols if column not in latest_exposures.columns]
    if missing_factor_cols:
        raise KeyError(f"Missing factor exposure columns required by covariance matrix: {missing_factor_cols}")

    cross_section = latest_exposures.loc[:, ["asset", *factor_cols]].merge(
        latest_market_cap,
        on="asset",
        how="left",
        validate="one_to_one",
    )
    cross_section = cross_section.merge(
        specific_risk.loc[:, ["asset", "specific_var_annual"]],
        on="asset",
        how="left",
        validate="one_to_one",
    )

    cross_section["market_cap"] = pd.to_numeric(cross_section["market_cap"], errors="coerce")
    cross_section = cross_section.loc[cross_section["market_cap"].notna() & (cross_section["market_cap"] > 0)].copy()
    if cross_section.empty:
        raise ValueError(f"No valid market cap weights found for latest date {latest_date}.")

    cross_section["specific_var_annual"] = pd.to_numeric(
        cross_section["specific_var_annual"],
        errors="coerce",
    )
    median_specific_risk = cross_section["specific_var_annual"].median()
    cross_section["specific_var_annual"] = cross_section["specific_var_annual"].fillna(median_specific_risk)
    cross_section["specific_var_annual"] = cross_section["specific_var_annual"].fillna(0.0)

    total_market_cap = float(cross_section["market_cap"].sum())
    if not np.isfinite(total_market_cap) or total_market_cap <= 0:
        raise ValueError(f"Invalid market cap total on latest date {latest_date}.")

    w_mkt = cross_section["market_cap"].to_numpy(dtype=np.float64) / total_market_cap
    X = cross_section.loc[:, factor_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    F = factor_covariance.loc[factor_cols, factor_cols].to_numpy(dtype=np.float64)
    delta = cross_section["specific_var_annual"].to_numpy(dtype=np.float64)

    benchmark_factor_exposure = w_mkt @ X
    systematic_variance = float(benchmark_factor_exposure @ F @ benchmark_factor_exposure.T)
    specific_variance = float(np.sum((w_mkt ** 2) * delta))
    total_variance = max(systematic_variance + specific_variance, 0.0)
    benchmark_sigma = float(np.sqrt(total_variance))

    message = f"[{latest_date}] Benchmark Total Risk (Annualized): {benchmark_sigma:.2%}"
    print(message)
    log_path.write_text(message + "\n", encoding="utf-8")

    return latest_date, benchmark_sigma


def main() -> None:
    compute_benchmark_total_risk()


if __name__ == "__main__":
    main()
