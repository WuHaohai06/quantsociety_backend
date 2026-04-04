"""研究员 C → 研究员 D：与 ``single_asset_backtest`` 衔接。

实际跑回测时才会加载 Backtrader（见 ``backtest_bridge.run_pipeline_then_single_asset_backtest`` 内部 import）。
"""

from strategy_layer.single_asset_alpha.integration.backtest_bridge import (
    run_pipeline_then_single_asset_backtest,
    target_position_dataframe_to_backtest_input,
)

__all__ = [
    "run_pipeline_then_single_asset_backtest",
    "target_position_dataframe_to_backtest_input",
]
