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
3. 按可配置的收益窗口计算逐资产未来收益。
4. 根据可交易约束过滤停牌、涨跌停或其他不可成交资产。
5. 计算组合收益、换手、交易成本、净值、回撤、胜率、风险收益指标等。
6. 输出标准化产物，供后续分析或准入评估使用。

更具体地说，这个类承担的是“把策略权重变成标准化回测产物”的工作，适合放在策略研究和策略准入之间做统一中间层。它除了计算最基础的收益曲线，还会同步产出：

- 逐日收益明细：毛收益、净收益、换手、交易成本、暴露、覆盖率、净值曲线。
- 指标明细：收益、波动、回撤、胜率、尾部风险、交易行为、数据有效性等。
- 摘要结果：适合快速浏览或入库的单行 summary。
- 元数据：本次运行的参数配置、输入规模、面板 shape、有效数据量等。

这个类有几个比较关键的设计点：

- 支持从长表输入自动透视成宽表，不要求你提前自己整理矩阵。
- 默认会把信号权重整体下移 1 期，避免未来函数。
- 收益窗口不是写死的，可以通过 `return_window` 控制，例如 1 日、5 日、10 日未来收益。
- 可以传入额外的 `tradable_df` 作为交易约束，屏蔽停牌、涨跌停、不可交易等资产。
- 可以选择性传入基准收益序列，自动计算超额收益、跟踪误差、信息比率、alpha/beta。

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

#### tradable_df

可选，用于描述每个交易日、每个标的是否允许交易。默认需要以下列：

- `trade_date`
- `symbol`
- `is_tradable`

这个表适合承载你提到的交易限制信息，例如：

- 停牌
- 涨停买不进
- 跌停卖不出
- 风险警示或临时不可交易状态

只要你能把这些约束最终整理成布尔列 `is_tradable`，这个类就会在收益计算前先把对应单元格过滤掉。

如果不传 `tradable_df`，类内部会退化为基于价格是否足够计算未来收益来判断“默认可交易”。这能处理缺失价格，但不能替代真实的停牌、涨跌停约束。

### 收益计算逻辑

类内部采用“未来 `return_window` 期收益”逻辑：

- 资产收益：`asset_return_t = close_{t+return_window} / close_t - 1`
- 为避免未来函数，输入权重宽表会先整体下移 1 行，即 `signal_weight_t -> execution_weight_{t+1}`
- 组合毛收益：`portfolio_return_t = sum_i(execution_weight_{t,i} * asset_return_{t,i})`

因此：

- 当 `return_window=1` 时，表示计算下一期收益，也就是最常见的 next-day return。
- 当 `return_window=5` 时，表示计算未来 5 期累计收益。
- 只要价格表中未来窗口对应的价格缺失，该资产该期收益就会被标记为无效。

交易成本按换手估算：

- `turnover_t = sum_i(abs(execution_weight_{t,i} - execution_weight_{t-1,i}))`
- `trading_cost_t = turnover_t * (fee_rate + slippage_rate)`
- `net_return_t = gross_return_t - trading_cost_t`

说明：

- 首日换手定义为首日权重绝对值之和。
- 对缺失的资产收益，内部会保留原始有效性掩码，并在收益聚合时将缺失值填为 `0.0`。
- 同时会计算持仓覆盖率，帮助判断数据有效性是否足够。

### 初始化参数

常用参数如下：

- 收益与成本参数：
- `annualization=252`：年化因子，用于把日频收益和波动率换算成年化指标。
- `return_window=1`：未来收益窗口长度，决定资产收益按多少期之后的价格计算。
- `fee_rate=0.0003`：手续费率。
- `slippage_rate=0.0002`：滑点率。
- 列名映射参数：
- `date_col="trade_date"`：持仓和行情中的日期列名。
- `symbol_col="symbol"`：持仓和行情中的标的列名。
- `weight_col="weight"`：持仓权重列名。
- `price_col="close"`：价格列名。
- 可交易约束参数：
- `tradable_df=None`：可选的交易约束长表，用于标记每个日期、每个标的是否可交易。
- `tradable_date_col="trade_date"`：可交易表中的日期列名。
- `tradable_symbol_col="symbol"`：可交易表中的标的列名。
- `tradable_flag_col="is_tradable"`：可交易布尔标记列名。
- 输出与归档参数：
- `output_root="./results"`：结果输出根目录。
- `strategy_name="default_strategy"`：策略名称，对应产物目录的策略层。
- 基准相关参数：
- `benchmark_df=None`：可选基准收益序列。
- `benchmark_date_col="trade_date"`：基准日期列名。
- `benchmark_return_col="benchmark_return"`：基准收益列名。

如果你的数据里已经有涨跌停、停牌、是否可成交等信息，推荐在进入回测前先整理成 `tradable_df` 再传给这个类；这样生成的收益、换手和覆盖率都会更接近真实可执行结果。

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

这里的产物目录是按“策略层 + 运行层”组织的：

