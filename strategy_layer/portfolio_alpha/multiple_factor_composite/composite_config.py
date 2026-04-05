from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from workspace_paths import default_composite_signal_root, default_factor_lake_root


@dataclass(frozen=True)
class MetaConfig:
    signal_id: str
    version: str = "v1"
    description: str | None = None


@dataclass(frozen=True)
class SourceConfig:
    factor_lake_root: str
    start: str | None = None
    end: str | None = None
    align_method: str = "outer"
    anchor_factor: str | None = None


@dataclass(frozen=True)
class FactorSpec:
    factor_id: str
    alias: str | None = None
    group: str | None = None
    direction: float = 1.0
    compose: bool = True
    required: bool = True

    @property
    def name(self) -> str:
        return self.alias or self.factor_id


@dataclass(frozen=True)
class AuxiliarySourceConfig:
    name: str
    path: str
    timestamp_col: str = "timestamp"
    symbol_col: str = "symbol"
    columns: dict[str, str] = field(default_factory=dict)
    recursive: bool = True
    align_method: str = "exact"


@dataclass(frozen=True)
class UniverseConfig:
    membership_column: str | None = None
    include_values: tuple[str, ...] = ()
    min_assets_per_date: int | None = None


@dataclass(frozen=True)
class WinsorizeConfig:
    enabled: bool = True
    method: str = "quantile"
    lower: float = 0.01
    upper: float = 0.99


@dataclass(frozen=True)
class StandardizeConfig:
    method: str = "zscore"


@dataclass(frozen=True)
class FillnaConfig:
    method: str = "keep"


@dataclass(frozen=True)
class PreprocessConfig:
    winsorize: WinsorizeConfig = field(default_factory=WinsorizeConfig)
    standardize: StandardizeConfig = field(default_factory=StandardizeConfig)
    fillna: FillnaConfig = field(default_factory=FillnaConfig)


@dataclass(frozen=True)
class NeutralizationStepConfig:
    method: str
    factors: tuple[str, ...] = ()
    group_column: str | None = None
    control_columns: tuple[str, ...] = ()
    add_intercept: bool = True


@dataclass(frozen=True)
class OrthogonalizationStepConfig:
    method: str
    factors: tuple[str, ...] = ()
    order: tuple[str, ...] = ()
    shrinkage: float = 0.05
    renormalize: bool = True


@dataclass(frozen=True)
class WeightingConfig:
    method: str = "equal"
    custom_weights: dict[str, float] = field(default_factory=dict)
    target_column: str | None = None
    lookback_periods: int = 20
    correlation: str = "spearman"
    min_history: int = 5
    fallback: str = "equal"


@dataclass(frozen=True)
class CompositionConfig:
    weighting: WeightingConfig = field(default_factory=WeightingConfig)
    final_transform: str = "zscore"
    long_top_k: int | None = None
    short_bottom_k: int | None = None
    score_column: str = "composite_score"


@dataclass(frozen=True)
class OutputConfig:
    root: str
    write_raw_panel: bool = True
    write_preprocessed_panel: bool = True
    write_neutralized_panel: bool = True
    write_orthogonalized_panel: bool = True
    write_weight_history: bool = True
    signal_filename: str = "composite_signal.parquet"


@dataclass(frozen=True)
class CompositeSignalConfig:
    meta: MetaConfig
    source: SourceConfig
    factors: tuple[FactorSpec, ...]
    auxiliary_sources: tuple[AuxiliarySourceConfig, ...] = ()
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    neutralization_steps: tuple[NeutralizationStepConfig, ...] = ()
    orthogonalization_steps: tuple[OrthogonalizationStepConfig, ...] = ()
    composition: CompositionConfig = field(default_factory=CompositionConfig)
    output: OutputConfig | None = None

    @property
    def factor_names(self) -> list[str]:
        return [spec.name for spec in self.factors]

    @property
    def composed_factor_names(self) -> list[str]:
        return [spec.name for spec in self.factors if spec.compose]


