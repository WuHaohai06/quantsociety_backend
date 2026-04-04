"""
C-2 仓位映射层抽象基类
======================

所有仓位映射器（状态机）都必须继承 BasePositionMapper 并实现 map_to_position() 方法。

核心约束:
  - 将 C-1 产出的连续信号转化为离散 target_position 值
  - target_position ∈ [-1.0, 1.0]，表示资金权重
  - 必须处理未来函数风险（T 日信号 → T+1 仓位）
  - 所有阈值参数通过 params dict 传入
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Any


# ── target_position Schema 标准列定义 ──────────────────────────────────
# 这是研究员 C 向研究员 D 交付的唯一凭证
TARGET_POSITION_COLUMNS = [
    "timestamp",       # datetime  - 指令执行时间 (T+1 开盘)
    "symbol",          # str       - 标的代码
    "target_position", # float     - 目标资金权重 ∈ [-1.0, 1.0]
    "signal_value",    # float     - (附加) 原始信号值，供归因
    "action_name",     # str       - (附加) 状态机动作名
]


class BasePositionMapper(ABC):
    """仓位映射器抽象基类（状态机）。

    Parameters
    ----------
    params : dict
        状态机参数字典，包括:
        - 开平仓阈值
        - 止盈止损线
        - 是否允许做空
        - 信号延迟 bar 数（shift 值）
        等所有可调参数
    name : str, optional
        映射器名称，默认使用类名。
    """

    def __init__(self, params: dict[str, Any], name: str | None = None):
        self.params = params
        self.name = name or self.__class__.__name__

    @abstractmethod
    def map_to_position(
        self,
        signals: pd.Series,
        market_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """将原始信号映射为目标仓位。

        Parameters
        ----------
        signals : pd.Series
            C-1 输出的原始信号，索引为 datetime。
        market_data : pd.DataFrame
            对应的行情数据，索引为 datetime。
            部分状态机可能需要行情信息（如 ATR 缩放）。

        Returns
        -------
        pd.DataFrame
            至少包含以下列:
            - target_position : float, 目标资金权重
            - signal_value    : float, 原始信号值 (shift 对齐后)
            - action_name     : str,   状态机动作名
            索引为 datetime (执行时间)。

        Notes
        -----
        ★ 极其关键：未来函数规避 ★
        T 日收盘价计算出的信号，只能指导 T+1 日的持仓状态。
        子类实现中务必在最终输出前执行 .shift(1) 操作。
        """
        ...

    @staticmethod
    def apply_shift(df: pd.DataFrame, shift_bars: int = 1) -> pd.DataFrame:
        """统一的 shift 工具，防止未来函数。

        将 target_position 和 signal_value 列整体延迟 `shift_bars` 根 bar,
        使信号在 T 日产生、T+1 日执行。
        """
        cols_to_shift = ["target_position", "signal_value"]
        for col in cols_to_shift:
            if col in df.columns:
                df[col] = df[col].shift(shift_bars)
        # 填充因 shift 产生的 NaN: 仓位默认空仓, 信号默认 0
        df["target_position"] = df["target_position"].fillna(0.0)
        df["signal_value"] = df["signal_value"].fillna(0.0)
        return df

    @staticmethod
    def debounce(df: pd.DataFrame) -> pd.DataFrame:
        """防抖处理：仅保留 target_position 发生变化的行。

        用于落盘前减少冗余指令，降低文件体积。
        注意：这是可选操作，完整时间序列版本也可直接交付。
        """
        mask = df["target_position"].diff().abs() > 1e-9
        mask.iloc[0] = True  # 保留第一行
        return df.loc[mask].copy()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, params={self.params})"
