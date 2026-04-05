from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
yaml = pytest.importorskip("yaml")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy_layer.single_asset_alpha.config import load_config
from strategy_layer.single_asset_alpha.config_runner import run_from_config
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher


def _write_config(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def _write_factor(lake_root: Path, factor_id: str, rows: list[tuple[pd.Timestamp, str, float]]) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def _write_aggregate_year(
    aggregate_root: Path,
    year: int,
    rows: list[tuple[str, pd.Timestamp, float, float, float, float, float]],
) -> None:
    dataset_dir = aggregate_root / "daily_market_summary"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        rows,
        columns=["ticker", "align_time", "o", "h", "l", "c", "v"],
    )
    frame["align_time"] = pd.to_datetime(frame["align_time"], utc=True)
    frame.to_parquet(dataset_dir / f"daily_market_summary_{year}.parquet", index=False)


def test_load_config_applies_defaults_and_supports_unquoted_dates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace_root = tmp_path / "workspace_data"
    monkeypatch.setenv("QUANTSOCIETY_WORKSPACE_DATA_ROOT", str(workspace_root))
    config_path = tmp_path / "dual_ma.yaml"
    config_path.write_text(
        "\n".join(
            [
                "meta:",
                "  strategy_id: dual_ma_demo",
                "instrument:",
                "  symbol: TEST",
                "market_data:",
                "  mode: mock",
                "run:",
                "  start_date: 2024-01-02",
                "  end_date: 2024-01-10 23:59:59",
                "signal:",
                "  type: dual_ma",
                "position_mapper:",
                "  type: threshold",
            ]
        )
    )

    config = load_config(config_path)

    assert config.meta.strategy_id == "dual_ma_demo"
    assert config.signal.name == "DualMA"
    assert config.signal.params["fast_window"] == 5
    assert config.position_mapper.params["shift_bars"] == 1
    assert config.run.start_date == "2024-01-02"
    assert config.run.end_date == "2024-01-10 23:59:59"
    assert config.market_data.cache_root == str(workspace_root / "cache" / "market_data")
    assert config.output.output_dir == str(workspace_root / "strategy" / "single_asset_alpha" / "dual_ma_demo_v1")


def test_load_config_rejects_factor_threshold_without_factor_source(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "bad.yaml",
        {
            "meta": {"strategy_id": "bad_factor_signal"},
            "instrument": {"symbol": "TEST"},
            "market_data": {"mode": "mock"},
            "signal": {
                "type": "factor_threshold",
                "params": {"factor_names": ["alpha_1"]},
            },
            "position_mapper": {"type": "threshold"},
        },
    )

    with pytest.raises(ValueError, match="factor_source.mode 不能为 none"):
        load_config(config_path)


def test_run_from_config_runs_dual_ma_with_mock_market_data(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "dual_ma_runtime.yaml",
        {
            "meta": {"strategy_id": "dual_ma_runtime"},
            "instrument": {"symbol": "TEST"},
            "market_data": {
                "mode": "mock",
                "mock_periods": 40,
                "mock_seed": 7,
            },
            "signal": {
                "type": "dual_ma",
            },
            "position_mapper": {
                "type": "threshold",
                "params": {"long_entry_threshold": 0.3},
            },
            "output": {
                "output_dir": "outputs",
                "output_format": "csv",
            },
        },
    )

    result = run_from_config(config_path)

    assert not result["target_position"].empty
    assert set(["timestamp", "symbol", "target_position", "signal_value", "action_name"]).issubset(
        result["target_position"].columns
    )
    assert (tmp_path / "outputs" / "TEST_target_position_full.csv").exists()
    assert (tmp_path / "outputs" / "config_snapshot.yaml").exists()


