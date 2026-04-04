# 华泰 GPT 因子工厂 2.0 ↔ 本引擎算子对照目录

> **来源**：华泰证券研究报告《GPT 因子工厂 2.0：基本面与高频因子挖掘》（金工深度研究，**2024-09-26**）。算子原文见报告 **图表 9（基本面因子算子）**、**图表 10（高频底层字段）**、**图表 11（高频算子）**。本地 PDF：`[docs/_refs/华泰因子工厂2.0.pdf](_refs/华泰因子工厂2.0.pdf)`。  
> **命名规范**：本引擎以 **WorldQuant BRAIN 风格蛇形名**（`ts_mean`、`rank`、`group_rank`…）为 **规范 DSL 名**；华泰原文为 PascalCase / 矩阵语境，**不**作为 DSL 函数名单独注册（避免「同逻辑两名」）。  
> **去重规则**：见 [`adr_huatai_factor_factory_operators.md`](adr_huatai_factor_factory_operators.md)。  
> **代码落点**：华泰可映射的语义写在各 ``api/operators/*.py`` / ``expr/*.py`` 的 **docstring**；图表 11 分钟类占位见 ``expr/intraday.py``、``api/operators/intraday.py``（``INTRADAY_STUB_OPS`` ⊆ ``STUB_IR_OPS``）。

## 图例（映射类型）


| 映射类型       | 含义                                                       |
| ---------- | -------------------------------------------------------- |
| **等价**     | 在引擎支持的输入契约下，与华泰定义一致或可用单算子直接表达。                           |
| **组合等价**   | 无单独 DSL 名，用 **组合表达式** 表达（不新增 IR 算子）。                     |
| **近似**     | 数学形式相近，但 **频率轴、对齐或窗口语义** 与研报不一致，须在因子解释中说明。               |
| **仅 stub** | DSL 可解析，Pandas 执行 `NotImplementedError`，待数据契约与内核。        |
| **无对应**    | 引擎当前 **无一等公民类型**（如分钟成交子序列上的 Agg/Agg_Explode）；见路线图「需数据层」。 |


---

## 一、图表 9：基本面因子算子列表

**语境（研报）**：`X` 为 **DataFrame 矩阵**；`Delay`/`TS_`* 中 **d 为季度**；`YOY`/`QOQ` 为 **财报维度同比/环比**。  
**本引擎语境**：因子为 `**(timestamp, instrument)` MultiIndex** 上的 **Series** 管道；`ts_`* 的 `d` 为 **bar 数**（交易日/日 K 等），**非自动「季度」**。


| 华泰名称                             | 华泰分类 | 引擎规范名 / 组合                                     | 映射类型    | 频率与数据契约                               | 语义摘要与差异                                   |
| -------------------------------- | ---- | ---------------------------------------------- | ------- | ------------------------------------- | ----------------------------------------- |
| `YOY(X)`                         | 元素   | `fundamental_yoy_stub(col("x"))`               | 仅 stub  | 财报季、双时态对齐；需 PiT 面板                    | 研报为矩阵同比；引擎为 **占位 stub**，无 TTM/YoY 数值内核。   |
| `QOQ(X)`                         | 元素   | `fundamental_qoq_stub(col("x"))`               | 仅 stub  | 同上                                    | 同上。                                       |
| `Inv(X)`                         | 元素   | `inverse(col("x"))`                            | 等价      | 逐点                                    | 倒数；DSL 为 `inverse`。                       |
| `Abs(X)`                         | 元素   | `abs_(col("x"))`                               | 等价      | 逐点                                    | DSL 名为 `abs`。                             |
| `Sign(X)`                        | 元素   | `sign(col("x"))`                               | 等价      | 逐点                                    | —                                         |
| `Log(X)`                         | 元素   | `log(col("x"))`                                | 等价      | 逐点                                    | 自然对数。                                     |
| `Exp(X)`                         | 元素   | —                                              | **无对应** | 逐点                                    | 引擎 **无** 独立 `exp` DSL；自然指数需后续扩展或用数据层预计算列。 |
| `Sqrt(X)`                        | 元素   | `sqrt(col("x"))`                               | 等价      | 逐点                                    | —                                         |
| `Pow(X, y)`                      | 元素   | `power(col("x"), col("y"))`                    | 等价      | 逐点                                    | 研报为标量/矩阵幂；引擎为逐点 `Pow`。                    |
| `Delay(X, d)`                    | 元素   | `ts_delay(col("x"), d)` 或 `delay(col("x"), d)` | 近似      | 研报：**过去第 d 个季度**；引擎：**过去 d 根 bar**    | 对齐方式不同；基本面季度延迟应对齐披露日历，见基本面 stub 路线。       |
| `CS_Rank(X)`                     | 截面   | `rank(col("x"))`                               | 等价      | 每个 `timestamp` 横截面                    | 分位秩 [0,1]。                                |
| `CS_Indus_Rank(X, indus_belong)` | 截面   | `group_rank(col("x"), col("indus_belong"))`    | 等价      | 需 **行业/组 id 列**                       | 组内分位秩；`group` 列即 `indus_belong`。          |
| `Add(X,Y)` … `Div(X,Y)`          | 关系   | `add` / `subtract` / `multiply` / `divide`     | 等价      | 逐点                                    | DSL：`add`、`subtract`、`multiply`、`divide`。 |
| `Rank_Add(X,Y)`                  | 关系   | `add(rank(col("x")), rank(col("y")))`          | 组合等价    | 截面 rank 后逐点加                          | 与研报「分位数和」一致时不新增 `rank_add` op。            |
| `Rank_Sub(X,Y)`                  | 关系   | `subtract(rank(col("x")), rank(col("y")))`     | 组合等价    | 同上                                    | —                                         |
| `Rank_Mul(X,Y)`                  | 关系   | `multiply(rank(col("x")), rank(col("y")))`     | 组合等价    | 同上                                    | `multiply` 为 nary 包装。                     |
| `Rank_Div(X,Y)`                  | 关系   | `divide(rank(col("x")), rank(col("y")))`       | 组合等价    | 同上                                    | 注意除零与 NaN。                                |
| `TS_Corr(X,Y,d)`                 | 时序   | `ts_corr(col("x"), col("y"), d)`               | 近似      | 研报：过去 **d 季度**；引擎：**过去 d 根 bar** 滚动相关 | 窗口语义须一致时再可比。                              |
| `TS_Std(X,d)`                    | 时序   | `ts_std_dev(col("x"), d)` 或 `ts_std`           | 近似      | 同上                                    | 标准差；别名见 `operators_semantics`。            |
| `TS_Min(X,d)`                    | 时序   | `ts_min(col("x"), d)`                          | 近似      | 同上                                    | —                                         |
| `TS_Max(X,d)`                    | 时序   | `ts_max(col("x"), d)`                          | 近似      | 同上                                    | —                                         |
| `TS_Mean(X,d)`                   | 时序   | `ts_mean(col("x"), d)`                         | 近似      | 同上                                    | —                                         |
| `TS_Sum(X,d)`                    | 时序   | `ts_sum(col("x"), d)`                          | 近似      | 同上                                    | —                                         |


**来源**：图表 9；资料来源标注：Wind，华泰研究。

---

## 二、图表 10：高频因子底层字段

**非算子**：为 GPT 挖掘时的 **原始列名** 约定，与本引擎 **列名字符串**（`col("OPEN")` 等）对应即可；需保证数据管线里存在同名字段（大小写一致）。


| 字段                                | 含义   |
| --------------------------------- | ---- |
| `OPEN` / `HIGH` / `LOW` / `CLOSE` | 开高低收 |
| `AMOUNT`                          | 成交额  |
| `VOLUME`                          | 成交量  |
| `ITEMS`                           | 成交笔数 |


**来源**：图表 10。

---

## 三、图表 11：高频因子挖掘算子列表

**语境（研报）**：`X` 为 **DataFrame 矩阵**；**聚合 / 聚合展开** 面向 **分钟或更细序列**（如 `Agg_Explode_Return` 明确定义为 **分钟收益率**）。  
**本引擎**：主路径为 **日频 (timestamp, instrument) 面板**；**无** 内置「单标的内成交笔序列 → Agg → 再日频化」的统一样式算子。

### 3.1 元素与关系（与图表 9 重叠部分）


| 华泰名称           | 华泰分类 | 引擎规范名 / 组合                                 | 映射类型 | 说明                    |
| -------------- | ---- | ------------------------------------------ | ---- | --------------------- |
| `Abs` … `Sqrt` | 元素   | 同图表 9                                      | 等价   | 与基本面表重复，**不重复登记 IR**。 |
| `Add` … `Div`  | 关系   | `add` / `subtract` / `multiply` / `divide` | 等价   | 同上。                   |
| `Exp(X)`       | 元素   | —                                          | 无对应  | 同图表 9。                |


### 3.2 聚合算子 `Agg_`*

**含义（研报）**：对「序列 X」做 **单序列统计量**（在报告的高频管线中，该序列通常为 **日内/分钟内** 采样序列）。  


| 华泰名称                                                                                  | 引擎侧                                    | 映射类型    | 说明                                                                                                         |
| ------------------------------------------------------------------------------------- | -------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------- |
| `Agg_Std` / `Agg_Var` / `Agg_Mean` / `Agg_Median` / `Agg_Sum` / `Agg_Max` / `Agg_Min` | —                                      | **无对应** | 非日频 MultiIndex 上单一 `ts_`* 可替代；需 **intraday schema + 内核**（见 ADR 第二阶段）。                                      |
| `Agg_Argmax` / `Agg_Argmin`                                                           | `ts_arg_max` / `ts_arg_min`            | **近似**  | 引擎为 **时间轴上 rolling arg 位置**；研报为 **单段序列内位置**，对象不一致。                                                         |
| `Agg_Skew` / `Agg_Kurt`                                                               | `ts_skew` / `ts_kurt`                  | **近似**  | 引擎为 **滚动窗口内** 偏度/峰度；频率轴需对齐。                                                                                |
| `Agg_Corr(X,Y)`                                                                       | `ts_corr(col("x"), col("y"), d)`       | **近似**  | 需指定 `d`；非单序列二元 Agg。                                                                                        |
| `Agg_Cov(X,Y)`                                                                        | `ts_covariance(col("x"), col("y"), d)` | **近似**  | 引擎为 **滚动协方差**（需窗口 `d`）；研报为单段序列协方差，对象与频率可能不同。                                                               |
| `Agg_Quantile(X,q)`                                                                   | `ts_quantile(col("x"), d, driver=...)` | **近似**  | 引擎 `ts_quantile` 为 **滚动经验分位 + driver 变换**（默认 gaussian），**无** 与 `q` 一一对应的「原始分位数」参数；与研报单序列 `q` 分位 **不完全等价**。 |


### 3.3 聚合展开算子 `Agg_Explode_`*


| 华泰名称                                                                                                                                                | 映射类型    | 说明                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Agg_Explode_Return` / `Cumsum` / `Cumprod` / `Cummin` / `Cummax` / `Ewmmean` / `Ewmstd` / `Ewmvar` / `Rolling*` / `Rollingsum` / `Rollingquantile` | **无对应** | 分钟级展开与滚动；依赖 **分钟线 schema 与执行语义**，当前 **未** 注册 DSL 名（避免与 `ts_`* 日频重复）。第二阶段见 `[adr_huatai_factor_factory_operators.md](adr_huatai_factor_factory_operators.md)`。 |


### 3.4 采样算子


| 华泰名称                      | 映射类型    | 说明                 |
| ------------------------- | ------- | ------------------ |
| `Tp_Sample(X, h=15, m=0)` | **无对应** | 特定时点采样；需专用数据与 ADR。 |


**来源**：图表 11；资料来源：华泰研究。

---

## 四、与《因子引擎+AI表达式撰写任务需求汇总》的关系

该 PDF 描述的是 **工程流程**（数据落盘、DSL→DAG、`**filter(sum(...))` 向量化拆分**、并发调度等），**不是**华泰算子表。  
能力对照请见 `[operators_roadmap.md](operators_roadmap.md)` 与执行器相关 ADR（若有）；**不**在本目录逐条映射为算子名。

---

## 五、与 `BrainCategory` 的分类对应（文档级）

本目录「华泰分类」与引擎 `[BrainCategory](../api/operator_registry.py)` 大致对应关系：


| 华泰研报分类                                   | 引擎侧归类（文档）                                    |
| ---------------------------------------- | -------------------------------------------- |
| 元素（YOY/Inv/…）                            | `ARITHMETIC` / `FUNDAMENTAL`（stub）           |
| 截面 `CS_`*                                | `CROSS_SECTIONAL` / `GROUP`（组内 rank）         |
| 关系 `Add`/`Rank_*`                        | `ARITHMETIC`（组合）                             |
| 时序 `TS_*`                                | `TIME_SERIES`                                |
| 高频 `Agg*` / `Agg_Explode*` / `Tp_Sample` | 需数据层；可与 `MICROSTRUCTURE` 或未来 `intraday` 文档并列 |


---

## 六、维护与校验

- 算子实现以 [`api/operator_registry.py`](../api/operator_registry.py) 与 `build_dsl_allowlist()` 为准。  
- **分钟类 stub** 以 ``expr.intraday.INTRADAY_STUB_OPS`` 与 ``api/operators/intraday.py`` 为准；变更时请同步本表并跑 ``tests/test_intraday_stub.py``。  
- 若本表与代码冲突，**更新本表或代码**并记入 [`changelog_shw.md`](changelog_shw.md)。  
- PDF 文本抽取可能有个别错字，**以扫描版图表 9/11 为准**。

