from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from workspace_paths import default_holdings_root


@dataclass(frozen=True)
class MetaConfig:
    portfolio_id: str = "generated_holdings"
    version: str = "v1"
    description: str | None = None


@dataclass(frozen=True)
class SignalInputConfig:
    path: str
    format: str = "infer"
    recursive: bool = False
    glob: str = "*"
    rename: dict[str, str] = field(default_factory=dict)
    timestamp_col: str = "timestamp"
    symbol_col: str = "symbol"
    score_col: str | None = "composite_score"
    selected_flag_col: str | None = "selected_flag"
    side_col: str | None = "side"
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class InputsConfig:
    signal: SignalInputConfig


@dataclass(frozen=True)
class ConstructionConfig:
    selection_mode: str = "selected_flag"
    weighting_method: str = "equal"
    long_budget: float = 1.0
    short_budget: float = 0.0
    normalize_total_abs_weight: float | None = None
    score_abs_floor: float = 1e-12
    default_side: str = "LONG"


@dataclass(frozen=True)
class OptimizerConfig:
    enabled: bool = False
    name: str = "noop"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskControlConfig:
    enabled: bool = False
    name: str = "noop"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutputConfig:
    root: str
    holdings_filename: str = "holdings.parquet"
    selected_signal_filename: str = "selected_signal.parquet"
    raw_holdings_filename: str = "raw_holdings.parquet"
    summary_filename: str = "summary.json"
    write_selected_signal: bool = True
    write_raw_holdings: bool = True


