"""
target_position 数据契约 (Schema)
=================================

这是研究员 C 向研究员 D 交付的唯一正式凭证。
Schema 一经冻结，任何变更均需同时通知研究员 D (孙海崴) 和研究员 A (吴浩海)。

字段定义:
┌──────────────────┬───────────┬──────────────────────────────────────────────────────┐
│ 字段名           │ 数据类型  │ 业务规范说明                                         │
├──────────────────┼───────────┼──────────────────────────────────────────────────────┤
│ timestamp        │ datetime  │ 指令执行时间（T+1 开盘），与 D 明确为执行时间        │
│ symbol           │ string    │ 标的代码，全局对齐 (如 000001.SZ 或 BTC-USDT)        │
│ target_position  │ float     │ 目标资金权重: 1.0 满仓多, -1.0 满仓空, 0.0 空仓     │
│ signal_value     │ float     │ (可选) 原始信号值，供归因分析                        │
│ action_name      │ string    │ (可选) 状态机动作名 (ENTRY_LONG/EXIT_LONG/...)       │
└──────────────────┴───────────┴──────────────────────────────────────────────────────┘

标准动作名枚举:
    HOLD          — 维持当前仓位
    ENTRY_LONG    — 开多
    EXIT_LONG     — 平多
    ENTRY_SHORT   — 开空
    EXIT_SHORT    — 平空
    STOP_LOSS     — 止损
    TAKE_PROFIT   — 止盈
"""

from __future__ import annotations

import pandas as pd
from enum import Enum
from dataclasses import dataclass
from typing import Literal


class ActionName(str, Enum):
    """标准动作名枚举。"""
    HOLD = "HOLD"
    ENTRY_LONG = "ENTRY_LONG"
    EXIT_LONG = "EXIT_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT_SHORT = "EXIT_SHORT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


@dataclass(frozen=True)
class TargetPositionSchema:
    """target_position 数据契约定义。"""

    REQUIRED_COLUMNS = ("timestamp", "symbol", "target_position")
    OPTIONAL_COLUMNS = ("signal_value", "action_name")
    ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

    # 目标仓位值域
    POSITION_MIN: float = -1.0
    POSITION_MAX: float = 1.0

    @staticmethod
    def validate(df: pd.DataFrame, strict: bool = True) -> list[str]:
        """校验 DataFrame 是否符合 target_position Schema。

        Parameters
        ----------
        df : pd.DataFrame
            待校验的目标仓位数据。
        strict : bool
            严格模式下会检查值域；宽松模式仅检查列存在性。

        Returns
        -------
        list[str]
            校验错误列表，空列表表示通过。
        """
        errors = []

        # 1. 必要列检查
        for col in TargetPositionSchema.REQUIRED_COLUMNS:
            if col not in df.columns:
                errors.append(f"缺少必要列: {col}")

        if errors:
            return errors  # 必要列缺失则不再继续

        # 2. 类型检查
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            errors.append(
                f"timestamp 列类型错误: 期望 datetime, "
                f"实际 {df['timestamp'].dtype}"
            )

        if not pd.api.types.is_float_dtype(df["target_position"]):
            # 此处仅探测能否转 float，不原地改传入的 df（调用方若需清洗应自行 astype）
            try:
                df["target_position"].astype(float)
            except (ValueError, TypeError):
                errors.append(
                    f"target_position 列无法转换为 float: "
                    f"实际 {df['target_position'].dtype}"
                )

        # 3. 严格模式：值域检查
        if strict:
            tp = df["target_position"].dropna()
            if (tp < TargetPositionSchema.POSITION_MIN).any():
                errors.append(
                    f"target_position 存在低于 {TargetPositionSchema.POSITION_MIN} 的值"
                )
            if (tp > TargetPositionSchema.POSITION_MAX).any():
                errors.append(
                    f"target_position 存在高于 {TargetPositionSchema.POSITION_MAX} 的值"
                )

        # 4. NaN：交付给 D 前应在 C 侧 ffill/填 0；此处报错便于早发现脏数据
        nan_count = df["target_position"].isna().sum()
        if nan_count > 0:
            errors.append(f"target_position 包含 {nan_count} 个 NaN 值")

        return errors

    @staticmethod
    def format_output(
        df: pd.DataFrame,
        symbol: str,
        include_optional: bool = True,
    ) -> pd.DataFrame:
        """将内部 DataFrame 格式化为标准 target_position 输出。

        Parameters
        ----------
        df : pd.DataFrame
            内部计算结果，索引为 datetime，
            至少包含 target_position 列。
        symbol : str
            标的代码。
        include_optional : bool
            是否包含可选列（signal_value, action_name）。

        Returns
        -------
        pd.DataFrame
            符合 Schema 的标准输出。
        """
        output = pd.DataFrame()
        output["timestamp"] = df.index  # 由「索引=bar 时间」展开成长表，便于落盘与跨系统对齐
        output["symbol"] = symbol

        output["target_position"] = df["target_position"].values

        if include_optional:
            if "signal_value" in df.columns:
                output["signal_value"] = df["signal_value"].values
            else:
                # 无原始信号时填 0，避免下游读 parquet 缺列
                output["signal_value"] = 0.0

            if "action_name" in df.columns:
                output["action_name"] = df["action_name"].values
            else:
                output["action_name"] = ActionName.HOLD.value

        output = output.reset_index(drop=True)
        return output
