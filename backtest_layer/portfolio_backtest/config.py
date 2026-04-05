from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from workspace_paths import default_portfolio_backtest_root

InputFormat = Literal["infer", "csv", "parquet"]


@dataclass(frozen=True)
class MetaConfig:
    strategy_name: str
    run_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class TableInputConfig:
    path: str
    format: InputFormat = "infer"
    recursive: bool = True
    glob: str | None = None
    rename: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InputsConfig:
    holdings: TableInputConfig
    kline: TableInputConfig
    tradable: TableInputConfig | None = None
    benchmark: TableInputConfig | None = None


@dataclass(frozen=True)
class ColumnsConfig:
    date_col: str = "trade_date"
    symbol_col: str = "symbol"
    weight_col: str = "weight"
    price_col: str = "close"
    tradable_date_col: str = "trade_date"
    tradable_symbol_col: str = "symbol"
    tradable_flag_col: str = "is_tradable"
    benchmark_date_col: str = "trade_date"
    benchmark_return_col: str = "benchmark_return"


@dataclass(frozen=True)
class BacktestConfig:
    annualization: int = 252
    return_window: int = 1
    fee_rate: float = 0.0003
    slippage_rate: float = 0.0002


@dataclass(frozen=True)
class OutputConfig:
    output_root: str = field(default_factory=lambda: str(default_portfolio_backtest_root()))


@dataclass(frozen=True)
class RegistryConfig:
    enabled: bool = False
    min_trade_days: int = 120
    min_annual_return: float = 0.05
    min_sharpe: float = 0.8
    min_calmar: float = 0.5
    max_drawdown_limit: float = -0.20
    max_annual_volatility: float = 0.40
    min_monthly_win_rate: float = 0.45
    max_turnover_mean: float = 1.0
    min_effective_data_ratio: float = 0.95
    max_top5_day_pnl_contribution: float = 0.50


@dataclass(frozen=True)
class PortfolioBacktestConfig:
    meta: MetaConfig
    inputs: InputsConfig
    columns: ColumnsConfig = field(default_factory=ColumnsConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)


def _as_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是 object")
    return dict(value)


def _normalize_scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _require_non_empty_text(value: Any, *, field_name: str) -> str:
    text = _normalize_scalar_text(value)
    if text is None or not text.strip():
        raise ValueError(f"{field_name} 不能为空")
    return text.strip()


def _resolve_path_text(value: Any, *, field_name: str, base_dir: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{field_name} 必须是路径字符串")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} 不能为空字符串")
    expanded = Path(os.path.expandvars(os.path.expanduser(text)))
    if not expanded.is_absolute():
        expanded = (base_dir / expanded).resolve()
    return str(expanded)


def _parse_table_input(
    raw: Any,
    *,
    field_name: str,
    base_dir: Path,
    required: bool,
) -> TableInputConfig | None:
    if raw is None:
        if required:
            raise ValueError(f"{field_name} 不能为空")
        return None
    payload = _as_mapping(raw, field_name=field_name)
    path = _resolve_path_text(payload.get("path"), field_name=f"{field_name}.path", base_dir=base_dir)
    if path is None:
        if required:
            raise ValueError(f"{field_name}.path 不能为空")
        return None
    input_format = (_normalize_scalar_text(payload.get("format")) or "infer").lower()
    if input_format not in {"infer", "csv", "parquet"}:
        raise ValueError(f"{field_name}.format 不支持: {input_format}")
    rename_payload = _as_mapping(payload.get("rename"), field_name=f"{field_name}.rename")
    return TableInputConfig(
        path=path,
        format=input_format,  # type: ignore[arg-type]
        recursive=bool(payload.get("recursive", True)),
        glob=_normalize_scalar_text(payload.get("glob")),
        rename={str(key): str(value) for key, value in rename_payload.items()},
    )


def _validate_meta_config(config: MetaConfig) -> None:
    if not config.strategy_name.strip():
        raise ValueError("meta.strategy_name 不能为空")


def _validate_table_input(config: TableInputConfig, *, field_name: str) -> None:
    path = Path(config.path)
    if not path.exists():
        raise ValueError(f"{field_name}.path 不存在: {config.path}")
    if not path.is_file() and not path.is_dir():
        raise ValueError(f"{field_name}.path 必须是文件或目录: {config.path}")
    if config.format not in {"infer", "csv", "parquet"}:
        raise ValueError(f"{field_name}.format 不支持: {config.format}")
    if config.glob is not None and not config.glob.strip():
        raise ValueError(f"{field_name}.glob 不能为空字符串")
    for source_name, target_name in config.rename.items():
        if not str(source_name).strip() or not str(target_name).strip():
            raise ValueError(f"{field_name}.rename 中的列名不能为空")


def _validate_columns_config(config: ColumnsConfig) -> None:
    fields = {
        "date_col": config.date_col,
        "symbol_col": config.symbol_col,
        "weight_col": config.weight_col,
        "price_col": config.price_col,
        "tradable_date_col": config.tradable_date_col,
        "tradable_symbol_col": config.tradable_symbol_col,
        "tradable_flag_col": config.tradable_flag_col,
        "benchmark_date_col": config.benchmark_date_col,
        "benchmark_return_col": config.benchmark_return_col,
    }
    for field_name, value in fields.items():
        if not str(value).strip():
            raise ValueError(f"columns.{field_name} 不能为空")


