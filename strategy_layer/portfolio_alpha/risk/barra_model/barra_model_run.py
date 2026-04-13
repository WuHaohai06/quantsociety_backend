from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from strategy_layer.data import FactorRef
from strategy_layer.portfolio_alpha.risk.barra_model import barra_data, project_inputs


DEFAULT_FACTOR_PATH: str | None = None
DEFAULT_MARKET_PATH: str | None = None
DEFAULT_CAP_PATH: str | None = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\market_cap\market_cap_weights.parquet"
DEFAULT_OUTPUT_DIR: str | None = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx"


def _normalize_factor_refs(factor_refs: Sequence[str | FactorRef] | None) -> list[FactorRef]:
    if factor_refs is None:
        return []

    normalized: list[FactorRef] = []
    for item in factor_refs:
        if isinstance(item, FactorRef):
            normalized.append(item)
            continue

        text = str(item).strip()
        if not text:
            continue
        if ":" in text:
            factor_id, alias = text.split(":", 1)
            factor_id = factor_id.strip()
            alias = alias.strip()
            normalized.append(FactorRef(factor_id=factor_id, column_name=alias or None))
        else:
            normalized.append(FactorRef(factor_id=text, column_name=text))
    return normalized


def _write_cleaned_outputs(
    output_dir: str | Path,
    cleaned_factors: pd.DataFrame,
    cleaned_returns: pd.DataFrame,
    cleaned_caps: pd.DataFrame | None,
) -> tuple[Path, Path, Path | None]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    factor_output_path = output_dir / "cleaned_factors.parquet"
    return_output_path = output_dir / "cleaned_returns.parquet"
    cap_output_path = output_dir / "cleaned_market_cap.parquet" if cleaned_caps is not None else None

    cleaned_factors.to_parquet(factor_output_path, index=False)
    cleaned_returns.to_parquet(return_output_path, index=False)
    if cleaned_caps is not None and cap_output_path is not None:
        cleaned_caps.to_parquet(cap_output_path, index=False)

    return factor_output_path, return_output_path, cap_output_path


def _run_risk_engine(
    *,
    factor_path: str | Path,
    return_path: str | Path,
    cap_path: str | Path,
    output_dir: str | Path,
    half_life: int = 63,
    lags: int = 2,
    min_obs: int | None = None,
) -> pd.DataFrame:
    from strategy_layer.portfolio_alpha.risk.barra_model import barra_risk

    engine = barra_risk.BarraRiskEngine(
        factor_path=factor_path,
        return_path=return_path,
        cap_path=cap_path,
    )
    factor_returns, covariance, specific_returns = engine.run_full_pipeline(
        min_obs=min_obs,
        half_life=half_life,
        lags=lags,
    )
    saved_paths = engine.save_outputs(output_dir)

    print(f"factor_days={len(factor_returns)} factor_count={factor_returns.shape[1]}")
    print(f"covariance_shape={covariance.shape}")
    print(f"specific_rows={len(specific_returns)}")
    if engine.specific_risk is not None:
        print(f"specific_assets={len(engine.specific_risk)}")
    print(f"factor_covariance_path={saved_paths['factor_covariance']}")
    return covariance


def _run_file_mode(
    *,
    factor_path: str | Path,
    market_path: str | Path,
    cap_path: str | Path,
    output_dir: str | Path,
    factor_columns: Sequence[str] | None = None,
    half_life: int = 63,
    lags: int = 2,
    min_obs: int | None = None,
) -> pd.DataFrame:
    print("进行数据对齐")
    factor_output_path, return_output_path, cap_output_path = barra_data.generate_aligned_datasets(
        factor_path=factor_path,
        market_path=market_path,
        cap_path=cap_path,
        output_dir=output_dir,
        factor_columns=factor_columns,
    )
    if cap_output_path is None:
        raise ValueError("Market cap alignment output was not generated.")

    print("启动风险引擎")
    return _run_risk_engine(
        factor_path=factor_output_path,
        return_path=return_output_path,
        cap_path=cap_output_path,
        output_dir=output_dir,
        half_life=half_life,
        lags=lags,
        min_obs=min_obs,
    )


