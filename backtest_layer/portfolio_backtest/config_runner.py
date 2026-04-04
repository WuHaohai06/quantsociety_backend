from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import PortfolioBacktestConfig, RegistryConfig, TableInputConfig, load_config
from .portfolio_backtest import PortfolioBacktestArtifactBuilder
from .strategy_registry import StrategyRegistryEvaluator


def _is_csv_path(path: Path) -> bool:
    return path.suffix.lower() == ".csv"


def _is_parquet_path(path: Path) -> bool:
    return path.suffix.lower() in {".parquet", ".pq"}


def _collect_input_paths(config: TableInputConfig) -> tuple[list[Path], str]:
    base_path = Path(config.path)
    if base_path.is_file():
        if config.format == "infer":
            if _is_csv_path(base_path):
                return [base_path], "csv"
            if _is_parquet_path(base_path):
                return [base_path], "parquet"
            raise ValueError(f"不支持的输入文件类型: {base_path}")
        return [base_path], config.format

    if not base_path.is_dir():
        raise ValueError(f"输入路径必须是文件或目录: {config.path}")

    search_pattern = config.glob or ("**/*" if config.recursive else "*")
    candidates = [path for path in sorted(base_path.glob(search_pattern)) if path.is_file()]
    csv_paths = [path for path in candidates if _is_csv_path(path)]
    parquet_paths = [path for path in candidates if _is_parquet_path(path)]

    if config.format == "csv":
        if not csv_paths:
            raise FileNotFoundError(f"目录下未找到 CSV 文件: {config.path}")
        return csv_paths, "csv"
    if config.format == "parquet":
        if not parquet_paths:
            raise FileNotFoundError(f"目录下未找到 Parquet 文件: {config.path}")
        return parquet_paths, "parquet"

    found_formats = []
    if csv_paths:
        found_formats.append("csv")
    if parquet_paths:
        found_formats.append("parquet")
    if not found_formats:
        raise FileNotFoundError(f"目录下未找到可读的 CSV/Parquet 文件: {config.path}")
    if len(found_formats) > 1:
        raise ValueError(
            f"inputs 路径包含多种文件格式，请显式指定 format 或 glob: {config.path}"
        )
    input_format = found_formats[0]
    return (csv_paths if input_format == "csv" else parquet_paths), input_format


def load_input_frame(config: TableInputConfig) -> pd.DataFrame:
    paths, input_format = _collect_input_paths(config)
    if input_format == "csv":
        frame = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    else:
        frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    if config.rename:
        frame = frame.rename(columns=dict(config.rename))
    return frame


def build_backtest_builder(
    config: PortfolioBacktestConfig,
    *,
    tradable_df: pd.DataFrame | None = None,
    benchmark_df: pd.DataFrame | None = None,
) -> PortfolioBacktestArtifactBuilder:
    return PortfolioBacktestArtifactBuilder(
        annualization=config.backtest.annualization,
        return_window=config.backtest.return_window,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
        date_col=config.columns.date_col,
        symbol_col=config.columns.symbol_col,
        weight_col=config.columns.weight_col,
        price_col=config.columns.price_col,
        tradable_df=tradable_df,
        tradable_date_col=config.columns.tradable_date_col,
        tradable_symbol_col=config.columns.tradable_symbol_col,
        tradable_flag_col=config.columns.tradable_flag_col,
        output_root=config.output.output_root,
        strategy_name=config.meta.strategy_name,
        benchmark_df=benchmark_df,
        benchmark_date_col=config.columns.benchmark_date_col,
        benchmark_return_col=config.columns.benchmark_return_col,
    )


def build_registry_evaluator(config: RegistryConfig) -> StrategyRegistryEvaluator:
    return StrategyRegistryEvaluator(
        min_trade_days=config.min_trade_days,
        min_annual_return=config.min_annual_return,
        min_sharpe=config.min_sharpe,
        min_calmar=config.min_calmar,
        max_drawdown_limit=config.max_drawdown_limit,
        max_annual_volatility=config.max_annual_volatility,
        min_monthly_win_rate=config.min_monthly_win_rate,
        max_turnover_mean=config.max_turnover_mean,
        min_effective_data_ratio=config.min_effective_data_ratio,
        max_top5_day_pnl_contribution=config.max_top5_day_pnl_contribution,
    )


def _write_config_snapshot(config_path: str | Path, output_dir: str | Path) -> str:
    snapshot_path = Path(output_dir) / "config_snapshot.yaml"
    snapshot_path.write_text(Path(config_path).read_text(encoding="utf-8"), encoding="utf-8")
    return str(snapshot_path)


def run_with_config(
    config: PortfolioBacktestConfig,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    holdings_df = load_input_frame(config.inputs.holdings)
    kline_df = load_input_frame(config.inputs.kline)
    tradable_df = load_input_frame(config.inputs.tradable) if config.inputs.tradable is not None else None
    benchmark_df = load_input_frame(config.inputs.benchmark) if config.inputs.benchmark is not None else None

    builder = build_backtest_builder(
        config,
        tradable_df=tradable_df,
        benchmark_df=benchmark_df,
    )
    backtest_result = builder.build(
        holdings_df=holdings_df,
        kline_df=kline_df,
        run_name=config.meta.run_name,
    )

    config_snapshot = None
    if config_path is not None:
        config_snapshot = _write_config_snapshot(config_path, backtest_result["output_dir"])

    registry_result = None
    if config.registry.enabled:
        evaluator = build_registry_evaluator(config.registry)
        registry_result = evaluator.evaluate(backtest_result["output_dir"])

    return {
        "config": config,
        "holdings_df": holdings_df,
        "kline_df": kline_df,
        "tradable_df": tradable_df,
        "benchmark_df": benchmark_df,
        "backtest": backtest_result,
        "registry": registry_result,
        "output_dir": backtest_result["output_dir"],
        "config_snapshot": config_snapshot,
    }


def run_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    return run_with_config(config, config_path=config_path)