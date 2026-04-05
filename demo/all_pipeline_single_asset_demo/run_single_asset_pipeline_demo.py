from __future__ import annotations

import json
import math
import shutil
import sys
from dataclasses import asdict
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

from backtest_layer.single_asset_backtest.config import BacktestConfig
from factor_layer.factor_engine.runtime.engine import FactorEngine
from strategy_layer.single_asset_alpha.config_runner import run_from_config as run_single_asset_alpha
from single_asset_backtest.runner import run_single_asset_backtest
from workspace_paths import (
    default_demo_root,
    default_factor_lake_root,
    default_single_asset_alpha_output_root,
    default_single_asset_backtest_root,
)


DEMO_NAME = "single_asset_pipeline_demo"
SYMBOL = "SINGLE_DEMO"
STRATEGY_ID = "single_asset_pipeline_factor_timing"
STRATEGY_VERSION = "v1"
BACKTEST_RUN_NAME = "e2e_demo"
BACKTEST_STRATEGY_NAME = "single_asset_factor_timing"
START_DATE = "2024-01-02"
N_PERIODS = 90

FACTOR_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "close_mom_3",
        "alias": "mom_3",
        "expr": 'ts_mom(col("close"), 3)',
        "factor_id": "single_asset_mom_3_v1",
        "description": "3-day close momentum for the single-asset pipeline demo.",
        "fields": {"close": "close"},
    },
    {
        "name": "close_gap_5",
        "alias": "gap_5",
        "expr": '(col("close") / (ts_mean(col("close"), 5) + 1e-9)) - 1',
        "factor_id": "single_asset_gap_5_v1",
        "description": "Distance to the 5-day mean for the single-asset pipeline demo.",
        "fields": {"close": "close"},
    },
    {
        "name": "volume_delta_2",
        "alias": "vol_delta_2",
        "expr": 'ts_delta(col("volume"), 2)',
        "factor_id": "single_asset_vol_delta_2_v1",
        "description": "2-day volume delta for the single-asset pipeline demo.",
        "fields": {"volume": "volume"},
    },
)


def _write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def build_demo_paths() -> dict[str, Path]:
    demo_root = default_demo_root(DEMO_NAME)
    factor_lake_root = default_factor_lake_root()
    alpha_output_root = default_single_asset_alpha_output_root(STRATEGY_ID, STRATEGY_VERSION)
    backtest_root = default_single_asset_backtest_root()
    backtest_output_dir = backtest_root / BACKTEST_STRATEGY_NAME / BACKTEST_RUN_NAME
    return {
        "demo_root": demo_root,
        "configs_root": demo_root / "configs",
        "inputs_root": demo_root / "inputs",
        "reports_root": demo_root / "reports",
        "kline_root": demo_root / "inputs" / "day_aggs_v1",
        "market_data_path": demo_root / "inputs" / "mock_single_asset_ohlcv.parquet",
        "factor_lake_root": factor_lake_root,
        "alpha_output_root": alpha_output_root,
        "target_position_path": alpha_output_root / f"{SYMBOL}_target_position_full.parquet",
        "factor_frame_path": demo_root / "reports" / "factor_frame.parquet",
        "backtest_output_dir": backtest_output_dir,
        "summary_path": demo_root / "reports" / "pipeline_summary.json",
    }


def _reset_demo_artifacts(paths: dict[str, Path]) -> None:
    shutil.rmtree(paths["demo_root"], ignore_errors=True)
    shutil.rmtree(paths["alpha_output_root"], ignore_errors=True)
    shutil.rmtree(paths["backtest_output_dir"], ignore_errors=True)
    for spec in FACTOR_SPECS:
        shutil.rmtree(paths["factor_lake_root"] / "factors" / spec["factor_id"], ignore_errors=True)


