"""
信号组合器 (Signal Combiner)
============================

将多个底层信号按权重合成为单一综合信号。

参数:
    signal_generators : list[BaseSignalGenerator], 信号生成器列表
    weights           : list[float], 对应权重 (默认等权)
    combine_method    : str, 合成方法: "weighted_avg" 或 "rank_avg"
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator


class SignalCombiner(BaseSignalGenerator):
    """多信号加权合成器。

    将多个信号生成器的输出进行加权平均，产生综合择时信号。
    """

    def __init__(
        self,
        signal_generators: list[BaseSignalGenerator],
        weights: list[float] | None = None,
        params: dict | None = None,
        name: str = "CombinedSignal",
    ):
        super().__init__(params=params or {}, name=name)
        self.signal_generators = signal_generators
        if weights is None:
            self.weights = [1.0 / len(signal_generators)] * len(signal_generators)
        else:
            total = sum(abs(w) for w in weights)
            # 按绝对值归一，允许多空对冲类权重和为 0 的写法
            self.weights = [w / total for w in weights]

    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        self.validate_market_data(market_data)

        all_signals = pd.DataFrame(index=market_data.index)

        for i, gen in enumerate(self.signal_generators):
            sig = gen.generate(market_data, factor_data)
            all_signals[gen.name] = sig

        method = self.params.get("combine_method", "weighted_avg")

        if method == "rank_avg":
            # 单标的序列上按「时间截面」做 pct 秩，削弱量纲差异大的因子/技术信号
            ranked = all_signals.rank(pct=True) * 2 - 1  # 每列约均匀落在 [-1,1]
            weights_arr = np.array(self.weights)
            composite = ranked.values @ weights_arr
        else:
            weights_arr = np.array(self.weights)
            # NaN 当 0 参与加权，避免某路信号预热期拖垮合成
            composite = all_signals.fillna(0.0).values @ weights_arr

        signal_out = pd.Series(
            np.tanh(composite),  # 再压一层，与单路信号输出范围一致
            index=market_data.index,
            name=self.name,
        )
        return signal_out
