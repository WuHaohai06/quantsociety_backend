# 前端对接说明

这份文档面向前端同事，目标是快速回答 4 个问题：

1. 这个仓库当前有哪些可以对接的主流程。
2. 每条流程的文件流是什么，结果落在哪里。
3. 各阶段怎么通过 CLI 运行。
4. 常见配置文件长什么样，前端展示时应该关心哪些字段。

## 1. 先说结论

当前仓库更适合做“文件型集成”，而不是直接做 HTTP API 集成。

也就是说，当前最稳定的对接对象不是接口返回，而是 `workspace_data/` 下的标准化产物：

- `pipeline_summary.json`
- `summary.json`
- `returns.csv`
- `metrics.csv`
- 若需要更细的数据，再读取或转换 `parquet`

前端如果只是先把页面搭起来，建议优先围绕两条 demo 主链做：

1. 多因子组合全链路：`demo/all_pipeline_demo/`
2. 单资产择时全链路：`demo/all_pipeline_single_asset_demo/`

## 2. 当前推荐前端对接方式

### 2.1 文件型集成优先

当前项目已经有比较稳定的落盘约定，但还没有统一的 API server。因此前端现阶段最适合对接的是“后端先产出文件，前端或中间层再读取这些文件”。

推荐顺序：

1. 先读 demo 级 `pipeline_summary.json`
2. 再按 `pipeline_summary.json` 里的路径，读取下游 `summary / returns / metrics`
3. 对 `parquet` 文件，由后端或中间层转成 JSON 再给前端

### 2.2 `workspace_data/` 是默认产物根目录

当前新流程默认把产物写到 `workspace_data/`，相关默认路径由 `workspace_paths.py` 管理。

主要约定如下：

| 路径 | 作用 |
| --- | --- |
| `workspace_data/demos/` | demo 输入、配置快照、summary |
| `workspace_data/factors/lake/` | factor lake 和评估结果 |
| `workspace_data/strategy/` | composite signal、holdings、single_asset_alpha 输出 |
| `workspace_data/backtests/` | 单资产和组合回测结果 |
| `workspace_data/cache/` | 行情缓存和中间缓存 |

如果需要改根目录，可以通过环境变量：

- `QUANTSOCIETY_WORKSPACE_DATA_ROOT`
- `FACTOR_LAKE_ROOT`

## 3. 项目总览

前端同事主要需要认识这 5 层：

| 层 | 目录 | 作用 |
| --- | --- | --- |
| 数据层 | `raw_data_layer/` | 抓取原始数据、清洗数据 |
| 因子层 | `factor_layer/` | 生成因子、评估因子、准入因子 |
| 策略层 | `strategy_layer/` | 把因子变成 signal、holdings 或 `target_position` |
| 回测层 | `backtest_layer/` | 把 signal/holdings 变成回测结果 |
| 演示层 | `demo/` | 端到端 demo、notebook、最适合前端先对接 |

## 4. 流程一：多因子组合全链路

这条链路对应：

- `demo/all_pipeline_demo/run_all_pipeline_demo.py`

### 4.1 流程图

```text
mock market data
-> factor_engine
-> factor_evaluation
-> factor_admission
-> multiple_factor_composite
-> holdings_gen
-> portfolio_backtest
-> pipeline_summary.json
```

### 4.2 文件流

| 阶段 | 模块 | 输入 | 输出 | 前端优先关注 |
| --- | --- | --- | --- | --- |
| 1 | demo runner | mock 参数 | `workspace_data/demos/all_pipeline_demo/inputs/mock_kline.parquet` | 一般不直接展示 |
| 2 | factor_engine | factor YAML + kline parquet | factor lake 分区 | 可做“因子已物化”状态展示 |
| 3 | factor_evaluation | 因子值 + 市场价格 | `summary.csv`、`summary.json`、`daily_ic.parquet` 等 | 因子评估表格 |
| 4 | factor_admission | evaluation summary | approve / reject 决策 + catalog 记录 | 准入状态卡片 |
| 5 | composite | factor lake | `composite_signal.parquet` | 信号预览 |
| 6 | holdings_gen | composite signal | `holdings.parquet` | 持仓预览 |
| 7 | portfolio_backtest | holdings + kline | `returns.csv`、`metrics.csv`、`summary.csv`、`metadata.json` | 净值曲线、指标面板 |
| 8 | demo 汇总 | 上述所有产物 | `workspace_data/demos/all_pipeline_demo/reports/pipeline_summary.json` | 前端总入口 |

### 4.3 多因子 demo 的关键文件

最推荐前端直接消费：

