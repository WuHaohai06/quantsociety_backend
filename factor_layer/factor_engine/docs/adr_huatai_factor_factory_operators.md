# ADR：华泰 GPT 因子工厂 2.0 算子与引擎的对照策略

## 状态

已采纳（文档命名约定；分钟类经 `INTRADAY_STUB_OPS` **受控** 扩展）。

## 背景

华泰证券研报《GPT 因子工厂 2.0：基本面与高频因子挖掘》（2024-09-26）给出 **PascalCase** 算子名与 **矩阵 / 季度 / 分钟序列** 语境。本引擎采用 **WorldQuant BRAIN 风格蛇形 DSL** 与 **`(timestamp, instrument)` MultiIndex** 面板。若把华泰名称逐一注册为独立 DSL 函数，易与现有算子 **语义重复**（同逻辑两名），或 **语义不同却名称相似**（季度 `Delay` vs `ts_delay`）。

## 决策

1. **单一规范名**：凡与现有 DSL **逻辑等价** 的华泰算子，**只**在 [`huatai_factor_factory_operator_catalog.md`](huatai_factor_factory_operator_catalog.md) 中维护 **华泰名 → 规范 DSL 名或组合式**，**不**新增重复 IR 算子。
2. **去重判定顺序**  
   - 查 [`build_dsl_allowlist()`](../api/operator_registry.py) 是否已有单算子；  
   - 再查是否可用 **组合表达式**（如 `add(rank(x), rank(y))`）；  
   - 仅当 **数学对象不同**（例如分钟成交子序列上的 `Agg_Explode_*`）才考虑未来新增 `Expr` / stub，且须单独 ADR。
3. **频率与契约冲突**：凡「**季度 vs bar**」「**矩阵 vs Series**」「**分钟序列 vs 日频面板**」须在 catalog 标为 **近似** 或 **无对应**，禁止在文档中宣称与华泰完全一致。
4. **华泰 PascalCase 不直接作为 DSL 函数名**：分钟类使用蛇形 `intraday_*_stub`（见 `INTRADAY_STUB_OPS`）；与 `Agg_Explode_*` 的对应写在各工厂 docstring。
5. **分钟占位已落地**：`expr/intraday.py`、`api/operators/intraday.py`、`ir/analyzer` 分支、`STUB_IR_OPS`；Pandas 仍为统一 `_stub`，待分钟 schema 后实装内核。

## 后果

- **正面**：避免 DSL 膨胀与 reviewer 混淆；来源与语义差异集中在一处维护。  
- **负面**：使用华泰原文写因子的用户须查阅 catalog；LLM 须被 Prompt 指向 catalog（见 [`factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md)）。

## 相关文档与代码

- [`huatai_factor_factory_operator_catalog.md`](huatai_factor_factory_operator_catalog.md)  
- [`expr/intraday.py`](../expr/intraday.py)、[`api/operators/intraday.py`](../api/operators/intraday.py) — 图表 11 类分钟序列占位（`INTRADAY_STUB_OPS`）  
- [`operators_roadmap.md`](operators_roadmap.md)  
- 研报 PDF：[`_refs/华泰因子工厂2.0.pdf`](_refs/华泰因子工厂2.0.pdf)
