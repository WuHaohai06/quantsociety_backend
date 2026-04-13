from __future__ import annotations

from pathlib import Path
import sys

import pytest

pd = pytest.importorskip("pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[6]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_layer.portfolio_alpha.risk.barra_model.barra_model_run import run_barra_pipeline
from strategy_layer.portfolio_alpha.risk.barra_model.project_inputs import build_project_barra_inputs


def _write_factor(lake_root: Path, factor_id: str, rows: list[tuple[str, str, float]]) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def _write_market_summary(root: Path, year: int, rows: list[tuple[str, str, float]]) -> None:
    dataset_dir = root / "daily_market_summary"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=["ticker", "align_time", "c"])
    frame["align_time"] = pd.to_datetime(frame["align_time"], utc=True)
    frame.to_parquet(dataset_dir / f"daily_market_summary_{year}.parquet", index=False)


def _write_floats(root: Path, year: int, rows: list[tuple[str, str, float]]) -> None:
    dataset_dir = root / "stocks_floats"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=["ticker", "effective_date", "free_float"])
    frame["effective_date"] = pd.to_datetime(frame["effective_date"], utc=True)
    frame.to_parquet(dataset_dir / f"stocks_floats_{year}.parquet", index=False)


def test_build_project_barra_inputs_uses_float_times_close(tmp_path: Path):
    lake_root = tmp_path / "factor_lake"
    market_root = tmp_path / "raw_market"
    floats_root = tmp_path / "raw_floats"

    _write_factor(
        lake_root,
        "value_factor_v1",
        [
            ("2024-01-02", "AAA", 1.0),
            ("2024-01-02", "BBB", 2.0),
            ("2024-01-03", "AAA", 1.5),
            ("2024-01-03", "BBB", 2.5),
        ],
    )
    _write_market_summary(
        market_root,
        2024,
        [
            ("AAA", "2024-01-02", 10.0),
            ("AAA", "2024-01-03", 11.0),
            ("BBB", "2024-01-02", 20.0),
            ("BBB", "2024-01-03", 21.0),
        ],
    )
    _write_floats(
        floats_root,
        2024,
        [
            ("AAA", "2024-01-01", 100.0),
            ("AAA", "2024-01-03", 120.0),
            ("BBB", "2024-01-01", 50.0),
        ],
    )

    factors, market, market_cap = build_project_barra_inputs(
        factor_lake_root=lake_root,
        factor_refs=["value_factor_v1:Value"],
        aggregate_bars_root=market_root,
        stocks_floats_root=floats_root,
        start="2024-01-02",
        end="2024-01-03",
        factor_align_method="outer",
    )

    assert list(factors.columns) == ["datetime", "asset", "Value"]
    assert list(market.columns) == ["align_time", "ticker", "c"]
    assert list(market_cap.columns) == ["datetime", "asset", "market_cap"]

    aaa_caps = market_cap.loc[market_cap["asset"] == "AAA", "market_cap"].tolist()
    bbb_caps = market_cap.loc[market_cap["asset"] == "BBB", "market_cap"].tolist()
    assert aaa_caps == pytest.approx([1000.0, 1320.0])
    assert bbb_caps == pytest.approx([1000.0, 1050.0])


def test_run_barra_pipeline_project_mode_writes_cleaned_outputs(tmp_path: Path):
    pytest.importorskip("statsmodels")
    lake_root = tmp_path / "factor_lake"
    market_root = tmp_path / "raw_market"
    floats_root = tmp_path / "raw_floats"
    output_dir = tmp_path / "barra_output"

    value_rows = []
    momentum_rows = []
    for date in ["2024-01-02", "2024-01-03"]:
        value_rows.extend(
            [
                (date, "AAA", 1.0 if date == "2024-01-02" else 1.2),
                (date, "BBB", 2.0 if date == "2024-01-02" else 2.2),
                (date, "CCC", 3.0 if date == "2024-01-02" else 3.2),
            ]
        )
        momentum_rows.extend(
            [
                (date, "AAA", 3.0 if date == "2024-01-02" else 3.1),
                (date, "BBB", 2.0 if date == "2024-01-02" else 2.1),
                (date, "CCC", 1.0 if date == "2024-01-02" else 1.1),
            ]
        )

    _write_factor(lake_root, "value_factor_v1", value_rows)
    _write_factor(lake_root, "momentum_factor_v1", momentum_rows)
    _write_market_summary(
        market_root,
        2024,
        [
            ("AAA", "2024-01-02", 10.0),
            ("BBB", "2024-01-02", 20.0),
            ("CCC", "2024-01-02", 30.0),
            ("AAA", "2024-01-03", 10.5),
            ("BBB", "2024-01-03", 20.5),
            ("CCC", "2024-01-03", 30.5),
        ],
    )
    _write_floats(
        floats_root,
        2024,
        [
            ("AAA", "2024-01-01", 100.0),
            ("BBB", "2024-01-01", 50.0),
            ("CCC", "2024-01-01", 25.0),
        ],
    )

    covariance = run_barra_pipeline(
        mode="project",
        output_dir=output_dir,
        factor_lake_root=lake_root,
        aggregate_bars_root=market_root,
        stocks_floats_root=floats_root,
        factor_refs=["value_factor_v1:Value", "momentum_factor_v1:Momentum"],
        start="2024-01-02",
        end="2024-01-03",
        symbols=["AAA", "BBB", "CCC"],
    )

    assert covariance.shape == (2, 2)
    assert (output_dir / "cleaned_factors.parquet").exists()
    assert (output_dir / "cleaned_returns.parquet").exists()
    assert (output_dir / "cleaned_market_cap.parquet").exists()
    assert (output_dir / "factor_covariance.parquet").exists()
    assert (output_dir / "specific_risk.parquet").exists()

    cleaned_factors = pd.read_parquet(output_dir / "cleaned_factors.parquet")
    cleaned_returns = pd.read_parquet(output_dir / "cleaned_returns.parquet")
    cleaned_caps = pd.read_parquet(output_dir / "cleaned_market_cap.parquet")

    assert pd.MultiIndex.from_frame(cleaned_factors[["date", "asset"]]).equals(
        pd.MultiIndex.from_frame(cleaned_returns[["date", "asset"]])
    )
    assert pd.MultiIndex.from_frame(cleaned_factors[["date", "asset"]]).equals(
        pd.MultiIndex.from_frame(cleaned_caps[["date", "asset"]])
    )
    assert cleaned_caps["market_cap"].gt(0).all()
