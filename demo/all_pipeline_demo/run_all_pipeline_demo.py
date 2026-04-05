from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _bootstrap_repo_paths(repo_root: Path) -> None:
    for candidate in (
        repo_root,
        repo_root / "backtest_layer",
        repo_root / "factor_layer" / "factor_engine",
    ):
        text = str(candidate)
        if text not in sys.path:
            sys.path.insert(0, text)


REPO_ROOT = Path(__file__).resolve().parents[2]
_bootstrap_repo_paths(REPO_ROOT)

from backtest_layer.portfolio_backtest.config_runner import run_from_config as run_portfolio_backtest
from factor_layer.factor_admission.config_runner import run_from_config as run_factor_admission
from factor_layer.factor_evaluation.config_runner import run_from_config as run_factor_evaluation
from runtime.engine import FactorEngine
from strategy_layer.portfolio_alpha.holdings_gen.pipeline import run_from_config as run_holdings_gen
from strategy_layer.portfolio_alpha.multiple_factor_composite.pipeline import run_from_config as run_composite_signal
from workspace_paths import (
    default_composite_signal_root,
    default_demo_root,
    default_factor_evaluation_root,
    default_factor_lake_root,
    default_holdings_root,
    default_portfolio_backtest_root,
)


DEMO_NAME = "all_pipeline_demo"
SIGNAL_ID = "all_pipeline_signal"
SIGNAL_VERSION = "v1"
PORTFOLIO_ID = "all_pipeline_holdings"
PORTFOLIO_VERSION = "v1"
BACKTEST_STRATEGY_NAME = "all_pipeline_strategy"
BACKTEST_RUN_NAME = "e2e_demo"
EVALUATION_RUN_NAME = "all_pipeline_eval"
START_DATE = "2024-01-02"
N_PERIODS = 18

FACTOR_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "close_rank_2d",
        "alias": "close_rank",
        "expr": 'rank(ts_mean(col("close"), 2))',
        "factor_id": "all_pipeline_close_rank_v1",
        "description": "Two-day close average rank factor for the all-pipeline demo.",
        "fields": {"close": "close"},
        "thresholds": {
            "min_rank_ic_mean": 0.90,
            "min_long_short_total_return": 0.00,
        },
    },
    {
        "name": "volume_rank_3d",
        "alias": "volume_rank",
        "expr": 'rank(ts_mean(col("volume"), 3))',
        "factor_id": "all_pipeline_volume_rank_v1",
        "description": "Three-day volume average rank factor for the all-pipeline demo.",
        "fields": {"volume": "volume"},
        "thresholds": {
            "min_rank_ic_mean": 0.90,
            "min_long_short_total_return": 0.00,
        },
    },
)

SYMBOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "symbol": "AAA",
        "start_price": 120.0,
        "daily_return": 0.018,
        "base_volume": 6200.0,
        "volume_step": 140.0,
    },
    {
        "symbol": "BBB",
        "start_price": 92.0,
        "daily_return": 0.013,
        "base_volume": 4700.0,
        "volume_step": 100.0,
    },
    {
        "symbol": "CCC",
        "start_price": 73.0,
        "daily_return": 0.006,
        "base_volume": 3500.0,
        "volume_step": 70.0,
    },
    {
        "symbol": "DDD",
        "start_price": 55.0,
        "daily_return": -0.002,
        "base_volume": 2400.0,
        "volume_step": 45.0,
    },
)


def _write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def build_demo_paths() -> dict[str, Path]:
    demo_root = default_demo_root(DEMO_NAME)
    factor_lake_root = default_factor_lake_root()
    evaluation_root = default_factor_evaluation_root(factor_lake_root=factor_lake_root)
    composite_root = default_composite_signal_root(SIGNAL_ID, SIGNAL_VERSION)
    holdings_root = default_holdings_root(PORTFOLIO_ID, PORTFOLIO_VERSION)
    backtest_root = default_portfolio_backtest_root()
    backtest_run_dir = backtest_root / BACKTEST_STRATEGY_NAME / BACKTEST_RUN_NAME
    return {
        "demo_root": demo_root,
        "configs_root": demo_root / "configs",
        "inputs_root": demo_root / "inputs",
        "reports_root": demo_root / "reports",
        "kline_root": demo_root / "inputs" / "day_aggs_v1",
        "market_data_path": demo_root / "inputs" / "mock_kline.parquet",
        "factor_lake_root": factor_lake_root,
        "evaluation_root": evaluation_root,
        "composite_root": composite_root,
        "signal_path": composite_root / "signals" / "composite_signal.parquet",
        "holdings_root": holdings_root,
        "holdings_path": holdings_root / "holdings" / "holdings.parquet",
        "backtest_root": backtest_root,
        "backtest_run_dir": backtest_run_dir,
        "summary_path": demo_root / "reports" / "pipeline_summary.json",
    }