def test_run_from_config_supports_factor_lake_factor_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace_root = tmp_path / "workspace_data"
    monkeypatch.setenv("QUANTSOCIETY_WORKSPACE_DATA_ROOT", str(workspace_root))
    lake_root = tmp_path / "factor_lake"
    dates = pd.bdate_range("2024-01-01", periods=8, freq="B")
    _write_factor(
        lake_root,
        "alpha_factor_v1",
        [(timestamp, "TEST", float(index + 1)) for index, timestamp in enumerate(dates)],
    )
    _write_factor(
        lake_root,
        "beta_factor_v1",
        [(timestamp, "TEST", float((index + 1) * 10)) for index, timestamp in enumerate(dates)],
    )

    config_path = _write_config(
        tmp_path / "factor_threshold.yaml",
        {
            "meta": {"strategy_id": "factor_threshold_runtime"},
            "instrument": {"symbol": "TEST"},
            "market_data": {
                "mode": "mock",
                "mock_periods": 8,
                "mock_start_date": "2024-01-01",
                "mock_seed": 3,
            },
            "factor_source": {
                "mode": "factor_lake",
                "factor_lake_root": str(lake_root),
                "factor_refs": [
                    {"factor_id": "alpha_factor_v1", "alias": "alpha_1"},
                    {"factor_id": "beta_factor_v1", "alias": "alpha_2"},
                ],
            },
            "signal": {
                "type": "factor_threshold",
                "params": {
                    "factor_names": ["alpha_1", "alpha_2"],
                    "factor_weights": {"alpha_1": 0.7, "alpha_2": 0.3},
                    "normalize": False,
                },
            },
            "position_mapper": {
                "type": "threshold",
                "params": {
                    "long_entry_threshold": 0.1,
                    "shift_bars": 0,
                },
            },
            "output": {
                "save_full_timeseries": False,
                "save_debounced": False,
            },
        },
    )

    result = run_from_config(config_path)

    assert result["factor_data"] is not None
    assert list(result["factor_data"].columns) == ["alpha_1", "alpha_2"]
    assert not result["target_position"].empty
    assert (workspace_root / "strategy" / "single_asset_alpha" / "factor_threshold_runtime_v1" / "config_snapshot.yaml").exists()


def test_data_fetcher_loads_aggregate_bars_daily_summary(tmp_path: Path):
    aggregate_root = tmp_path / "aggregate_bars"
    dates = pd.bdate_range("2024-01-01", periods=6, freq="B", tz="UTC")
    rows = []
    for index, timestamp in enumerate(dates):
        rows.append(("AAA", timestamp, 10.0 + index, 11.0 + index, 9.0 + index, 10.5 + index, 1000.0 + index))
        rows.append(("BBB", timestamp, 20.0 + index, 21.0 + index, 19.0 + index, 20.5 + index, 2000.0 + index))
    _write_aggregate_year(aggregate_root, 2024, rows)

    fetcher = DataFetcher(aggregate_bars_root=aggregate_root)
    market_data = fetcher.load_market_data(
        symbol="AAA",
        start_date="2024-01-03",
        end_date="2024-01-08",
    )

    assert list(market_data.columns) == ["open", "high", "low", "close", "volume"]
    assert market_data.index.name == "timestamp"
    assert market_data.index.tz is None
    assert len(market_data) == 4
    assert market_data.iloc[0]["open"] == 12.0


def test_run_from_config_supports_aggregate_bars_daily_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace_root = tmp_path / "workspace_data"
    monkeypatch.setenv("QUANTSOCIETY_WORKSPACE_DATA_ROOT", str(workspace_root))
    aggregate_root = tmp_path / "aggregate_bars"
    dates = pd.bdate_range("2024-01-01", periods=15, freq="B", tz="UTC")
    rows = []
    for index, timestamp in enumerate(dates):
        close_price = 10.0 + index * 0.5
        rows.append(("AAA", timestamp, close_price - 0.1, close_price + 0.3, close_price - 0.4, close_price, 1000.0 + index))
        rows.append(("ZZZ", timestamp, 30.0, 31.0, 29.0, 30.5, 500.0 + index))
    _write_aggregate_year(aggregate_root, 2024, rows)

    config_path = _write_config(
        tmp_path / "aggregate_runtime.yaml",
        {
            "meta": {"strategy_id": "aggregate_bars_runtime"},
            "instrument": {"symbol": "AAA"},
            "market_data": {
                "mode": "aggregate_bars_daily_summary",
                "aggregate_bars_root": str(aggregate_root),
                "aggregate_dataset": "daily_market_summary",
                "freq": "1d",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
            "signal": {
                "type": "dual_ma",
                "params": {"fast_window": 3, "slow_window": 5},
            },
            "position_mapper": {
                "type": "threshold",
                "params": {
                    "long_entry_threshold": 0.1,
                    "long_exit_threshold": -0.05,
                    "shift_bars": 0,
                },
            },
            "output": {
                "save_full_timeseries": False,
                "save_debounced": False,
            },
        },
    )

    result = run_from_config(config_path)

    assert not result["market_data"].empty
    assert list(result["market_data"].columns) == ["open", "high", "low", "close", "volume"]
    assert result["market_data"].index.tz is None
    assert not result["target_position"].empty
    assert (workspace_root / "strategy" / "single_asset_alpha" / "aggregate_bars_runtime_v1" / "config_snapshot.yaml").exists()