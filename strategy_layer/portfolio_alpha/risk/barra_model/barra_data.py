from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd


FACTOR_KEY_COLUMNS = ("date", "asset")
FACTOR_META_COLUMNS = ("datetime", "date", "asset")
MARKET_REQUIRED_COLUMNS = ("align_time", "ticker", "c")
CAP_REQUIRED_COLUMNS = ("datetime", "asset", "market_cap")
DEFAULT_FACTOR_PATH: str | None = None
DEFAULT_MARKET_PATH: str | None = None
DEFAULT_CAP_PATH: str | None = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\market_cap\market_cap_weights.parquet"
DEFAULT_OUTPUT_DIR: str | None = None
DEFAULT_FACTOR_COLUMNS: list[str] | None = None


def _normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _normalize_asset(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.upper()
    return normalized.where(normalized.notna() & (normalized != ""), pd.NA)


def _cast_float32(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype("float32")
    return result


def _resolve_factor_columns(df_factors: pd.DataFrame, factor_columns: Sequence[str] | None) -> list[str]:
    if factor_columns:
        missing = [column for column in factor_columns if column not in df_factors.columns]
        if missing:
            raise KeyError(f"Missing factor columns: {missing}")
        return list(factor_columns)

    inferred = [column for column in df_factors.columns if column not in FACTOR_META_COLUMNS]
    if not inferred:
        raise ValueError("No factor columns found. Provide --factor-columns explicitly.")
    return inferred


def _prepare_factor_template(
    df_factors: pd.DataFrame,
    factor_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    required = {"datetime", "asset"}
    missing = sorted(required - set(df_factors.columns))
    if missing:
        raise KeyError(f"Factor table missing required columns: {missing}")

    resolved_factor_columns = _resolve_factor_columns(df_factors, factor_columns)

    factor_frame = df_factors.copy()
    factor_frame["date"] = _normalize_date(factor_frame["datetime"])
    factor_frame["asset"] = _normalize_asset(factor_frame["asset"])
    factor_frame = factor_frame.loc[factor_frame["date"].notna() & factor_frame["asset"].notna()].copy()
    factor_frame = factor_frame.loc[:, ["date", "asset", *resolved_factor_columns]]
    factor_frame = _cast_float32(factor_frame, resolved_factor_columns)
    factor_frame = factor_frame.drop_duplicates(subset=list(FACTOR_KEY_COLUMNS), keep="last", ignore_index=True)
    factor_frame = factor_frame.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)
    return factor_frame, resolved_factor_columns


def _prepare_market_returns(df_market: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(MARKET_REQUIRED_COLUMNS) - set(df_market.columns))
    if missing:
        raise KeyError(f"Market table missing required columns: {missing}")

    market_frame = df_market.copy()
    market_frame["date"] = _normalize_date(market_frame["align_time"])
    market_frame["ticker"] = _normalize_asset(market_frame["ticker"])
    market_frame["c"] = pd.to_numeric(market_frame["c"], errors="coerce").astype("float32")
    market_frame = market_frame.loc[market_frame["date"].notna() & market_frame["ticker"].notna()].copy()
    market_frame = market_frame.sort_values(["ticker", "date"], kind="stable", ignore_index=True)
    market_frame = market_frame.drop_duplicates(subset=["date", "ticker"], keep="last", ignore_index=True)

    next_close = market_frame.groupby("ticker", sort=False)["c"].shift(-1)
    market_frame["next_ret"] = ((next_close / market_frame["c"]) - 1.0).astype("float32")
    return market_frame.loc[:, ["date", "ticker", "next_ret"]]


def _prepare_market_caps(df_cap: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(CAP_REQUIRED_COLUMNS) - set(df_cap.columns))
    if missing:
        raise KeyError(f"Market cap table missing required columns: {missing}")

    cap_frame = df_cap.copy()
    cap_frame["date"] = _normalize_date(cap_frame["datetime"])
    cap_frame["asset"] = _normalize_asset(cap_frame["asset"])
    cap_frame["market_cap"] = pd.to_numeric(cap_frame["market_cap"], errors="coerce").astype("float32")
    cap_frame = cap_frame.loc[
        cap_frame["date"].notna() & cap_frame["asset"].notna() & cap_frame["market_cap"].notna()
    ].copy()
    cap_frame = cap_frame.drop_duplicates(subset=list(FACTOR_KEY_COLUMNS), keep="last", ignore_index=True)
    cap_frame = cap_frame.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)
    return cap_frame.loc[:, ["date", "asset", "market_cap"]]


def align_barra_exposures_and_returns(
    df_factors: pd.DataFrame,
    df_market: pd.DataFrame,
    df_cap: pd.DataFrame | None = None,
    factor_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    factor_template, resolved_factor_columns = _prepare_factor_template(df_factors, factor_columns=factor_columns)
    market_returns = _prepare_market_returns(df_market)

    aligned = factor_template.merge(
        market_returns,
        left_on=["date", "asset"],
        right_on=["date", "ticker"],
        how="left",
        sort=False,
        validate="one_to_one",
    )
    aligned = aligned.drop(columns=["ticker"])
    aligned = aligned.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)

    cleaned_factors = aligned.loc[:, ["date", "asset", *resolved_factor_columns]].copy()
    cleaned_returns = aligned.loc[:, ["date", "asset", "next_ret"]].copy()
    cleaned_factors = cleaned_factors.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)
    cleaned_returns = cleaned_returns.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)

    if len(cleaned_factors) != len(cleaned_returns):
        raise ValueError("Row count mismatch between cleaned factor and return outputs.")

    factor_index = pd.MultiIndex.from_frame(cleaned_factors.loc[:, ["date", "asset"]])
    return_index = pd.MultiIndex.from_frame(cleaned_returns.loc[:, ["date", "asset"]])
    if not factor_index.equals(return_index):
        raise ValueError("Output indexes do not match on (date, asset).")

    cleaned_caps: pd.DataFrame | None = None
    if df_cap is not None:
        market_caps = _prepare_market_caps(df_cap)
        cleaned_caps = factor_template.merge(
            market_caps,
            on=["date", "asset"],
            how="left",
            sort=False,
            validate="one_to_one",
        )
        cleaned_caps = cleaned_caps.loc[:, ["date", "asset", "market_cap"]].copy()
        cleaned_caps = cleaned_caps.sort_values(list(FACTOR_KEY_COLUMNS), kind="stable", ignore_index=True)
        cap_index = pd.MultiIndex.from_frame(cleaned_caps.loc[:, ["date", "asset"]])
        if not factor_index.equals(cap_index):
            raise ValueError("Cap output index does not match factor/return outputs.")

    return cleaned_factors, cleaned_returns, cleaned_caps


