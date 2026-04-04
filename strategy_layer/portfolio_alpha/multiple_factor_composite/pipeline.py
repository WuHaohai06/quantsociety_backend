from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import CompositeSignalConfig, load_config
from strategy_layer.portfolio_alpha.multiple_factor_composite.factor_reader import AuxiliaryParquetLoader, FactorLakeReader, align_auxiliary_to_panel
from strategy_layer.portfolio_alpha.multiple_factor_composite.neutralization import apply_neutralization_steps
from strategy_layer.portfolio_alpha.multiple_factor_composite.orthogonalization import apply_orthogonalization_steps
from strategy_layer.portfolio_alpha.multiple_factor_composite.panel_preprocess import apply_factor_directions, preprocess_panel, standardize_panel
from strategy_layer.portfolio_alpha.multiple_factor_composite.weighting import compose_signal, compute_weight_history


def _filter_universe(panel: pd.DataFrame, config: CompositeSignalConfig) -> pd.DataFrame:
    out = panel.copy()
    if config.universe.membership_column and config.universe.include_values:
        out = out[out[config.universe.membership_column].isin(config.universe.include_values)].copy()
    if config.universe.min_assets_per_date is not None:
        counts = out.groupby("datetime")["asset"].nunique()
        valid_dates = counts[counts >= int(config.universe.min_assets_per_date)].index
        out = out[out["datetime"].isin(valid_dates)].copy()
    return out.reset_index(drop=True)


def _write_panel(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return str(path)


def _write_outputs(
    config: CompositeSignalConfig,
    *,
    config_path: Path | None,
    raw_panel: pd.DataFrame,
    preprocessed_panel: pd.DataFrame,
    neutralized_panel: pd.DataFrame,
    orthogonalized_panel: pd.DataFrame,
    weight_history: pd.DataFrame,
    signal_frame: pd.DataFrame,
) -> dict[str, str]:
    assert config.output is not None
    root = Path(config.output.root)
    root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    if config.output.write_raw_panel:
        outputs["raw_panel"] = _write_panel(root / "panels" / "raw_factor_panel.parquet", raw_panel)
    if config.output.write_preprocessed_panel:
        outputs["preprocessed_panel"] = _write_panel(
            root / "panels" / "preprocessed_factor_panel.parquet",
            preprocessed_panel,
        )
    if config.output.write_neutralized_panel:
        outputs["neutralized_panel"] = _write_panel(
            root / "panels" / "neutralized_factor_panel.parquet",
            neutralized_panel,
        )
    if config.output.write_orthogonalized_panel:
        outputs["orthogonalized_panel"] = _write_panel(
            root / "panels" / "orthogonalized_factor_panel.parquet",
            orthogonalized_panel,
        )
    if config.output.write_weight_history:
        outputs["weight_history"] = _write_panel(root / "weights" / "weight_history.parquet", weight_history)

    outputs["signal"] = _write_panel(root / "signals" / config.output.signal_filename, signal_frame)

    manifest = {
        "signal_id": config.meta.signal_id,
        "version": config.meta.version,
        "factor_ids": [factor.factor_id for factor in config.factors],
        "factor_names": config.factor_names,
        "composed_factor_names": config.composed_factor_names,
        "row_count": int(len(signal_frame)),
        "output_files": outputs,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    outputs["manifest"] = str(manifest_path)

    if config_path is not None:
        snapshot_path = root / "config_snapshot.yaml"
        snapshot_path.write_text(config_path.read_text())
        outputs["config_snapshot"] = str(snapshot_path)

    return outputs


def run_pipeline(config: CompositeSignalConfig, *, config_path: str | Path | None = None) -> dict[str, Any]:
    reader = FactorLakeReader(config.source.factor_lake_root)
    raw_panel = reader.load_factors(
        list(config.factors),
        start=config.source.start,
        end=config.source.end,
        align_method=config.source.align_method,
        anchor_factor=config.source.anchor_factor,
    )

    directions = {factor.name: factor.direction for factor in config.factors}
    raw_panel = apply_factor_directions(raw_panel, directions)

    auxiliary_loader = AuxiliaryParquetLoader()
    enriched_panel = raw_panel
    for source in config.auxiliary_sources:
        auxiliary = auxiliary_loader.load(source, start=config.source.start, end=config.source.end)
        enriched_panel = align_auxiliary_to_panel(
            enriched_panel,
            auxiliary,
            method=source.align_method,
        )

    enriched_panel = _filter_universe(enriched_panel, config)

    factor_columns = config.factor_names
    composed_factor_columns = config.composed_factor_names
    preprocessed_panel = preprocess_panel(enriched_panel, factor_columns, config.preprocess)
    neutralized_panel = apply_neutralization_steps(
        preprocessed_panel,
        composed_factor_columns,
        config.neutralization_steps,
    )
    neutralized_panel = standardize_panel(
        neutralized_panel,
        composed_factor_columns,
        config.preprocess.standardize.method,
    )

    orthogonalized_panel = apply_orthogonalization_steps(
        neutralized_panel,
        composed_factor_columns,
        config.orthogonalization_steps,
    )
    orthogonalized_panel = standardize_panel(
        orthogonalized_panel,
        composed_factor_columns,
        config.preprocess.standardize.method,
    )

    weight_history = compute_weight_history(
        orthogonalized_panel,
        composed_factor_columns,
        config.composition.weighting,
    )
    signal_frame = compose_signal(
        orthogonalized_panel,
        composed_factor_columns,
        weight_history,
        config.composition,
    )
    signal_frame["signal_id"] = config.meta.signal_id
    signal_frame["signal_version"] = config.meta.version

    outputs = _write_outputs(
        config,
        config_path=Path(config_path) if config_path is not None else None,
        raw_panel=raw_panel,
        preprocessed_panel=preprocessed_panel,
        neutralized_panel=neutralized_panel,
        orthogonalized_panel=orthogonalized_panel,
        weight_history=weight_history,
        signal_frame=signal_frame,
    )

    return {
        "raw_panel": raw_panel,
        "preprocessed_panel": preprocessed_panel,
        "neutralized_panel": neutralized_panel,
        "orthogonalized_panel": orthogonalized_panel,
        "weight_history": weight_history,
        "signal": signal_frame,
        "outputs": outputs,
    }


def run_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    return run_pipeline(config, config_path=config_path)