from __future__ import annotations

"""回测配置快照（不可变 dataclass）：单标的 Backtrader 与多标的组合会计共用同一结构。

未使用的字段在对应模式下可忽略；完整语义见本目录 ``README.md`` 与 ``factor_layer/factor_engine/docs`` 下 ADR。"""
from dataclasses import dataclass, field
from typing import Literal

from workspace_paths import default_market_cache_root


PortfolioExecutionEngine = Literal["python", "numpy", "numba", "auto"]
MarketDataMode = Literal["data_root", "source_path", "aggregate_bars_daily_summary"]

_DEFAULT_AGGREGATE_COLUMNS = {
    "open": "o",
    "high": "h",
    "low": "l",
    "close": "c",
    "volume": "v",
}


@dataclass(frozen=True)
class BacktestConfig:
    """回测参数：会写入报告 ``summary["config"]``，便于复现与对比实验。"""

    # --- 单标的执行与费用（Backtrader 路径） ---
    initial_cash: float = 1_000_000.0
    commission: float = 0.0
    slippage_perc: float = 0.0
    rebalance_threshold: float = 1e-8
    enforce_target_bounds: bool = True
    metrics_profile: Literal["fast", "core", "standard", "industrial"] = "core"

    # --- 从磁盘加载 OHLCV（与 inline ohlcv 二选一；strict_real_data 时禁止 inline）---
    market_data_mode: MarketDataMode = "data_root"
    data_root: str = "/home/yluel/share/data/ibkr"
    source_path: str | None = None
    symbol: str | None = None
    frequency: Literal["1min", "5min", "15min", "30min", "1h", "1d"] | None = None
    prefer_parquet: bool = True
    max_rows: int | None = None
    strict_real_data: bool = False
    market_data_cache_root: str | None = field(default_factory=lambda: str(default_market_cache_root()))

    aggregate_bars_root: str | None = None
    aggregate_dataset: str = "daily_market_summary"
    aggregate_symbol_column: str = "ticker"
    aggregate_timestamp_column: str = "align_time"
    aggregate_columns: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_AGGREGATE_COLUMNS))

    strict_temporal_validation: bool = True

    # --- 单标的融资与无风险（摘要展示用；融券为事后近似）---
    allow_short: bool = True
    borrow_rate_annual: float = 0.0
    short_margin_requirement: float = 0.0
    risk_free_rate_annual: float = 0.0

    # --- 多标的组合：执行、成本、权重滞后（见 runner 与 ADR §9）---
    portfolio_mode: Literal["single", "multi"] = "single"
    portfolio_cost_model: Literal["simple_bps", "linear_impact", "square_impact"] = "simple_bps"
    portfolio_commission_bps: float = 0.0
    portfolio_spread_bps: float = 0.0
    portfolio_impact_coeff: float = 0.0
    portfolio_adv_participation_cap: float | None = None
    portfolio_min_trade_weight: float = 0.0
    portfolio_half_turnover: bool = True
    portfolio_execution_engine: PortfolioExecutionEngine = "python"

    include_trade_ledger: bool = False
    include_data_fingerprint: bool = True

    #: 单资产：在时间与行情索引对齐后，再按 bar 数向后推移目标仓位（pandas shift）。
    #: 0 = 不额外滞后；1 = 第 t 根 K 线使用的目标为原始序列在 t-1 的值（用于「信号在上一根收盘才可得」等约定）。
    #: 流水线若已自行对齐信号时点，应保持为 0。
    target_lag_bars: int = 0

    #: 多资产：收益上使用的持仓权重相对目标权重矩阵的滞后 bar 数。必须 >= 1，
    #: 表示用上一根（或更早）已确定权重去乘当期资产收益，避免用当期已知收益反推的权重。
    portfolio_weight_lag_bars: int = 1
