# ADR：change_instrument（基准列）约定

> **第 7 版更改-shw**：新增短文，固定 ``change_instrument`` 与数据源契约，避免 silently 错配。

## 背景

研究报告与 Qlib 均提到在个股计算流中切换/对齐**基准标的**（指数、板块收益等）。本引擎用显式列名 ``benchmark_column`` 表达基准序列，而不在 DSL 内嵌 instrument id 注册表。

## 决策

1. **表达式**：``change_instrument(child, benchmark_column="...")`` 对 ``child`` 逐点除以与**时间戳对齐**的基准序列。
2. **基准列形态**  
   - **推荐**：与因子相同的 ``(timestamp, instrument)`` MultiIndex；同一 ``timestamp`` 下可有多行（多标的重复发布指数值）。  
   - **聚合**：对每个 ``timestamp`` 取该列值的 **算术均值** 得到标量 \(B_t\)，再广播到当日所有 ``(t, \*)`` 行。  
   - **单索引**：若基准列为单层 ``DatetimeIndex``，则直接 ``reindex`` 到因子的 ``timestamp`` 层级。
3. **除零**：基准为 0 的位置替换为 NaN，避免 Inf。
4. **非 MultiIndex 单列**：按单层索引对齐；若长度/时间戳与因子不一致，依赖 ``reindex`` 产生 NaN（需数据层保证质量）。

## 后果

- 与「全市场一张表」的 Parquet 字典模型兼容；指数可存为与普通标的相同的 schema。  
- 若需「固定单标的作基准」且表中仅一行/日，均值等价于该行。  
- **未覆盖**：分钟频与交易日历严格对齐、货币汇率转换等，仍在数据准备阶段处理。

## 相关实现

- ``expr/context.py``：``ChangeInstrument``  
- ``backend/pandas_backend.py``：``_op_change_instrument``  
