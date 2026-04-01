# 多因子策略构建与回测框架建议

这份文档不是对仓库现状的描述，而是面向下一阶段开发的工程化路线建议。

重点不是先讨论某个优化器或某个回测指标，而是先明确：

- 哪些中间结果必须落盘。
- 哪些配置必须快照。
- 哪些文件应该作为模块之间的正式接口。
- 未来多因子策略和回测框架应该如何通过文件流串起来。

## 1. 推荐的总体思路

建议把未来的主链拆成五段：

原始行情 / 基本面 parquet
→ 因子值文件
→ 多因子组合信号文件
→ 目标持仓文件
→ 回测执行与结果文件

这五段最好都能分别落盘，而不是只保留最终收益曲线。原因很直接：

- 因子值文件是研究复盘的基础资产。
- 组合信号文件体现的是“因子怎么合成 alpha”。
- 目标持仓文件体现的是“策略想持有什么”。
- 实际持仓文件体现的是“回测引擎最终真的持有什么”。
- 回测结果文件体现的是“这套持仓在给定成本、调仓频率和成交假设下表现如何”。

这里有一个工程上非常重要的区分：

- target_positions 是策略层输出。
- realized_holdings 是回测层输出。

这两个文件不要合并成一个，因为只要后面引入延迟成交、涨跌停、成交量约束、滑点或手续费，两者就一定会分叉。

## 2. 推荐的三条实现路径

### 2.1 路径 A：因子分数直接转目标权重，再做批处理回测

这是最适合先落地的路径，也是最推荐的起步方案。

核心流程：

因子值 parquet
→ 标准化 / 去极值 / 缺失值处理
→ 多因子加权合成 composite score
→ 按规则生成 target_positions.parquet
→ 用简化回测器按收盘调仓或次日开盘调仓
→ 输出收益率时间序列和汇总指标

特点：

- 实现速度最快。
- 足够支撑多因子选股、多空分层、TopK 组合、等权 / 分数权重等主流研究工作。
- 非常适合作为 MVP。

适合先支持的能力：

- 调仓频率：日频、周频、月频。
- 组合方式：等权、按分数归一化权重、TopK / BottomK。
- 中性化：先支持行业中性 / 市值中性中的一部分，后续再扩。
- 成本模型：固定单边费率 + 简单滑点。

### 2.2 路径 B：多因子分数先进入组合优化器，再生成目标持仓

这是路径 A 稳定之后的第二阶段。

核心流程：

因子值 parquet
→ composite score / alpha score
→ 风险暴露矩阵、行业暴露、基准权重、约束参数
→ optimizer
→ target_positions.parquet
→ 回测

特点：

- 更接近真实机构组合构建流程。
- 可以加入风格约束、行业约束、单票权重上限、换手约束、tracking error 等。
- 但如果在最开始就做，会显著拉高开发复杂度。

建议顺序：

- 先把路径 A 跑通。
- 等 target_positions 和回测结果文件契约稳定后，再把 optimizer 插进中间。

### 2.3 路径 C：目标持仓先转订单，再做成交与持仓仿真

这是更偏执行层的回测路径，建议放在第三阶段。

核心流程：

target_positions.parquet
→ orders.parquet
→ fills.parquet
→ realized_holdings.parquet
→ pnl / returns / attribution

特点：

- 能处理延迟成交、成交价模型、成交量上限、未成交订单、分批成交等问题。
- 更真实，但也更重。
- 如果在策略逻辑和组合构建尚未稳定时过早引入，工程复杂度会先把研究速度拖慢。

建议结论：

- 第一阶段优先做路径 A。
- 第二阶段补路径 B。
- 第三阶段再扩路径 C。

## 3. 文件流角度下，建议沉淀的核心中间产物

下面这些文件建议明确做成标准产物，而不是只在内存里传递。

