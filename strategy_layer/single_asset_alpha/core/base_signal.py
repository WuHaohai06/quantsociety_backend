"""
C-1 信号生成层抽象基类
======================

所有具体信号实现都必须继承 BaseSignalGenerator 并实现 generate() 方法。

核心约束:
  - 使用 Pandas 向量化操作 (.shift(), .rolling(), .ewm() 等)
  - 严禁在时间序列上写 for 循环
  - 输出为原始连续预测信号 (pd.Series)，值域不限定
  - 不包含仓位映射逻辑（仓位映射交由 C-2 模块处理）
"""

from __future__ import annotations

import pandas as pd
from abc import ABC, abstractmethod
from typing import Any


class BaseSignalGenerator(ABC):
    """信号生成器抽象基类。

    Parameters
    ----------
    params : dict
        信号参数字典，所有超参数（窗口期、权重等）均通过此字典传入，
        禁止在子类中硬编码 magic number。
    name : str, optional
        信号名称，默认使用类名。
    """

    def __init__(self, params: dict[str, Any], name: str | None = None):
        self.params = params
        self.name = name or self.__class__.__name__

    @abstractmethod
    def generate(
        self,
        market_data: pd.DataFrame,
        factor_data: pd.DataFrame | None = None,
    ) -> pd.Series:
        """生成原始预测信号。

        Parameters
        ----------
        market_data : pd.DataFrame
            单标的 OHLCV 行情数据，索引为 datetime。
            必须包含列: open, high, low, close, volume
        factor_data : pd.DataFrame, optional
            外部因子数据（来自陆殷世杰的因子库），索引为 datetime，
            列名为因子名。

        Returns
        -------
        pd.Series
            原始信号值，索引与 market_data 对齐。
            正值倾向看多，负值倾向看空，0 表示中性。

        Notes
        -----
        - 信号计算必须使用向量化操作
        - 输出信号不应包含未来信息
        - NaN 值保留，交由下游 PositionMapper 统一处理
        """
        ...

    def validate_market_data(self, market_data: pd.DataFrame) -> None:
        """校验行情数据基本格式。"""
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(market_data.columns)
        if missing:
            raise ValueError(
                f"[{self.name}] 行情数据缺少必要列: {missing}. "
                f"当前列: {list(market_data.columns)}"
            )
        # 与 factor_data 按索引对齐；若上游是整数索引，须先重采样为交易日 DatetimeIndex
        if not isinstance(market_data.index, pd.DatetimeIndex):
            raise TypeError(
                f"[{self.name}] 行情数据索引必须为 DatetimeIndex, "
                f"当前类型: {type(market_data.index)}"
            )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, params={self.params})"
