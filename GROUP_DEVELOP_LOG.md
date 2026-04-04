# 协作开发工作报告

## 2026-04-01

### 吴浩海

1. 工作结果：完善了 cleaned_parquet 接入 factor_engine 的功能，支持基于 cleaned parquet 的配置驱动计算与因子落盘。
2. 工作结果：实现了多数据源合并送入 factor_engine 的功能，当前已支持以 day_aggs_v1 作为锚点源，将基本面数据对齐后统一送入引擎计算。
3. 工作结果：完成了因子落盘测试并产出了可供下游研究员参考的因子文件。示例文件路径：/home/yluel/share/projects/factor_data/factors/day_aggs_v1_fundamental_asset_scale_rank_2016_2025_v1/year=2016/data.parquet
- git push 说明参考：已完成 factor_engine 的 cleaned_parquet 接入、多数据源合并能力和示例因子落盘验证，相关代码与配置已整理，可按功能模块拆分后推送。

## 2026-04-03

### 孙海崴（研究员 D · 单标回测 / `backtest_layer`）

- **当前任务**：维护「目标驱动」回测子系统（单标执行 + 多标组合），与研究员 C 的 **`target_position`** 交付在数据契约上闭环；文档与示例可复现。
- **本次进展（按代码能力归纳）**：
  - **`single_asset_backtest`**：单标的 **`run_single_asset_backtest`**（Backtrader 执行、佣金/滑点、可选 **`trade_ledger`**、分层 **`metrics_profile`**、**`target_lag_bars`** 等与 ADR 对齐的审计字段）；同包 **多标的组合** **`run_multi_asset_backtest`**（**`target_weights`** → 逐 bar 执行与成本、**`executed_weights`**、**`portfolio_weight_lag_bars`**、多档执行内核与 **`FACTOR_BACKTEST_EXECUTION_ENGINE`**、组合指纹与 **`summary` 中 requested/resolved** 等）。
  - **冻结协议**：`contracts` + **`build_backtest_report`** 保证 **`returns` / `metrics` / `summary`** 必需键；**`strategy_registry` / `strategy_library`** 支持策略名版本化（D-3 与任务清单一致）。
  - **与研究员 C 衔接**：在 **`single_asset_alpha`** 侧增加 **`integration/backtest_bridge`**（C 的 **`StrategyPipeline`** 产出 **`target_position`** 后直接调用 **`run_single_asset_backtest`**）及 **`examples/c_to_d_end_to_end`**；两侧 README 写明 **`target_position`** 列约定与 **滞后/频率** 需联合约定，避免重复 shift。
  - **测试与示例**：专项测试覆盖契约、IO、单/多资产、报告 schema、可复现指纹、扩展指标等；示例脚本演示单标与多标调用方式。
- **当前产出**：可交付的 **`target_position` / `target_weights` → 统一报告结构** 链路；C–D 端到端示例与 bridge API；子系统长篇说明见 **`backtest_layer/single_asset_backtest/README.md`**。
- **当前问题 / 风险**：C 侧状态机若已含 **T→T+1** 映射，须与 D 侧 **`target_lag_bars`** 显式对齐，避免逻辑上双重滞后；行情与 **`target_position` 时间轴**须同频、同日历。
- **下一步**：与 C 冻结「滞后只在一侧生效」的默认配置；若业务需要，再补因子引擎输出接入 C-1 的示例路径。
- **需要谁配合**：研究员 C 维持 **`TargetPositionSchema`** 字段语义；若组合侧与研究员 B 共用策略库命名，再对齐 **strategy_name@version** 登记习惯。

- **关联文件 / 结果**：
  - 核心包：`backtest_layer/single_asset_backtest/`（`runner.py`、`config.py`、`contracts.py`、`report.py`、`strategy_registry.py`、`strategy_library.py` 等）
  - 专项测试：`backtest_layer/tests/test_backtest_*.py`；示例：`backtest_layer/examples/backtest_*.py`
  - C–D：`strategy_layer/single_asset_alpha/integration/backtest_bridge.py`、`strategy_layer/single_asset_alpha/examples/c_to_d_end_to_end.py`
  - 协议：`factor_layer/factor_engine/docs/adr_backtest_target_position.md`

- **git push 说明（示例，可按实际改动删减）**：

```
backtest: 目标驱动回测能力与 C-target_position 衔接文档/示例

- single_asset_backtest：单标 Backtrader + 多标组合会计、冻结 returns/metrics/summary 与策略注册表
- 与 single_asset_alpha：backtest_bridge + c_to_d_end_to_end；README 约定滞后与契约
- 专项测试与单/多标 examples；GROUP_DEVELOP_LOG 2026-04-03 研究员 D
```

##

