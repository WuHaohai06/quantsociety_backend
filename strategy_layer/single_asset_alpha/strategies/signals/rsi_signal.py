"""
RSI 信号 (Relative Strength Index)
===================================

基于 RSI 指标生成均值回复型择时信号。

参数:
    rsi_period    : int,   RSI 计算窗口 (默认 14)
    overbought    : float, 超买阈值 (默认 70)
    oversold      : float, 超卖阈值 (默认 30)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator


class RSISignal(BaseSignalGenerator):
    """RSI 均值回复信号。

    信号逻辑:
      - RSI < oversold  → 正值 (看多，认为超卖反弹)
      - RSI > overbought → 负值 (看空，认为超买回落)
      - 50 附近 → 中性
    """

    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        self.validate_market_data(market_data)

        period = self.params.get("rsi_period", 14)
        overbought = self.params.get("overbought", 70.0)
        oversold = self.params.get("oversold", 30.0)

        close = market_data["close"]

        # RSI 计算 (Wilder 平滑, 全向量化)
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)

        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.clip(lower=1e-10)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # 转换为对称信号: 将 [0, 100] 映射到 [-1, 1]
        midpoint = (overbought + oversold) / 2.0
        half_range = (overbought - oversold) / 2.0

        # 线性映射后 tanh 压缩
        raw_signal = -(rsi - midpoint) / half_range
        signal_out = np.tanh(raw_signal)
        signal_out.name = self.name

        return signal_out
