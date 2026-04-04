"""
使用 factor_lake_root 驱动单资产因子信号的最小示例。

这个脚本会：
1. 生成一份模拟 OHLCV
2. 临时写入一个最小 factor lake 分区
3. 通过 DataFetcher(factor_lake_root=..., factor_refs=...) 读取因子
4. 用 FactorThresholdSignal + StrategyPipeline 生成 target_position

运行:
    cd quantsociety_backend_project
    python strategy_layer/single_asset_alpha/examples/factor_lake_signal_demo.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy_layer.data import FactorRef
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline
from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import ThresholdPositionMapper
from strategy_layer.single_asset_alpha.strategies.signals.factor_threshold_signal import FactorThresholdSignal


def _write_factor_partition(
    lake_root: Path,
    factor_id: str,
    rows: list[tuple[pd.Timestamp, str, float]],
) -> None:
    frame = pd.DataFrame(rows, columns=["datetime", "asset", "value"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    year = int(frame["datetime"].dt.year.iloc[0])
    target = lake_root / "factors" / factor_id / f"year={year}"
    target.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target / "data.parquet", index=False)


def main() -> None:
    symbol = "FACTOR_DEMO"
    output_dir = Path(PROJECT_ROOT) / "outputs" / "factor_lake_demo"
    market = DataFetcher.generate_sample_data(
        symbol=symbol,
        periods=40,
        start_date="2024-01-01",
        seed=21,
    )

    with tempfile.TemporaryDirectory(prefix="single_asset_factor_lake_") as tmpdir:
        lake_root = Path(tmpdir)
        factor_rows: list[tuple[pd.Timestamp, str, float]] = []
        for index, timestamp in enumerate(market.index):
            regime = 1.0 if (index // 8) % 2 == 0 else -1.0
            factor_rows.append((timestamp, symbol, regime))

        _write_factor_partition(
            lake_root,
            factor_id="demo_timing_factor_v1",
            rows=factor_rows,
        )

        pipeline = StrategyPipeline(
            symbol=symbol,
            signal_generator=FactorThresholdSignal(
                params={
                    "factor_names": ["timing_signal"],
                    "normalize": False,
                },
                name="FactorThreshold",
            ),
            position_mapper=ThresholdPositionMapper(
                params={
                    "long_entry_threshold": 0.2,
                    "long_exit_threshold": -0.2,
                    "allow_short": False,
                    "shift_bars": 0,
                },
                name="ThresholdMapper",
            ),
            data_fetcher=DataFetcher(
                factor_lake_root=lake_root,
                factor_refs=[FactorRef("demo_timing_factor_v1", "timing_signal")],
            ),
            output_dir=output_dir,
        )

        output = pipeline.run(
            market_data=market,
            save_full_timeseries=False,
            save_debounced=False,
        )

    print("=" * 72)
    print("Factor lake single-asset demo")
    print("=" * 72)
    print(output.head(12).to_string(index=False))
    print("\n输出目录:", output_dir)
    print("说明: 真实接入时，把临时 lake_root 替换成你的 factor_engine 落盘根目录即可。")


if __name__ == "__main__":
    main()