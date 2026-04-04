from __future__ import annotations

from pathlib import Path
import sys

import pytest

pd = pytest.importorskip("pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_layer.data import (  # noqa: E402
    CANONICAL_SYMBOL_COLUMN,
    CANONICAL_TIMESTAMP_COLUMN,
    FACTOR_VALUE_COLUMN,
    FactorRef,
    build_factor_panel,
    load_factor_long,
    project_single_asset,
)


def _write_factor(
    lake_root: Path,
    factor_id: str,
    rows: list[tuple[str, str, float]],
) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def test_load_factor_long_normalizes_and_filters_symbol_early(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    _write_factor(
        lake_root,
        "alpha_v1",
        [
            ("2024-01-01", "AAA", 1.0),
            ("2024-01-02", "AAA", 1.2),
            ("2024-01-02", "BBB", 2.0),
            ("2024-01-03", "AAA", 1.3),
        ],
    )

    result = load_factor_long(
        lake_root,
        "alpha_v1",
        start="2024-01-02",
        end="2024-01-03",
        symbols=["AAA"],
    )

    assert list(result.columns) == [
        CANONICAL_TIMESTAMP_COLUMN,
        CANONICAL_SYMBOL_COLUMN,
        FACTOR_VALUE_COLUMN,
    ]
    assert result[CANONICAL_SYMBOL_COLUMN].tolist() == ["AAA", "AAA"]
    assert result[FACTOR_VALUE_COLUMN].tolist() == pytest.approx([1.2, 1.3])


def test_build_factor_panel_returns_sparse_outer_panel(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    _write_factor(
        lake_root,
        "value_v1",
        [
            ("2024-01-02", "AAA", 1.0),
            ("2024-01-03", "BBB", 2.0),
        ],
    )
    _write_factor(
        lake_root,
        "quality_v1",
        [
            ("2024-01-02", "BBB", 10.0),
            ("2024-01-04", "AAA", 20.0),
        ],
    )

    panel = build_factor_panel(
        lake_root,
        [
            FactorRef("value_v1", "value_factor"),
            FactorRef("quality_v1", "quality_factor"),
        ],
        align_method="outer",
    )

    keys = {
        (row.timestamp.strftime("%Y-%m-%d"), row.symbol)
        for row in panel.itertuples(index=False)
    }
    assert len(panel) == 4
    assert keys == {
        ("2024-01-02", "AAA"),
        ("2024-01-02", "BBB"),
        ("2024-01-03", "BBB"),
        ("2024-01-04", "AAA"),
    }
    assert ("2024-01-03", "AAA") not in keys
    assert ("2024-01-04", "BBB") not in keys


def test_build_factor_panel_supports_asof_backward_and_symbol_filter(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    _write_factor(
        lake_root,
        "anchor_v1",
        [
            ("2024-01-02", "AAA", 1.0),
            ("2024-01-03", "AAA", 2.0),
            ("2024-01-03", "BBB", 3.0),
        ],
    )
    _write_factor(
        lake_root,
        "aux_v1",
        [
            ("2024-01-01", "AAA", 10.0),
            ("2024-01-03", "AAA", 20.0),
            ("2024-01-02", "BBB", 30.0),
        ],
    )

    panel = build_factor_panel(
        lake_root,
        [FactorRef("anchor_v1", "anchor"), FactorRef("aux_v1", "aux")],
        align_method="asof_backward",
        anchor_factor="anchor",
        symbols=["AAA"],
    )

    assert panel[CANONICAL_SYMBOL_COLUMN].tolist() == ["AAA", "AAA"]
    assert panel["aux"].tolist() == pytest.approx([10.0, 20.0])


def test_project_single_asset_returns_time_indexed_factor_frame():
    panel = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-02",
                    "2024-01-02",
                    "2024-01-03",
                ]
            ),
            "symbol": ["AAA", "BBB", "AAA"],
            "f1": [1.0, 9.0, 2.0],
            "f2": [3.0, 8.0, 4.0],
        }
    )

    result = project_single_asset(panel, "AAA")

    assert result.index.name == "timestamp"
    assert list(result.columns) == ["f1", "f2"]
    assert result.loc[pd.Timestamp("2024-01-02"), "f1"] == pytest.approx(1.0)
    assert result.loc[pd.Timestamp("2024-01-03"), "f2"] == pytest.approx(4.0)