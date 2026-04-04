"""
双均线交叉信号 (Dual Moving Average Crossover)
===============================================

经典趋势跟踪信号: 快线上穿慢线看多，快线下穿慢线看空。

参数:
    fast_window : int, 快线窗口期 (默认 5)
    slow_window : int, 慢线窗口期 (默认 20)
    ma_type     : str, 均线类型: "sma" (简单) 或 "ema" (指数), 默认 "sma"
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator


class DualMASignal(BaseSignalGenerator):
    """双均线交叉信号。

    当快速均线 > 慢速均线时输出 +1 (看多),
    当快速均线 < 慢速均线时输出 -1 (看空),
    交叉点附近输出连续过渡值。
    """

    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        self.validate_market_data(market_data)

        fast_window = self.params.get("fast_window", 5)
        slow_window = self.params.get("slow_window", 20)
        ma_type = self.params.get("ma_type", "sma")

        close = market_data["close"]

        if ma_type == "ema":
            fast_ma = close.ewm(span=fast_window, adjust=False).mean()
            slow_ma = close.ewm(span=slow_window, adjust=False).mean()
        else:
            # min_periods=窗口长度：预热期输出 NaN，与「不足窗口不算信号」一致
            fast_ma = close.rolling(window=fast_window, min_periods=fast_window).mean()
            slow_ma = close.rolling(window=slow_window, min_periods=slow_window).mean()

        # 连续信号：相对强弱，非简单 ±1
        diff = fast_ma - slow_ma
        signal = diff / slow_ma  # 按价格尺度归一，方便跨标的比较量级

        # 再用波动率归一，避免单边趋势导致长期饱和
        rolling_std = signal.rolling(window=slow_window * 2, min_periods=slow_window).std()
        signal_normalized = signal / rolling_std.clip(lower=1e-8)

        signal_out = np.tanh(signal_normalized)  # 有界，便于下游阈值状态机
        signal_out.name = self.name

        return signal_out
