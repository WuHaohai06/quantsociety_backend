# 策略与回测任务清单

这份清单面向团队排期和分工使用，默认前提是：

- 当前仓库已经完成了原始数据落地。
- 当前仓库已经具备因子计算能力。
- 当前工作流的稳定产出可以视为“可用数据目录 + 可计算因子值”。

也就是说，可以把当前状态理解为：

原始数据
→ 标准化 parquet 数据目录
→ 因子定义 / 因子表达式
→ 因子值

从这里往后，后续开发建议拆成两条路径：

- 路径 A：多因子投资组合。
- 路径 B：单标的择时 + Backtrader 执行回测。

这个理解整体是对的，但有一个工程化上的补充：

- 不论走哪条路径，下一步都不应该直接写“最终回测器”。
- 两条路径都应该先补齐中间产物层，尤其是信号文件、目标仓位文件、配置快照和结果文件。

## 1. 当前工作流产出与下一阶段分叉点

### 当前工作流主产出

| 资产 | 当前状态 | 主要来源 |
| --- | --- | --- |
| 原始 / 清洗后 parquet 数据 | 已具备 | [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py)、[raw_data_layer/raw_data_fetching/download_all_history.py](raw_data_layer/raw_data_fetching/download_all_history.py) |
| 可运行的因子表达与配置 | 已具备 | [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py)、[factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) |
| 单因子评估与统计口径 | 已具备 | [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) |
| 多因子组合层 | 未实现 | [strategy_layer](strategy_layer) 当前为空 |
| 通用回测执行层 | 未实现 | [backtest_layer](backtest_layer) 当前为空 |

### 下一阶段分叉

从团队任务上，建议从这里开始拆成三段：

1. 公共基础层。
2. 多因子投资组合路径。
3. 单标的择时路径。

其中公共基础层要优先做，因为两条路径都会复用。

## 2. 公共基础层任务

### T0. 数据契约冻结

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 明确后续策略与回测层统一消费的数据列名、时间字段、标的字段和价格字段。 |
| 工作流输入 | 已落地的 parquet 数据目录；现有因子配置和 engine 示例。 |
| 工作流输出 | 一份数据契约文档；可选一份标准字段映射 YAML。 |
| 可复用模块 / 工具 | [raw_data_layer/raw_data_fetching/validate_parquet.py](raw_data_layer/raw_data_fetching/validate_parquet.py)、[factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) |
| 大致任务内容 | 统一 timestamp、instrument、open、high、low、close、volume 等字段；约定日频和分钟频单标的 / 多标的输入格式。 |
| 备注 | 这是后续所有模块的前置条件；字段名不要在多个模块里各自定义。 |

### T1. 因子值落盘层

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把当前主要停留在内存里的因子结果，正式落成标准化因子值文件。 |
| 工作流输入 | 因子定义 YAML 或 Python 因子定义；标准数据目录。 |
| 工作流输出 | factor_value parquet；可选 manifest 文件。 |
| 可复用模块 / 工具 | [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py)、[factor_layer/factor_engine/runtime/config.py](factor_layer/factor_engine/runtime/config.py)、[factor_layer/factor_engine/storage/factory.py](factor_layer/factor_engine/storage/factory.py) |
| 大致任务内容 | 实现一个 factor runner，读取一份或一批配置，运行后把结果以长表或宽表形式落盘。 |
| 备注 | 这是多因子路径和单标的路径的共同上游资产；建议优先做。 |

### T2. 回测 run 目录标准

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 统一一次实验的输出目录和文件命名，避免后续每条路径各自发明产物结构。 |
| 工作流输入 | 路线图文档中的 run 产物建议；团队对结果文件的最低需求。 |
| 工作流输出 | run 目录规范；建议配套 manifest.json 和 config_snapshot.yaml 约定。 |
| 可复用模块 / 工具 | [MULTI_FACTOR_STRATEGY_BACKTEST_ROADMAP.md](MULTI_FACTOR_STRATEGY_BACKTEST_ROADMAP.md) |
| 大致任务内容 | 约定 runs/<run_id>/ 下至少包含 config_snapshot、returns、metrics、summary、manifest。 |
| 备注 | 这一步本身不复杂，但能避免后面两个分支的结果文件不可比较。 |

### T3. 指标分析层抽象

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把收益率曲线、持仓和交易明细统一转成标准绩效指标。 |
| 工作流输入 | returns 序列、holdings、trades。 |
| 工作流输出 | metrics.json、summary.csv、可选 attribution 文件。 |
| 可复用模块 / 工具 | [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) |
| 大致任务内容 | 抽离年化收益、Sharpe、最大回撤、换手率、胜率、盈亏比等通用统计。 |
| 备注 | 不要完全依赖回测引擎自己的 analyzer；指标层最好独立。 |

## 3. 路径 A：多因子投资组合任务清单

