"""
MACD 信号 (Moving Average Convergence Divergence)
=================================================

基于 MACD 柱状图（Histogram）生成择时信号。

参数:
    fast_period  : int, 快速 EMA 周期 (默认 12)
    slow_period  : int, 慢速 EMA 周期 (默认 26)
    signal_period: int, 信号线 EMA 周期 (默认 9)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator


class MACDSignal(BaseSignalGenerator):
    """MACD 柱状图择时信号。

    信号值 = tanh(MACD_Histogram / adaptive_scale)
    """

    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        self.validate_market_data(market_data)

        fast_period = self.params.get("fast_period", 12)
        slow_period = self.params.get("slow_period", 26)
        signal_period = self.params.get("signal_period", 9)

        close = market_data["close"]

        # MACD 计算 (全向量化)
        ema_fast = close.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        # 自适应缩放: 使用 histogram 的 rolling std
        hist_std = histogram.rolling(
            window=slow_period * 2, min_periods=slow_period
        ).std()
        normalized = histogram / hist_std.clip(lower=1e-8)

        # tanh 压缩
        signal_out = np.tanh(normalized)
        signal_out.name = self.name

        return signal_out
