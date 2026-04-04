from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


FACTOR_PATH = Path(r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\cleaned_factors.parquet")
OUTPUT_PATH = Path(r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\alpha_vector.parquet")
TARGET_DAILY_VOL = 0.10 / np.sqrt(252.0)
NOISE_STD = 0.001
RANDOM_SEED = 42
ALPHA_WEIGHTS = {
    "Value": 0.4,
    "Momentum": 0.4,
    "Size": -0.2,
}


def _winsorize_3sigma(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=0)
    std = frame.std(axis=0, ddof=1).fillna(0.0)
    lower = mean - 3.0 * std
    upper = mean + 3.0 * std
    return frame.clip(lower=lower, upper=upper, axis=1)


def _zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=0)
    std = frame.std(axis=0, ddof=1).replace(0.0, np.nan)
    normalized = (frame - mean) / std
    return normalized.fillna(0.0)


def generate_expected_returns(
    clean_factors_path: str | Path = FACTOR_PATH,
    output_path: str | Path = OUTPUT_PATH,
) -> pd.DataFrame:
    clean_factors_path = Path(clean_factors_path)
    output_path = Path(output_path)

    factors = pd.read_parquet(clean_factors_path).copy()
    factors["date"] = pd.to_datetime(factors["date"], errors="coerce").dt.date

    latest_date = factors["date"].max()
    latest_cross_section = factors.loc[factors["date"] == latest_date].copy()

    required_columns = ["asset", *ALPHA_WEIGHTS.keys()]
    missing = [column for column in required_columns if column not in latest_cross_section.columns]
    if missing:
        raise KeyError(f"Alpha generation requires columns: {missing}")

    style_factors = latest_cross_section.loc[:, list(ALPHA_WEIGHTS.keys())].apply(pd.to_numeric, errors="coerce")
    style_factors = _zscore(_winsorize_3sigma(style_factors))

    raw_alpha = sum(ALPHA_WEIGHTS[column] * style_factors[column] for column in ALPHA_WEIGHTS)
    raw_std = float(raw_alpha.std(ddof=1))
    if not np.isfinite(raw_std) or raw_std == 0.0:
        scaled_alpha = raw_alpha * 0.0
    else:
        scaled_alpha = raw_alpha * (TARGET_DAILY_VOL / raw_std)

    rng = np.random.default_rng(RANDOM_SEED)
    expected_ret = scaled_alpha + rng.normal(loc=0.0, scale=NOISE_STD, size=len(scaled_alpha))

    alpha_vector = pd.DataFrame(
        {
            "asset": latest_cross_section["asset"].astype("string").str.strip().str.upper(),
            "expected_ret": expected_ret.astype("float32"),
        }
    )
    alpha_vector = alpha_vector.dropna(subset=["asset"]).sort_values("asset", kind="stable", ignore_index=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    alpha_vector.to_parquet(output_path, index=False)
    return alpha_vector


def main() -> None:
    alpha_vector = generate_expected_returns()
    print(f"alpha_vector_rows={len(alpha_vector)}")
    print(f"alpha_vector_path={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
