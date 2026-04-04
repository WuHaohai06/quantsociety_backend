from __future__ import annotations

from pathlib import Path
import sys


def _bootstrap_repo_paths(repo_root: Path) -> None:
    for candidate in (
        repo_root,
        repo_root / "backtest_layer",
        repo_root / "factor_layer" / "factor_engine",
    ):
        text = str(candidate)
        if text not in sys.path:
            sys.path.insert(0, text)


def run_python_strategy_demo(
    *,
    demo_root: str | Path,
    symbol: str = "A",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
    aggregate_bars_root: str | Path = "/home/yluel/share/projects/massive_parquet/cleaned_massive_data/aggregate_bars",
) -> dict:
    demo_path = Path(demo_root).resolve()
    repo_root = demo_path.parents[1]
    _bootstrap_repo_paths(repo_root)

    from strategy_layer.data import load_single_asset_ohlcv
    from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline
    from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import ThresholdPositionMapper
    from strategy_layer.single_asset_alpha.strategies.signals.dual_ma_signal import DualMASignal
    from strategy_layer.single_asset_alpha.strategies.signals.macd_signal import MACDSignal
    from strategy_layer.single_asset_alpha.strategies.signals.rsi_signal import RSISignal
    from strategy_layer.single_asset_alpha.strategies.signals.signal_combiner import SignalCombiner

    market_data = load_single_asset_ohlcv(
        symbol=symbol,
        mode="aggregate_bars_daily_summary",
        aggregate_bars_root=aggregate_bars_root,
        aggregate_dataset="daily_market_summary",
        freq="1d",
        start_date=start_date,
        end_date=end_date,
        cache_root=demo_path / "cache" / "market_data",
    )

    output_dir = demo_path / "outputs" / "python_alpha"
    output_dir.mkdir(parents=True, exist_ok=True)

    combiner = SignalCombiner(
        signal_generators=[
            DualMASignal(
                params={"fast_window": 3, "slow_window": 8, "ma_type": "sma"},
                name="FastDualMA",
            ),
            MACDSignal(
                params={"fast_period": 5, "slow_period": 13, "signal_period": 4},
                name="FastMACD",
            ),
            RSISignal(
                params={"rsi_period": 6, "overbought": 65.0, "oversold": 35.0},
                name="FastRSI",
            ),
        ],
        weights=[0.45, 0.35, 0.20],
        params={"combine_method": "weighted_avg"},
        name="ActiveCombinedSignal",
    )
    mapper = ThresholdPositionMapper(
        params={
            "long_entry_threshold": 0.10,
            "long_exit_threshold": 0.0,
            "short_entry_threshold": -0.10,
            "short_exit_threshold": 0.0,
            "allow_short": False,
            "position_size": 1.0,
            "shift_bars": 1,
        },
        name="ActiveThresholdMapper",
    )
    pipeline = StrategyPipeline(
        symbol=symbol,
        signal_generator=combiner,
        position_mapper=mapper,
        output_dir=str(output_dir),
    )
    target_position = pipeline.run(
        market_data=market_data,
        start_date=start_date,
        end_date=end_date,
        save_full_timeseries=True,
        save_debounced=True,
        output_format="parquet",
    )

    return {
        "market_data": market_data,
        "target_position": target_position,
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    payload = run_python_strategy_demo(
        demo_root=Path(__file__).resolve().parent,
    )
    print(payload["target_position"].head().to_string(index=False))