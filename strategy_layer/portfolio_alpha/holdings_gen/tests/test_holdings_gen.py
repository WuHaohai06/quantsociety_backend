from __future__ import annotations

from pathlib import Path
import sys

import pytest

pd = pytest.importorskip("pandas")
yaml = pytest.importorskip("yaml")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_layer.portfolio_alpha.holdings_gen.config import ConstructionConfig
from strategy_layer.portfolio_alpha.holdings_gen.pipeline import generate_holdings_from_signal, run_from_config


def test_generate_holdings_from_signal_long_only_equal_weight():
    signal = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([
                "2024-01-02", "2024-01-02", "2024-01-02",
                "2024-01-03", "2024-01-03",
            ]),
            "symbol": ["AAA", "BBB", "CCC", "AAA", "DDD"],
            "score": [3.0, 2.0, 1.0, 5.0, 4.0],
            "selected_flag": [True, True, False, True, True],
            "side": ["LONG", "LONG", "LONG", "LONG", "LONG"],
        }
    )

    result = generate_holdings_from_signal(
        signal,
        ConstructionConfig(
            selection_mode="selected_flag",
            weighting_method="equal",
            long_budget=1.0,
            short_budget=0.0,
            normalize_total_abs_weight=1.0,
        ),
    )
    holdings = result["holdings"]

    assert set(holdings.columns) == {"trade_date", "symbol", "weight"}
    assert holdings.groupby("trade_date")["weight"].sum().eq(1.0).all()
    assert holdings.groupby("trade_date")["weight"].apply(lambda s: s.abs().sum()).eq(1.0).all()
    first_day = holdings[holdings["trade_date"] == pd.Timestamp("2024-01-02")]
    assert first_day["weight"].tolist() == pytest.approx([0.5, 0.5])


def test_generate_holdings_from_signal_long_short_score_proportional():
    signal = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02"] * 4),
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "score": [3.0, 1.0, -2.0, -1.0],
            "selected_flag": [True, True, True, True],
            "side": ["LONG", "LONG", "SHORT", "SHORT"],
        }
    )

    result = generate_holdings_from_signal(
        signal,
        ConstructionConfig(
            selection_mode="selected_flag",
            weighting_method="score_proportional",
            long_budget=0.6,
            short_budget=0.4,
            normalize_total_abs_weight=1.0,
        ),
    )
    holdings = result["holdings"].sort_values("symbol").reset_index(drop=True)

    assert holdings["weight"].tolist() == pytest.approx([0.45, 0.15, -0.2666666667, -0.1333333333])
    assert holdings["weight"].abs().sum() == pytest.approx(1.0)
    assert holdings["weight"].sum() == pytest.approx(0.2)


def test_run_from_config_writes_holdings_outputs_and_filters_unquoted_dates(tmp_path: Path):
    signal = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([
                "2024-01-02", "2024-01-02",
                "2024-01-03", "2024-01-03",
                "2024-01-04", "2024-01-04",
            ]),
            "symbol": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "composite_score": [2.0, 1.0, 1.5, 3.0, 4.0, 2.5],
            "selected_flag": [True, False, True, True, False, True],
            "side": ["LONG", "LONG", "LONG", "LONG", "LONG", "LONG"],
        }
    )
    signal_path = tmp_path / "signal.parquet"
    signal.to_parquet(signal_path, index=False)

    config_path = tmp_path / "holdings_gen.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "meta": {"portfolio_id": "demo_holdings", "version": "v1"},
                "inputs": {
                    "signal": {
                        "path": "./signal.parquet",
                        "format": "parquet",
                        "start": "2024-01-03",
                        "end": "2024-01-04 23:59:59",
                    }
                },
                "construction": {
                    "selection_mode": "selected_flag",
                    "weighting_method": "equal",
                    "long_budget": 1.0,
                    "normalize_total_abs_weight": 1.0,
                },
                "optimizer": {"enabled": False, "name": "noop"},
                "risk_control": {"enabled": False, "name": "noop"},
                "output": {"root": "./generated_holdings"},
            },
            sort_keys=False,
        )
    )

    result = run_from_config(config_path)
    holdings = result["holdings"]

    assert not holdings.empty
    assert holdings["trade_date"].min() == pd.Timestamp("2024-01-03")
    assert holdings["trade_date"].max() == pd.Timestamp("2024-01-04")
    assert (tmp_path / "generated_holdings" / "holdings" / "holdings.parquet").exists()
    assert (tmp_path / "generated_holdings" / "manifest.json").exists()
    assert (tmp_path / "generated_holdings" / "summary.json").exists()
    assert (tmp_path / "generated_holdings" / "config_snapshot.yaml").exists()
    assert result["summary"]["trade_days"] == 2