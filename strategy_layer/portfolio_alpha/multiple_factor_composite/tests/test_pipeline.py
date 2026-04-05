from __future__ import annotations

from pathlib import Path
import sys

import pytest

pd = pytest.importorskip("pandas")
yaml = pytest.importorskip("yaml")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import OrthogonalizationStepConfig, WeightingConfig
from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import FactorSpec
from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import load_config
from strategy_layer.portfolio_alpha.multiple_factor_composite.factor_reader import FactorLakeReader
from strategy_layer.portfolio_alpha.multiple_factor_composite.orthogonalization import apply_orthogonalization_steps
from strategy_layer.portfolio_alpha.multiple_factor_composite.pipeline import run_from_config
from strategy_layer.portfolio_alpha.multiple_factor_composite.weighting import compute_weight_history


def _write_factor(lake_root: Path, factor_id: str, rows: list[tuple[str, str, float]]) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def _write_auxiliary(path: Path, rows: list[tuple[str, str, object, float | None]]) -> None:
    frame = pd.DataFrame(rows, columns=["timestamp", "symbol", "industry", "fwd_return_5d"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def test_run_from_config_writes_signal_artifacts(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    output_root = tmp_path / "run_output"
    aux_path = tmp_path / "auxiliary" / "controls.parquet"

    value_rows = []
    quality_rows = []
    size_rows = []
    aux_rows = []
    for day_idx, day in enumerate(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]):
        for asset_idx, asset in enumerate(["AAA", "BBB", "CCC", "DDD"]):
            size = float(asset_idx + 1)
            value = float(5 - asset_idx + day_idx * 0.1)
            quality = float(value * 0.8 + size * 0.2)
            value_rows.append((day, asset, value))
            quality_rows.append((day, asset, quality))
            size_rows.append((day, asset, size))
            aux_rows.append((day, asset, "G1" if asset_idx < 2 else "G2", float(value * 0.05)))

    _write_factor(lake_root, "value_factor_v1", value_rows)
    _write_factor(lake_root, "quality_factor_v1", quality_rows)
    _write_factor(lake_root, "size_factor_v1", size_rows)
    _write_auxiliary(aux_path, aux_rows)

    config_path = tmp_path / "composite_signal.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "meta": {
                    "signal_id": "demo_signal",
                    "version": "v1",
                },
                "source": {
                    "factor_lake_root": str(lake_root),
                    "start": "2024-01-02",
                    "end": "2024-01-05",
                    "align_method": "outer",
                },
                "factors": [
                    {"factor_id": "value_factor_v1", "alias": "value", "group": "value"},
                    {"factor_id": "quality_factor_v1", "alias": "quality", "group": "quality"},
                    {"factor_id": "size_factor_v1", "alias": "size", "compose": False},
                ],
                "auxiliary_sources": [
                    {
                        "name": "controls",
                        "path": str(aux_path),
                        "columns": {
                            "industry": "industry",
                            "fwd_return_5d": "fwd_return_5d",
                        },
                        "align_method": "exact",
                    }
                ],
                "preprocess": {
                    "winsorize": {"enabled": True, "method": "quantile", "lower": 0.05, "upper": 0.95},
                    "standardize": {"method": "zscore"},
                    "fillna": {"method": "keep"},
                },
                "neutralization": {
                    "steps": [
                        {"method": "group_demean", "factors": ["value", "quality"], "group_column": "industry"},
                        {"method": "ols", "factors": ["value", "quality"], "control_columns": ["size"]},
                    ]
                },
                "orthogonalization": {
                    "steps": [
                        {"method": "sequential", "factors": ["value", "quality"], "order": ["value", "quality"], "renormalize": True}
                    ]
                },
                "composition": {
                    "weighting": {"method": "equal"},
                    "final_transform": "rank",
                    "long_top_k": 1,
                },
                "output": {
                    "root": str(output_root),
                },
            },
            sort_keys=False,
        )
    )

    result = run_from_config(config_path)
    signal = result["signal"]

    assert not signal.empty
    assert set(["timestamp", "symbol", "composite_score", "rank", "selected_flag", "side", "signal_id", "signal_version"]).issubset(signal.columns)
    assert signal.groupby("timestamp")["selected_flag"].sum().eq(1).all()
    assert (output_root / "signals" / "composite_signal.parquet").exists()
    assert (output_root / "panels" / "raw_factor_panel.parquet").exists()
    assert (output_root / "panels" / "orthogonalized_factor_panel.parquet").exists()
    assert (output_root / "weights" / "weight_history.parquet").exists()
    assert (output_root / "manifest.json").exists()
    assert (output_root / "config_snapshot.yaml").exists()


