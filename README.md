# QuantSociety Backend Project

量化研究后端工作区，覆盖原始数据获取与清洗、因子表达引擎、因子生成 Agent、因子评估与可视化等环节。

这个仓库目前更接近一个多模块工作区，而不是单一可直接安装的 Python 包。不同子目录有各自的运行入口、依赖和开发节奏。

## 目录概览

- `raw_data_layer/`：原始数据抓取、校验与清洗。
- `factor_layer/`：因子相关核心实现，包括 Agent、计算引擎、评估模块与因子池。
- `backtest_layer/`：回测层预留目录。
- `strategy_layer/`：策略层预留目录。
- `users_workspace/`：本地实验区，不属于核心实现主线。

## 主要模块

### 1. Factor Agent

路径：`factor_layer/factor_agent/`

定位：将研报 PDF 转成可执行的 YAML 因子配置，并通过评分反馈循环持续修订。

核心流程：PDF -> LLM 生成 YAML -> 评价脚本打分 -> 未达标则继续修订。

参考文档：`factor_layer/factor_agent/README.md`

### 2. Factor Engine

路径：`factor_layer/factor_engine/`

定位：可扩展的量化因子计算引擎，支持表达式树、DSL、YAML 配置和多后端执行。

特点：

- 支持 Pandas 后端，Polars 后端提供部分能力。
- 支持截面、时序、分组、清洗、技术指标等算子。
- 可对接 Parquet 数据源进行配置驱动运行。

参考文档：`factor_layer/factor_engine/README.md`

### 3. Factor Indicators

路径：`factor_layer/factor_indicators/`

定位：分钟级期货因子评估与可视化模块，当前重点是 NQ 的 VWAP Reversion 因子。

包含内容：

- 因子生成脚本
- 评估框架
- Streamlit 可视化看板

参考文档：`factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md`

### 4. Raw Data Layer

路径：`raw_data_layer/`

定位：原始数据下载、格式校验、清洗准备。

当前可见实现主要在：

- `raw_data_layer/raw_data_fetching/`：历史数据抓取、下载记录、Parquet 校验。
- `raw_data_layer/raw_data_cleaning/`：数据清洗相关目录。

## 建议阅读顺序

如果你是第一次进入这个仓库，建议按下面顺序了解：

1. [IMPLEMENTED_WORKFLOWS.md](IMPLEMENTED_WORKFLOWS.md)：先看已经落地的工作流和文件流总览。
2. `factor_layer/factor_engine/README.md`：再理解因子表达和执行框架。
3. `factor_layer/factor_agent/README.md`：再看 Agent 如何产出 YAML 配置。
4. `factor_layer/factor_indicators/PROJECT_HANDOFF_AI.md`：最后看因子评估与可视化链路。

## 工作流文档

仓库里已经实现的功能串联关系、上下游文件流、当前断点说明，见：

- [IMPLEMENTED_WORKFLOWS.md](IMPLEMENTED_WORKFLOWS.md)

## 快速开始

由于仓库没有统一的根级依赖管理，建议按模块分别运行：

1. 进入目标子模块目录。
2. 使用该模块自己的依赖文件或现有环境安装依赖。
3. 从对应入口脚本启动。

常见入口示例：

- `factor_layer/factor_agent/main.py`
- `factor_layer/factor_engine/examples/`
- `factor_layer/factor_indicators/factor_eval_dashboard.py`
- `raw_data_layer/raw_data_fetching/download_all_history.py`

## 当前状态

- `factor_layer/` 是当前最完整、最值得优先阅读的实现层。
- `backtest_layer/` 与 `strategy_layer/` 目前还是预留目录。
- 仓库内包含一定数量的本地输出文件与实验痕迹，提交前应结合 `.gitignore` 检查变更范围。