- `workspace_data/demos/all_pipeline_demo/reports/pipeline_summary.json`
- `workspace_data/backtests/portfolio/all_pipeline_strategy/e2e_demo/returns.csv`
- `workspace_data/backtests/portfolio/all_pipeline_strategy/e2e_demo/metrics.csv`
- `workspace_data/backtests/portfolio/all_pipeline_strategy/e2e_demo/summary.csv`

如果需要更细阶段数据：

- `workspace_data/strategy/composite_signals/all_pipeline_signal_v1/signals/composite_signal.parquet`
- `workspace_data/strategy/holdings/all_pipeline_holdings_v1/holdings/holdings.parquet`
- `workspace_data/factors/lake/evaluations/.../summary.csv`

### 4.4 `pipeline_summary.json` 里有什么

多因子 demo 的 summary 顶层结构包括：

- `paths`
- `inputs`
- `factor_engine`
- `factor_evaluations`
- `factor_admissions`
- `composite`
- `holdings`
- `backtest`

前端最常用字段：

| 字段 | 用途 |
| --- | --- |
| `factor_evaluations[].summary` | 因子评估表格 |
| `factor_admissions[]` | 因子准入状态 |
| `composite.rows` | 信号生成结果量级 |
| `holdings.summary` | holdings 摘要 |
| `backtest.summary` | 回测汇总卡片 |
| `backtest.returns_path` / `metrics_path` | 后续图表和指标数据源 |

## 5. 流程二：单资产择时全链路

这条链路对应：

- `demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py`

### 5.1 流程图

```text
mock single-asset OHLCV
-> factor_engine
-> single_asset_alpha
-> single_asset_backtest
-> pipeline_summary.json
```

### 5.2 文件流

| 阶段 | 模块 | 输入 | 输出 | 前端优先关注 |
| --- | --- | --- | --- | --- |
| 1 | demo runner | mock 参数 | `workspace_data/demos/single_asset_pipeline_demo/inputs/mock_single_asset_ohlcv.parquet` | 一般不直接展示 |
| 2 | factor_engine | factor YAML + day_aggs parquet | factor lake 分区 | 因子物化状态 |
| 3 | single_asset_alpha | 市场数据 + factor lake | `target_position` parquet、config snapshot | 信号 / 目标仓位图 |
| 4 | single_asset_backtest | OHLCV + `target_position` | `returns.csv`、`metrics.csv`、`summary.json`、`metadata.json` | 单资产回测图表 |
| 5 | demo 汇总 | 上述所有产物 | `workspace_data/demos/single_asset_pipeline_demo/reports/pipeline_summary.json` | 前端总入口 |

### 5.3 单资产 demo 的关键文件

最推荐前端直接消费：

- `workspace_data/demos/single_asset_pipeline_demo/reports/pipeline_summary.json`
- `workspace_data/backtests/single_asset/single_asset_factor_timing/e2e_demo/returns.csv`
- `workspace_data/backtests/single_asset/single_asset_factor_timing/e2e_demo/metrics.csv`
- `workspace_data/backtests/single_asset/single_asset_factor_timing/e2e_demo/summary.json`

如果需要更细阶段数据：

- `workspace_data/strategy/single_asset_alpha/single_asset_pipeline_factor_timing_v1/SINGLE_DEMO_target_position_full.parquet`
- `workspace_data/demos/single_asset_pipeline_demo/reports/factor_frame.parquet`

### 5.4 `pipeline_summary.json` 里有什么

单资产 demo 的 summary 顶层结构包括：

- `paths`
- `inputs`
- `factor_engine`
- `alpha`
- `backtest`

前端最常用字段：

| 字段 | 用途 |
| --- | --- |
| `alpha.factor_columns` | 因子列表 |
| `alpha.target_position_rows` | 目标仓位数据量 |
| `alpha.target_position_path` | 目标仓位数据源 |
| `backtest.summary` | 回测汇总卡片 |
| `backtest.metrics` | 回测指标摘要 |
| `backtest.outputs.returns` | 净值曲线和仓位曲线数据源 |

## 6. 前端最关心的文件格式

### 6.1 JSON

最适合作为页面总入口。

常见文件：

- `pipeline_summary.json`
- 单资产回测的 `summary.json`
- portfolio backtest 的 `metadata.json`

适合展示：

- 概览页
- 状态页
- 卡片式指标
- 结果目录导航

### 6.2 CSV

最适合作为表格和折线图数据源。

常见文件：

- `returns.csv`
- `metrics.csv`
- factor evaluation 的 `summary.csv`

适合展示：

- 净值曲线
- 收益序列
- 指标表
- 因子评估总表

### 6.3 Parquet

适合做中间层或后端读取，不建议前端浏览器直接作为首选数据源。

常见文件：

