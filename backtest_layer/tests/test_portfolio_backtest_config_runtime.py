from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
yaml = pytest.importorskip("yaml")

from backtest_layer.portfolio_backtest import load_config
from backtest_layer.portfolio_backtest.config_runner import run_from_config


def _write_config(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_load_config_supports_unquoted_date_like_run_name_and_relative_paths(tmp_path: Path):
    holdings_path = tmp_path / "holdings.csv"
    kline_path = tmp_path / "kline.csv"
    pd.DataFrame(
        {
            "trade_date": ["2024-01-02"],
            "symbol": ["AAA"],
            "weight": [1.0],
        }
    ).to_csv(holdings_path, index=False)
    pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03"],
            "symbol": ["AAA", "AAA"],
            "close": [10.0, 10.5],
        }
    ).to_csv(kline_path, index=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "meta:",
                "  strategy_name: demo_strategy",
                "  run_name: 2024-01-05",
                "inputs:",
                "  holdings:",
                "    path: ./holdings.csv",
                "  kline:",
                "    path: ./kline.csv",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.meta.run_name == "2024-01-05"
    assert config.inputs.holdings.path == str(holdings_path.resolve())
    assert config.inputs.kline.path == str(kline_path.resolve())


def test_run_from_config_builds_artifacts_and_registry_outputs(tmp_path: Path):
    holdings_path = tmp_path / "holdings.csv"
    kline_path = tmp_path / "kline.csv"
    pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "symbol": ["AAA", "AAA", "AAA"],
            "weight": [1.0, 1.0, 0.0],
        }
    ).to_csv(holdings_path, index=False)
    pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "symbol": ["AAA", "AAA", "AAA", "AAA"],
            "close": [10.0, 11.0, 11.5, 12.0],
        }
    ).to_csv(kline_path, index=False)

    config_path = _write_config(
        tmp_path / "runtime.yaml",
        {
            "meta": {
                "strategy_name": "demo_strategy",
                "run_name": "demo_run",
            },
            "inputs": {
                "holdings": {"path": str(holdings_path)},
                "kline": {"path": str(kline_path)},
            },
            "output": {
                "output_root": "results",
            },
            "registry": {
                "enabled": True,
            },
        },
    )

    result = run_from_config(config_path)

    output_dir = Path(result["output_dir"])
    assert output_dir.exists()
    assert (output_dir / "returns.csv").exists()
    assert (output_dir / "metrics.csv").exists()
    assert (output_dir / "summary.csv").exists()
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "config_snapshot.yaml").exists()
    assert (output_dir / "registry_evaluation.csv").exists()
    assert (output_dir / "registry_evaluation.json").exists()
    assert result["registry"] is not None
    assert result["backtest"]["summary_df"].iloc[0]["strategy_name"] == "demo_strategy"


def test_run_from_config_supports_parquet_directory_inputs_and_column_rename(tmp_path: Path):
    holdings_path = tmp_path / "holdings.csv"
    pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "symbol": ["AAA", "AAA", "AAA"],
            "weight": [1.0, 0.5, 0.0],
        }
    ).to_csv(holdings_path, index=False)

    kline_root = tmp_path / "day_aggs_like"
    kline_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "align_time": pd.to_datetime([
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
            ]),
            "ticker": ["AAA", "AAA", "AAA", "AAA"],
            "close": [10.0, 10.4, 10.7, 11.0],
            "open": [9.9, 10.2, 10.5, 10.8],
        }
    ).to_parquet(kline_root / "daily_market_summary_2024.parquet", index=False)

    config_path = _write_config(
        tmp_path / "parquet_dir.yaml",
        {
            "meta": {
                "strategy_name": "dir_strategy",
                "run_name": "dir_run",
            },
            "inputs": {
                "holdings": {"path": str(holdings_path)},
                "kline": {
                    "path": str(kline_root),
                    "format": "parquet",
                    "rename": {
                        "align_time": "trade_date",
                        "ticker": "symbol",
                    },
                },
            },
            "output": {
                "output_root": "results",
            },
        },
    )

    result = run_from_config(config_path)

    assert not result["kline_df"].empty
    assert {"trade_date", "symbol", "close"}.issubset(result["kline_df"].columns)
    assert Path(result["output_dir"]).exists()