| 产物 | 建议格式 | 建议位置 | 作用 |
| --- | --- | --- | --- |
| 因子定义文件 | YAML | factor_pool 或 factor_engine/configs | 描述单因子公式、频率、数据源、字段映射 |
| 因子值文件 | Parquet | factor_layer/factor_store/ | 保存单因子或一批因子的时序值 |
| universe 快照 | Parquet | strategy_layer/universe_store/ | 保存每个调仓点可交易股票池 |
| 组合信号文件 | Parquet | strategy_layer/signal_store/ | 保存多因子合成后的综合得分 |
| 目标持仓文件 | Parquet | strategy_layer/target_positions/ | 保存策略层想要的目标权重 / 目标股数 |
| 回测配置快照 | YAML | backtest_layer/runs/<run_id>/config_snapshot.yaml | 固化这次回测的成本、调仓、撮合和基准参数 |
| 实际持仓文件 | Parquet | backtest_layer/runs/<run_id>/holdings.parquet | 保存回测层实际持有的仓位 |
| 交易文件 | Parquet | backtest_layer/runs/<run_id>/trades.parquet | 保存调仓产生的交易明细 |
| 收益率序列文件 | Parquet 或 CSV | backtest_layer/runs/<run_id>/returns.parquet | 保存组合净值、收益率、成本、换手等时间序列 |
| 汇总指标文件 | JSON + CSV | backtest_layer/runs/<run_id>/metrics.json、summary.csv | 保存 Sharpe、回撤、年化收益等摘要指标 |
| 归因结果文件 | Parquet 或 CSV | backtest_layer/runs/<run_id>/attribution.parquet | 保存行业、因子、成本等归因结果 |
| 实验清单文件 | JSON | backtest_layer/runs/<run_id>/manifest.json | 记录上游文件路径、hash、git commit、运行时间 |

## 4. 建议优先标准化的文件契约

真正开始做工程之前，最好先把下面几个文件的列结构约定下来。

### 4.1 因子值文件

建议分成两层：

- 长表作为标准存储格式。
- 宽表作为单次策略运行的缓存格式。

推荐的长表列：

- timestamp
- instrument
- factor_name
- value
- universe_id
- asof_time

原因：

- 长表更适合持续追加新因子。
- 长表更容易做分区存储。
- 多因子策略运行时，再把一批长表拼成宽表 factor_panel.parquet，会更灵活。

### 4.2 组合信号文件

建议列：

- rebalance_ts
- instrument
- composite_score
- rank
- selected_flag
- signal_version

如果后面要做解释性分析，也可以额外保留：

- factor_1_zscore
- factor_2_zscore
- factor_3_zscore
- weight_factor_1
- weight_factor_2
- weight_factor_3

也就是让这个文件既能作为策略输入，又能用于事后解释为什么这只股票被选中。

### 4.3 目标持仓文件

这个文件非常关键，建议作为策略层和回测层之间的正式接口。

建议列：

- rebalance_ts
- instrument
- target_weight
- target_shares
- score
- side
- strategy_id
- portfolio_id

这里建议至少保留 target_weight，即使暂时还不做股数级仿真。因为权重接口是最稳定、最容易跨资产和跨频率复用的。

### 4.4 实际持仓文件

建议列：

- timestamp
- instrument
- actual_weight
- shares
- price
- market_value
- cash_after_rebalance
- gross_exposure
- net_exposure

这个文件的意义是：后续无论增加多少执行细节，分析层都只需要读 realized_holdings。

### 4.5 收益率序列文件

建议列：

- timestamp
- portfolio_return
- benchmark_return
- excess_return
- turnover
- transaction_cost
- gross_exposure
- net_exposure
- nav
- drawdown

注意：

- 时间序列文件只放逐时点数据。
- 汇总指标不要硬塞进这个文件里。
- 汇总指标单独写 metrics.json 或 summary.csv，会更干净。

## 5. 推荐的目录与 run 组织方式

当前 [backtest_layer](backtest_layer)、[strategy_layer](strategy_layer)、[factor_layer/factor_pool](factor_layer/factor_pool) 还是空目录，所以现在正好适合先按产物设计目录，而不是先被旧实现绑住。

一个比较稳妥的目录草案可以是：

```text
factor_layer/
  factor_pool/
    definitions/
    registries/
  factor_store/
    daily/
    minute/

strategy_layer/
  strategy_defs/
  signal_store/
  target_positions/
  universe_store/
  runs/

backtest_layer/
  configs/
  engine/
  analytics/
  runs/
    <run_id>/
      manifest.json
      config_snapshot.yaml
      factor_panel.parquet
      composite_signal.parquet
      target_positions.parquet
      holdings.parquet
      trades.parquet
      returns.parquet
      metrics.json
      summary.csv
      attribution.parquet
      report.html
```

这里最关键的不是目录名字本身，而是两个原则：

- 公共资产和单次运行产物分开。
- 每次回测都用 run_id 建独立目录。

