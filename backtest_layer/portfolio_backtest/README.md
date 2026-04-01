# Portfolio Backtest

这个目录包含两个核心组件：

- `PortfolioBacktestArtifactBuilder`：把持仓长表和行情长表转换为宽表，生成组合收益序列、绩效指标和回测产物。
- `StrategyRegistryEvaluator`：读取回测产物，按一组准入规则对策略做注册评估。

两者的定位是分层的：

1. 先由 `PortfolioBacktestArtifactBuilder` 产出标准化回测结果。
2. 再由 `StrategyRegistryEvaluator` 基于这些结果做策略准入判断。

## 目录结构

当前目录下主要文件：

- `portfolio_backtest.py`：回测产物生成器。
- `strategy_registry.py`：策略注册评估器。
- `mock_holdings.csv`：示例持仓数据。
- `mock_kline.csv`：示例行情数据。

## 1. PortfolioBacktestArtifactBuilder

### 作用

`PortfolioBacktestArtifactBuilder` 用于把持仓数据和价格数据转换成统一的回测结果文件，核心流程包括：

1. 校验并清洗输入长表。
2. 将持仓和价格转换为按日期 x 标的组织的宽表。
3. 计算逐日资产收益和组合收益。
4. 计算换手、交易成本、净值、回撤、胜率、风险收益指标等。
5. 输出标准化产物，供后续分析或准入评估使用。

### 输入数据格式

#### holdings_df

默认要求包含以下列：

- `trade_date`：交易日
- `symbol`：标的代码
- `weight`：该日组合权重

说明：

- 输入是长表。
- 同一交易日、同一 `symbol` 如出现重复记录，会在宽表阶段按 `sum` 聚合权重。

#### kline_df

默认要求包含以下列：

- `trade_date`：交易日
- `symbol`：标的代码
- `close`：收盘价

说明：

- 输入也是长表。
- 同一交易日、同一 `symbol` 如有多条记录，会在宽表阶段按 `last` 取值。

#### benchmark_df

可选，用于生成基准相关指标。默认需要：

- `trade_date`
- `benchmark_return`

如果传入基准，结果中会额外生成：

- `benchmark_nav`
- `excess_return`
- `excess_nav`
- `tracking_error`
- `information_ratio`
- `beta`
- `alpha`

### 收益计算逻辑

类内部采用 next-day return 逻辑：

- 资产收益：`asset_return_t = close_{t+1} / close_t - 1`
- 组合毛收益：`portfolio_return_t = sum_i(weight_{t,i} * asset_return_{t,i})`

交易成本按换手估算：

- `turnover_t = sum_i(abs(weight_{t,i} - weight_{t-1,i}))`
- `trading_cost_t = turnover_t * (fee_rate + slippage_rate)`
- `net_return_t = gross_return_t - trading_cost_t`

说明：

- 首日换手定义为首日权重绝对值之和。
- 对缺失的资产收益，内部会保留原始有效性掩码，并在收益聚合时将缺失值填为 `0.0`。
- 同时会计算持仓覆盖率，帮助判断数据有效性是否足够。

### 初始化参数

常用参数如下：

- `annualization=252`：年化因子。
- `fee_rate=0.0003`：手续费率。
- `slippage_rate=0.0002`：滑点率。
- `date_col="trade_date"`：日期列名。
- `symbol_col="symbol"`：标的列名。
- `weight_col="weight"`：权重列名。
- `price_col="close"`：价格列名。
- `output_root="./results"`：结果输出根目录。
- `strategy_name="default_strategy"`：策略名称。
- `benchmark_df=None`：可选基准收益序列。
- `benchmark_date_col="trade_date"`：基准日期列名。
- `benchmark_return_col="benchmark_return"`：基准收益列名。

### 对外接口

#### `build(holdings_df, kline_df, run_name=None)`

执行完整回测产物生成流程。

返回值是一个字典，主要包含：

- `output_dir`
- `returns_path`
- `metrics_path`
- `summary_path`
- `metadata_path`
- `returns_df`
- `metrics_df`
- `summary_df`
- `metadata`

### 输出文件说明

输出目录结构如下：

```text
{output_root}/{strategy_name}/{run_name_or_timestamp}/
├── returns.csv
├── metrics.csv
├── summary.csv
└── metadata.json
```

#### returns.csv

逐日回测序列，通常包括：