def _reset_demo_artifacts(paths: dict[str, Path]) -> None:
    shutil.rmtree(paths["demo_root"], ignore_errors=True)
    shutil.rmtree(paths["composite_root"], ignore_errors=True)
    shutil.rmtree(paths["holdings_root"], ignore_errors=True)
    shutil.rmtree(paths["backtest_run_dir"], ignore_errors=True)
    for spec in FACTOR_SPECS:
        shutil.rmtree(paths["factor_lake_root"] / "factors" / spec["factor_id"], ignore_errors=True)
        shutil.rmtree(paths["evaluation_root"] / spec["factor_id"] / EVALUATION_RUN_NAME, ignore_errors=True)


def prepare_mock_market_data(paths: dict[str, Path]) -> dict[str, Any]:
    dates = pd.bdate_range(START_DATE, periods=N_PERIODS, freq="B")
    state = {spec["symbol"]: float(spec["start_price"]) for spec in SYMBOL_SPECS}
    long_rows: list[dict[str, Any]] = []

    for day_idx, timestamp in enumerate(dates):
        month_dir = paths["kline_root"] / f"{timestamp.year}" / f"{timestamp.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        daily_rows: list[dict[str, Any]] = []

        for symbol_idx, spec in enumerate(SYMBOL_SPECS):
            symbol = str(spec["symbol"])
            state[symbol] = round(float(state[symbol]) * (1.0 + float(spec["daily_return"])), 6)
            close_price = state[symbol]
            open_price = round(close_price / (1.0 + float(spec["daily_return"]) * 0.35), 6)
            high_price = round(max(open_price, close_price) * 1.004, 6)
            low_price = round(min(open_price, close_price) * 0.996, 6)
            volume = round(float(spec["base_volume"]) + day_idx * float(spec["volume_step"]), 3)
            transactions = int(100 + day_idx * 3 + symbol_idx)
            daily_rows.append(
                {
                    "ticker": symbol,
                    "window_start": pd.Timestamp(timestamp, tz="UTC").value,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "transactions": transactions,
                }
            )
            long_rows.append(
                {
                    "trade_date": pd.Timestamp(timestamp),
                    "symbol": symbol,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        pd.DataFrame(daily_rows).to_parquet(month_dir / f"{timestamp.date()}.parquet", index=False)

    market_frame = pd.DataFrame(long_rows)
    paths["market_data_path"].parent.mkdir(parents=True, exist_ok=True)
    market_frame.to_parquet(paths["market_data_path"], index=False)
    return {
        "symbols": [spec["symbol"] for spec in SYMBOL_SPECS],
        "start_date": str(dates[0].date()),
        "end_date": str(dates[-1].date()),
        "trade_days": int(len(dates)),
        "market_data_path": str(paths["market_data_path"]),
        "kline_root": str(paths["kline_root"]),
    }


def write_runtime_configs(paths: dict[str, Path], market_info: dict[str, Any]) -> dict[str, Any]:
    configs_root = paths["configs_root"]
    factor_engine_paths: dict[str, Path] = {}
    factor_evaluation_paths: dict[str, Path] = {}
    factor_admission_paths: dict[str, Path] = {}

    for spec in FACTOR_SPECS:
        factor_id = str(spec["factor_id"])
        factor_engine_paths[factor_id] = _write_yaml(
            configs_root / "factor_engine" / f"{factor_id}.yaml",
            {
                "factor": {
                    "name": spec["name"],
                    "expr": spec["expr"],
                    "freq": "1d",
                    "description": spec["description"],
                },
                "data_source": {
                    "type": "parquet_kline",
                    "root": str(paths["kline_root"]),
                    "instrument_column": "ticker",
                    "timestamp_column": "window_start",
                    "fields": spec["fields"],
                },
                "backend": {"type": "pandas"},
                "engine": {"enable_cache": True},
                "materialization": {
                    "factor_id": factor_id,
                    "author": "all_pipeline_demo",
                    "frequency": "1d",
                    "description": spec["description"],
                    "expression": spec["expr"],
                },
            },
        )

        factor_evaluation_paths[factor_id] = _write_yaml(
            configs_root / "factor_evaluation" / f"{factor_id}.yaml",
            {
                "meta": {
                    "factor_id": factor_id,
                    "run_name": EVALUATION_RUN_NAME,
                    "primary_horizon": 1,
                    "description": f"Evaluation for {factor_id}",
                },
                "source": {
                    "market_data_path": str(paths["market_data_path"]),
                    "market_timestamp_col": "trade_date",
                    "market_symbol_col": "symbol",
                    "market_price_col": "open",
                },
                "run": {
                    "start": market_info["start_date"],
                    "end": market_info["end_date"],
                    "horizons": [1, 3, 5],
                    "n_quantiles": 4,
                    "min_assets_per_date": 4,
                },
            },
        )

        factor_admission_paths[factor_id] = _write_yaml(
            configs_root / "factor_admission" / f"{factor_id}.yaml",
            {
                "meta": {
                    "factor_id": factor_id,
                    "run_id": EVALUATION_RUN_NAME,
                },
                "decision": {
                    "mode": "rule_based",
                    "decided_by": "all_pipeline_demo",
                    "policy_name": "all_pipeline_demo_policy",
                    "primary_horizon": 1,
                    "thresholds": spec["thresholds"],
                },
            },
        )

    composite_path = _write_yaml(
        configs_root / "composite_signal.yaml",
        {
            "meta": {
                "signal_id": SIGNAL_ID,
                "version": SIGNAL_VERSION,
                "description": "All-pipeline composite signal built from materialized demo factors.",
            },
            "source": {
                "start": market_info["start_date"],
                "end": market_info["end_date"],
                "align_method": "outer",
            },
            "factors": [
                {
                    "factor_id": spec["factor_id"],
                    "alias": spec["alias"],
                }
                for spec in FACTOR_SPECS
            ],
            "composition": {
                "weighting": {"method": "equal"},
                "final_transform": "rank",
                "long_top_k": 2,
            },
        },
    )

    holdings_path = _write_yaml(
        configs_root / "holdings_from_signal.yaml",
        {
            "meta": {
                "portfolio_id": PORTFOLIO_ID,
                "version": PORTFOLIO_VERSION,
                "description": "Convert all-pipeline composite signal into portfolio holdings.",
            },
            "inputs": {
                "signal": {
                    "path": str(paths["signal_path"]),
                    "format": "parquet",
                    "timestamp_col": "timestamp",
                    "symbol_col": "symbol",
                    "score_col": "composite_score",
                    "selected_flag_col": "selected_flag",
                    "side_col": "side",
                }
            },
            "construction": {
                "selection_mode": "selected_flag",
                "weighting_method": "equal",
                "long_budget": 1.0,
                "short_budget": 0.0,
                "normalize_total_abs_weight": 1.0,
            },
        },
    )

    backtest_path = _write_yaml(
        configs_root / "portfolio_backtest.yaml",
        {
            "meta": {
                "strategy_name": BACKTEST_STRATEGY_NAME,
                "run_name": BACKTEST_RUN_NAME,
                "description": "Portfolio backtest for the all-pipeline demo.",
            },
            "inputs": {
                "holdings": {
                    "path": str(paths["holdings_path"]),
                    "format": "parquet",
                },
                "kline": {
                    "path": str(paths["market_data_path"]),
                    "format": "parquet",
                },
            },
            "columns": {
                "date_col": "trade_date",
                "symbol_col": "symbol",
                "weight_col": "weight",
                "price_col": "close",
            },
            "backtest": {
                "annualization": 252,
                "return_window": 1,
                "fee_rate": 0.0003,
                "slippage_rate": 0.0002,
            },
        },
    )

    return {
        "factor_engine": factor_engine_paths,
        "factor_evaluation": factor_evaluation_paths,
        "factor_admission": factor_admission_paths,
        "composite": composite_path,
        "holdings": holdings_path,
        "backtest": backtest_path,
    }


def load_demo_summary(summary_path: str | Path | None = None) -> dict[str, Any]:
    target = Path(summary_path) if summary_path is not None else build_demo_paths()["summary_path"]
    return json.loads(target.read_text(encoding="utf-8"))


def load_demo_artifacts(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = summary or load_demo_summary()

    evaluation_frames = []
    for item in payload["factor_evaluations"]:
        frame = pd.read_csv(Path(item["output_dir"]) / "summary.csv")
        frame["factor_id"] = item["factor_id"]
        evaluation_frames.append(frame)

    returns_frame = pd.read_csv(payload["backtest"]["returns_path"], parse_dates=["trade_date"])
    metrics_frame = pd.read_csv(payload["backtest"]["metrics_path"])
    signal_frame = pd.read_parquet(payload["composite"]["outputs"]["signal"])
    holdings_frame = pd.read_parquet(payload["holdings"]["outputs"]["holdings"])

    admission_frame = pd.DataFrame(
        [
            {
                "factor_id": item["factor_id"],
                "decision": item["decision"],
                "approved": item["approved"],
                "reason": item["reason"],
                "latest_status": (item.get("status") or {}).get("status"),
            }
            for item in payload["factor_admissions"]
        ]
    )

    return {
        "evaluation_summary": pd.concat(evaluation_frames, ignore_index=True),
        "admission_summary": admission_frame,
        "signal": signal_frame,
        "holdings": holdings_frame,
        "returns": returns_frame,
        "metrics": metrics_frame,
    }


def run_demo(*, force: bool = True) -> dict[str, Any]:
    paths = build_demo_paths()
    if force:
        _reset_demo_artifacts(paths)

    market_info = prepare_mock_market_data(paths)
    config_paths = write_runtime_configs(paths, market_info)

    factor_engine_runs: list[dict[str, Any]] = []
    factor_evaluations: list[dict[str, Any]] = []
    factor_admissions: list[dict[str, Any]] = []

    for spec in FACTOR_SPECS:
        factor_id = str(spec["factor_id"])
        materialized = FactorEngine.materialize_from_config(config_paths["factor_engine"][factor_id])
        factor_engine_runs.append(
            {
                "factor_id": materialized["materialization"]["factor_id"],
                "rows_written": int(materialized["materialization"]["rows_written"]),
                "partitions": list(materialized["materialization"]["partitions"]),
                "lake_root": materialized["materialization"]["lake_root"],
                "watermark": materialized["materialization"]["watermark"],
                "config_path": str(config_paths["factor_engine"][factor_id]),
            }
        )

        evaluation = run_factor_evaluation(config_paths["factor_evaluation"][factor_id])
        factor_evaluations.append(
            {
                "factor_id": factor_id,
                "run_id": str(evaluation["meta"]["run_id"]),
                "output_dir": str(evaluation["output_dir"]),
                "summary": evaluation["summary_df"].to_dict(orient="records"),
                "config_path": str(config_paths["factor_evaluation"][factor_id]),
            }
        )

        admission = run_factor_admission(config_paths["factor_admission"][factor_id])
        factor_admissions.append(
            {
                **admission,
                "config_path": str(config_paths["factor_admission"][factor_id]),
            }
        )

    composite = run_composite_signal(config_paths["composite"])
    holdings = run_holdings_gen(config_paths["holdings"])
    backtest = run_portfolio_backtest(config_paths["backtest"])

    backtest_payload = backtest["backtest"]
    summary = {
        "paths": {key: str(value) for key, value in paths.items()},
        "inputs": market_info,
        "factor_engine": factor_engine_runs,
        "factor_evaluations": factor_evaluations,
        "factor_admissions": factor_admissions,
        "composite": {
            "rows": int(len(composite["signal"])),
            "output_root": str(paths["composite_root"]),
            "outputs": composite["outputs"],
            "config_path": str(config_paths["composite"]),
        },
        "holdings": {
            "rows": int(len(holdings["holdings"])),
            "output_root": str(paths["holdings_root"]),
            "summary": holdings["summary"],
            "outputs": holdings["outputs"],
            "config_path": str(config_paths["holdings"]),
        },
        "backtest": {
            "output_dir": backtest["output_dir"],
            "returns_path": backtest_payload["returns_path"],
            "metrics_path": backtest_payload["metrics_path"],
            "summary_path": backtest_payload["summary_path"],
            "metadata_path": backtest_payload["metadata_path"],
            "summary": backtest_payload["summary_df"].iloc[0].to_dict(),
            "config_path": str(config_paths["backtest"]),
        },
    }

    paths["reports_root"].mkdir(parents=True, exist_ok=True)
    paths["summary_path"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    summary = run_demo(force=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()