- `composite_signal.parquet`
- `holdings.parquet`
- `target_position.parquet`
- `factor_frame.parquet`

建议：

如果前端要展示这些明细数据，优先由 Python 中间层把 parquet 转成 JSON，再交给前端。

## 7. CLI 速查表

### 7.1 最推荐前端联调时直接跑的命令

```bash
python demo/all_pipeline_demo/run_all_pipeline_demo.py
python demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py
```

如果只是做 smoke test：

```bash
pytest demo/all_pipeline_demo/test_all_pipeline_demo.py -q
pytest demo/all_pipeline_single_asset_demo/test_single_asset_pipeline_demo.py -q
```

### 7.2 分阶段 CLI

| 模块 | 命令 | CLI 输出 |
| --- | --- | --- |
| factor_evaluation | `python factor_layer/factor_evaluation/run_from_config.py <config.yaml>` | `factor_id`、`run_id`、`output_dir` |
| factor_admission | `python factor_layer/factor_admission/run_from_config.py <config.yaml>` | `factor_id`、`run_id`、`decision` |
| multiple_factor_composite | `python strategy_layer/portfolio_alpha/multiple_factor_composite/run_from_config.py <config.yaml>` | `signal_rows`、`outputs` |
| holdings_gen | `python strategy_layer/portfolio_alpha/holdings_gen/run_from_config.py <config.yaml>` | `holdings_rows`、`summary`、`outputs` |
| portfolio_backtest | `python backtest_layer/portfolio_backtest/run_from_config.py <config.yaml>` | `output_dir`、`config_snapshot`、`summary` |
| single_asset_alpha | `python strategy_layer/single_asset_alpha/run_from_config.py <config.yaml>` | `rows`、`output_dir`、`factor_columns` |

说明：

这些 CLI 大多会打印 JSON 摘要，前端同事如果需要本地联调，也可以先通过终端确认产物目录是否生成成功。

## 8. 配置文件的统一理解方式

虽然每个模块的 YAML 结构不同，但整体上都遵循“元信息 + 输入源 + 运行参数 + 输出约定”的模式。

### 8.1 常见顶层字段

| 字段 | 常见含义 |
| --- | --- |
| `meta` | 任务 ID、版本、描述、run 名称 |
| `source` / `inputs` | 输入数据文件或目录 |
| `run` | 时间区间、horizon、quantile、方向等运行参数 |
| `composition` / `construction` | 信号合成或持仓构建规则 |
| `backtest` | 回测参数 |
| `output` | 输出格式、是否保存全量结果 |

### 8.2 因子计算配置：factor_engine

核心结构：

```yaml
factor:
  name: close_mom_3
  expr: ts_mom(col("close"), 3)
  freq: 1d

data_source:
  type: parquet_kline
  root: /path/to/day_aggs_v1
  instrument_column: ticker
  timestamp_column: window_start
  fields:
    close: close

backend:
  type: pandas

engine:
  enable_cache: true

materialization:
  factor_id: single_asset_mom_3_v1
```

前端需要知道的是：

- `factor.name` 是显示名
- `materialization.factor_id` 是落盘后的真正因子 ID
- `data_source.root` 指向因子输入数据源

### 8.3 因子评估配置：factor_evaluation

核心结构：

```yaml
meta:
  factor_id: all_pipeline_close_rank_v1
  run_name: all_pipeline_eval
  primary_horizon: 1

source:
  market_data_path: /path/to/mock_kline.parquet
  market_timestamp_col: trade_date
  market_symbol_col: symbol
  market_price_col: open

run:
  start: 2024-01-02
  end: 2024-01-25
  horizons: [1, 3, 5]
  n_quantiles: 4
```

前端需要知道的是：

- `factor_id` 和评估结果目录强相关
- `run.horizons` 决定 summary 里会出现哪些 horizon 结果

### 8.4 因子准入配置：factor_admission

核心结构：

```yaml
meta:
  factor_id: all_pipeline_close_rank_v1
  run_id: all_pipeline_eval

decision:
  mode: rule_based
  decided_by: all_pipeline_demo
  policy_name: all_pipeline_demo_policy
  primary_horizon: 1
  thresholds:
    min_rank_ic_mean: 0.90
    min_long_short_total_return: 0.0
```

前端需要知道的是：

- 这里的核心是 `decision.thresholds`
- 页面展示时可把它理解成“准入规则”和“最终结果”的来源

### 8.5 组合信号配置：multiple_factor_composite

核心结构：

```yaml
meta:
  signal_id: all_pipeline_signal
  version: v1

source:
  start: 2024-01-02
  end: 2024-01-25
  align_method: outer

factors:
  - factor_id: all_pipeline_close_rank_v1
    alias: close_rank
  - factor_id: all_pipeline_volume_rank_v1
    alias: volume_rank

composition:
  weighting:
    method: equal
  final_transform: rank
  long_top_k: 2
```