### A1. 多因子面板构建

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把多份因子值按 timestamp 和 instrument 对齐成可组合的 factor panel。 |
| 工作流输入 | 多份 factor_value parquet；universe 过滤规则。 |
| 工作流输出 | factor_panel.parquet。 |
| 可复用模块 / 工具 | T1 因子值落盘层；[factor_layer/factor_engine](factor_layer/factor_engine) 现有因子计算结果 |
| 大致任务内容 | 对齐多因子时间轴，处理缺失值、方向统一、winsorize、zscore。 |
| 备注 | 这是从单因子研究走向组合构建的第一步。 |

### A2. 组合信号生成器

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把多个因子组合成 composite score。 |
| 工作流输入 | factor_panel.parquet；组合权重配置；可选中性化配置。 |
| 工作流输出 | composite_signal.parquet。 |
| 可复用模块 / 工具 | T0 数据契约；A1 factor panel；可借鉴 [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 的预处理方式 |
| 大致任务内容 | 支持线性加权、方向调整、可选行业 / 市值中性化、TopK / BottomK 信号打标。 |
| 备注 | 第一版建议只做线性加权，不要先做优化器。 |

### A3. 目标持仓生成器

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把组合信号变成可回测的目标仓位文件。 |
| 工作流输入 | composite_signal.parquet；调仓频率配置；持仓规则；风险约束。 |
| 工作流输出 | target_positions.parquet。 |
| 可复用模块 / 工具 | A2 组合信号文件 |
| 大致任务内容 | 支持等权、分数权重、TopK 等基本持仓生成方式；输出目标权重。 |
| 备注 | 目标持仓是策略层和回测层之间的正式接口。 |

### A4. 组合批处理回测器 MVP

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 基于目标权重做一个简单、可复现的组合回测器。 |
| 工作流输入 | target_positions.parquet；行情数据；回测配置快照。 |
| 工作流输出 | holdings.parquet、trades.parquet、returns.parquet。 |
| 可复用模块 / 工具 | T2 run 目录规范；T3 指标分析层 |
| 大致任务内容 | 实现固定调仓频率、次日开盘或收盘成交、单边手续费、简单滑点。 |
| 备注 | 第一版不要做订单级撮合仿真，先做权重驱动型批处理回测。 |

### A5. 组合结果分析与归因

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 统一输出组合回测的时间序列结果和汇总指标。 |
| 工作流输入 | returns、holdings、trades。 |
| 工作流输出 | metrics.json、summary.csv、可选 attribution.parquet、report.html。 |
| 可复用模块 / 工具 | T3 指标分析层 |
| 大致任务内容 | 输出净值曲线、年化收益、波动、Sharpe、回撤、换手、成本拖累和基准对比。 |
| 备注 | 这一步完成后，多因子路径就具备了最小闭环。 |

### A6. 组合优化器二期任务

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 在 A3 目标持仓生成器中引入约束优化。 |
| 工作流输入 | composite signal；风格暴露；行业暴露；基准权重；约束参数。 |
| 工作流输出 | 优化后的 target_positions.parquet。 |
| 可复用模块 / 工具 | A2、A3 已有产物 |
| 大致任务内容 | 增加单票上限、行业中性、换手约束、tracking error 约束。 |
| 备注 | 这是第二阶段任务，不要放到 MVP 里。 |

## 4. 路径 B：单标的择时 + Backtrader 任务清单

### B1. 单标的行情标准化

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 从现有 parquet 数据中抽出单个标的的标准行情文件。 |
| 工作流输入 | 标准数据目录；symbol / 合约标识；频率选择。 |
| 工作流输出 | 单标的 OHLCV parquet。 |
| 可复用模块 / 工具 | [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py)、[raw_data_layer/raw_data_fetching/download_all_history.py](raw_data_layer/raw_data_fetching/download_all_history.py)、[raw_data_layer/raw_data_fetching/validate_parquet.py](raw_data_layer/raw_data_fetching/validate_parquet.py) |
| 大致任务内容 | 提取某个标的的 OHLCV，统一时间列、价格列、成交量列，并做好缺失检查。 |
| 备注 | 不建议让 Backtrader 直接扫原始 massive_parquet 目录。 |

### B2. 单标的信号生成器

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 计算单标的择时信号或 timing score。 |
| 工作流输入 | 单标的 OHLCV parquet；信号配置。 |
| 工作流输出 | signal.parquet 或 timing_score.parquet。 |
| 可复用模块 / 工具 | [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py)、[factor_layer/factor_engine/api/dsl_parser.py](factor_layer/factor_engine/api/dsl_parser.py)、[factor_layer/factor_engine/api/operators/technical.py](factor_layer/factor_engine/api/operators/technical.py) |
| 大致任务内容 | 用现有 Factor Engine 预计算 RSI、MACD、EMA、均线差、波动率等择时特征。 |
| 备注 | 这一步建议放在 Backtrader 外面做，不要一开始就把信号算在 Strategy 里。 |

### B3. 目标仓位状态机

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把 timing score 转成做多 / 空仓 / 做空目标仓位。 |
| 工作流输入 | signal.parquet；阈值配置；调仓规则。 |
| 工作流输出 | target_positions.parquet。 |
| 可复用模块 / 工具 | B2 单标的信号文件；可借鉴 [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 的持仓统计思路 |
| 大致任务内容 | 做三态状态机，支持开多阈值、平多阈值、开空阈值、平空阈值和反手规则。 |
| 备注 | 这一层是研究逻辑，不建议放到 Backtrader 里。 |

### B4. Backtrader 数据适配层

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 让单标的标准行情文件和外部目标仓位文件能被 Backtrader 读取。 |
| 工作流输入 | 单标的 OHLCV parquet；target_positions.parquet。 |
| 工作流输出 | Backtrader feed 适配器；回测运行时可加载的数据源。 |
| 可复用模块 / 工具 | B1、B3 产物；Backtrader 的 PandasData 或自定义 feed |
| 大致任务内容 | 把 parquet 转 pandas，再封装成 Backtrader feed；必要时增加外部 signal / position feed。 |
| 备注 | 这是 Backtrader 落地前的桥接层。 |

### B5. Backtrader 执行器 MVP

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 基于目标仓位执行单标的多空回测。 |
| 工作流输入 | 行情 feed；目标仓位 feed；回测配置快照。 |
| 工作流输出 | trades.parquet、holdings.parquet、returns.parquet。 |
| 可复用模块 / 工具 | Backtrader；T2 run 目录规范 |
| 大致任务内容 | 在 Strategy 中只做执行逻辑：比较当前仓位与目标仓位、发单、处理成交、成本和滑点。 |
| 备注 | Cerebro / Strategy 不负责研究信号主逻辑，只负责执行。 |

### B6. 单标的回测结果分析

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 把 Backtrader 结果统一转成团队一致的绩效输出。 |
| 工作流输入 | returns、holdings、trades。 |
| 工作流输出 | metrics.json、summary.csv、可选报告文件。 |
| 可复用模块 / 工具 | [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) |
| 大致任务内容 | 输出净值、Sharpe、回撤、胜率、盈亏比、平均持有时长、多头 / 空头收益拆分。 |
| 备注 | 不建议完全依赖 Backtrader 内置 analyzer 作为最终口径。 |

### B7. pandas 基准回测对齐测试

| 项目 | 内容 |
| --- | --- |
| 任务目标 | 验证 Backtrader 执行结果与简化 pandas 回测逻辑一致。 |
| 工作流输入 | 同一份 signal 或 target_positions 文件；同一份成本和成交假设。 |
| 工作流输出 | 一份对齐测试报告或 notebook；误差说明。 |
| 可复用模块 / 工具 | B3 目标仓位状态机；B5 Backtrader 执行器；可借鉴 [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 的向量化收益计算思路 |
| 大致任务内容 | 用最简单策略，例如均线或 RSI 三态，分别用 pandas 和 Backtrader 跑，检查收益曲线和持仓切换是否一致。 |
| 备注 | 这是单标的路径里非常重要的验收任务。 |

## 5. 团队分工建议

如果团队要并行推进，建议按下面方式切：

### 小组 1：公共基础组

- T0 数据契约冻结
- T1 因子值落盘层
- T2 run 目录标准
- T3 指标分析层抽象

### 小组 2：多因子组合组

- A1 多因子面板构建
- A2 组合信号生成器
- A3 目标持仓生成器
- A4 组合批处理回测器 MVP
- A5 组合结果分析与归因

### 小组 3：单标的择时组

- B1 单标的行情标准化
- B2 单标的信号生成器
- B3 目标仓位状态机
- B4 Backtrader 数据适配层
- B5 Backtrader 执行器 MVP
- B6 单标的回测结果分析
- B7 pandas 基准回测对齐测试

## 6. 推荐的开发顺序

如果要兼顾团队效率和落地速度，我建议排期顺序是：

1. T0、T1、T2、T3
2. A1、A2、A3
3. B1、B2、B3
4. A4、A5
5. B4、B5、B6、B7
6. A6

原因是：

- 公共基础层会被两条路径复用，必须先做。
- 多因子路径的回测引擎可以先走批处理权重型，复杂度低于 Backtrader 接入。
- 单标的路径虽然策略简单，但一旦接入 Backtrader，会多出适配层和结果对齐成本。

## 7. 最后一句判断

你现在的理解可以整理成团队共识版本如下：

- 当前仓库主线已经推进到“有可用数据，有因子值”的阶段。
- 接下来确实可以分成“多因子投资组合”和“单标的择时”两条路径。
- 多因子路径的核心任务是：因子值 → 组合信号 → 目标持仓 → 组合回测。
- 单标的路径的核心任务是：单标的行情 → 信号 / 状态机 → 目标仓位 → Backtrader 执行回测。
- 两条路径都不应该跳过中间产物层，尤其是 signal、target_positions、returns 和 metrics 这些正式文件接口。