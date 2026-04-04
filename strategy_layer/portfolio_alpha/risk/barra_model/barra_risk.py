from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


DEFAULT_FACTOR_PATH: str | None = None
DEFAULT_RETURN_PATH: str | None = None
DEFAULT_CAP_PATH: str | None = None
DEFAULT_OUTPUT_DIR: str | None = None


class BarraRiskEngine:
    """
    Layer 2 Barra risk engine.

    Workflow:
    1. Load aligned factor / return / market-cap parquet files.
    2. Drop rows with missing next_ret or market_cap synchronously.
    3. For each date, winsorize and z-score factor exposures.
    4. Estimate daily factor returns with WLS using sqrt(market_cap).
    5. Build annualized factor covariance from the full factor-return history with EWMA.
    6. Store WLS residuals and output only the latest-date specific risk cross-section.
    """

    def __init__(
        self,
        factor_path: str | Path,
        return_path: str | Path,
        cap_path: str | Path,
        *,
        date_column: str = "date",
        asset_column: str = "asset",
        return_column: str = "next_ret",
        cap_column: str = "market_cap",
    ) -> None:
        self.factor_path = Path(factor_path)
        self.return_path = Path(return_path)
        self.cap_path = Path(cap_path)
        self.date_column = date_column
        self.asset_column = asset_column
        self.return_column = return_column
        self.cap_column = cap_column

        self.df_factors = pd.read_parquet(self.factor_path).copy()
        self.df_returns = pd.read_parquet(self.return_path).copy()
        self.df_caps = pd.read_parquet(self.cap_path).copy()

        self.factor_columns: list[str] = []
        self.cleaned_factors: pd.DataFrame | None = None
        self.cleaned_returns: pd.DataFrame | None = None
        self.cleaned_caps: pd.DataFrame | None = None
        self.processed_exposures: pd.DataFrame | None = None
        self.factor_returns: pd.DataFrame | None = None
        self.specific_returns: pd.DataFrame | None = None
        self.specific_risk: pd.DataFrame | None = None
        self.factor_covariance: pd.DataFrame | None = None

        self._validate_inputs()
        self._synchronize_inputs()

    def _validate_inputs(self) -> None:
        factor_required = {self.date_column, self.asset_column}
        return_required = {self.date_column, self.asset_column, self.return_column}
        cap_required = {self.date_column, self.asset_column, self.cap_column}

        missing_factor = sorted(factor_required - set(self.df_factors.columns))
        missing_return = sorted(return_required - set(self.df_returns.columns))
        missing_cap = sorted(cap_required - set(self.df_caps.columns))
        if missing_factor:
            raise KeyError(f"Factor file missing required columns: {missing_factor}")
        if missing_return:
            raise KeyError(f"Return file missing required columns: {missing_return}")
        if missing_cap:
            raise KeyError(f"Cap file missing required columns: {missing_cap}")

        for frame in (self.df_factors, self.df_returns, self.df_caps):
            frame[self.date_column] = pd.to_datetime(frame[self.date_column], errors="coerce").dt.date
            frame[self.asset_column] = frame[self.asset_column].astype("string").str.strip().str.upper()

        self.df_returns[self.return_column] = pd.to_numeric(
            self.df_returns[self.return_column], errors="coerce"
        ).astype("float32")
        self.df_caps[self.cap_column] = pd.to_numeric(
            self.df_caps[self.cap_column], errors="coerce"
        ).astype("float32")

        factor_index = pd.MultiIndex.from_frame(self.df_factors.loc[:, [self.date_column, self.asset_column]])
        return_index = pd.MultiIndex.from_frame(self.df_returns.loc[:, [self.date_column, self.asset_column]])
        cap_index = pd.MultiIndex.from_frame(self.df_caps.loc[:, [self.date_column, self.asset_column]])
        if len(self.df_factors) != len(self.df_returns) or not factor_index.equals(return_index):
            raise ValueError("cleaned_factors.parquet and cleaned_returns.parquet must align on (date, asset).")
        if len(self.df_factors) != len(self.df_caps) or not factor_index.equals(cap_index):
            raise ValueError("cleaned_factors.parquet and cleaned_market_cap.parquet must align on (date, asset).")

        self.factor_columns = [
            column for column in self.df_factors.columns if column not in {self.date_column, self.asset_column}
        ]
        if not self.factor_columns:
            raise ValueError("No factor exposure columns found in factor parquet.")

        self.df_factors.loc[:, self.factor_columns] = self.df_factors.loc[:, self.factor_columns].apply(
            pd.to_numeric, errors="coerce"
        )
        self.df_factors.loc[:, self.factor_columns] = self.df_factors.loc[:, self.factor_columns].astype("float32")

    def _synchronize_inputs(self) -> None:
        mask = (
            self.df_returns[self.return_column].notna()
            & self.df_caps[self.cap_column].notna()
            & (self.df_caps[self.cap_column] > 0)
        )

        self.cleaned_factors = self.df_factors.loc[mask].reset_index(drop=True).copy()
        self.cleaned_returns = self.df_returns.loc[mask].reset_index(drop=True).copy()
        self.cleaned_caps = self.df_caps.loc[mask].reset_index(drop=True).copy()

        factor_index = pd.MultiIndex.from_frame(self.cleaned_factors.loc[:, [self.date_column, self.asset_column]])
        return_index = pd.MultiIndex.from_frame(self.cleaned_returns.loc[:, [self.date_column, self.asset_column]])
        cap_index = pd.MultiIndex.from_frame(self.cleaned_caps.loc[:, [self.date_column, self.asset_column]])
        if not (factor_index.equals(return_index) and factor_index.equals(cap_index)):
            raise ValueError("Synchronized factor/return/cap tables are not aligned on (date, asset).")

    @staticmethod
    def _winsorize_3sigma(exposures: np.ndarray) -> np.ndarray:
        mu = np.nanmean(exposures, axis=0)
        sigma = np.nanstd(exposures, axis=0, ddof=1)
        sigma = np.where(np.isnan(sigma), 0.0, sigma)
        return np.clip(exposures, mu - 3.0 * sigma, mu + 3.0 * sigma)

    @staticmethod
    def _zscore(exposures: np.ndarray) -> np.ndarray:
        mean = np.nanmean(exposures, axis=0)
        std = np.nanstd(exposures, axis=0, ddof=1)
        std = np.where((std == 0.0) | np.isnan(std), 1.0, std)
        normalized = (exposures - mean) / std
        return np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)

    def _preprocess_cross_section(self, X: np.ndarray) -> np.ndarray:
        return self._zscore(self._winsorize_3sigma(X)).astype(np.float32, copy=False)

    def _iter_daily_slices(self):
        if self.cleaned_factors is None or self.cleaned_returns is None or self.cleaned_caps is None:
            raise ValueError("Cleaned tables have not been prepared.")

        dates = self.cleaned_factors[self.date_column].to_numpy()
        boundaries = np.flatnonzero(dates[1:] != dates[:-1]) + 1
        starts = np.concatenate(([0], boundaries))
        ends = np.concatenate((boundaries, [len(dates)]))

        factor_values = self.cleaned_factors.loc[:, self.factor_columns].to_numpy(dtype=np.float32, copy=False)
        return_values = self.cleaned_returns[self.return_column].to_numpy(dtype=np.float32, copy=False)
        cap_values = self.cleaned_caps[self.cap_column].to_numpy(dtype=np.float32, copy=False)
        assets = self.cleaned_factors[self.asset_column].to_numpy()

        for start, end in zip(starts, ends, strict=True):
            yield dates[start], factor_values[start:end], return_values[start:end], cap_values[start:end], assets[start:end]

    def run_regression(self, min_obs: int | None = None) -> pd.DataFrame:
        if self.cleaned_factors is None or self.cleaned_returns is None or self.cleaned_caps is None:
            raise ValueError("Data not initialized.")

        required_obs = min_obs or max(len(self.factor_columns), 2)

        factor_return_rows: list[np.ndarray] = []
        factor_return_dates: list[object] = []
        residual_frames: list[pd.DataFrame] = []
        processed_frames: list[pd.DataFrame] = []

        for current_date, X_raw, y_raw, cap_raw, assets in self._iter_daily_slices():
            valid_mask = np.isfinite(y_raw) & np.all(np.isfinite(X_raw), axis=1) & np.isfinite(cap_raw) & (cap_raw > 0)
            if valid_mask.sum() < required_obs:
                continue

            X_valid = X_raw[valid_mask]
            y_valid = y_raw[valid_mask]
            cap_valid = cap_raw[valid_mask]
            assets_valid = assets[valid_mask]

            X_processed = self._preprocess_cross_section(X_valid)
            regression_weights = np.sqrt(cap_valid.astype(np.float64, copy=False))
            fit = sm.WLS(y_valid.astype(np.float64, copy=False), X_processed.astype(np.float64, copy=False), weights=regression_weights).fit()
            coeffs = fit.params.astype(np.float32, copy=False)
            residuals = fit.resid.astype(np.float32, copy=False)

            factor_return_dates.append(current_date)
            factor_return_rows.append(coeffs)

            processed_frames.append(
                pd.DataFrame(
                    {
                        self.date_column: current_date,
                        self.asset_column: assets_valid,
                        self.cap_column: cap_valid.astype(np.float32, copy=False),
                        **{column: X_processed[:, idx] for idx, column in enumerate(self.factor_columns)},
                    }
                )
            )
            residual_frames.append(
                pd.DataFrame(
                    {
                        self.date_column: current_date,
                        self.asset_column: assets_valid,
                        self.return_column: y_valid.astype(np.float32, copy=False),
                        self.cap_column: cap_valid.astype(np.float32, copy=False),
                        "residual": residuals,
                    }
                )
            )

        if not factor_return_rows:
            raise ValueError("No valid daily cross-sections were available for regression.")

        self.factor_returns = pd.DataFrame(
            np.vstack(factor_return_rows),
            index=pd.Index(factor_return_dates, name=self.date_column),
            columns=self.factor_columns,
        ).astype("float32")
        self.factor_returns.sort_index(inplace=True)

        self.specific_returns = pd.concat(residual_frames, ignore_index=True)
        self.processed_exposures = pd.concat(processed_frames, ignore_index=True)

        residual_history = self.specific_returns.loc[:, [self.date_column, self.asset_column, "residual"]].copy()
        residual_history = residual_history.sort_values(
            [self.asset_column, self.date_column],
            kind="stable",
            ignore_index=True,
        )

        expanding_std = (
            residual_history.groupby(self.asset_column, sort=False)["residual"]
            .expanding(min_periods=1)
            .std()
            .reset_index(level=0, drop=True)
        )
        residual_history["specific_std_daily"] = expanding_std.astype("float32")

        daily_median = (
            residual_history.groupby(self.date_column, sort=False)["specific_std_daily"]
            .median()
            .rename("daily_market_median")
            .reset_index()
        )
        residual_history = residual_history.merge(
            daily_median,
            on=self.date_column,
            how="left",
            validate="many_to_one",
        )

        residual_history["specific_std_daily"] = residual_history["specific_std_daily"].fillna(
            residual_history["daily_market_median"]
        )
        latest_date = residual_history[self.date_column].max()
        latest_specific_risk = residual_history.loc[
            residual_history[self.date_column] == latest_date,
            [self.date_column, self.asset_column, "specific_std_daily"],
        ].copy()

        latest_median = latest_specific_risk["specific_std_daily"].median()
        latest_specific_risk["specific_std_daily"] = latest_specific_risk["specific_std_daily"].fillna(latest_median)
        latest_specific_risk["specific_std_daily"] = latest_specific_risk["specific_std_daily"].fillna(0.0)
        latest_specific_risk["specific_var_annual"] = (
            latest_specific_risk["specific_std_daily"].astype("float32") ** 2 * 252.0
        ).astype("float32")

        self.specific_risk = latest_specific_risk.loc[:, [self.asset_column, "specific_var_annual"]].copy()
        return self.factor_returns

    def estimate_covariance(
        self,
        *,
        half_life: int = 63,
        annualization: int = 252,
    ) -> pd.DataFrame:
        if self.factor_returns is None:
            raise ValueError("Run run_regression() before estimate_covariance().")
        if half_life <= 0:
            raise ValueError("half_life must be positive.")

        F = self.factor_returns.to_numpy(dtype=np.float64, copy=False)
        n_obs = F.shape[0]
        if n_obs <= 1:
            raise ValueError("At least two factor return observations are required.")

        decay = np.exp(np.log(0.5) / half_life)
        weights = decay ** np.arange(n_obs - 1, -1, -1, dtype=np.float64)
        weights /= weights.sum()

        ewma_mean = np.average(F, axis=0, weights=weights)
        centered = F - ewma_mean
        weighted_centered = centered * np.sqrt(weights[:, None])
        ewma_cov = weighted_centered.T @ weighted_centered
        combined_cov = ewma_cov * float(annualization)

        self.factor_covariance = pd.DataFrame(
            combined_cov.astype("float32"),
            index=self.factor_columns,
            columns=self.factor_columns,
        )
        return self.factor_covariance

    def run_full_pipeline(
        self,
        *,
        min_obs: int | None = None,
        half_life: int = 63,
        annualization: int = 252,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        factor_returns = self.run_regression(min_obs=min_obs)
        covariance = self.estimate_covariance(half_life=half_life, annualization=annualization)
        if self.specific_returns is None:
            raise ValueError("Specific returns were not generated.")
        return factor_returns, covariance, self.specific_returns

    def save_outputs(
        self,
        output_dir: str | Path,
        *,
        save_factor_returns: bool = True,
        save_specific_returns: bool = True,
        save_specific_risk: bool = True,
    ) -> dict[str, Path]:
        if self.factor_covariance is None:
            raise ValueError("Run estimate_covariance() or run_full_pipeline() before save_outputs().")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: dict[str, Path] = {}

        covariance_path = output_dir / "factor_covariance.parquet"
        self.factor_covariance.to_parquet(covariance_path)
        saved_paths["factor_covariance"] = covariance_path

        if save_factor_returns and self.factor_returns is not None:
            factor_returns_path = output_dir / "factor_returns.parquet"
            self.factor_returns.reset_index().to_parquet(factor_returns_path, index=False)
            saved_paths["factor_returns"] = factor_returns_path

        if save_specific_returns and self.specific_returns is not None:
            specific_returns_path = output_dir / "specific_returns.parquet"
            self.specific_returns.to_parquet(specific_returns_path, index=False)
            saved_paths["specific_returns"] = specific_returns_path

        if save_specific_risk and self.specific_risk is not None:
            specific_risk_path = output_dir / "specific_risk.parquet"
            self.specific_risk.to_parquet(specific_risk_path, index=False)
            saved_paths["specific_risk"] = specific_risk_path

        return saved_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Barra Layer 2 risk engine.")
    parser.add_argument("--factor-path", required=False, help="Path to cleaned_factors.parquet.")
    parser.add_argument("--return-path", required=False, help="Path to cleaned_returns.parquet.")
    parser.add_argument("--cap-path", required=False, help="Path to cleaned_market_cap.parquet.")
    parser.add_argument("--output-dir", required=False, help="Directory for covariance and regression outputs.")
    parser.add_argument("--half-life", type=int, default=63, help="EWMA half-life in trading days.")
    parser.add_argument("--min-obs", type=int, default=None, help="Minimum assets per daily cross-section.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    factor_path = args.factor_path or DEFAULT_FACTOR_PATH
    return_path = args.return_path or DEFAULT_RETURN_PATH
    cap_path = args.cap_path or DEFAULT_CAP_PATH
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR

    missing = [
        name
        for name, value in (
            ("factor_path", factor_path),
            ("return_path", return_path),
            ("cap_path", cap_path),
            ("output_dir", output_dir),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required runtime paths: "
            + ", ".join(missing)
            + ". Pass them by CLI or set DEFAULT_FACTOR_PATH / DEFAULT_RETURN_PATH / DEFAULT_CAP_PATH / DEFAULT_OUTPUT_DIR in barra_risk.py."
        )

        pass

    engine = BarraRiskEngine(factor_path=factor_path, return_path=return_path, cap_path=cap_path)
    factor_returns, covariance, specific_returns = engine.run_full_pipeline(
        min_obs=args.min_obs,
        half_life=args.half_life,
    )
    saved_paths = engine.save_outputs(output_dir)

    print(f"factor_days={len(factor_returns)} factor_count={factor_returns.shape[1]}")
    print(f"covariance_shape={covariance.shape}")
    print(f"specific_rows={len(specific_returns)}")
    if engine.specific_risk is not None:
        print(f"specific_assets={len(engine.specific_risk)}")
    print(f"factor_covariance_path={saved_paths['factor_covariance']}")


if __name__ == "__main__":
    main()