- `output_root`：所有回测结果的总目录。
- `strategy_name`：策略级目录，用来归档同一个策略的多次回测结果。
- `run_name_or_timestamp`：单次运行目录，用来区分同一策略在不同参数、不同样本区间、不同时间下的具体一次回测。

例如：

```text
./results/
└── demo_strategy/
    ├── demo_run/
    ├── demo_run_v2/
    └── 20260403_153000/
```

这样设计的目的是避免不同回测批次互相覆盖，并且方便对同一策略做多版本横向比较。

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

如果上面的示例参数不变，那么产物会输出到：

```text
./results/demo_strategy/demo_run/
```

其中 `demo_strategy` 是策略名，`demo_run` 是本次运行名。

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

这里的 `artifact_dir` 应该传“某一次具体回测运行目录”，而不是只传策略目录。

正确示例：

```python
evaluator.evaluate("./results/demo_strategy/demo_run")
```

因为评估器会直接在这个目录下查找：

- `metrics.csv`
- `summary.csv`
- `metadata.json`

## 3. YAML 配置运行

现在这个目录已经补齐了和 `single_asset_alpha`、`multiple_factor_composite` 类似的配置驱动入口。

新增接口：

- `backtest_layer.portfolio_backtest.load_config(config_path)`：加载并校验 YAML。
- `backtest_layer.portfolio_backtest.run_from_config(config_path)`：读取输入表、运行回测、可选执行注册评估，并返回结构化结果。
- `backtest_layer/portfolio_backtest/run_from_config.py`：命令行入口。

### 配置文件结构

推荐使用如下结构：

```yaml
meta:
    strategy_name: demo_strategy
    run_name: demo_run
    description: optional

inputs:
    holdings:
        path: ./holdings.csv
    kline:
        path: ./kline.csv
    tradable:
        path: ./tradable.csv
    benchmark:
        path: ./benchmark.csv

columns:
    date_col: trade_date
    symbol_col: symbol
    weight_col: weight
    price_col: close
    tradable_date_col: trade_date
    tradable_symbol_col: symbol
    tradable_flag_col: is_tradable
    benchmark_date_col: trade_date
    benchmark_return_col: benchmark_return

backtest:
    annualization: 252
    return_window: 1
    fee_rate: 0.0003
    slippage_rate: 0.0002

output:
    output_root: ./results

registry:
    enabled: true
    min_trade_days: 120
    min_annual_return: 0.05
```

说明：

- 所有路径都按“相对配置文件所在目录”解析。
- `inputs.*.path` 既可以是单个文件，也可以是目录。
- 目录输入支持 `format: csv|parquet`、`recursive`、`glob`。
- `inputs.*.rename` 可以把上游字段改成回测器期望字段，适合直接接 `day_aggs` 一类数据。

### Python 用法

```python
from backtest_layer.portfolio_backtest import run_from_config

result = run_from_config("backtest_layer/portfolio_backtest/examples/mock_portfolio_backtest.yaml")

print(result["output_dir"])
print(result["backtest"]["summary_df"])
print(result["registry"])
```

返回结构里包含：

- `config`
- `holdings_df`
- `kline_df`
- `tradable_df`
- `benchmark_df`
- `backtest`
- `registry`
- `output_dir`
- `config_snapshot`

### CLI 用法

```bash
cd /home/yluel/share/projects/quantsociety_backend_project
python backtest_layer/portfolio_backtest/run_from_config.py \
    backtest_layer/portfolio_backtest/examples/mock_portfolio_backtest.yaml
```

CLI 会输出本次运行的：

- `output_dir`
- `config_snapshot`
- `summary`
- `registry_approved`

### Day Aggs 直连示例

如果 `kline_df` 来自清洗后的 `day_aggs`，可以直接在 YAML 里做列名适配：

```yaml
inputs:
    kline:
        path: /path/to/us_stocks_sip/day_aggs_v1
        format: parquet
        recursive: true
        rename:
            align_time: trade_date
            ticker: symbol
```

这样就不需要额外手工改列名，`run_from_config` 会在加载时统一处理。

### 示例配置

仓库内提供了一个最小可运行样例：

- `backtest_layer/portfolio_backtest/examples/mock_portfolio_backtest.yaml`

以及一个面向真实清洗行情目录的模板：

- `backtest_layer/portfolio_backtest/examples/us_stocks_sip_day_aggs_v1_template.yaml`

这个模板已经把 `kline` 指向当前真实的 `us_stocks_sip/day_aggs_v1` 清洗目录，并配置好了：

- 递归读取 `**/*.parquet`
- `align_time -> trade_date`
- `ticker -> symbol`

你只需要把 `holdings.path` 换成自己的组合持仓长表即可。

它直接消费当前目录下的：

- `mock_holdings.csv`
- `mock_kline.csv`

并把结果输出到：

- `results/demo_strategy/demo_run_from_config/`

这些文件都位于单次 run 目录中，而不是 `./results/demo_strategy/` 这种策略根目录中。

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