- `trade_date`
- `gross_return`
- `net_return`
- `trading_cost`
- `turnover`
- `holdings_count`
- `long_exposure`
- `short_exposure`
- `net_exposure`
- `gross_exposure`
- `holding_cells`
- `valid_holding_cells`
- `asset_return_coverage`
- `nav_gross`
- `nav_net`

如果有基准，还会包含：

- `benchmark_return`
- `benchmark_nav`
- `excess_return`
- `excess_nav`
- `benchmark_drawdown`

并且会附加：

- `drawdown_net`
- `drawdown_gross`
- `is_win_day`
- `is_loss_day`

#### metrics.csv

按 `metric/value` 二列表输出的指标明细。当前实现覆盖的指标主要包括：

- 收益类：`total_return`、`gross_total_return`、`annual_return`、`gross_annual_return`
- 波动类：`annual_volatility`、`gross_annual_volatility`、`downside_volatility`
- 风险收益类：`sharpe`、`gross_sharpe`、`sortino`、`calmar`
- 回撤类：`max_drawdown`、`gross_max_drawdown`、`max_drawdown_duration`
- 胜率类：`daily_win_rate`、`weekly_win_rate`、`monthly_win_rate`
- 分布类：`avg_daily_return`、`median_daily_return`、`best_day`、`worst_day`
- 风险尾部类：`var_95`、`cvar_95`
- 交易行为类：`avg_turnover`、`median_turnover`、`max_turnover`
- 持仓暴露类：`avg_holding_count`、`avg_long_exposure`、`avg_short_exposure`、`avg_net_exposure`、`avg_gross_exposure`
- 成本类：`total_trading_cost`、`cost_drag`
- 稳定性类：`profit_loss_ratio`、`longest_win_streak`、`longest_loss_streak`
- 数据有效性类：`top5_day_pnl_contribution`、`effective_asset_return_ratio`、`avg_daily_asset_return_coverage`

如果启用了基准，还会增加：

- `benchmark_total_return`
- `excess_total_return`
- `excess_annual_return`
- `tracking_error`
- `information_ratio`
- `excess_sharpe`
- `beta`
- `alpha`

#### summary.csv

摘要表，适合快速浏览或落库。当前包含的核心字段有：

- `strategy_name`
- `trade_days`
- `total_return`
- `annual_return`
- `annual_volatility`
- `sharpe`
- `sortino`
- `calmar`
- `max_drawdown`
- `monthly_win_rate`
- `avg_turnover`
- `avg_holding_count`
- `avg_gross_exposure`
- `cost_drag`
- `top5_day_pnl_contribution`
- `effective_asset_return_ratio`
- `avg_daily_asset_return_coverage`

#### metadata.json

记录本次回测的参数和输入面板信息，主要包括：

- 策略名、运行名、生成时间
- 年化因子、费率、滑点率
- 字段映射配置
- 是否包含 benchmark
- 输入数据行数、时间范围、标的数量
- 宽表和对齐面板的 shape
- 非零持仓单元数、有效收益单元数

### 使用示例

```python
import pandas as pd

from portfolio_backtest import PortfolioBacktestArtifactBuilder


holdings_df = pd.read_csv("mock_holdings.csv")
kline_df = pd.read_csv("mock_kline.csv")

builder = PortfolioBacktestArtifactBuilder(
    annualization=252,
    fee_rate=0.0003,
    slippage_rate=0.0002,
    date_col="trade_date",
    symbol_col="symbol",
    weight_col="weight",
    price_col="close",
    output_root="./results",
    strategy_name="demo_strategy",
)

result = builder.build(
    holdings_df=holdings_df,
    kline_df=kline_df,
    run_name="demo_run",
)

print(result["output_dir"])
print(result["summary_df"])
```

### 适用场景

- 因子选股后的权重回测
- 多空组合的宽表收益归因前处理
- 统一生成策略评估产物
- 作为后续策略注册、策略池入库的标准输入

## 2. StrategyRegistryEvaluator

### 作用

`StrategyRegistryEvaluator` 不直接参与收益计算。它只读取 `PortfolioBacktestArtifactBuilder` 生成的产物目录，并根据预设规则判断该策略是否满足注册或准入要求。

它的目标是把“回测结果”转换为“是否可入库、是否可进入策略池”的结构化决策结果。

### 默认读取文件

在 `artifact_dir` 下默认读取：

- `metrics.csv`
- `summary.csv`
- `metadata.json`

如果任一文件不存在，会直接抛出 `FileNotFoundError`。

### 默认评估规则