def _as_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是 object")
    return dict(value)


def _as_list_of_mappings(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须是数组")
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} 的每一项都必须是 object")
        out.append(dict(item))
    return out


def _normalize_scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _resolve_path_text(value: Any, *, base_dir: Path, field_name: str) -> str | None:
    text = _normalize_scalar_text(value)
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"{field_name} 不能为空")
    path = Path(stripped)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def load_config(path: str | Path) -> CompositeSignalConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("配置文件顶层必须是 object")
    base_dir = config_path.parent.resolve()

    meta_payload = _as_mapping(payload.get("meta"), field_name="meta")
    source_payload = _as_mapping(payload.get("source"), field_name="source")
    output_payload = _as_mapping(payload.get("output"), field_name="output")
    universe_payload = _as_mapping(payload.get("universe"), field_name="universe")
    preprocess_payload = _as_mapping(payload.get("preprocess"), field_name="preprocess")
    neutralization_payload = _as_mapping(
        payload.get("neutralization"), field_name="neutralization"
    )
    orthogonalization_payload = _as_mapping(
        payload.get("orthogonalization"), field_name="orthogonalization"
    )
    composition_payload = _as_mapping(payload.get("composition"), field_name="composition")

    factors_payload = payload.get("factors")
    if not isinstance(factors_payload, list) or not factors_payload:
        raise ValueError("factors 必须是非空数组")

    meta = MetaConfig(
        signal_id=str(meta_payload.get("signal_id") or "composite_signal"),
        version=str(meta_payload.get("version") or "v1"),
        description=meta_payload.get("description"),
    )

    factor_lake_root = _resolve_path_text(
        source_payload.get("factor_lake_root"),
        base_dir=base_dir,
        field_name="source.factor_lake_root",
    ) or str(default_factor_lake_root())
    source = SourceConfig(
        factor_lake_root=factor_lake_root,
        start=_normalize_scalar_text(source_payload.get("start")),
        end=_normalize_scalar_text(source_payload.get("end")),
        align_method=str(source_payload.get("align_method") or "outer"),
        anchor_factor=source_payload.get("anchor_factor"),
    )

    factors = []
    for raw in factors_payload:
        if not isinstance(raw, dict):
            raise ValueError("factors 的每一项都必须是 object")
        factor_id = raw.get("factor_id")
        if not isinstance(factor_id, str) or not factor_id.strip():
            raise ValueError("factor.factor_id 不能为空")
        factors.append(
            FactorSpec(
                factor_id=factor_id,
                alias=raw.get("alias"),
                group=raw.get("group"),
                direction=float(raw.get("direction", 1.0)),
                compose=bool(raw.get("compose", True)),
                required=bool(raw.get("required", True)),
            )
        )

    auxiliary_sources = []
    for raw in _as_list_of_mappings(payload.get("auxiliary_sources"), field_name="auxiliary_sources"):
        name = raw.get("name")
        data_path = _resolve_path_text(raw.get("path"), base_dir=base_dir, field_name="auxiliary_sources.path")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("auxiliary_sources.name 不能为空")
        if data_path is None:
            raise ValueError("auxiliary_sources.path 不能为空")
        auxiliary_sources.append(
            AuxiliarySourceConfig(
                name=name,
                path=data_path,
                timestamp_col=str(raw.get("timestamp_col") or "timestamp"),
                symbol_col=str(raw.get("symbol_col") or raw.get("asset_col") or "symbol"),
                columns=dict(raw.get("columns") or {}),
                recursive=bool(raw.get("recursive", True)),
                align_method=str(raw.get("align_method") or "exact"),
            )
        )

    universe = UniverseConfig(
        membership_column=universe_payload.get("membership_column"),
        include_values=tuple(universe_payload.get("include_values") or ()),
        min_assets_per_date=universe_payload.get("min_assets_per_date"),
    )

    winsorize_payload = _as_mapping(preprocess_payload.get("winsorize"), field_name="preprocess.winsorize")
    standardize_payload = _as_mapping(preprocess_payload.get("standardize"), field_name="preprocess.standardize")
    fillna_payload = _as_mapping(preprocess_payload.get("fillna"), field_name="preprocess.fillna")
    preprocess = PreprocessConfig(
        winsorize=WinsorizeConfig(
            enabled=bool(winsorize_payload.get("enabled", True)),
            method=str(winsorize_payload.get("method") or "quantile"),
            lower=float(winsorize_payload.get("lower", 0.01)),
            upper=float(winsorize_payload.get("upper", 0.99)),
        ),
        standardize=StandardizeConfig(
            method=str(standardize_payload.get("method") or "zscore")
        ),
        fillna=FillnaConfig(method=str(fillna_payload.get("method") or "keep")),
    )

    neutralization_steps = []
    for raw in _as_list_of_mappings(neutralization_payload.get("steps"), field_name="neutralization.steps"):
        neutralization_steps.append(
            NeutralizationStepConfig(
                method=str(raw.get("method") or "none"),
                factors=tuple(raw.get("factors") or ()),
                group_column=raw.get("group_column"),
                control_columns=tuple(raw.get("control_columns") or ()),
                add_intercept=bool(raw.get("add_intercept", True)),
            )
        )

    orthogonalization_steps = []
    for raw in _as_list_of_mappings(orthogonalization_payload.get("steps"), field_name="orthogonalization.steps"):
        orthogonalization_steps.append(
            OrthogonalizationStepConfig(
                method=str(raw.get("method") or "none"),
                factors=tuple(raw.get("factors") or ()),
                order=tuple(raw.get("order") or ()),
                shrinkage=float(raw.get("shrinkage", 0.05)),
                renormalize=bool(raw.get("renormalize", True)),
            )
        )

    weighting_payload = _as_mapping(composition_payload.get("weighting"), field_name="composition.weighting")
    composition = CompositionConfig(
        weighting=WeightingConfig(
            method=str(weighting_payload.get("method") or "equal"),
            custom_weights={
                str(key): float(value)
                for key, value in dict(weighting_payload.get("custom_weights") or {}).items()
            },
            target_column=weighting_payload.get("target_column"),
            lookback_periods=int(weighting_payload.get("lookback_periods", 20)),
            correlation=str(weighting_payload.get("correlation") or "spearman"),
            min_history=int(weighting_payload.get("min_history", 5)),
            fallback=str(weighting_payload.get("fallback") or "equal"),
        ),
        final_transform=str(composition_payload.get("final_transform") or "zscore"),
        long_top_k=composition_payload.get("long_top_k"),
        short_bottom_k=composition_payload.get("short_bottom_k"),
        score_column=str(composition_payload.get("score_column") or "composite_score"),
    )

    output_root = _resolve_path_text(
        output_payload.get("root"),
        base_dir=base_dir,
        field_name="output.root",
    ) or str(default_composite_signal_root(meta.signal_id, meta.version))
    output = OutputConfig(
        root=output_root,
        write_raw_panel=bool(output_payload.get("write_raw_panel", True)),
        write_preprocessed_panel=bool(output_payload.get("write_preprocessed_panel", True)),
        write_neutralized_panel=bool(output_payload.get("write_neutralized_panel", True)),
        write_orthogonalized_panel=bool(output_payload.get("write_orthogonalized_panel", True)),
        write_weight_history=bool(output_payload.get("write_weight_history", True)),
        signal_filename=str(output_payload.get("signal_filename") or "composite_signal.parquet"),
    )

    return CompositeSignalConfig(
        meta=meta,
        source=source,
        factors=tuple(factors),
        auxiliary_sources=tuple(auxiliary_sources),
        universe=universe,
        preprocess=preprocess,
        neutralization_steps=tuple(neutralization_steps),
        orthogonalization_steps=tuple(orthogonalization_steps),
        composition=composition,
        output=output,
    )