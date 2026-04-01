# 已实现功能工作流与文件流

这份文档只描述仓库里当前已经能看见、能运行、或至少已经形成稳定文件约定的部分。

重点不是目录介绍，而是把下面几件事串起来：

- 哪些功能已经落地。
- 每条链路的入口文件是什么。
- 输入文件放在哪里，输出文件落到哪里。
- 上下游模块之间哪些已经接通，哪些还停留在“概念上相邻、代码上未闭环”。

## 1. 当前已落地能力总览

| 主线 | 当前状态 | 主要入口 | 主要输入 | 主要输出 |
| --- | --- | --- | --- | --- |
| 原始数据 flatfile 下载与转 parquet | 已实现 | [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py) | Massive flatfiles / S3 key 前缀 | massive_parquet 目录下的 parquet 和 .sha256 |
| 原始数据 REST 历史抓取 | 已实现 | [raw_data_layer/raw_data_fetching/download_all_history.py](raw_data_layer/raw_data_fetching/download_all_history.py) | Massive REST API + 数据集清单 | 按 category/sub 分层的 parquet、.ok 标记、download_results.csv |
| parquet 完整性校验 | 已实现 | [raw_data_layer/raw_data_fetching/validate_parquet.py](raw_data_layer/raw_data_fetching/validate_parquet.py) | 某个 parquet 根目录 | 终端摘要和逐文件告警 |
| Factor Agent 生成 YAML 并评分迭代 | 部分实现 | [factor_layer/factor_agent/main.py](factor_layer/factor_agent/main.py) | 用户 query、人工提供的研报上下文、已有 Markdown/YAML 文件 | output 下的 YAML、audit_log.jsonl |
| Factor Engine 配置驱动执行因子 | 已实现 | [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py) | Python Expr 或 YAML 配置 + parquet 数据源 | 内存中的结果 dict |
| 多数据集 smoke 测试 | 已实现 | [factor_layer/factor_engine/examples/run_real_data_factor_smoke.py](factor_layer/factor_engine/examples/run_real_data_factor_smoke.py) | massive_parquet 数据目录 | 各数据集因子 smoke 报告 |
| NQ 分钟因子评估与可视化 | 已实现 | [factor_layer/factor_indicators/factor_vwap_reversion.py](factor_layer/factor_indicators/factor_vwap_reversion.py)、[factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py)、[factor_layer/factor_indicators/factor_eval_dashboard.py](factor_layer/factor_indicators/factor_eval_dashboard.py) | NQ 分钟数据、NQ_vwap.parquet | factor_output.parquet、evaluation_output/*.csv、Streamlit 看板 |
| Backtest / Strategy 层 | 未实现主流程 | [backtest_layer](backtest_layer)、[strategy_layer](strategy_layer) | - | 目前为预留目录 |

## 2. 仓库主串联图

当前仓库里真正成形的主线可以拆成三条：

### 2.1 数据到引擎主线

Massive 数据源
→ [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py) 或 [raw_data_layer/raw_data_fetching/download_all_history.py](raw_data_layer/raw_data_fetching/download_all_history.py)
→ parquet 文件目录
→ [factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) 里的 YAML 配置
→ [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py)
→ 因子结果

### 2.2 研报到 YAML 主线

人工整理的研报上下文 / 已提取 Markdown
→ [factor_layer/factor_agent/main.py](factor_layer/factor_agent/main.py)
→ [factor_layer/factor_agent/core/agent_loop.py](factor_layer/factor_agent/core/agent_loop.py)
→ write_file / run_eval 循环
→ output 下 YAML + 审计日志

### 2.3 NQ 因子评估主线

NQ 分钟数据目录 + NQ_vwap.parquet
→ [factor_layer/factor_indicators/factor_vwap_reversion.py](factor_layer/factor_indicators/factor_vwap_reversion.py)
→ factor_output.parquet
→ [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py)
→ evaluation_output/*.csv
→ [factor_layer/factor_indicators/factor_eval_dashboard.py](factor_layer/factor_indicators/factor_eval_dashboard.py)

需要明确的是，这三条主线目前不是一条完整的大一统流水线，而是三个成熟度不同的子系统：

- 原始数据层和 Factor Engine 已经能通过 parquet 目录和 YAML 配置接起来。
- Factor Agent 和 Factor Engine 在概念上相邻，但自动衔接还没有彻底打通。
- Factor Indicators 目前是一条独立的分钟级研究链，不直接消费 Engine 输出。

## 3. 原始数据层工作流与文件流

### 3.1 Flatfile / S3 下载链路

入口文件：

- [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py)

当前实现的职责：

- 从 Massive flatfiles 拉取 CSV / CSV.GZ。
- 先下载到本地临时文件。
- 按 chunk 流式转成 parquet。
- 通过 .part 临时文件原子替换为正式 parquet。
- 给每个 parquet 生成 .sha256 校验文件。
- 已存在文件时优先校验 checksum，避免重复下载。

当前默认文件流：

1. 远端 key 前缀默认指向 us_stocks_sip/trades_v1 的某个月目录。
2. 远端 CSV / CSV.GZ 下载到本地临时目录 .tmp。
3. 流式转写成 local_root 下与 key 同路径的 parquet。
4. 同目录写入对应的 .sha256。

典型输出形态：

- massive_parquet/us_stocks_sip/trades_v1/年/月/*.parquet
- massive_parquet/us_stocks_sip/trades_v1/年/月/*.parquet.sha256

和下游的关系：

- 这条链路产出的 massive_parquet 目录结构，与 [factor_layer/factor_engine/examples/run_real_data_factor_smoke.py](factor_layer/factor_engine/examples/run_real_data_factor_smoke.py) 和 [factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) 采用的目录风格最接近。
- 如果把 prefix 切到 quotes、day_aggs、minute_aggs，对接 Engine 会最自然。

### 3.2 REST 历史抓取链路

入口文件：

- [raw_data_layer/raw_data_fetching/download_all_history.py](raw_data_layer/raw_data_fetching/download_all_history.py)

当前实现的职责：

- 维护一个数据集字典，覆盖 fundamentals、aggregate_bars、news、filing、market metadata 等。
- 自动探测分区方式，按 fiscal year、calendar year、year/month 或 all 去抓取。
- 每个 partition 流式写 parquet。
- 给成功分区写 .ok marker，支持断点续跑。
- 汇总结果导出为 download_results.csv。

当前文件流：

1. Massive RESTClient 或 raw endpoint。
2. 依据数据集类型拆成多个 partition。
3. 每个 partition 写到 root_dir/category/sub 目录下。
4. 生成 prefix_partition.parquet。
5. 生成同名 .ok 标记文件。
6. 全量汇总写入 download_results.csv。

典型输出形态：

- root_dir/fundamentals/balance_sheet/balance_sheet_2024.parquet
- root_dir/fundamentals/balance_sheet/balance_sheet_2024.parquet.ok
- root_dir/aggregate_bars/daily_market_summary/daily_market_summary_2024.parquet
- [raw_data_layer/raw_data_fetching/download_results.csv](raw_data_layer/raw_data_fetching/download_results.csv)

和下游的关系：

- 这条链路更偏“全量归档型下载”，适合先把数据稳定落地。
- 它的目录命名和 [factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) 里的 us_stocks_sip 示例并不是完全同一套，需要在 YAML 中按实际 root、timestamp 列、instrument 列重新配置。

### 3.3 parquet 校验链路

入口文件：

- [raw_data_layer/raw_data_fetching/validate_parquet.py](raw_data_layer/raw_data_fetching/validate_parquet.py)

当前实现的职责：

- 递归扫描某个根目录下所有 parquet 文件。
- 校验文件能否读取、是否为空。
- 校验文件名日期和时间戳列是否匹配。
- 检查常见质量问题，例如 NaN 和负值。

这一步不生成新 parquet，而是给出质量报告，常用于下载后抽检。

## 4. Factor Agent 工作流与文件流

入口文件：

- [factor_layer/factor_agent/main.py](factor_layer/factor_agent/main.py)

核心运行环：

- [factor_layer/factor_agent/core/agent_loop.py](factor_layer/factor_agent/core/agent_loop.py)
- [factor_layer/factor_agent/tools/registry.py](factor_layer/factor_agent/tools/registry.py)
- [factor_layer/factor_agent/verifiers/evaluator.py](factor_layer/factor_agent/verifiers/evaluator.py)
- [factor_layer/factor_agent/scripts/配置文件评价脚本.py](factor_layer/factor_agent/scripts/配置文件评价脚本.py)
- [factor_layer/factor_agent/verifiers/audit.py](factor_layer/factor_agent/verifiers/audit.py)

当前真正已经落地的闭环不是“自动 PDF 解析 + 自动 YAML 生成”的全套，而是下面这个更准确的流程：

1. 启动 [factor_layer/factor_agent/main.py](factor_layer/factor_agent/main.py)，传入 query。
2. main.py 选择 LLM provider，然后进入 agent_loop。
3. agent_loop 从 [factor_layer/factor_agent/docs/CLAUDE.md](factor_layer/factor_agent/docs/CLAUDE.md) 加载常驻系统上下文。
4. agent_loop 暴露可用工具。
5. 模型通过工具读文件、写 YAML、调用评分脚本、更新 todo，必要时调用子智能体。
6. 如果写的是 YAML，会先经过 pre hook 和 schema 校验。
7. 如果调用 run_eval，则执行评价脚本并解析 JSON 结果。
8. 达标后执行 post hook，并把结果写入 audit_log.jsonl。

### 4.1 当前可用工具

真正注册到运行时的工具在 [factor_layer/factor_agent/tools/registry.py](factor_layer/factor_agent/tools/registry.py)：

- read_file
- write_file
- run_eval
- todo
- task

其中 task 会走 [factor_layer/factor_agent/planning/sub_agents/base.py](factor_layer/factor_agent/planning/sub_agents/base.py) 的子智能体循环。

### 4.2 当前文件流

当前仓库里已经存在的输入/输出约定主要是：

- [factor_layer/factor_agent/input](factor_layer/factor_agent/input)：预留输入目录。
- [factor_layer/factor_agent/output](factor_layer/factor_agent/output)：Agent 工作产物主目录。
- [factor_layer/factor_agent/output/audit_log.jsonl](factor_layer/factor_agent/output/audit_log.jsonl)：最终结果审计日志。
- [factor_layer/factor_agent/output/config_v2.yaml](factor_layer/factor_agent/output/config_v2.yaml)：生成过的 YAML 示例。
- [factor_layer/factor_agent/output/config_keyperiod_v1.yaml](factor_layer/factor_agent/output/config_keyperiod_v1.yaml)：生成过的 YAML 示例。
- output 下多份 MinerU_markdown_*.md：已经准备好的研报 Markdown 资产。

当前更接近真实的工作方式是：

研报 PDF 或人工整理内容
→ 先在仓库外或手工转成 Markdown / 文本上下文
→ Agent 读取这些文件
→ 生成 YAML 到 output
→ 评价脚本打分
→ 达标后审计留痕

### 4.3 当前未完全落地的部分

需要明确区分“README 里的目标形态”和“代码里已实现的形态”：

- [factor_layer/factor_agent/tools/pdf_tools.py](factor_layer/factor_agent/tools/pdf_tools.py) 目前还是占位文件。
- [factor_layer/factor_agent/tools/yaml_tools.py](factor_layer/factor_agent/tools/yaml_tools.py) 目前还是占位文件。
- [factor_layer/factor_agent/tools/eval_tools.py](factor_layer/factor_agent/tools/eval_tools.py) 目前还是占位文件。

所以 Factor Agent 目前的强项是“LLM 工具调用闭环”和“YAML 评分审计”，不是仓库内置的 PDF 解析能力。

### 4.4 与 Factor Engine 的衔接现状

这部分是当前最容易误判的地方。

概念上：

- Factor Agent 的产物是因子 YAML。
- Factor Engine 的输入也可以是因子 YAML。

但代码层面目前只部分接通：

- Agent 的 schema 在 [factor_layer/factor_agent/config/yaml_schema.py](factor_layer/factor_agent/config/yaml_schema.py) 中要求 data_source.timestamp_col 和 data_source.instrument_col。
- Engine 的 generic parquet / multi_parquet 路径可以接受这套字段名。
- 但 Engine 的 parquet_kline 数据源在 [factor_layer/factor_engine/storage/kline_parquet_source.py](factor_layer/factor_engine/storage/kline_parquet_source.py) 中要求的是 instrument_column 和 timestamp_column。

结论：

- Agent 产出的 YAML 目前可以视为“接近 Engine 配置”，但不是对所有数据源类型都能原样直跑。
- 如果目标数据源是 parquet_kline，通常还需要做一次字段名适配。

## 5. Factor Engine 工作流与文件流

入口文件：

- [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py)

配置相关文件：

- [factor_layer/factor_engine/runtime/config.py](factor_layer/factor_engine/runtime/config.py)
- [factor_layer/factor_engine/storage/factory.py](factor_layer/factor_engine/storage/factory.py)

示例入口：

- [factor_layer/factor_engine/examples/simple_factor.py](factor_layer/factor_engine/examples/simple_factor.py)
- [factor_layer/factor_engine/examples/pandas_factor.py](factor_layer/factor_engine/examples/pandas_factor.py)
- [factor_layer/factor_engine/examples/run_factors_joblib.py](factor_layer/factor_engine/examples/run_factors_joblib.py)
- [factor_layer/factor_engine/examples/run_real_data_factor_smoke.py](factor_layer/factor_engine/examples/run_real_data_factor_smoke.py)

### 5.1 代码驱动执行流

代码驱动时的文件流比较简单：

1. 在 Python 里构造 Factor 对象，或者用 DSL 解析字符串。
2. 把 backend 和 data_source 注入 FactorEngine。
3. engine.compile 走 Analyzer → Lowerer → Optimizer。
4. engine.run 构造 ExecutionContext，调用 backend.execute。
5. 返回一个结果 dict，其中包含 factor、analysis、plan、result。

这条链路以“内存对象”为主，不会自动往磁盘写统一格式的结果文件。

### 5.2 YAML 配置驱动执行流

这条链路是当前最适合承接上游 parquet 文件的实现：

1. 读取 YAML 配置文件。
2. [factor_layer/factor_engine/runtime/config.py](factor_layer/factor_engine/runtime/config.py) 解析 factor、data_source、backend、engine 四段配置。
3. [factor_layer/factor_engine/storage/factory.py](factor_layer/factor_engine/storage/factory.py) 根据 data_source.type 构造数据源实例。
4. [factor_layer/factor_engine/api/dsl_parser.py](factor_layer/factor_engine/api/dsl_parser.py) 解析 factor.expr。
5. [factor_layer/factor_engine/runtime/engine.py](factor_layer/factor_engine/runtime/engine.py) 执行并返回结果。

当前已经落地的数据源类型：

- parquet
- multi_parquet
- parquet_kline

相关示例配置：

- [factor_layer/factor_engine/examples/config_driven_factor.yaml](factor_layer/factor_engine/examples/config_driven_factor.yaml)
- [factor_layer/factor_engine/examples/configs/us_stocks_sip_day_aggs_v1.yaml](factor_layer/factor_engine/examples/configs/us_stocks_sip_day_aggs_v1.yaml)
- [factor_layer/factor_engine/examples/configs/us_stocks_sip_minute_aggs_v1.yaml](factor_layer/factor_engine/examples/configs/us_stocks_sip_minute_aggs_v1.yaml)
- [factor_layer/factor_engine/examples/configs/fundamentals_balance_sheet.yaml](factor_layer/factor_engine/examples/configs/fundamentals_balance_sheet.yaml)

### 5.3 与原始数据层的衔接现状

当前已经可以形成的实际链路是：

原始数据下载脚本
→ parquet 文件目录
→ 手工或示例 YAML 指向对应 root
→ FactorEngine.run_from_config

其中最顺畅的组合通常是：

- flatfile 下载出来的 massive_parquet 目录
- 加上 [factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) 里的真实数据示例
- 再跑 [factor_layer/factor_engine/examples/run_real_data_factor_smoke.py](factor_layer/factor_engine/examples/run_real_data_factor_smoke.py)

### 5.4 当前还没有统一落地的部分

Factor Engine 当前更像“执行内核”，而不是“研究任务编排器”。目前尚未看到统一的：

- 标准化 factor 结果落盘规范。
- 统一的实验 run 目录。
- 与回测层、策略层的自动对接。

## 6. Factor Indicators 工作流与文件流

这是当前仓库里最完整的一条独立研究链路。

入口文件：

- [factor_layer/factor_indicators/factor_vwap_reversion.py](factor_layer/factor_indicators/factor_vwap_reversion.py)
- [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py)
- [factor_layer/factor_indicators/factor_eval_dashboard.py](factor_layer/factor_indicators/factor_eval_dashboard.py)

配套说明文档：

- [factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md](factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md)

### 6.1 因子生成文件流

1. [factor_layer/factor_indicators/NQ](factor_layer/factor_indicators/NQ) 目录下的分钟数据被读入。
2. [factor_layer/factor_indicators/factor_vwap_reversion.py](factor_layer/factor_indicators/factor_vwap_reversion.py) 计算日内累计 VWAP 偏离因子。
3. 输出为 [factor_layer/factor_indicators/factor_output.parquet](factor_layer/factor_indicators/factor_output.parquet)。

当前因子生成脚本同时会输出一份终端 IC 摘要，但正式评估结果由下一步框架负责。

### 6.2 评估框架文件流

1. [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 读取：
   - [factor_layer/factor_indicators/factor_output.parquet](factor_layer/factor_indicators/factor_output.parquet)
   - [factor_layer/factor_indicators/NQ_vwap.parquet](factor_layer/factor_indicators/NQ_vwap.parquet)
2. 在内存中完成对齐、rolling zscore、前瞻收益构造、IC / RankIC 计算、分层回测、持有回测、成本回测。
3. 把结果 CSV 写入 [factor_layer/factor_indicators/evaluation_output](factor_layer/factor_indicators/evaluation_output)。

当前会稳定落盘的文件包括：

- [factor_layer/factor_indicators/evaluation_output/evaluation_summary.csv](factor_layer/factor_indicators/evaluation_output/evaluation_summary.csv)
- daily_ic_h*.csv
- daily_rank_ic_h*.csv
- layered_single_period_h*.csv
- holding_pnl_h*.csv

需要注意：evaluation_output 目录下还保留了一些历史口径文件，例如 h15、h30，这些不是当前默认 horizons 的唯一真相，要以脚本当前参数为准。

### 6.3 Dashboard 文件流

这一点很重要：

- [factor_layer/factor_indicators/factor_eval_dashboard.py](factor_layer/factor_indicators/factor_eval_dashboard.py) 不直接读 evaluation_output 里的 CSV。
- 它会重新调用 [factor_layer/factor_indicators/factor_evaluation_framework.py](factor_layer/factor_indicators/factor_evaluation_framework.py) 的 run_evaluation。
- 也就是说，Dashboard 的实时数据源仍然是 factor_output.parquet 和 NQ_vwap.parquet。

当前实际文件流是：

factor_output.parquet + NQ_vwap.parquet
→ Dashboard 运行时重算 metrics
→ 页面展示 Plotly 图和统计表

## 7. 目前已经接通和未接通的地方

### 7.1 已基本接通

- 原始数据 flatfile parquet 目录 → Factor Engine YAML 配置 → 引擎执行。
- NQ 原始数据 → 因子生成 → 评估框架 → Dashboard。
- Factor Agent 的 YAML 生成 → 评分 → 审计留痕。

### 7.2 部分接通

- Factor Agent → Factor Engine。
  目前在概念和文件格式层面接近，但数据源字段名对不同 source type 还不完全统一。

- 原始数据 REST 下载 → Factor Engine。
  可以通过重新写 YAML 接上，但不是“下载完即插即跑”的固定目录约定。

### 7.3 还未形成闭环

- Factor Engine → Backtest Layer。
- Factor Engine → Strategy Layer。
- Factor Agent 仓库内自动 PDF 解析 → YAML 生成。
- Factor Engine 输出 → Factor Indicators 评估框架。

## 8. 如果按“先读懂当前仓库”来走，推荐阅读顺序

1. [README.md](README.md)
2. [IMPLEMENTED_WORKFLOWS.md](IMPLEMENTED_WORKFLOWS.md)
3. [factor_layer/factor_engine/README.md](factor_layer/factor_engine/README.md)
4. [factor_layer/factor_agent/README.md](factor_layer/factor_agent/README.md)
5. [factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md](factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md)

如果你的目标是“从数据落地到跑出因子”，最短路径通常是：

1. 先看 [raw_data_layer/raw_data_fetching/download_history.py](raw_data_layer/raw_data_fetching/download_history.py) 和 [raw_data_layer/raw_data_fetching/validate_parquet.py](raw_data_layer/raw_data_fetching/validate_parquet.py)。
2. 再看 [factor_layer/factor_engine/examples/configs](factor_layer/factor_engine/examples/configs) 和 [factor_layer/factor_engine/examples/run_real_data_factor_smoke.py](factor_layer/factor_engine/examples/run_real_data_factor_smoke.py)。
3. 最后再看 [factor_layer/factor_agent/main.py](factor_layer/factor_agent/main.py)，把 Agent 视为“YAML 生成辅助器”，而不是已经完全自动化的数据到因子总控。

## 9. 下一阶段文档

刚才追加的多因子策略构建与回测框架建议，已经独立整理到 [MULTI_FACTOR_STRATEGY_BACKTEST_ROADMAP.md](MULTI_FACTOR_STRATEGY_BACKTEST_ROADMAP.md)。

这样当前这份 [IMPLEMENTED_WORKFLOWS.md](IMPLEMENTED_WORKFLOWS.md) 继续只聚焦“已经实现的工作流和文件流”，而未来规划单独维护在路线图文档里。