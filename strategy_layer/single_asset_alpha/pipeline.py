"""
总控制台 Pipeline
=================

串联 Data → Signal → Position → 落盘 的完整流水线。
这是研究员 C 模块的主入口，负责:
  1. 加载数据
  2. 生成信号 (C-1)
  3. 映射仓位 (C-2)
  4. 格式化并校验输出
  5. 落盘交付给研究员 D

使用示例:
    python -m strategy_layer.single_asset_alpha.pipeline --symbol 000001.SZ --mode demo
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Any
import json
import logging

from workspace_paths import default_single_asset_alpha_output_root

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("single_asset_alpha.pipeline")

# 内部导入
from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator
from strategy_layer.single_asset_alpha.core.base_position import BasePositionMapper
from strategy_layer.single_asset_alpha.core.schema import TargetPositionSchema
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher

# ---- 信号实现 ----
from strategy_layer.single_asset_alpha.strategies.signals.dual_ma_signal import DualMASignal
from strategy_layer.single_asset_alpha.strategies.signals.macd_signal import MACDSignal
from strategy_layer.single_asset_alpha.strategies.signals.rsi_signal import RSISignal
from strategy_layer.single_asset_alpha.strategies.signals.signal_combiner import SignalCombiner

# ---- 仓位映射器 ----
from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import (
    ThresholdPositionMapper,
)
from strategy_layer.single_asset_alpha.strategies.position_mappers.atr_volatility_mapper import (
    ATRVolatilityMapper,
)


class StrategyPipeline:
    """策略流水线主控制器。

    Parameters
    ----------
    symbol : str
        标的代码。
    signal_generator : BaseSignalGenerator
        C-1 信号生成器实例。
    position_mapper : BasePositionMapper
        C-2 仓位映射器实例。
    data_fetcher : DataFetcher
        数据获取器实例。
    output_dir : str or Path
        输出目录。
    """

    def __init__(
        self,
        symbol: str,
        signal_generator: BaseSignalGenerator,
        position_mapper: BasePositionMapper,
        data_fetcher: DataFetcher | None = None,
        output_dir: str | Path | None = None,
    ):
        self.symbol = symbol
        self.signal_generator = signal_generator
        self.position_mapper = position_mapper
        self.data_fetcher = data_fetcher or DataFetcher()
        self.output_dir = Path(output_dir or default_single_asset_alpha_output_root(symbol))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        market_data: pd.DataFrame | None = None,
        factor_data: pd.DataFrame | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        save_full_timeseries: bool = True,
        save_debounced: bool = True,
        output_format: str = "parquet",
    ) -> pd.DataFrame:
        """执行完整策略流水线。

        Parameters
        ----------
        market_data : pd.DataFrame, optional
            直接提供行情数据。若为 None 则通过 data_fetcher 加载。
        factor_data : pd.DataFrame, optional
            直接提供因子数据。若为 None 则尝试通过 data_fetcher 加载。
        start_date, end_date : str, optional
            时间范围。
        save_full_timeseries : bool
            是否保存完整时间序列版本。
        save_debounced : bool
            是否保存防抖版本（仅仓位变化点）。
        output_format : str
            输出格式: "parquet" 或 "csv"。

        Returns
        -------
        pd.DataFrame
            符合 target_position Schema 的输出数据。
        """
        logger.info(f"═══ 策略流水线启动 [{self.symbol}] ═══")
        logger.info(f"信号生成器: {self.signal_generator}")
        logger.info(f"仓位映射器: {self.position_mapper}")

        # ── Step 1: 数据加载 ──
        if market_data is None:
            logger.info("Step 1/5: 加载行情数据...")
            market_data = self.data_fetcher.load_market_data(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            logger.info("Step 1/5: 使用外部提供的行情数据")
            if start_date:
                market_data = market_data.loc[start_date:]
            if end_date:
                market_data = market_data.loc[:end_date]

        logger.info(
            f"  行情数据: {len(market_data)} 行, "
            f"时间范围: [{market_data.index[0]} ~ {market_data.index[-1]}]"
        )

        if factor_data is None and self.data_fetcher.has_factor_source:
            logger.info("Step 1b: 尝试加载因子数据...")
            factor_data = self.data_fetcher.load_factor_data(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if factor_data is not None:
                logger.info(f"  因子数据: {len(factor_data)} 行, {len(factor_data.columns)} 个因子")
            else:
                logger.info("  未找到因子数据，将仅使用行情数据")

        # ── Step 2: 信号生成 (C-1) ──
        logger.info("Step 2/5: 生成择时信号 (C-1)...")
        raw_signals = self.signal_generator.generate(market_data, factor_data)
        logger.info(
            f"  信号统计: mean={raw_signals.mean():.4f}, "
            f"std={raw_signals.std():.4f}, "
            f"NaN={raw_signals.isna().sum()}"
        )

        # ── Step 3: 仓位映射 (C-2) ──
        logger.info("Step 3/5: 信号转目标仓位 (C-2)...")
        internal_df = self.position_mapper.map_to_position(raw_signals, market_data)
        logger.info(
            f"  仓位分布: "
            f"多头={( internal_df['target_position'] > 0).sum()}, "
            f"空仓={(internal_df['target_position'] == 0).sum()}, "
            f"空头={(internal_df['target_position'] < 0).sum()}"
        )

        # ── Step 4: 格式化输出 ──
        logger.info("Step 4/5: 格式化为标准 target_position Schema...")
        # internal_df 索引为时间；此处展开为长表 timestamp 列，供 CSV/Parquet 与 D 侧读入
        output_df = TargetPositionSchema.format_output(
            df=internal_df,
            symbol=self.symbol,
            include_optional=True,
        )

        errors = TargetPositionSchema.validate(output_df, strict=True)
        if errors:
            logger.warning(f"  ⚠️ Schema 校验发现问题:")
            for e in errors:
                logger.warning(f"    - {e}")
        else:
            logger.info("  ✅ Schema 校验通过")

        # ── Step 5: 落盘 ──
        logger.info("Step 5/5: 落盘交付...")
        saved_files = []

        if save_full_timeseries:
            full_path = self._save_output(
                output_df, suffix="_full", fmt=output_format
            )
            saved_files.append(full_path)

        if save_debounced:
            # 仅保留仓位变化行，减小文件；回测前若用 debounced 文件需确认 D 侧是否先展开成全日序列
            debounced_df = BasePositionMapper.debounce(internal_df)
            debounced_output = TargetPositionSchema.format_output(
                df=debounced_df,
                symbol=self.symbol,
                include_optional=True,
            )
            debounced_path = self._save_output(
                debounced_output, suffix="_debounced", fmt=output_format
            )
            saved_files.append(debounced_path)

        # 保存运行元信息
        meta = self._build_run_metadata(output_df, raw_signals)
        meta_path = self.output_dir / f"{self.symbol}_run_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, default=str)
        saved_files.append(str(meta_path))

        logger.info(f"═══ 流水线完成 [{self.symbol}] ═══")
        for fp in saved_files:
            logger.info(f"  📄 {fp}")

        return output_df  # 列符合 TargetPositionSchema；可交给研究员 D（single_asset_backtest）或 integration.backtest_bridge

    def _save_output(
        self, df: pd.DataFrame, suffix: str, fmt: str
    ) -> str:
        """保存输出文件。"""
        if fmt == "csv":
            path = self.output_dir / f"{self.symbol}_target_position{suffix}.csv"
            df.to_csv(path, index=False)
        else:
            path = self.output_dir / f"{self.symbol}_target_position{suffix}.parquet"
            df.to_parquet(path, index=False)
        return str(path)

    def _build_run_metadata(
        self, output_df: pd.DataFrame, raw_signals: pd.Series
    ) -> dict:
        """构建运行元信息。"""
        tp = output_df["target_position"]
        return {
            "run_timestamp": datetime.now().isoformat(),
            "symbol": self.symbol,
            "signal_generator": repr(self.signal_generator),
            "position_mapper": repr(self.position_mapper),
            "data_range": {
                "start": str(output_df["timestamp"].iloc[0]),
                "end": str(output_df["timestamp"].iloc[-1]),
                "total_bars": len(output_df),
            },
            "signal_stats": {
                "mean": float(raw_signals.mean()),
                "std": float(raw_signals.std()),
                "nan_count": int(raw_signals.isna().sum()),
            },
            "position_stats": {
                "long_bars": int((tp > 0).sum()),
                "flat_bars": int((tp == 0).sum()),
                "short_bars": int((tp < 0).sum()),
                "mean_position": float(tp.mean()),
                "position_changes": int((tp.diff().abs() > 1e-9).sum()),
            },
        }


# ═══════════════════════════════════════════════════════════════════
# 预制策略工厂 (快速构建常用策略组合)
# ═══════════════════════════════════════════════════════════════════

def create_dual_ma_strategy(
    symbol: str = "000001.SZ",
    fast_window: int = 5,
    slow_window: int = 20,
    long_threshold: float = 0.5,
    allow_short: bool = False,
    output_dir: str | Path | None = None,
    **kwargs,
) -> StrategyPipeline:
    """创建双均线策略流水线。"""
    signal = DualMASignal(
        params={"fast_window": fast_window, "slow_window": slow_window, "ma_type": "sma"},
        name="DualMA",
    )
    mapper = ThresholdPositionMapper(
        params={
            "long_entry_threshold": long_threshold,
            "long_exit_threshold": -long_threshold * 0.3,
            "allow_short": allow_short,
            "short_entry_threshold": -long_threshold,
            "short_exit_threshold": long_threshold * 0.3,
            **kwargs,
        },
        name="ThresholdMapper",
    )
    return StrategyPipeline(
        symbol=symbol, signal_generator=signal, position_mapper=mapper, output_dir=output_dir
    )


def create_macd_strategy(
    symbol: str = "000001.SZ",
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    long_threshold: float = 0.4,
    allow_short: bool = False,
    output_dir: str | Path | None = None,
    **kwargs,
) -> StrategyPipeline:
    """创建 MACD 策略流水线。"""
    signal = MACDSignal(
        params={"fast_period": fast_period, "slow_period": slow_period, "signal_period": signal_period},
        name="MACD",
    )
    mapper = ThresholdPositionMapper(
        params={
            "long_entry_threshold": long_threshold,
            "long_exit_threshold": -long_threshold * 0.3,
            "allow_short": allow_short,
            "short_entry_threshold": -long_threshold,
            "short_exit_threshold": long_threshold * 0.3,
            **kwargs,
        },
        name="ThresholdMapper",
    )
    return StrategyPipeline(
        symbol=symbol, signal_generator=signal, position_mapper=mapper, output_dir=output_dir
    )


def create_combined_strategy(
    symbol: str = "000001.SZ",
    use_atr_mapper: bool = True,
    allow_short: bool = False,
    output_dir: str | Path | None = None,
    **kwargs,
) -> StrategyPipeline:
    """创建多信号组合策略流水线。"""
    signals = [
        DualMASignal(params={"fast_window": 5, "slow_window": 20}, name="DualMA"),
        MACDSignal(params={"fast_period": 12, "slow_period": 26, "signal_period": 9}, name="MACD"),
        RSISignal(params={"rsi_period": 14}, name="RSI"),
    ]
    combiner = SignalCombiner(
        signal_generators=signals,
        weights=[0.4, 0.4, 0.2],  # MACD 和均线为主，RSI 辅助
        name="CombinedSignal",
    )
    if use_atr_mapper:
        mapper = ATRVolatilityMapper(
            params={
                "atr_period": 14,
                "base_long_threshold": 0.4,
                "base_short_threshold": -0.4,
                "target_volatility": 0.15,
                "allow_short": allow_short,
                **kwargs,
            },
            name="ATRVolMapper",
        )
    else:
        mapper = ThresholdPositionMapper(
            params={
                "long_entry_threshold": 0.4,
                "long_exit_threshold": -0.1,
                "allow_short": allow_short,
                "short_entry_threshold": -0.4,
                "short_exit_threshold": 0.1,
                **kwargs,
            },
            name="ThresholdMapper",
        )

    return StrategyPipeline(
        symbol=symbol, signal_generator=combiner, position_mapper=mapper, output_dir=output_dir
    )


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════

def main():
    """命令行入口: Demo 模式运行。"""
    import argparse

    parser = argparse.ArgumentParser(description="单标的择时策略流水线")
    parser.add_argument("--symbol", default="000001.SZ", help="标的代码")
    parser.add_argument(
        "--strategy",
        choices=["dual_ma", "macd", "combined"],
        default="combined",
        help="预制策略",
    )
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument(
        "--format", choices=["parquet", "csv"], default="parquet", help="输出格式"
    )
    parser.add_argument("--periods", type=int, default=500, help="模拟数据天数")
    parser.add_argument("--allow-short", action="store_true", help="允许做空")
    args = parser.parse_args()

    # 使用模拟数据 (Sprint 0 Mock 交付)
    logger.info("📊 使用模拟行情数据 (Sprint 0 Mock 模式)")
    market_data = DataFetcher.generate_sample_data(
        symbol=args.symbol, periods=args.periods
    )

    # 构建策略
    if args.strategy == "dual_ma":
        pipeline = create_dual_ma_strategy(
            symbol=args.symbol, allow_short=args.allow_short, output_dir=args.output_dir
        )
    elif args.strategy == "macd":
        pipeline = create_macd_strategy(
            symbol=args.symbol, allow_short=args.allow_short, output_dir=args.output_dir
        )
    else:
        pipeline = create_combined_strategy(
            symbol=args.symbol, allow_short=args.allow_short, output_dir=args.output_dir
        )

    # 运行
    result = pipeline.run(
        market_data=market_data,
        output_format=args.format,
    )

    print(f"\n{'='*60}")
    print(f"🎯 目标仓位数据预览 (前 10 行):")
    print(f"{'='*60}")
    print(result.head(10).to_string(index=False))
    print(f"\n{'='*60}")
    print(f"✅ [{args.symbol}] 目标仓位数据已生成，可交付给研究员 D (孙海崴)！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