def test_run_from_config_accepts_unquoted_yaml_dates(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    output_root = tmp_path / "run_output"

    _write_factor(
        lake_root,
        "single_factor_v1",
        [
            ("2024-01-02", "AAA", 1.0),
            ("2024-01-02", "BBB", 2.0),
            ("2024-01-03", "AAA", 1.5),
            ("2024-01-03", "BBB", 2.5),
        ],
    )

    config_path = tmp_path / "unquoted_dates.yaml"
    config_path.write_text(
        "\n".join(
            [
                "meta:",
                "  signal_id: unquoted_dates_demo",
                "  version: v1",
                "source:",
                f"  factor_lake_root: {lake_root}",
                "  start: 2024-01-02",
                "  end: 2024-01-03 23:59:59",
                "factors:",
                "  - factor_id: single_factor_v1",
                "    alias: single_factor",
                "composition:",
                "  weighting:",
                "    method: equal",
                "  final_transform: zscore",
                "  long_top_k: 1",
                "output:",
                f"  root: {output_root}",
            ]
        )
    )

    result = run_from_config(config_path)

    assert not result["signal"].empty
    assert (output_root / "signals" / "composite_signal.parquet").exists()


def test_load_config_defaults_output_root_to_workspace_data_and_resolves_relative_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace_root = tmp_path / "workspace_data"
    monkeypatch.setenv("QUANTSOCIETY_WORKSPACE_DATA_ROOT", str(workspace_root))

    factor_lake_root = tmp_path / "factor_lake"
    auxiliary_path = tmp_path / "auxiliary" / "controls.parquet"
    auxiliary_path.parent.mkdir(parents=True, exist_ok=True)
    auxiliary_path.write_bytes(b"")

    config_path = tmp_path / "relative_defaults.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "meta": {"signal_id": "relative_defaults", "version": "v2"},
                "source": {"factor_lake_root": "./factor_lake"},
                "factors": [{"factor_id": "value_factor_v1", "alias": "value"}],
                "auxiliary_sources": [
                    {
                        "name": "controls",
                        "path": "./auxiliary/controls.parquet",
                    }
                ],
            },
            sort_keys=False,
        )
    )

    config = load_config(config_path)

    assert config.source.factor_lake_root == str(factor_lake_root.resolve())
    assert config.auxiliary_sources[0].path == str(auxiliary_path.resolve())
    assert config.output is not None
    assert config.output.root == str(workspace_root / "strategy" / "composite_signals" / "relative_defaults_v2")


def test_factor_reader_returns_canonical_timestamp_symbol(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"

    _write_factor(
        lake_root,
        "value_factor_v1",
        [
            ("2024-01-02", "AAA", 1.0),
            ("2024-01-02", "BBB", 9.0),
            ("2024-01-03", "AAA", 1.5),
        ],
    )
    _write_factor(
        lake_root,
        "quality_factor_v1",
        [
            ("2024-01-02", "AAA", 3.0),
            ("2024-01-03", "AAA", 4.0),
        ],
    )

    reader = FactorLakeReader(lake_root)
    panel = reader.load_factors(
        [
            FactorSpec(factor_id="value_factor_v1", alias="value"),
            FactorSpec(factor_id="quality_factor_v1", alias="quality"),
        ],
        start="2024-01-02",
        end="2024-01-03",
        symbols=["AAA"],
    )

    assert list(panel.columns) == ["timestamp", "symbol", "value", "quality"]
    assert panel["symbol"].tolist() == ["AAA", "AAA"]
    assert panel["value"].tolist() == [1.0, 1.5]
    assert panel["quality"].tolist() == [3.0, 4.0]


def test_ic_weighting_uses_target_column():
    panel = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-01", "2024-01-01", "2024-01-01",
                    "2024-01-02", "2024-01-02", "2024-01-02",
                    "2024-01-03", "2024-01-03", "2024-01-03",
                ]
            ),
            "symbol": ["A", "B", "C"] * 3,
            "value": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5, 1.1, 2.1, 3.1],
            "quality": [3.0, 2.0, 1.0, 3.2, 2.2, 1.2, 3.1, 2.1, 1.1],
            "fwd_return_5d": [0.1, 0.2, 0.3, 0.12, 0.22, 0.32, 0.11, 0.21, 0.31],
        }
    )

    weight_history = compute_weight_history(
        panel,
        ["value", "quality"],
        WeightingConfig(
            method="ic",
            target_column="fwd_return_5d",
            lookback_periods=2,
            min_history=1,
            correlation="spearman",
        ),
    )

    latest = weight_history.sort_values("timestamp").iloc[-1]
    assert latest["value"] > 0
    assert latest["quality"] < 0


def test_symmetric_orthogonalization_reduces_pairwise_correlation():
    panel = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01"] * 6),
            "symbol": ["A", "B", "C", "D", "E", "F"],
            "f1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "f2": [1.1, 2.1, 3.1, 4.2, 5.1, 6.2],
        }
    )

    before = panel[["f1", "f2"]].corr().iloc[0, 1]
    result = apply_orthogonalization_steps(
        panel,
        ["f1", "f2"],
        (
            OrthogonalizationStepConfig(
                method="symmetric",
                factors=("f1", "f2"),
                shrinkage=0.0,
                renormalize=True,
            ),
        ),
    )
    after = result[["f1", "f2"]].corr().iloc[0, 1]

    assert abs(before) > 0.9
    assert abs(after) < 0.2