前端需要知道的是：

- `signal_id + version` 决定输出目录名
- `factors[]` 是组合输入因子列表
- `composition` 决定策略规则摘要

### 8.6 持仓配置：holdings_gen

核心结构：

```yaml
meta:
  portfolio_id: all_pipeline_holdings
  version: v1

inputs:
  signal:
    path: /path/to/composite_signal.parquet
    score_col: composite_score
    selected_flag_col: selected_flag
    side_col: side

construction:
  selection_mode: selected_flag
  weighting_method: equal
  long_budget: 1.0
  short_budget: 0.0
```

前端需要知道的是：

- `portfolio_id + version` 决定 holdings 输出目录
- `construction` 描述的是持仓构建逻辑，不是回测逻辑

### 8.7 单资产策略配置：single_asset_alpha

核心结构：

```yaml
meta:
  strategy_id: single_asset_pipeline_factor_timing
  version: v1

instrument:
  symbol: SINGLE_DEMO

market_data:
  mode: source_path
  source_path: /path/to/mock_single_asset_ohlcv.parquet
  freq: 1d

factor_source:
  mode: factor_lake
  factor_refs:
    - factor_id: single_asset_mom_3_v1
      alias: mom_3

signal:
  type: factor_threshold
  params:
    factor_names: [mom_3, gap_5, vol_delta_2]

position_mapper:
  type: threshold
  params:
    long_entry_threshold: 0.18
    long_exit_threshold: -0.04
    position_size: 0.99
    shift_bars: 1
```

前端需要知道的是：

- `strategy_id + version` 决定单资产 alpha 输出目录
- `signal` 决定信号如何生成
- `position_mapper` 决定信号如何变成 `target_position`

### 8.8 回测配置

#### 单资产回测

```yaml
initial_cash: 100000.0
commission: 0.001
slippage_perc: 0.0
target_lag_bars: 0
metrics_profile: core
allow_short: false
symbol: SINGLE_DEMO
frequency: 1d
```

#### 组合回测

```yaml
meta:
  strategy_name: all_pipeline_strategy
  run_name: e2e_demo

inputs:
  holdings:
    path: /path/to/holdings.parquet
  kline:
    path: /path/to/mock_kline.parquet

columns:
  date_col: trade_date
  symbol_col: symbol
  weight_col: weight
  price_col: close

backtest:
  annualization: 252
  return_window: 1
  fee_rate: 0.0003
  slippage_rate: 0.0002
```

前端需要知道的是：

- 组合回测更像“读持仓和价格后生成标准产物”
- 单资产回测更像“读 `target_position` 后生成标准产物”

## 9. 前端页面可以怎样映射这些文件

### 9.1 概览页

数据源：`pipeline_summary.json`

建议展示：

- 当前流程执行成功与否
- 每个 stage 的产物路径
- demo 名称、时间区间、样本长度
- 因子数、symbol 数、最终回测收益

### 9.2 因子评估页

数据源：

- `factor_evaluations[].summary`
- `summary.csv`

建议展示：

- IC / RankIC
- long-short total return
- 每个因子的 admission 状态

### 9.3 信号 / 持仓页

数据源：

- `composite_signal.parquet`
- `holdings.parquet`
- `target_position.parquet`

建议：

这些文件建议先由 Python 中间层转 JSON，再给前端。

### 9.4 回测页

数据源：

- `returns.csv`
- `metrics.csv`
- `summary.json` 或 `summary.csv`

建议展示：

- 净值曲线
- period return 序列
- realized position / target position
- 回测指标表

## 10. 当前限制与建议

### 10.1 当前限制

- 还没有统一的 HTTP API 层
- 很多中间产物是 parquet，不适合浏览器直接消费
- 不同模块已有统一趋势，但仍然是“文件型流水线”而不是“服务型流水线”

### 10.2 建议的对接策略

最实用的做法是：

1. 先用 demo 跑出标准产物
2. 以前端最需要的 JSON / CSV 为第一批对接对象
3. 对 parquet 加一个轻量 Python adapter 层
4. 前端先把页面和数据契约稳定下来，再考虑抽象成 API

## 11. 最后给前端同事的一句话

这个仓库当前最适合对接的不是“接口”，而是“标准化落盘文件”。

如果只做第一版联调，请直接从下面两个文件开始：

- `workspace_data/demos/all_pipeline_demo/reports/pipeline_summary.json`
- `workspace_data/demos/single_asset_pipeline_demo/reports/pipeline_summary.json`

它们已经能把流程、产物路径和最终结果全部串起来。