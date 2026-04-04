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
            # 对每个信号做截面排名后加权
            ranked = all_signals.rank(pct=True) * 2 - 1  # 映射到 [-1, 1]
            weights_arr = np.array(self.weights)
            composite = ranked.values @ weights_arr
        else:
            # 加权平均
            weights_arr = np.array(self.weights)
            composite = all_signals.fillna(0.0).values @ weights_arr

        signal_out = pd.Series(
            np.tanh(composite),
            index=market_data.index,
            name=self.name,
        )
        return signal_out