def _validate_backtest_config(config: BacktestConfig) -> None:
    if config.annualization <= 0:
        raise ValueError("backtest.annualization 必须大于 0")
    if config.return_window <= 0:
        raise ValueError("backtest.return_window 必须大于 0")
    if config.fee_rate < 0:
        raise ValueError("backtest.fee_rate 不能小于 0")
    if config.slippage_rate < 0:
        raise ValueError("backtest.slippage_rate 不能小于 0")


def _validate_output_config(config: OutputConfig) -> None:
    if not str(config.output_root).strip():
        raise ValueError("output.output_root 不能为空")


def _validate_registry_config(config: RegistryConfig) -> None:
    if config.min_trade_days < 0:
        raise ValueError("registry.min_trade_days 不能小于 0")


def load_config(path: str | Path) -> PortfolioBacktestConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("配置文件顶层必须是 object")

    base_dir = config_path.resolve().parent
    meta_payload = _as_mapping(payload.get("meta"), field_name="meta")
    inputs_payload = _as_mapping(payload.get("inputs"), field_name="inputs")
    columns_payload = _as_mapping(payload.get("columns"), field_name="columns")
    backtest_payload = _as_mapping(payload.get("backtest"), field_name="backtest")
    output_payload = _as_mapping(payload.get("output"), field_name="output")
    registry_payload = _as_mapping(payload.get("registry"), field_name="registry")

    meta = MetaConfig(
        strategy_name=_require_non_empty_text(
            meta_payload.get("strategy_name"),
            field_name="meta.strategy_name",
        ),
        run_name=_normalize_scalar_text(meta_payload.get("run_name")),
        description=_normalize_scalar_text(meta_payload.get("description")),
    )

    inputs = InputsConfig(
        holdings=_parse_table_input(
            inputs_payload.get("holdings"),
            field_name="inputs.holdings",
            base_dir=base_dir,
            required=True,
        ),
        kline=_parse_table_input(
            inputs_payload.get("kline"),
            field_name="inputs.kline",
            base_dir=base_dir,
            required=True,
        ),
        tradable=_parse_table_input(
            inputs_payload.get("tradable"),
            field_name="inputs.tradable",
            base_dir=base_dir,
            required=False,
        ),
        benchmark=_parse_table_input(
            inputs_payload.get("benchmark"),
            field_name="inputs.benchmark",
            base_dir=base_dir,
            required=False,
        ),
    )

    columns = ColumnsConfig(
        date_col=_normalize_scalar_text(columns_payload.get("date_col")) or "trade_date",
        symbol_col=_normalize_scalar_text(columns_payload.get("symbol_col")) or "symbol",
        weight_col=_normalize_scalar_text(columns_payload.get("weight_col")) or "weight",
        price_col=_normalize_scalar_text(columns_payload.get("price_col")) or "close",
        tradable_date_col=_normalize_scalar_text(columns_payload.get("tradable_date_col")) or "trade_date",
        tradable_symbol_col=_normalize_scalar_text(columns_payload.get("tradable_symbol_col")) or "symbol",
        tradable_flag_col=_normalize_scalar_text(columns_payload.get("tradable_flag_col")) or "is_tradable",
        benchmark_date_col=_normalize_scalar_text(columns_payload.get("benchmark_date_col")) or "trade_date",
        benchmark_return_col=_normalize_scalar_text(columns_payload.get("benchmark_return_col")) or "benchmark_return",
    )

    backtest = BacktestConfig(
        annualization=int(backtest_payload.get("annualization", 252)),
        return_window=int(backtest_payload.get("return_window", 1)),
        fee_rate=float(backtest_payload.get("fee_rate", 0.0003)),
        slippage_rate=float(backtest_payload.get("slippage_rate", 0.0002)),
    )

    output = OutputConfig(
        output_root=_resolve_path_text(
            output_payload.get("output_root"),
            field_name="output.output_root",
            base_dir=base_dir,
        )
        or str(default_portfolio_backtest_root()),
    )

    registry = RegistryConfig(
        enabled=bool(registry_payload.get("enabled", False)),
        min_trade_days=int(registry_payload.get("min_trade_days", 120)),
        min_annual_return=float(registry_payload.get("min_annual_return", 0.05)),
        min_sharpe=float(registry_payload.get("min_sharpe", 0.8)),
        min_calmar=float(registry_payload.get("min_calmar", 0.5)),
        max_drawdown_limit=float(registry_payload.get("max_drawdown_limit", -0.20)),
        max_annual_volatility=float(registry_payload.get("max_annual_volatility", 0.40)),
        min_monthly_win_rate=float(registry_payload.get("min_monthly_win_rate", 0.45)),
        max_turnover_mean=float(registry_payload.get("max_turnover_mean", 1.0)),
        min_effective_data_ratio=float(registry_payload.get("min_effective_data_ratio", 0.95)),
        max_top5_day_pnl_contribution=float(
            registry_payload.get("max_top5_day_pnl_contribution", 0.50)
        ),
    )

    config = PortfolioBacktestConfig(
        meta=meta,
        inputs=inputs,
        columns=columns,
        backtest=backtest,
        output=output,
        registry=registry,
    )

    _validate_meta_config(config.meta)
    _validate_table_input(config.inputs.holdings, field_name="inputs.holdings")
    _validate_table_input(config.inputs.kline, field_name="inputs.kline")
    if config.inputs.tradable is not None:
        _validate_table_input(config.inputs.tradable, field_name="inputs.tradable")
    if config.inputs.benchmark is not None:
        _validate_table_input(config.inputs.benchmark, field_name="inputs.benchmark")
    _validate_columns_config(config.columns)
    _validate_backtest_config(config.backtest)
    _validate_output_config(config.output)
    _validate_registry_config(config.registry)

    return config