也就是说：

- factor_store、universe_store 属于共享上游资产。
- runs/<run_id>/ 属于一次实验的不可变快照。

## 6. 推荐的主文件流

如果按工程化最小闭环来设计，未来的主文件流建议是：

1. 因子定义文件
   - 描述单因子公式、数据源、频率。
   - 输入给 Factor Engine 或因子 runner。

2. 因子 runner 产出因子值文件
   - 把每个因子的结果落成 parquet。
   - 不再只停留在内存中的 result dict。

3. 策略构建器读取多份因子值文件
   - 对齐 timestamp 和 instrument。
   - 做 winsorize、zscore、缺失值处理、方向统一。
   - 合成 composite signal。

4. 组合构建模块生成 target_positions.parquet
   - 决定持仓股票池。
   - 决定权重分配。
   - 决定调仓时点。

5. 回测引擎读取两类输入
   - target_positions.parquet。
   - backtest config snapshot。

6. 回测引擎再结合市场行情
   - 生成 holdings.parquet、trades.parquet、returns.parquet。

7. 分析模块读取 returns / holdings / trades
   - 生成 metrics.json、summary.csv、attribution.parquet、report.html。

这个设计的核心好处是：

- 任一阶段都可以单独复跑。
- 可以只替换组合构建逻辑，不动因子计算。
- 可以只替换成本模型，不动目标持仓文件。
- 可以做实验复现，因为 run 目录里有完整配置快照和上游引用记录。

## 7. 更推荐的最小 MVP 顺序

如果只从尽快做出可用的多因子策略框架出发，建议按下面顺序推进。

### 7.1 第一步：先给 Factor Engine 补一个结果落盘层

当前 [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py) 已经能算结果，但结果主要停留在内存里。

下一步最值得先做的是：

- 提供一个 factor runner。
- 输入：factor config YAML 或一批 factor definitions。
- 输出：标准化的 factor_value parquet。

也就是说，先把因子结果变成稳定文件资产这件事做出来。

### 7.2 第二步：做一个最简单的多因子组合构建器

建议先只支持：

- 读取多份 factor_value parquet。
- 对齐到同一个调仓时点。
- zscore 后线性加权。
- 取 TopK / BottomK。
- 输出 target_positions.parquet。

这个阶段先不要急着做复杂优化器。

### 7.3 第三步：做一个权重驱动型 backtester

先支持：

- 固定调仓频率。
- 用收盘价或次日开盘价成交。
- 单边手续费。
- 简单滑点。
- 输出 holdings、trades、returns、metrics。

只要这一步落成，整个仓库就第一次真正形成：

因子
→ 策略
→ 持仓
→ 回测
→ 结果

### 7.4 第四步：再补分析层

分析层建议借鉴 [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 当前已经落地的思路，把结果拆成：

- 时间序列结果。
- 汇总指标。
- 分层或分组结果。
- 成本前后对照结果。

可以先输出：

- 累计净值曲线。
- 年化收益 / 波动 / Sharpe。
- 最大回撤。
- 换手率。
- 成本拖累。
- 基准对比。
- 按行业或因子来源的归因。

### 7.5 第五步：最后再补优化器和执行仿真

也就是把路径 B、路径 C 插进去。

## 8. 从文件流出发，最值得坚持的几个工程原则

1. 不要只存最终回测结果，至少要存 raw factor values、target positions、realized holdings 三层文件。
2. 不要让回测直接重新计算因子，回测层应该消费已经冻结的因子文件。
3. 不要把所有参数散落在代码里，每次回测都要把配置快照写进 run 目录。
4. 不要只保存 summary 指标，必须同时保存完整收益率时间序列。
5. 不要让同一份文件同时承担研究输入和回测输出两种职责，信号、目标持仓、实际持仓要分文件。
6. 不要在一开始就做过重的事件驱动仿真，先把权重驱动的批处理框架做稳。

## 9. 一个建议的最终闭环

如果按上面的路线走，仓库未来比较理想的闭环会是：

原始数据 parquet
→ Factor Engine 产出因子值文件
→ Strategy Layer 产出 composite signal 和 target_positions
→ Backtest Layer 结合配置与市场数据产出 holdings / trades / returns
→ Analytics 产出 metrics / attribution / report

到那一步，这个仓库才会真正从因子研究工作区升级成可复现的多因子策略研究与回测工作区。