这份文件就当团队的公共工作报告来用，不用写得太正式。

目的很简单：

- 大家每天或每次有阶段进展时，来这里补一条。
- 让团队快速看到每个人现在在做什么。
- 看清楚谁交付了什么，谁还卡着什么。
- 如果有阻塞，能第一时间看到需要谁配合。

## 1. 谁来写

当前默认这几位研究员会在这里更新：

- 研究员 A：多因子路径，负责因子值 -> 面板数据 -> 持仓数据。
- 研究员 B：多因子路径，负责组合回测、组合策略入库、组合策略库搭建。
- 研究员 C：单标的路径，负责行情 / 因子 -> 信号 -> 目标仓位逻辑。
- 研究员 D：单标的路径，负责 Backtrader 回测、单标的策略入库、单标的策略库搭建。

任务边界可以参考 [WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md) 和 [STRATEGY_BACKTEST_TEAM_TASKLIST.md](STRATEGY_BACKTEST_TEAM_TASKLIST.md)。

## 2. 怎么写

不用写成制度文件，按工作报告写就行。

每次更新尽量回答下面几件事：

- 我这次在做什么。
- 我这次完成了什么。
- 我现在产出了什么。
- 我现在卡在哪里。
- 我下一步要做什么。

新记录直接写在最上面，越新的越靠前。

## 3. 推荐写法

建议每次更新都用下面这个简单格式。

```md
## YYYY-MM-DD

### 研究员X

- 当前任务：
- 本次进展：
- 当前产出：
- 当前问题 / 风险：
- 下一步：
- 需要谁配合：
```

如果这次有具体文件、结果、回测 run 或策略版本，也可以顺手补一行：

```md
- 关联文件 / 结果：
- git push 说明：
```

## 4. 写的时候注意什么

### 4.1 只写新增进展

不用把背景每次都重写一遍，只写这次新做了什么。

### 4.2 问题尽量写具体

不要只写“还在调试”。

尽量写成这种形式：

- 等待研究员 A 给第一版 holdings_target 字段。
- 等待研究员 C 冻结 target_position 三态规则。
- 当前回测收益异常，怀疑成交时点定义有偏差。

### 4.3 产出尽量写成可交付物

比如：

- 第一版 factor_panel 样例数据。
- 第一版 target_position 规则。
- 第一版组合回测 returns 输出。
- 某个 strategy_id 的入库记录。

### 4.4 策略入库任务记得写版本信息

研究员 B 和研究员 D 在做策略入库和策略库搭建时，尽量写上：

- strategy_id
- version
- 关联 run_id
- 这次入库的是哪一版结果

### 4.5 如果这次有代码或文档改动，顺手补一句 git push 说明

不用写得太复杂，简单说明下面这些信息就够了：

- 这次改动是否已经 push。
- push 到哪个分支。
- 这次 push 大概包含哪些改动。

比如可以这样写：

- 已 push 到 `feature/backtest-mvp`，包含第一版回测输入适配和 returns 输出。
- 代码已本地完成，暂未 push，等和研究员 C 对齐 target_position 字段后一起推送。
- 已 push 文档更新，代码部分还在本地验证。

## 5. 一个更像工作报告的例子

```md
## 2026-04-01

### 研究员A

- 当前任务：因子值转面板数据
- 本次进展：完成了 3 个因子值文件的时间对齐，缺失值情况已经初步检查完。
- 当前产出：第一版 factor_panel 字段草案。
- 当前问题 / 风险：还需要和研究员 B 对齐 holdings_target 最少字段要求。
- 下一步：补齐标准化和方向统一逻辑，输出第一版 factor_panel 样例。
- 需要谁配合：研究员 B
- 关联文件 / 结果：[WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md)
- git push 说明：文档已 push，面板数据处理代码还在本地整理。

### 研究员D

- 当前任务：Backtrader 回测框架搭建
- 本次进展：已经完成最小行情 feed 验证，行情数据可以正常加载。
- 当前产出：可运行的最小 Backtrader 输入验证代码。
- 当前问题 / 风险：target_position 字段还没有完全冻结，执行层映射暂时不能定死。
- 下一步：先补手续费和滑点配置结构，再等研究员 C 的目标仓位规则。
- 需要谁配合：研究员 C
- 关联文件 / 结果：[backtest_layer](backtest_layer)
- git push 说明：暂未 push，准备等 target_position 接口冻结后一起提交。
```

## 6. 建议怎么维护

- 这份文件顶部保留最近的更新。
- 旧内容不用频繁整理，真的太长了再按月归档。
- 别人写过的历史内容尽量不要改，除非是修正明显笔误。

从现在开始，大家直接在文件最上面按这个格式追加自己的进展就可以了。