初始化参数代表一组准入阈值，默认包括：

- `min_trade_days=120`
- `min_annual_return=0.05`
- `min_sharpe=0.8`
- `min_calmar=0.5`
- `max_drawdown_limit=-0.20`
- `max_annual_volatility=0.40`
- `min_monthly_win_rate=0.45`
- `max_turnover_mean=1.0`
- `min_effective_data_ratio=0.95`
- `max_top5_day_pnl_contribution=0.50`

这些规则主要覆盖四类问题：

- 样本是否足够：如 `trade_days`
- 收益风险比是否达标：如 `annual_return`、`sharpe`、`calmar`
- 风险是否可控：如 `max_drawdown`、`annual_volatility`
- 结果是否稳健：如 `avg_turnover`、`effective_asset_return_ratio`、`top5_day_pnl_contribution`

### 对外接口

#### `evaluate(artifact_dir)`

读取产物并输出评估结果。

返回字典包括：

- `registry_evaluation_path`
- `registry_evaluation_json_path`
- `registry_evaluation_df`
- `registry_evaluation_json`

### 输出文件说明

#### registry_evaluation.csv

逐条规则评估结果，字段包括：

- `rule_name`
- `actual_value`
- `threshold`
- `operator`
- `passed`
- `note`

最后会附加一行 `rule_name = __FINAL__`，用于给出：

- 通过规则数
- 总规则数
- 最终等级
- 最终是否批准

#### registry_evaluation.json

结构化评估结果，适合给上层系统或注册流程消费。主要包括：

- `strategy_name`
- `evaluation_time`
- `passed_rules`
- `total_rules`
- `pass_rate`
- `grade`
- `approved`
- `rules`
- `final_decision`
- `summary_snapshot`
- `metadata_snapshot`

### 评级逻辑

当前内置评级逻辑如下：

- `A`：通过率至少 90%，且 `sharpe >= 1.5`、`annual_return >= 0.15`、`max_drawdown >= -0.15`
- `B`：通过率至少 80%
- `C`：通过率至少 60%
- `D`：其余情况

最终 `__FINAL__` 行中，只有 `A` 或 `B` 会被视为 `approved=True`。

### 使用示例

```python
from strategy_registry import StrategyRegistryEvaluator


evaluator = StrategyRegistryEvaluator(
    min_trade_days=120,
    min_annual_return=0.05,
    min_sharpe=0.8,
)

result = evaluator.evaluate("./results/demo_strategy/demo_run")

print(result["registry_evaluation_df"])
print(result["registry_evaluation_json"])
```

## 推荐工作流

```python
import pandas as pd

from portfolio_backtest import PortfolioBacktestArtifactBuilder
from strategy_registry import StrategyRegistryEvaluator


holdings_df = pd.read_csv("mock_holdings.csv")
kline_df = pd.read_csv("mock_kline.csv")

builder = PortfolioBacktestArtifactBuilder(strategy_name="demo_strategy")
build_result = builder.build(holdings_df, kline_df, run_name="demo_run")

evaluator = StrategyRegistryEvaluator()
registry_result = evaluator.evaluate(build_result["output_dir"])
```

这个工作流适合：

1. 先统一生成标准回测产物。
2. 再用统一阈值进行策略准入。
3. 最后把通过的策略纳入注册表或策略池。

## 注意事项

- 当前收益定义是基于 `t -> t+1` 的 next-day close return，不是当日收盘到当日收盘收益。
- 权重和价格会先对齐日期与标的全集，因此缺失数据不会直接报错，但会反映到覆盖率指标中。
- 成本模型目前是简单线性成本模型：`fee_rate + slippage_rate` 乘以换手。
- `StrategyRegistryEvaluator` 依赖 `metrics.csv` 中的指标命名，如果后续修改指标名，需要同步调整评估逻辑。
- `summary.csv` 主要用于摘要展示，真正的准入判断主要依赖 `metrics.csv`。

## 最小实践建议

- 在接入真实策略前，先用目录中的 `mock_holdings.csv` 和 `mock_kline.csv` 做一次冒烟测试。
- 如果你的持仓是多空权重，建议重点检查 `gross_exposure`、`net_exposure` 和 `avg_turnover`。
- 如果行情覆盖不完整，优先关注 `effective_asset_return_ratio` 和 `avg_daily_asset_return_coverage`。
- 如果想把这个模块接入更大的策略工厂流程，建议把 `output_dir` 作为标准回测产物目录向后传递。