def _run_project_mode(
    *,
    factor_lake_root: str | Path,
    aggregate_bars_root: str | Path,
    stocks_floats_root: str | Path,
    factor_refs: Sequence[str | FactorRef] | None,
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    symbols: Sequence[str] | None = None,
    factor_align_method: str = "outer",
    factor_anchor: str | None = None,
    market_dataset: str = project_inputs.DEFAULT_MARKET_DATASET,
    floats_dataset: str = project_inputs.DEFAULT_FLOATS_DATASET,
    market_timestamp_column: str = "align_time",
    market_symbol_column: str = "ticker",
    market_close_column: str = "c",
    floats_timestamp_column: str = "effective_date",
    floats_symbol_column: str = "ticker",
    floats_column: str | None = None,
    factor_columns: Sequence[str] | None = None,
    half_life: int = 63,
    lags: int = 2,
    min_obs: int | None = None,
) -> pd.DataFrame:
    normalized_refs = _normalize_factor_refs(factor_refs)
    if not normalized_refs:
        raise ValueError("project mode requires factor_refs")

    print("进行真实数据接入与对齐")
    factors, market, market_cap = project_inputs.build_project_barra_inputs(
        factor_lake_root=factor_lake_root,
        factor_refs=normalized_refs,
        aggregate_bars_root=aggregate_bars_root,
        stocks_floats_root=stocks_floats_root,
        start=start,
        end=end,
        symbols=symbols,
        factor_align_method=factor_align_method,
        factor_anchor=factor_anchor,
        market_dataset=market_dataset,
        floats_dataset=floats_dataset,
        market_timestamp_column=market_timestamp_column,
        market_symbol_column=market_symbol_column,
        market_close_column=market_close_column,
        floats_timestamp_column=floats_timestamp_column,
        floats_symbol_column=floats_symbol_column,
        floats_column=floats_column,
    )

    if factor_columns is not None:
        selected_factor_columns = list(factor_columns)
        missing = [column for column in selected_factor_columns if column not in factors.columns]
        if missing:
            raise KeyError(f"Missing factor columns in project inputs: {missing}")
        factors = factors.loc[:, ["datetime", "asset", *selected_factor_columns]].copy()

    cleaned_factors, cleaned_returns, cleaned_caps = barra_data.align_barra_exposures_and_returns(
        df_factors=factors,
        df_market=market,
        df_cap=market_cap,
        factor_columns=factor_columns,
    )
    if cleaned_caps is None:
        raise ValueError("Project mode market cap alignment output was not generated.")

    factor_output_path, return_output_path, cap_output_path = _write_cleaned_outputs(
        output_dir=output_dir,
        cleaned_factors=cleaned_factors,
        cleaned_returns=cleaned_returns,
        cleaned_caps=cleaned_caps,
    )

    print("启动风险引擎")
    return _run_risk_engine(
        factor_path=factor_output_path,
        return_path=return_output_path,
        cap_path=cap_output_path,
        output_dir=output_dir,
        half_life=half_life,
        lags=lags,
        min_obs=min_obs,
    )


def run_barra_pipeline(
    *,
    mode: str = "file",
    output_dir: str | Path,
    factor_path: str | Path | None = None,
    market_path: str | Path | None = None,
    cap_path: str | Path | None = None,
    factor_lake_root: str | Path | None = None,
    aggregate_bars_root: str | Path | None = None,
    stocks_floats_root: str | Path | None = None,
    factor_refs: Sequence[str | FactorRef] | None = None,
    start: str | None = None,
    end: str | None = None,
    symbols: Sequence[str] | None = None,
    factor_align_method: str = "outer",
    factor_anchor: str | None = None,
    market_dataset: str = project_inputs.DEFAULT_MARKET_DATASET,
    floats_dataset: str = project_inputs.DEFAULT_FLOATS_DATASET,
    market_timestamp_column: str = "align_time",
    market_symbol_column: str = "ticker",
    market_close_column: str = "c",
    floats_timestamp_column: str = "effective_date",
    floats_symbol_column: str = "ticker",
    floats_column: str | None = None,
    factor_columns: Sequence[str] | None = None,
    half_life: int = 63,
    lags: int = 2,
    min_obs: int | None = None,
) -> pd.DataFrame:
    if mode == "file":
        missing = [
            name
            for name, value in (
                ("factor_path", factor_path),
                ("market_path", market_path),
                ("cap_path", cap_path),
            )
            if value is None
        ]
        if missing:
            raise ValueError("file mode requires factor_path, market_path, and cap_path")
        return _run_file_mode(
            factor_path=factor_path,
            market_path=market_path,
            cap_path=cap_path,
            output_dir=output_dir,
            factor_columns=factor_columns,
            half_life=half_life,
            lags=lags,
            min_obs=min_obs,
        )

    if mode == "project":
        missing = [
            name
            for name, value in (
                ("factor_lake_root", factor_lake_root),
                ("aggregate_bars_root", aggregate_bars_root),
                ("stocks_floats_root", stocks_floats_root),
            )
            if value is None
        ]
        if missing:
            raise ValueError("project mode requires factor_lake_root, aggregate_bars_root, and stocks_floats_root")
        return _run_project_mode(
            factor_lake_root=factor_lake_root,
            aggregate_bars_root=aggregate_bars_root,
            stocks_floats_root=stocks_floats_root,
            factor_refs=factor_refs,
            output_dir=output_dir,
            start=start,
            end=end,
            symbols=symbols,
            factor_align_method=factor_align_method,
            factor_anchor=factor_anchor,
            market_dataset=market_dataset,
            floats_dataset=floats_dataset,
            market_timestamp_column=market_timestamp_column,
            market_symbol_column=market_symbol_column,
            market_close_column=market_close_column,
            floats_timestamp_column=floats_timestamp_column,
            floats_symbol_column=floats_symbol_column,
            floats_column=floats_column,
            factor_columns=factor_columns,
            half_life=half_life,
            lags=lags,
            min_obs=min_obs,
        )

    raise ValueError(f"Unsupported mode: {mode}")


