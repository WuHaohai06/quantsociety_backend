from __future__ import annotations

"""内置策略工厂：在运行时绑定 Backtrader 的 ``bt`` 上构造策略类并注册到 ``StrategyRegistry``。

- ``target_position``：按外部给定的目标仓位序列（或数组）调仓，业务主路径。
- ``dual_ma``：示例策略（短均 > 长多则满仓），用于演示注册机制，一般研究用 ``target_position``。
"""

import numpy as np

from single_asset_backtest.strategy_registry import StrategyRegistry, StrategySpec


_DEFAULT_TARGET_POSITION_VERSION = "1.0"
_DEFAULT_DUAL_MA_VERSION = "1.0"


def _build_target_position_strategy(bt):
    from single_asset_backtest.strategy import TargetPositionStrategyMixin

    class _TargetPositionStrategy(TargetPositionStrategyMixin, bt.Strategy):
        params = (
            ("target_series", None),
            ("target_values", None),
            ("rebalance_threshold", 1e-8),
            ("allow_short", True),
            ("short_margin_requirement", 0.0),
            ("include_trade_ledger", False),
        )

        def __init__(self):
            self._init_trace(include_trade_ledger=bool(self.p.include_trade_ledger))
            self._target_series = self.p.target_series
            self._target_values = None
            if self.p.target_values is not None:
                self._target_values = np.asarray(self.p.target_values, dtype=float)
            self._last_target = 0.0
            self._bar_index = -1
            self._rebalance_threshold = float(self.p.rebalance_threshold)
            self._allow_short = bool(self.p.allow_short)
            self._short_margin_requirement = float(self.p.short_margin_requirement)
            if self._target_values is None and self._target_series is None:
                raise ValueError("target_series is required")

        def next(self):
            self._bar_index += 1

            # 当前 bar 的目标仓位：优先用预计算数组（与行情对齐），否则按时间戳查 Series
            if self._target_values is not None and 0 <= self._bar_index < len(self._target_values):
                target = float(self._target_values[self._bar_index])
            else:
                ts = self.data.datetime.datetime(0).replace(tzinfo=None)
                target = float(self._target_series.get(ts, 0.0))

            if not self._allow_short and target < 0:
                raise ValueError("short position requested but allow_short=False")

            # 空头时按保证金要求裁剪目标，避免超过经纪商允许的空头杠杆
            if self._short_margin_requirement > 0 and target < 0:
                target = max(target, -1.0 + self._short_margin_requirement)

            # 仅当与上一档目标差异超过阈值时才下单，减少噪声换手
            if abs(target - self._last_target) >= self._rebalance_threshold:
                self.order_target_percent(target=target)
                self._last_target = target

            ts = self.data.datetime.datetime(0).replace(tzinfo=None)
            self._record_bar(ts, target)

    return _TargetPositionStrategy


def _build_dual_ma_strategy(bt):
    from single_asset_backtest.strategy import TargetPositionStrategyMixin

    class _DualMAStrategy(TargetPositionStrategyMixin, bt.Strategy):
        params = (
            ("short_window", 5),
            ("long_window", 20),
            ("position_size", 1.0),
            ("include_trade_ledger", False),
        )

        def __init__(self):
            self._init_trace(include_trade_ledger=bool(self.p.include_trade_ledger))
            self._short_window = int(self.p.short_window)
            self._long_window = int(self.p.long_window)
            if self._short_window <= 0 or self._long_window <= 0:
                raise ValueError("short_window and long_window must be > 0")
            if self._short_window >= self._long_window:
                raise ValueError("short_window must be < long_window")

            self._position_size = float(self.p.position_size)
            if self._position_size < 0.0 or self._position_size > 1.0:
                raise ValueError("position_size must be within [0, 1]")

            self._short_ma = bt.indicators.SimpleMovingAverage(self.data.close, period=self._short_window)
            self._long_ma = bt.indicators.SimpleMovingAverage(self.data.close, period=self._long_window)
            self._last_target = 0.0

        def next(self):
            # 经典双均线：短线上穿长线则满仓，否则空仓（仓位幅度由 position_size 限制）
            target = self._position_size if float(self._short_ma[0]) > float(self._long_ma[0]) else 0.0
            if abs(target - self._last_target) >= 1e-8:
                self.order_target_percent(target=target)
                self._last_target = target

            ts = self.data.datetime.datetime(0).replace(tzinfo=None)
            self._record_bar(ts, target)

    return _DualMAStrategy


def build_strategy_registry(bt) -> StrategyRegistry:
    """构造并填充默认策略注册表（需传入已 import 的 ``backtrader`` 模块 ``bt``）。"""
    registry = StrategyRegistry()
    registry.register(
        StrategySpec(
            name="target_position",
            version=_DEFAULT_TARGET_POSITION_VERSION,
            strategy_cls=_build_target_position_strategy(bt),
            default_params={},
        )
    )
    registry.register(
        StrategySpec(
            name="dual_ma",
            version=_DEFAULT_DUAL_MA_VERSION,
            strategy_cls=_build_dual_ma_strategy(bt),
            default_params={
                "short_window": 5,
                "long_window": 20,
                "position_size": 1.0,
            },
        )
    )
    return registry
