"""研究员 C → 研究员 D：与 ``single_asset_backtest`` 衔接（可选依赖 Backtrader）。"""

from strategy_layer.single_asset_alpha.integration.backtest_bridge import (
    run_pipeline_then_single_asset_backtest,
    target_position_dataframe_to_backtest_input,
)

__all__ = [
    "run_pipeline_then_single_asset_backtest",
    "target_position_dataframe_to_backtest_input",
]
