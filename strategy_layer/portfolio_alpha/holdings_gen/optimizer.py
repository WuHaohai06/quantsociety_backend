from __future__ import annotations

import pandas as pd

from .config import OptimizerConfig


def apply_optimizer(
    holdings_df: pd.DataFrame,
    *,
    signal_frame: pd.DataFrame,
    config: OptimizerConfig,
) -> pd.DataFrame:
    if holdings_df.empty or not config.enabled or config.name == "noop":
        return holdings_df
    raise NotImplementedError(
        f"Optimizer '{config.name}' 尚未实现；当前预留了 signal_frame/config 接口，后续可在这里接组合优化器。"
    )