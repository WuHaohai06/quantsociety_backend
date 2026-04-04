"""
简单阈值状态机 (Simple Threshold Mapper)
=========================================

基于固定阈值的三态/四态仓位映射器。
具有开仓/平仓双阈值机制，防止信号在阈值附近震荡导致频繁换手。

参数:
    long_entry_threshold  : float, 开多阈值 (默认 0.5)
    long_exit_threshold   : float, 平多阈值 (默认 0.0)
    short_entry_threshold : float, 开空阈值 (默认 -0.5)
    short_exit_threshold  : float, 平空阈值 (默认 0.0)
    allow_short           : bool,  是否允许做空 (默认 False)
    position_size         : float, 仓位大小 (默认 1.0, 满仓)
    shift_bars            : int,   信号延迟 bar 数 (默认 1, T日信号T+1执行)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_position import BasePositionMapper
from strategy_layer.single_asset_alpha.core.schema import ActionName


class ThresholdPositionMapper(BasePositionMapper):
    """固定阈值仓位状态机。

    状态转移逻辑 (带滞回的双阈值机制):
    ┌───────────┐    signal >= long_entry     ┌───────────┐
    │  FLAT (0) │ ──────────────────────────→ │  LONG (+1)│
    │           │ ←────────────────────────── │           │
    └───────────┘    signal <= long_exit      └───────────┘
         │                                        │
         │  signal <= short_entry                  │
         ↓                                        │
    ┌───────────┐                                 │
    │ SHORT (-1)│ ←───────────────────────────────┘
    │           │    (if allow_short & signal <= short_entry)
    └───────────┘
    """

    def map_to_position(
        self,
        signals: pd.Series,
        market_data: pd.DataFrame,
    ) -> pd.DataFrame:

        long_entry = self.params.get("long_entry_threshold", 0.5)
        long_exit = self.params.get("long_exit_threshold", 0.0)
        short_entry = self.params.get("short_entry_threshold", -0.5)
        short_exit = self.params.get("short_exit_threshold", 0.0)
        allow_short = self.params.get("allow_short", False)
        position_size = self.params.get("position_size", 1.0)
        shift_bars = self.params.get("shift_bars", 1)

        n = len(signals)
        positions = np.zeros(n)
        actions = np.full(n, ActionName.HOLD.value, dtype=object)

        # 状态机逐 bar 运行 (这里使用 numpy 数组避免 pandas overhead)
        # 注意: 这是唯一允许使用循环的地方，因为状态机具有路径依赖性
        current_state = 0.0  # 0=空仓, 1=多头, -1=空头
        sig_vals = signals.values

        for i in range(n):
            sig = sig_vals[i]
            if np.isnan(sig):
                positions[i] = current_state
                actions[i] = ActionName.HOLD.value
                continue

            if current_state == 0.0:
                # 空仓 → 判断开仓
                if sig >= long_entry:
                    current_state = position_size
                    actions[i] = ActionName.ENTRY_LONG.value
                elif allow_short and sig <= short_entry:
                    current_state = -position_size
                    actions[i] = ActionName.ENTRY_SHORT.value
                else:
                    actions[i] = ActionName.HOLD.value
            elif current_state > 0:
                # 多头 → 判断平仓或反手
                if sig <= long_exit:
                    if allow_short and sig <= short_entry:
                        current_state = -position_size
                        actions[i] = ActionName.ENTRY_SHORT.value
                    else:
                        current_state = 0.0
                        actions[i] = ActionName.EXIT_LONG.value
                else:
                    actions[i] = ActionName.HOLD.value
            else:
                # 空头 → 判断平仓或反手
                if sig >= short_exit:
                    if sig >= long_entry:
                        current_state = position_size
                        actions[i] = ActionName.ENTRY_LONG.value
                    else:
                        current_state = 0.0
                        actions[i] = ActionName.EXIT_SHORT.value
                else:
                    actions[i] = ActionName.HOLD.value

            positions[i] = current_state

        # 构建 DataFrame
        df = pd.DataFrame(
            {
                "target_position": positions,
                "signal_value": sig_vals,
                "action_name": actions,
            },
            index=signals.index,
        )

        # ★ 防未来函数: shift
        df = self.apply_shift(df, shift_bars=shift_bars)

        return df