def prepare_mock_market_data(paths: dict[str, Path]) -> dict[str, Any]:
    dates = pd.bdate_range(START_DATE, periods=N_PERIODS, freq="B")
    state_price = 100.0
    rows: list[dict[str, Any]] = []

    paths["inputs_root"].mkdir(parents=True, exist_ok=True)

    for day_idx, timestamp in enumerate(dates):
        drift = 0.0028 + 0.0045 * math.sin(day_idx / 6.0) + 0.0012 * math.cos(day_idx / 3.0)
        state_price = round(state_price * (1.0 + drift), 6)
        open_price = round(state_price / (1.0 + drift * 0.4), 6)
        high_price = round(max(open_price, state_price) * (1.002 + 0.0005 * abs(math.sin(day_idx))), 6)
        low_price = round(min(open_price, state_price) * (0.998 - 0.0003 * abs(math.cos(day_idx))), 6)
        volume = round(2500.0 + day_idx * 28.0 + 180.0 * (1.0 + math.sin(day_idx / 5.0)), 3)
        transactions = int(90 + day_idx + (day_idx % 7))
        rows.append(
            {
                "timestamp": pd.Timestamp(timestamp),
                "ticker": SYMBOL,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": state_price,
                "volume": volume,
                "transactions": transactions,
            }
        )

    frame = pd.DataFrame(rows)
    frame.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].to_parquet(
        paths["market_data_path"],
        index=False,
    )

    for timestamp, day_frame in frame.groupby(frame["timestamp"].dt.date, sort=True):
        day_value = pd.Timestamp(timestamp)
        month_dir = paths["kline_root"] / f"{day_value.year}" / f"{day_value.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        partition = day_frame.copy()
        partition["window_start"] = partition["timestamp"].map(lambda value: pd.Timestamp(value, tz="UTC").value)
        partition = partition.drop(columns=["timestamp"])
        partition.to_parquet(month_dir / f"{day_value.date()}.parquet", index=False)

    return {
        "symbol": SYMBOL,
        "start_date": str(dates[0].date()),
        "end_date": str(dates[-1].date()),
        "trade_days": int(len(dates)),
        "market_data_path": str(paths["market_data_path"]),
        "kline_root": str(paths["kline_root"]),
    }


def write_runtime_configs(paths: dict[str, Path], market_info: dict[str, Any]) -> dict[str, Any]:
    configs_root = paths["configs_root"]
    factor_engine_paths: dict[str, Path] = {}

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
                    "author": "single_asset_pipeline_demo",
                    "frequency": "1d",
                    "description": spec["description"],
                    "expression": spec["expr"],
                },
            },
        )

    alpha_config_path = _write_yaml(
        configs_root / "single_asset_alpha.yaml",
        {
            "meta": {
                "strategy_id": STRATEGY_ID,
                "version": STRATEGY_VERSION,
                "description": "Single-asset factor timing demo built from factor_engine outputs.",
            },
            "instrument": {"symbol": SYMBOL},
            "market_data": {
                "mode": "source_path",
                "source_path": str(paths["market_data_path"]),
                "freq": "1d",
                "start_date": market_info["start_date"],
                "end_date": market_info["end_date"],
            },
            "factor_source": {
                "mode": "factor_lake",
                "factor_lake_align_method": "outer",
                "factor_refs": [
                    {
                        "factor_id": spec["factor_id"],
                        "alias": spec["alias"],
                    }
                    for spec in FACTOR_SPECS
                ],
            },
            "signal": {
                "type": "factor_threshold",
                "name": "FactorThreshold",
                "params": {
                    "factor_names": [spec["alias"] for spec in FACTOR_SPECS],
                    "factor_weights": {
                        "mom_3": 0.45,
                        "gap_5": 0.40,
                        "vol_delta_2": 0.15,
                    },
                    "normalize": True,
                    "zscore_window": 12,
                },
            },
            "position_mapper": {
                "type": "threshold",
                "name": "ThresholdMapper",
                "params": {
                    "long_entry_threshold": 0.18,
                    "long_exit_threshold": -0.04,
                    "short_entry_threshold": -0.18,
                    "short_exit_threshold": 0.04,
                    "allow_short": False,
                    "position_size": 0.99,
                    "shift_bars": 1,
                },
            },
            "output": {
                "output_format": "parquet",
                "save_full_timeseries": True,
                "save_debounced": True,
            },
        },
    )

    backtest_config = {
        "initial_cash": 100000.0,
        "commission": 0.001,
        "slippage_perc": 0.0,
        "target_lag_bars": 0,
        "metrics_profile": "core",
        "allow_short": False,
        "symbol": SYMBOL,
        "frequency": "1d",
    }
    backtest_config_path = _write_yaml(
        configs_root / "single_asset_backtest.yaml",
        backtest_config,
    )

    return {
        "factor_engine": factor_engine_paths,
        "alpha": alpha_config_path,
        "backtest": backtest_config_path,
        "backtest_config": backtest_config,
    }


