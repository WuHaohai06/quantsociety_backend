# `docs` — 文档中心与索引（详尽说明)

本目录集中存放 **算子语义、路线图、ADR、数据字典、变更记录** 及 **LLM 提示词**；**规范以 Markdown/JSON 为准**，代码若有出入以 **文档 + 测试** 为优先对齐目标。

### 协作者速览（约 5 分钟）

1. **先读谁**：**算子权威** → [`operators_semantics.md`](operators_semantics.md)；**架构决策** → 各 **ADR**；**版本沿革** → [`changelog_shw.md`](changelog_shw.md)。
2. **读代码地图**：下面 **§1** 表格链到 **`api/`、`backend/`、`runtime/`** 等包内 **`README.md`**（多数含 **「协作者速览」** 文首小节）。
3. **回测协议**：[`adr_backtest_target_position.md`](adr_backtest_target_position.md)；**实现与长篇说明**见 monorepo [`../../../backtest_layer/single_asset_backtest/README.md`](../../../backtest_layer/single_asset_backtest/README.md)（含 **新人 5 分钟上手**）。

---

## 1. 各包目录 `README` 导航（源码导读）

阅读源码时建议 **先读包级 README**（多数文首有 **「协作者速览（约 5 分钟）」**），再下钻模块：

| 目录 | README | 内容焦点 |
|------|--------|----------|
| `api/` | [`api/README.md`](../api/README.md) | 用户 API、DSL、算子注册 |
| `api/operators/` | [`api/operators/README.md`](../api/operators/README.md) | 按文件算子清单 |
| `backend/` | [`backend/README.md`](../backend/README.md) | Pandas/Polars/Modin 执行 |
| `expr/` | [`expr/README.md`](../expr/README.md) | 表达式 AST |
| `ir/` | [`ir/README.md`](../ir/README.md) | IR 与分析 |
| `planner/` | [`planner/README.md`](../planner/README.md) | 计划、CSE、DAG |
| `runtime/` | [`runtime/README.md`](../runtime/README.md) | FactorEngine、YAML |
| `storage/` | [`storage/README.md`](../storage/README.md) | 数据源与缓存 |
| `backtest_layer/single_asset_backtest/` | [`../../../backtest_layer/single_asset_backtest/README.md`](../../../backtest_layer/single_asset_backtest/README.md) | 回测全流程（极详，monorepo）；包名 **`single_asset_backtest`** |
| `tests/` | [`tests/README.md`](../tests/README.md) | 测试分类 |
| `examples/` | [`examples/README.md`](../examples/README.md) | 示例脚本 |
| `examples/configs/` | [`examples/configs/README.md`](../examples/configs/README.md) | YAML 模板 |
| `scripts/` | [`scripts/README.md`](../scripts/README.md) | 性能脚本 |
| `docs/_refs/` | [`_refs/README.md`](_refs/README.md) | 外部参考摘录（非规范） |

---

## 2. 算子与 DSL（权威）

| 文档 | 用途 |
|------|------|
| [`operators_semantics.md`](operators_semantics.md) | **算子语义、参数、列依赖、DSL 限制** — **必读** |
| [`operators_roadmap.md`](operators_roadmap.md) | Deep Research 对照与实现状态 |
| [`huatai_factor_factory_operator_catalog.md`](huatai_factor_factory_operator_catalog.md) | 华泰因子工厂 ↔ 本引擎 DSL 名 |
| [`changelog_shw.md`](changelog_shw.md) | 第 N 版 **更改-shw** 变更记录 |

---

## 3. ADR（架构决策）

| 文档 | 主题 |
|------|------|
| [`adr_backtest_target_position.md`](adr_backtest_target_position.md) | 回测协议、`target_position`、多资产执行/滞后/指纹（§13–§14）、可复现、信号时点 |
| [`adr_huatai_factor_factory_operators.md`](adr_huatai_factor_factory_operators.md) | 华泰算子扩展策略 |
| [`adr_context_benchmark.md`](adr_context_benchmark.md) | `change_instrument` 基准列 |
| [`adr_trade_when.md`](adr_trade_when.md) | `trade_when` |
| [`adr_ts_step_hump.md`](adr_ts_step_hump.md) | `ts_step` / `hump` |

---

## 4. 数据字典

| 文档 | 格式 |
|------|------|
| [`massive_parquet_data_dictionary.md`](massive_parquet_data_dictionary.md) | Markdown，含中文释义 |
| [`massive_parquet_data_dictionary.json`](massive_parquet_data_dictionary.json) | 机器可读 |

---

## 5. LLM 与提示词

| 文档 | 说明 |
|------|------|
| [`factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md) | 给模型的算子与约定摘要 |
| [`factor_engine_llm_prompt.txt`](factor_engine_llm_prompt.txt) | 纯文本版 |

---

## 6. 子目录 [`_refs/`](_refs/README.md)

- **外部参考摘录**（非本仓库规范正文）；详见该目录 README。

---

## 7. 与根 `README.md` 的关系

- 根目录 [`README.md`](../README.md) 提供 **项目总览、快速开始、数据集列表、项目结构树**；**细节** 以本 `docs/` 与各包 **`README.md`** 为准。