def generate_aligned_datasets(
    factor_path: str | Path,
    market_path: str | Path,
    output_dir: str | Path,
    cap_path: str | Path | None = None,
    factor_columns: Sequence[str] | None = None,
) -> tuple[Path, Path, Path | None]:
    factor_path = Path(factor_path)
    market_path = Path(market_path)
    output_dir = Path(output_dir)

    df_factors = pd.read_parquet(factor_path)
    df_market = pd.read_parquet(market_path)
    df_cap = pd.read_parquet(cap_path) if cap_path is not None else None

    cleaned_factors, cleaned_returns, cleaned_caps = align_barra_exposures_and_returns(
        df_factors=df_factors,
        df_market=df_market,
        df_cap=df_cap,
        factor_columns=factor_columns,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    factor_output_path = output_dir / "cleaned_factors.parquet"
    return_output_path = output_dir / "cleaned_returns.parquet"
    cap_output_path = output_dir / "cleaned_market_cap.parquet" if cleaned_caps is not None else None

    cleaned_factors.to_parquet(factor_output_path, index=False)
    cleaned_returns.to_parquet(return_output_path, index=False)
    if cleaned_caps is not None and cap_output_path is not None:
        cleaned_caps.to_parquet(cap_output_path, index=False)

    return factor_output_path, return_output_path, cap_output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Factor-driven Barra alignment engine.")
    parser.add_argument("--factor-path", required=False, help="Input parquet path for factor exposures.")
    parser.add_argument("--market-path", required=False, help="Input parquet path for market prices.")
    parser.add_argument("--cap-path", required=False, help="Input parquet path for market cap data.")
    parser.add_argument("--output-dir", required=False, help="Directory to store cleaned parquet outputs.")
    parser.add_argument(
        "--factor-columns",
        nargs="+",
        default=None,
        help="Optional explicit factor columns. If omitted, all non-key columns are treated as factors.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    factor_path = args.factor_path or DEFAULT_FACTOR_PATH
    market_path = args.market_path or DEFAULT_MARKET_PATH
    cap_path = args.cap_path or DEFAULT_CAP_PATH
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    factor_columns = args.factor_columns or DEFAULT_FACTOR_COLUMNS

    missing = [
        name
        for name, value in (
            ("factor_path", factor_path),
            ("market_path", market_path),
            ("cap_path", cap_path),
            ("output_dir", output_dir),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required runtime paths: "
            + ", ".join(missing)
            + ". Pass them by CLI or set DEFAULT_FACTOR_PATH / DEFAULT_MARKET_PATH / DEFAULT_CAP_PATH / DEFAULT_OUTPUT_DIR in barra_data.py."
        )

    factor_output_path, return_output_path, cap_output_path = generate_aligned_datasets(
        factor_path=factor_path,
        market_path=market_path,
        cap_path=cap_path,
        output_dir=output_dir,
        factor_columns=factor_columns,
    )

    cleaned_factors = pd.read_parquet(factor_output_path, columns=["date", "asset"])
    cleaned_returns = pd.read_parquet(return_output_path, columns=["date", "asset", "next_ret"])
    cleaned_caps = pd.read_parquet(cap_output_path, columns=["date", "asset", "market_cap"]) if cap_output_path else None

    matched_index = pd.MultiIndex.from_frame(cleaned_factors).equals(
        pd.MultiIndex.from_frame(cleaned_returns.loc[:, ["date", "asset"]])
    )
    cap_index_match = (
        pd.MultiIndex.from_frame(cleaned_factors).equals(
            pd.MultiIndex.from_frame(cleaned_caps.loc[:, ["date", "asset"]])
        )
        if cleaned_caps is not None
        else True
    )

    print(f"cleaned_factors -> {factor_output_path}")
    print(f"cleaned_returns -> {return_output_path}")
    if cap_output_path is not None:
        print(f"cleaned_market_cap -> {cap_output_path}")
    print(f"rows={len(cleaned_factors)} index_match={matched_index}")
    print(f"cap_index_match={cap_index_match}")
    print(f"return_nan_count={int(cleaned_returns['next_ret'].isna().sum())}")


if __name__ == "__main__":
    main()
