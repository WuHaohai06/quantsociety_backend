"""
ATR 波动率自适应状态机 (ATR Volatility Mapper)
===============================================

基于 ATR (Average True Range) 的动态阈值仓位映射器。
阈值随近期波动率自适应调整:
  - 高波动时期: 阈值放宽，减少噪声交易
  - 低波动时期: 阈值收紧，捕捉更多机会

同时支持基于 ATR 的仓位缩放:
  - 波动越大 → 仓位越小 (等波动暴露/风险平价思想)

参数:
    atr_period              : int,   ATR 计算周期 (默认 14)
    base_long_threshold     : float, 基准开多阈值 (默认 0.5)
    base_short_threshold    : float, 基准开空阈值 (默认 -0.5)
    exit_buffer_ratio       : float, 平仓缓冲比例 (默认 0.4, 即平仓阈值=开仓×0.4)
    volatility_scale_factor : float, 波动率缩放因子 (默认 1.0)
    target_volatility       : float, 目标年化波动率 (默认 0.15)
    allow_short             : bool,  是否允许做空 (默认 False)
    max_position            : float, 最大仓位上限 (默认 1.0)
    min_position            : float, 最小仓位下限 (默认 0.1)
    annualize_factor        : int,   年化系数 (默认 252, 日频; 分钟频可设 252*390=98280)
    shift_bars              : int,   信号延迟 bar 数 (默认 1)
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from strategy_layer.single_asset_alpha.core.base_position import BasePositionMapper
from strategy_layer.single_asset_alpha.core.schema import ActionName


class ATRVolatilityMapper(BasePositionMapper):
    """ATR 波动率自适应仓位映射器。

    特点:
      1. 动态开平仓阈值: threshold = base_threshold × (atr / atr_median)
      2. 波动率仓位缩放: position_size = target_vol / realized_vol, clipped
    """

    def map_to_position(
        self,
        signals: pd.Series,
        market_data: pd.DataFrame,
    ) -> pd.DataFrame:

        atr_period = self.params.get("atr_period", 14)
        base_long = self.params.get("base_long_threshold", 0.5)
        base_short = self.params.get("base_short_threshold", -0.5)
        exit_buffer = self.params.get("exit_buffer_ratio", 0.4)
        vol_scale = self.params.get("volatility_scale_factor", 1.0)
        target_vol = self.params.get("target_volatility", 0.15)
        allow_short = self.params.get("allow_short", False)
        max_pos = self.params.get("max_position", 1.0)
        min_pos = self.params.get("min_position", 0.1)
        annualize = self.params.get("annualize_factor", 252)
        shift_bars = self.params.get("shift_bars", 1)

        high = market_data["high"]
        low = market_data["low"]
        close = market_data["close"]

        # 经典 TR：三根 bar 内最大真实波幅，再对 TR 做 SMA 得 ATR（非 Wilder ATR，与部分软件略有差异）
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=atr_period, min_periods=atr_period).mean()

        # 用较长窗的中位数当「典型波动」，atr_ratio>1 表示当前比近期更躁
        atr_median = atr.rolling(
            window=atr_period * 10, min_periods=atr_period * 2
        ).median()
        atr_ratio = (atr / atr_median.clip(lower=1e-10)).fillna(1.0)

        # 波动大 → 阈值抬高 → 减少噪声开仓；exit_buffer 把平仓线设在开仓线内侧形成滞回
        dynamic_long_entry = base_long * (atr_ratio ** vol_scale)
        dynamic_long_exit = dynamic_long_entry * exit_buffer
        dynamic_short_entry = base_short * (atr_ratio ** vol_scale)
        dynamic_short_exit = dynamic_short_entry * exit_buffer

        # 实现波动率越高，仓位因子越小（近似风险平价）；annualize 需与 bar 频率一致
        bar_returns = close.pct_change()
        realized_vol = bar_returns.rolling(
            window=atr_period * 2, min_periods=atr_period
        ).std() * np.sqrt(annualize)
        vol_scaled_size = (target_vol / realized_vol.clip(lower=0.01)).clip(
            lower=min_pos, upper=max_pos
        )

        # 路径依赖状态机，必须用循环；阈值与仓位上限每 bar 可变
        n = len(signals)
        positions = np.zeros(n)
        actions = np.full(n, ActionName.HOLD.value, dtype=object)

        sig_vals = signals.values
        le_vals = dynamic_long_entry.values
        lx_vals = dynamic_long_exit.values
        se_vals = dynamic_short_entry.values
        sx_vals = dynamic_short_exit.values
        size_vals = vol_scaled_size.values

        current_state = 0.0

        for i in range(n):
            sig = sig_vals[i]
            if np.isnan(sig) or np.isnan(le_vals[i]):
                positions[i] = current_state
                actions[i] = ActionName.HOLD.value
                continue

            size = float(size_vals[i]) if not np.isnan(size_vals[i]) else 0.5

            if current_state == 0.0:
                if sig >= le_vals[i]:
                    current_state = size
                    actions[i] = ActionName.ENTRY_LONG.value
                elif allow_short and sig <= se_vals[i]:
                    current_state = -size
                    actions[i] = ActionName.ENTRY_SHORT.value
                else:
                    actions[i] = ActionName.HOLD.value
            elif current_state > 0:
                if sig <= lx_vals[i]:
                    if allow_short and sig <= se_vals[i]:
                        current_state = -size
                        actions[i] = ActionName.ENTRY_SHORT.value
                    else:
                        current_state = 0.0
                        actions[i] = ActionName.EXIT_LONG.value
                else:
                    # 仍持有多头，但按新波动率更新目标杠杆（动作记 HOLD）
                    current_state = size
                    actions[i] = ActionName.HOLD.value
            else:
                if sig >= sx_vals[i]:
                    if sig >= le_vals[i]:
                        current_state = size
                        actions[i] = ActionName.ENTRY_LONG.value
                    else:
                        current_state = 0.0
                        actions[i] = ActionName.EXIT_SHORT.value
                else:
                    current_state = -size
                    actions[i] = ActionName.HOLD.value

            positions[i] = current_state

        df = pd.DataFrame(
            {
                "target_position": positions,
                "signal_value": sig_vals,
                "action_name": actions,
            },
            index=signals.index,
        )

        df = self.apply_shift(df, shift_bars=shift_bars)  # 与 SimpleMapper 一致，默认 T+1 生效

        return df