@dataclass(frozen=True)
class HoldingsGenConfig:
    meta: MetaConfig = field(default_factory=MetaConfig)
    inputs: InputsConfig | None = None
    construction: ConstructionConfig = field(default_factory=ConstructionConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    risk_control: RiskControlConfig = field(default_factory=RiskControlConfig)
    output: OutputConfig | None = None


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


def _resolve_path(raw_path: str, *, base_dir: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def _validate_config(config: HoldingsGenConfig) -> HoldingsGenConfig:
    if config.inputs is None:
        raise ValueError("inputs 不能为空")
    if config.output is None:
        raise ValueError("output 不能为空")

    signal = config.inputs.signal
    if signal.format not in {"infer", "csv", "parquet"}:
        raise ValueError("inputs.signal.format 仅支持 infer/csv/parquet")
    if not signal.path.strip():
        raise ValueError("inputs.signal.path 不能为空")
    if not Path(signal.path).exists():
        raise ValueError(f"inputs.signal.path 不存在: {signal.path}")

    construction = config.construction
    if construction.selection_mode not in {"selected_flag", "all"}:
        raise ValueError("construction.selection_mode 仅支持 selected_flag/all")
    if construction.weighting_method not in {"equal", "score_proportional"}:
        raise ValueError("construction.weighting_method 仅支持 equal/score_proportional")
    if construction.long_budget < 0 or construction.short_budget < 0:
        raise ValueError("construction.long_budget/short_budget 不能为负数")
    if construction.normalize_total_abs_weight is not None and construction.normalize_total_abs_weight <= 0:
        raise ValueError("construction.normalize_total_abs_weight 必须大于 0")
    if construction.score_abs_floor <= 0:
        raise ValueError("construction.score_abs_floor 必须大于 0")

    if not config.output.root.strip():
        raise ValueError("output.root 不能为空")
    if not config.output.holdings_filename.strip():
        raise ValueError("output.holdings_filename 不能为空")

    return config


def load_config(path: str | Path) -> HoldingsGenConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("配置文件顶层必须是 object")

    base_dir = config_path.parent.resolve()
    meta_payload = _as_mapping(payload.get("meta"), field_name="meta")
    inputs_payload = _as_mapping(payload.get("inputs"), field_name="inputs")
    signal_payload = _as_mapping(inputs_payload.get("signal"), field_name="inputs.signal")
    construction_payload = _as_mapping(payload.get("construction"), field_name="construction")
    optimizer_payload = _as_mapping(payload.get("optimizer"), field_name="optimizer")
    risk_payload = _as_mapping(payload.get("risk_control"), field_name="risk_control")
    output_payload = _as_mapping(payload.get("output"), field_name="output")

    signal_path = signal_payload.get("path")
    if not isinstance(signal_path, str) or not signal_path.strip():
        raise ValueError("inputs.signal.path 不能为空")
    output_root = output_payload.get("root")
    if output_root is None:
        resolved_output_root = str(default_holdings_root(
            str(meta_payload.get("portfolio_id") or "generated_holdings"),
            str(meta_payload.get("version") or "v1"),
        ))
    elif isinstance(output_root, str) and output_root.strip():
        resolved_output_root = _resolve_path(output_root, base_dir=base_dir)
    else:
        raise ValueError("output.root 不能为空")

    config = HoldingsGenConfig(
        meta=MetaConfig(
            portfolio_id=str(meta_payload.get("portfolio_id") or "generated_holdings"),
            version=str(meta_payload.get("version") or "v1"),
            description=meta_payload.get("description"),
        ),
        inputs=InputsConfig(
            signal=SignalInputConfig(
                path=_resolve_path(signal_path, base_dir=base_dir),
                format=str(signal_payload.get("format") or "infer"),
                recursive=bool(signal_payload.get("recursive", False)),
                glob=str(signal_payload.get("glob") or "*"),
                rename={str(key): str(value) for key, value in _as_mapping(signal_payload.get("rename"), field_name="inputs.signal.rename").items()},
                timestamp_col=str(signal_payload.get("timestamp_col") or "timestamp"),
                symbol_col=str(signal_payload.get("symbol_col") or "symbol"),
                score_col=(None if signal_payload.get("score_col") is None else str(signal_payload.get("score_col") or "composite_score")),
                selected_flag_col=(None if signal_payload.get("selected_flag_col") is None else str(signal_payload.get("selected_flag_col") or "selected_flag")),
                side_col=(None if signal_payload.get("side_col") is None else str(signal_payload.get("side_col") or "side")),
                start=_normalize_scalar_text(signal_payload.get("start")),
                end=_normalize_scalar_text(signal_payload.get("end")),
            )
        ),
        construction=ConstructionConfig(
            selection_mode=str(construction_payload.get("selection_mode") or "selected_flag"),
            weighting_method=str(construction_payload.get("weighting_method") or "equal"),
            long_budget=float(construction_payload.get("long_budget", 1.0)),
            short_budget=float(construction_payload.get("short_budget", 0.0)),
            normalize_total_abs_weight=(None if construction_payload.get("normalize_total_abs_weight") is None else float(construction_payload.get("normalize_total_abs_weight"))),
            score_abs_floor=float(construction_payload.get("score_abs_floor", 1e-12)),
            default_side=str(construction_payload.get("default_side") or "LONG").upper(),
        ),
        optimizer=OptimizerConfig(
            enabled=bool(optimizer_payload.get("enabled", False)),
            name=str(optimizer_payload.get("name") or "noop"),
            params={str(key): value for key, value in _as_mapping(optimizer_payload.get("params"), field_name="optimizer.params").items()},
        ),
        risk_control=RiskControlConfig(
            enabled=bool(risk_payload.get("enabled", False)),
            name=str(risk_payload.get("name") or "noop"),
            params={str(key): value for key, value in _as_mapping(risk_payload.get("params"), field_name="risk_control.params").items()},
        ),
        output=OutputConfig(
            root=resolved_output_root,
            holdings_filename=str(output_payload.get("holdings_filename") or "holdings.parquet"),
            selected_signal_filename=str(output_payload.get("selected_signal_filename") or "selected_signal.parquet"),
            raw_holdings_filename=str(output_payload.get("raw_holdings_filename") or "raw_holdings.parquet"),
            summary_filename=str(output_payload.get("summary_filename") or "summary.json"),
            write_selected_signal=bool(output_payload.get("write_selected_signal", True)),
            write_raw_holdings=bool(output_payload.get("write_raw_holdings", True)),
        ),
    )
    return _validate_config(config)