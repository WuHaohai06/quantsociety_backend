"""
因子阈值信号 (Factor Threshold Signal)
=======================================

利用外部因子数据（来自陆殷世杰因子库）生成择时信号。
支持单因子或多因子线性加权。

参数:
    factor_names  : list[str], 使用的因子列表
    factor_weights: dict[str, float], 因子权重 (默认等权)
    normalize     : bool, 是否对因子做 z-score 标准化 (默认 True)
    zscore_window : int, z-score 滚动窗口 (默认 60)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator


class FactorThresholdSignal(BaseSignalGenerator):
    """因子阈值信号。

    将外部因子做 z-score 标准化后加权合成，经 tanh 压缩输出。
    可与其他技术面信号组合使用。
    """

    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        self.validate_market_data(market_data)

        if factor_data is None or factor_data.empty:
            # 无因子数据时返回全零信号
            return pd.Series(0.0, index=market_data.index, name=self.name)

        factor_names = self.params.get("factor_names", list(factor_data.columns))
        factor_weights = self.params.get("factor_weights", {})
        normalize = self.params.get("normalize", True)
        zscore_window = self.params.get("zscore_window", 60)

        # 过滤出可用因子
        available_factors = [f for f in factor_names if f in factor_data.columns]
        if not available_factors:
            return pd.Series(0.0, index=market_data.index, name=self.name)

        # 与行情对齐；因子缺某日则 NaN，后续 rolling 会自然跳过或你可先 ffill
        factors = factor_data[available_factors].reindex(market_data.index)

        if normalize:
            rolling_mean = factors.rolling(
                window=zscore_window, min_periods=zscore_window // 2
            ).mean()
            rolling_std = factors.rolling(
                window=zscore_window, min_periods=zscore_window // 2
            ).std()
            factors = (factors - rolling_mean) / rolling_std.clip(lower=1e-8)

        weights = np.array([
            factor_weights.get(f, 1.0 / len(available_factors))
            for f in available_factors
        ])
        weights = weights / np.sum(np.abs(weights))

        composite = factors.values @ weights

        # tanh 压缩
        signal_out = pd.Series(
            np.tanh(composite),
            index=market_data.index,
            name=self.name,
        )
        return signal_out