def _write_backtest_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path,
    config_payload: dict[str, Any],
    alpha_output_dir: str,
    market_data_path: str,
    target_position_path: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    returns_payload: dict[str, pd.Series] = report["returns"]
    equity_curve = returns_payload["equity_curve"]
    returns_frame = pd.DataFrame(
        {
            "timestamp": equity_curve.index,
            "equity_curve": equity_curve.values,
            "period_return": returns_payload["period_return"].reindex(equity_curve.index).values,
            "realized_position": returns_payload["realized_position"].reindex(equity_curve.index).values,
        }
    )
    returns_path = output_dir / "returns.csv"
    returns_frame.to_csv(returns_path, index=False)

    metrics_df = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in report["metrics"].items()]
    )
    metrics_path = output_dir / "metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)

    summary_payload = {
        "summary": report["summary"],
        "metrics": report["metrics"],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    metadata_payload = {
        "alpha_output_dir": alpha_output_dir,
        "market_data_path": market_data_path,
        "target_position_path": target_position_path,
        "backtest_config": config_payload,
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    config_snapshot_path = output_dir / "backtest_config_snapshot.yaml"
    config_snapshot_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    return {
        "returns": str(returns_path),
        "metrics": str(metrics_path),
        "summary": str(summary_path),
        "metadata": str(metadata_path),
        "config_snapshot": str(config_snapshot_path),
    }


def load_demo_summary(summary_path: str | Path | None = None) -> dict[str, Any]:
    target = Path(summary_path) if summary_path is not None else build_demo_paths()["summary_path"]
    return json.loads(target.read_text(encoding="utf-8"))


def load_demo_artifacts(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = summary or load_demo_summary()
    factor_frame = pd.read_parquet(payload["alpha"]["factor_frame_path"])
    target_position = pd.read_parquet(payload["alpha"]["target_position_path"])
    market_data = pd.read_parquet(payload["inputs"]["market_data_path"])
    returns = pd.read_csv(payload["backtest"]["outputs"]["returns"], parse_dates=["timestamp"])
    metrics = pd.read_csv(payload["backtest"]["outputs"]["metrics"])
    return {
        "factor_frame": factor_frame,
        "target_position": target_position,
        "market_data": market_data,
        "returns": returns,
        "metrics": metrics,
    }


def run_demo(*, force: bool = True) -> dict[str, Any]:
    paths = build_demo_paths()
    if force:
        _reset_demo_artifacts(paths)

    market_info = prepare_mock_market_data(paths)
    config_paths = write_runtime_configs(paths, market_info)

    factor_engine_runs: list[dict[str, Any]] = []
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

    alpha_result = run_single_asset_alpha(config_paths["alpha"])
    factor_frame = alpha_result["factor_data"]
    if factor_frame is None:
        raise RuntimeError("single_asset_alpha did not return factor_data")
    factor_frame = factor_frame.reset_index().rename(columns={factor_frame.index.name or "index": "timestamp"})
    paths["factor_frame_path"].parent.mkdir(parents=True, exist_ok=True)
    factor_frame.to_parquet(paths["factor_frame_path"], index=False)

    backtest_config = BacktestConfig(**config_paths["backtest_config"])
    backtest_report = run_single_asset_backtest(
        ohlcv=alpha_result["market_data"],
        target_position=alpha_result["target_position"],
        config=backtest_config,
    )
    backtest_outputs = _write_backtest_outputs(
        backtest_report,
        output_dir=paths["backtest_output_dir"],
        config_payload=config_paths["backtest_config"],
        alpha_output_dir=alpha_result["output_dir"],
        market_data_path=str(paths["market_data_path"]),
        target_position_path=str(paths["target_position_path"]),
    )

    metrics = backtest_report["metrics"]
    summary = {
        "paths": {key: str(value) for key, value in paths.items()},
        "inputs": market_info,
        "factor_engine": factor_engine_runs,
        "alpha": {
            "output_dir": alpha_result["output_dir"],
            "config_path": str(config_paths["alpha"]),
            "config_snapshot": alpha_result["config_snapshot"],
            "target_position_rows": int(len(alpha_result["target_position"])),
            "factor_columns": list(alpha_result["factor_data"].columns),
            "factor_frame_path": str(paths["factor_frame_path"]),
            "target_position_path": str(paths["target_position_path"]),
        },
        "backtest": {
            "output_dir": str(paths["backtest_output_dir"]),
            "outputs": backtest_outputs,
            "config_path": str(config_paths["backtest"]),
            "summary": backtest_report["summary"],
            "metrics": {
                key: metrics.get(key)
                for key in (
                    "total_return",
                    "annual_return",
                    "sharpe",
                    "max_drawdown",
                    "turnover_mean",
                    "trade_count",
                )
            },
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