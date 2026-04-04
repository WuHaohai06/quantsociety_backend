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
            fast_ma = close.rolling(window=fast_window, min_periods=fast_window).mean()
            slow_ma = close.rolling(window=slow_window, min_periods=slow_window).mean()

        # 连续信号: 归一化的快慢线差
        diff = fast_ma - slow_ma
        # 用慢线做归一化基准，避免价格量级影响
        signal = diff / slow_ma

        # 缩放到合理范围（用历史 rolling std 自适应）
        rolling_std = signal.rolling(window=slow_window * 2, min_periods=slow_window).std()
        signal_normalized = signal / rolling_std.clip(lower=1e-8)

        # tanh 压缩到 (-1, 1)
        signal_out = np.tanh(signal_normalized)
        signal_out.name = self.name

        return signal_out
