"""目标驱动回测：包名强调单标的 Backtrader 路径，同包亦含多标的 ``run_multi_asset_backtest``。

默认导出单标的入口与契约/策略注册；多标的请 ``from single_asset_backtest.runner import run_multi_asset_backtest``。
"""

from .config import BacktestConfig
from .contracts import (
    BACKTEST_SCHEMA_VERSION,
    REQUIRED_METRICS_KEYS,
    REQUIRED_RETURNS_KEYS,
    REQUIRED_SUMMARY_KEYS,
    align_target_position_to_index,
    validate_target_position,
)
from .io import load_ohlcv, load_target_position
from .runner import run_single_asset_backtest
from .strategy_library import build_strategy_registry
from .strategy_registry import StrategyRegistry, StrategySpec

__all__ = [
    "BACKTEST_SCHEMA_VERSION",
    "REQUIRED_METRICS_KEYS",
    "REQUIRED_RETURNS_KEYS",
    "REQUIRED_SUMMARY_KEYS",
    "BacktestConfig",
    "align_target_position_to_index",
    "load_ohlcv",
    "load_target_position",
    "run_single_asset_backtest",
    "StrategyRegistry",
    "StrategySpec",
    "build_strategy_registry",
    "validate_target_position",
]