def start_to_finish(f_raw, m_raw, c_raw, out_dir):
    return run_barra_pipeline(
        mode="file",
        factor_path=f_raw,
        market_path=m_raw,
        cap_path=c_raw,
        output_dir=out_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Barra Layer 2 risk pipeline.")
    parser.add_argument("--mode", choices=("file", "project"), default="file")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for all cleaned and risk outputs.")
    parser.add_argument("--factor-path", default=DEFAULT_FACTOR_PATH, help="Path to input factor parquet for file mode.")
    parser.add_argument("--market-path", default=DEFAULT_MARKET_PATH, help="Path to input market parquet for file mode.")
    parser.add_argument("--cap-path", default=DEFAULT_CAP_PATH, help="Path to input market cap parquet for file mode.")
    parser.add_argument("--factor-lake-root", help="Factor lake root for project mode.")
    parser.add_argument("--aggregate-bars-root", help="Aggregate bars root for project mode.")
    parser.add_argument("--stocks-floats-root", help="Stocks floats root for project mode.")
    parser.add_argument(
        "--factor-ref",
        action="append",
        dest="factor_refs",
        help="Project mode factor ref, formatted as factor_id[:alias]. Can be repeated.",
    )
    parser.add_argument("--start", help="Optional inclusive start date for project mode.")
    parser.add_argument("--end", help="Optional inclusive end date for project mode.")
    parser.add_argument("--symbols", nargs="+", help="Optional subset of symbols for project mode.")
    parser.add_argument("--factor-align-method", default="outer", help="Factor lake alignment method.")
    parser.add_argument("--factor-anchor", help="Optional anchor factor for asof_backward alignment.")
    parser.add_argument("--market-dataset", default=project_inputs.DEFAULT_MARKET_DATASET, help="Market dataset folder name.")
    parser.add_argument("--floats-dataset", default=project_inputs.DEFAULT_FLOATS_DATASET, help="Float dataset folder name.")
    parser.add_argument("--market-timestamp-column", default="align_time", help="Market timestamp column name.")
    parser.add_argument("--market-symbol-column", default="ticker", help="Market symbol column name.")
    parser.add_argument("--market-close-column", default="c", help="Market close column name.")
    parser.add_argument("--floats-timestamp-column", default="effective_date", help="Float timestamp column name.")
    parser.add_argument("--floats-symbol-column", default="ticker", help="Float symbol column name.")
    parser.add_argument("--floats-column", help="Explicit float quantity column name.")
    parser.add_argument("--factor-columns", nargs="+", help="Optional explicit factor columns/order.")
    parser.add_argument("--half-life", type=int, default=63, help="EWMA half-life in trading days.")
    parser.add_argument("--lags", type=int, default=2, help="Newey-West lag count.")
    parser.add_argument("--min-obs", type=int, default=None, help="Minimum assets per daily cross-section.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_barra_pipeline(
        mode=args.mode,
        output_dir=args.output_dir,
        factor_path=args.factor_path,
        market_path=args.market_path,
        cap_path=args.cap_path,
        factor_lake_root=args.factor_lake_root,
        aggregate_bars_root=args.aggregate_bars_root,
        stocks_floats_root=args.stocks_floats_root,
        factor_refs=args.factor_refs,
        start=args.start,
        end=args.end,
        symbols=args.symbols,
        factor_align_method=args.factor_align_method,
        factor_anchor=args.factor_anchor,
        market_dataset=args.market_dataset,
        floats_dataset=args.floats_dataset,
        market_timestamp_column=args.market_timestamp_column,
        market_symbol_column=args.market_symbol_column,
        market_close_column=args.market_close_column,
        floats_timestamp_column=args.floats_timestamp_column,
        floats_symbol_column=args.floats_symbol_column,
        floats_column=args.floats_column,
        factor_columns=args.factor_columns,
        half_life=args.half_life,
        lags=args.lags,
        min_obs=args.min_obs,
    )


if __name__ == "__main__":
    main()
