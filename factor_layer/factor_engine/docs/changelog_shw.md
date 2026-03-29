# 变更记录（shw）

本文档按版本记录与 **WorldQuant BRAIN 风格算子库** 相关的代码与文档改动。每条均标注 **第 N 版更改-shw**，便于追溯。

---

## 第 1 版更改-shw

**内容**：确立算子分类与目录约定，不新增与现有 `expr` 重复的模块名。

- **`expr/`**：在既有 `arithmetic.py`、`logical.py`、`ts.py`、`cs.py` 上扩展表达式节点；**不**新增 `time_series.py` / `cross_sectional.py`；新增同级文件 `vector.py`、`transformational.py`、`group.py`（占位 Expr）。
- **`api/operators/`**：由单文件 `api/operators.py` 改为**包**，子模块与 expr 对齐：`arithmetic.py`、`logical.py`、`ts.py`、`cs.py`、`vector.py`、`transformational.py`、`group.py`，`__init__.py` 统一 re-export。
- **新增** [`api/operator_registry.py`](../api/operator_registry.py)：`build_dsl_allowlist()` 生成 DSL 白名单；`STUB_IR_OPS` 标明仅编译、Pandas 未实现的算子。
- **对外命名**：DSL/API 优先 WQ 蛇形名（如 `ts_std_dev`、`ts_delay`、`ts_max`、`ts_min`）；保留 `ts_std`、`delay` 等兼容别名。

---

## 第 2 版更改-shw

**内容**：编译链与 DSL 行为对齐新算子。

- **`ir/analyzer.py`**：为全部新 `Expr` 类型增加 `visit` 分支，输出 `IRNode`；滚动窗口属性统一使用 **`d`**（与 WQ 文档一致）；`TsStdDev` / `Delay` 等与旧类型兼容。
- **`api/dsl_parser.py`**：白名单改为从注册表构建；支持 **`ast.Compare`**（仅允许单段比较，不支持链式）；支持 **call 的 kwargs** 写入 IR `attrs`；逻辑算子在 Python 语法下使用 **`and_` / `or_` / `not_`**。

---

## 第 3 版更改-shw

**内容**：`PandasBackend` 扩展与占位策略。

- **`backend/pandas_backend.py`**：实现 Arithmetic / Logical / Time Series / Cross Sectional 下大量算子的 kernel；**`ts_max`、`ts_min`** 已实现；`ts_std_dev` 为主实现并注册 `ts_std` 别名；`nary_add` / `nary_mul` / `nary_sub` 及 `densify` 等。
- **依赖**：截面/时序 `quantile`（Gaussian）依赖 **scipy**，已写入 `pyproject.toml` 的 `[project.optional-dependencies] pandas`。
- **占位**：`vec_*`、`bucket`、`trade_when`、`group_*`、`ts_step`、`hump` 等在注册表中存在，执行时统一 **`NotImplementedError`**（说明见 `STUB_IR_OPS`）。  
  *（注：第 7 版起 **`group_*` 已在 Pandas 实装**，上句为第 3 版当时状态；当前占位集以仓库内 `STUB_IR_OPS` 为准。）*

---

## 第 4 版更改-shw

**内容**：测试与共享工具。

- **新增** [`tests/helpers.py`](../tests/helpers.py)：`InMemorySeriesSource`，供多测试复用。
- **新增** `tests/__init__.py`（包标识）。
- **新增** `test_operators_arithmetic.py`、`test_operators_logical.py`、`test_operators_ts.py`、`test_operators_cs.py`、`test_operators_stub.py`。
- **`test_pandas_backend.py`**：改为从 `tests.helpers` 引用 `InMemorySeriesSource`。

---

## 第 5 版更改-shw

**内容**：文档与 README 同步（本条及后续小节）。

- **新增** [`docs/operators_semantics.md`](operators_semantics.md)：Bar/日历语义、DSL 限制、scipy 依赖、占位算子列表。
- **新增** 本文档 [`docs/changelog_shw.md`](changelog_shw.md)。
- **更新** [`README.md`](../README.md)：`支持的算子` 与 `项目结构` 反映 `api/operators/` 包、注册表与新 expr 文件；增加文档索引链接。
- **更新** [`docs/factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md)：文首增加文档修订说明与算子文档指向。
- **更新** [`docs/massive_parquet_data_dictionary.md`](massive_parquet_data_dictionary.md)：文首增加与因子算子变更的交叉引用（数据字典本身无算子逻辑变更）。

---

## 第 6 版更改-shw

**内容**：为核心源码补充 **中文模块/类/关键函数注释**（`expr/`、`api/`、`ir/`、`planner/`、`backend/pandas_backend` 与 `debug_backend`、`runtime/engine` 等），便于快速理解职责与数据约定（MultiIndex、时序/截面分组）。

---

## 第 7 版更改-shw

**内容**：对照《算子库扩展与加速规划》落地 **路线图文档**、**清洗/技术指标/上下文** 算子、**group_* Pandas 实现**、**子树缓存 MVP**，并同步依赖与文档。

- **新增** [`docs/operators_roadmap.md`](operators_roadmap.md)：研究报告主题 ↔ 算子名 ↔ 实现状态表；可选加速依赖说明。
- **新增** [`docs/adr_context_benchmark.md`](adr_context_benchmark.md)：`change_instrument` 基准列 MultiIndex 与按日聚合约定。
- **`api/operator_registry.py`**：扩展 `BrainCategory`（`TECHNICAL` / `CLEANING` / `CONTEXT` 及远期枚举）；`STUB_IR_OPS` **移除** `group_*`（已可执行）。
- **新增** `expr/cleaning.py`、`expr/technical.py`、`expr/context.py` 与对应 `api/operators/*.py`；**`ir/analyzer.py`** 增加 visit 分支。
- **`backend/pandas_backend.py`**：实现上述 op 的 kernel；**`group_*`** 全套 kernel；**`ExecutionContext.cache`** 启用时按 **JSON 结构键** 做子树结果缓存（与 `CacheManager` 集成）。
- **`pyproject.toml`**：可选依赖组 **`accel`**（bottleneck、numba）、**`talib`**（TA-Lib）。
- **测试**：新增 [`tests/test_operators_extension.py`](../tests/test_operators_extension.py)；调整 `test_operators_stub.py`（`group_*` 不再属 stub）。
- **文档/README**：更新 [`operators_semantics.md`](operators_semantics.md)、[`README.md`](../README.md) 算子表、项目结构树与文档索引。

---

## 第 8 版更改-shw

**内容**：补齐与第 7 版实现不同步的文档与测试，避免「代码已实装、Prompt/历史条目仍写旧状态」。

- **[`docs/factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md)**：新增 **§5.4**（Group / 清洗 / 技术 / 上下文）与 **§5.5** 算术（原 5.4 顺延）；修正 **性能** 小节中关于 `enable_cache` 的表述（子树缓存 MVP）。
- **[`docs/factor_engine_llm_prompt.txt`](factor_engine_llm_prompt.txt)**：文首 **NOTE（第 7 版）**、算子字典新增同名扩展段、性能说明与 `.md` 对齐。
- **[`docs/changelog_shw.md`](changelog_shw.md)**：为 **第 3 版** 中「`group_*` 占位」补 **脚注**（标明为历史快照，当前以 `STUB_IR_OPS` 为准）。
- **[`README.md`](../README.md)**：`operator_registry` 一行注释改为 **STUB_IR_OPS** 表述，避免「全是占位」歧义。
- **测试**：[`tests/test_dsl_parser.py`](../tests/test_dsl_parser.py) 增加 `test_parse_expr_new_operators_v7`，覆盖新 DSL 函数解析。

---

## 第 9 版更改-shw

**内容**：**Bottleneck 可选滚动加速**（阶段 1）：`ts_mean` / `ts_max` / `ts_min` 在已安装 Bottleneck 且未设置 `FACTOR_ENGINE_DISABLE_BOTTLENECK=1` 时走 `move_*`，与 pandas `rolling` 结果对齐。

- **[`backend/pandas_backend.py`](../backend/pandas_backend.py)**：`_bottleneck_mod`、`_ts_roll_via_bottleneck`；上述三算子优先尝试 Bottleneck。
- **测试**：[`tests/test_bottleneck_ts_roll.py`](../tests/test_bottleneck_ts_roll.py)（`importorskip("bottleneck")`）。
- **[`docs/operators_roadmap.md`](operators_roadmap.md)**：Bottleneck 行改为「部分/可选（已接线）」。
- **[`README.md`](../README.md)**：可选依赖 `accel` / 环境变量说明一句。

---

## 第 10 版更改-shw

**内容**：**`bucket` / `trade_when` / `ts_step` / `hump`** 在 Pandas 实装；**`STUB_IR_OPS`** 仅余 `vec_*`；新增 ADR 与测试。

- **[`backend/pandas_backend.py`](../backend/pandas_backend.py)**：`_op_bucket`、`_op_trade_when`、`_op_ts_step`、`_op_hump`；`_as_bool_mask_scalar`。
- **[`api/operator_registry.py`](../api/operator_registry.py)**：从 `STUB_IR_OPS` 移除 `bucket`、`trade_when`、`ts_step`、`hump`。
- **[`expr/ts.py`](../expr/ts.py)** / **[`api/operators/ts.py`](../api/operators/ts.py)**：**`ts_step(d, anchor)`** 须显式传入 `anchor` 以对齐 MultiIndex。
- **ADR**：[`adr_trade_when.md`](adr_trade_when.md)、[`adr_ts_step_hump.md`](adr_ts_step_hump.md)。
- **文档**：[`operators_semantics.md`](operators_semantics.md)、[`factor_engine_llm_prompt` *.md/*.txt](factor_engine_llm_prompt.md)。
- **测试**：[`test_operators_transformational.py`](../tests/test_operators_transformational.py)、[`test_trade_when_ts_hump.py`](../tests/test_trade_when_ts_hump.py)；[`test_operators_stub.py`](../tests/test_operators_stub.py) 仅保留 `vec_avg` 占位编译测。

---

## 第 11 版更改-shw

**内容**：**`vec_avg` / `vec_sum` 路径 B**（阶段 5）— 暂不实现标量列上的假向量语义；在路线图与语义文档中写明 **需 Parquet 向量列 / object ndarray 契约** 后再实装。

- **[`docs/operators_roadmap.md`](operators_roadmap.md)**：新增「向量算子」行（路径 B）。
- **[`README.md`](../README.md)**：支持的算子段补充一句。

---

## 第 12 版更改-shw

**内容**：**PolarsBackend 核心子集**（阶段 6）：长表执行 `column` / `literal` / `add` `sub` `mul` `div` / `rank` / `ts_mean`，结果转回 pandas MultiIndex Series。

- **[`backend/polars_backend.py`](../backend/polars_backend.py)**：重写递归求值与 `_series_to_long` / `_long_to_series`。
- **测试**：[`tests/test_polars_backend.py`](../tests/test_polars_backend.py)（`importorskip("polars")`）。

---

## 第 13 版更改-shw

**内容**：**远期数据层算子占位**（阶段 7）：微观结构 / 基本面 / 另类各 1 个 Expr + IR + DSL + Pandas stub，**不假装有 LOB/PiT 数据**。

- **新增** `expr/microstructure.py`、`expr/fundamental.py`、`expr/alternative.py`；[`api/operators/future_data.py`](../api/operators/future_data.py)；`STUB_IR_OPS` 增加 `lob_ofi_stub`、`fundamental_ttm_stub`、`alt_sentiment_stub`。
- **[`ir/analyzer.py`](../ir/analyzer.py)**、[`operator_registry.py`](../api/operator_registry.py) 接线。
- **[`docs/operators_roadmap.md`](operators_roadmap.md)**：标明「仅接口 stub」行。

---

## 第 14 版更改-shw

**内容**：**`sin` / `cos`** 与 **Joblib 多因子并行示例**（阶段 8）；**Welford / RLS 显式算子**仍延期（与内部滚动优化合并评估）。

- **算术**：`expr/arithmetic.py` `Sin`/`Cos`；`api/operators/arithmetic.py`；`PandasBackend` 一元 `np.sin`/`np.cos`；**Polars** 同步子集。
- **示例**：[`examples/run_factors_joblib.py`](../examples/run_factors_joblib.py)。

---

## 第 15 版更改-shw

**内容**：为 **难理解算子** 加长 **中文 docstring / 模块说明**（不改数值语义），便于阅读源码与 IDE 悬停即懂；行为与测试不变。

- **Expr**：[`expr/transformational.py`](../expr/transformational.py)（`Bucket` / `TradeWhen`）、[`expr/ts.py`](../expr/ts.py)（`TsStep` / `Hump` / `TsRegression` / `TsQuantile` / `TsDecayLinear` / `KthElement` / `LastDiffValue` / `TsBackfill`）、[`expr/group.py`](../expr/group.py)（各 `Group*`）、[`expr/cs.py`](../expr/cs.py)（`CsQuantile` / `Scale`）、[`expr/logical.py`](../expr/logical.py)（模块说明 / `IfElse`）、[`expr/context.py`](../expr/context.py)（`Orthogonalize` / `ChangeInstrument`）、[`expr/microstructure.py`](../expr/microstructure.py) 等远期占位。
- **API**：[`api/operators/transformational.py`](../api/operators/transformational.py)、[`api/operators/ts.py`](../api/operators/ts.py)、[`api/operators/cs.py`](../api/operators/cs.py)、[`api/operators/group.py`](../api/operators/group.py)、[`api/operators/future_data.py`](../api/operators/future_data.py)。
- **后端**：[`backend/pandas_backend.py`](../backend/pandas_backend.py) 中 `_as_bool_mask*`、`_op_bucket` / `_op_trade_when` / `_op_ts_step` / `_op_hump` 的说明性 docstring。

---

## 第 16 版更改-shw

**内容**：**研究导向算子扩充**：技术指标（通道、波动、动量、成交量、Overlap 均线族）+ 截面 **`neutralize`** + 时序 **`ts_skew` / `ts_kurt`**；TA-Lib 优先、pandas/numpy 退化；DSL 白名单与测试同步。

- **Expr**：[`expr/technical.py`](../expr/technical.py)（`TsAtr`/`TsNatr`/`TsTrange`/`TsDonchian`/`TsKeltner`/`TsMaEnvelope`/`TsMacd`/`TsCci`/`TsStoch`/`TsWillr`/`TsRoc`/`TsObv`/`TsMfi`/`TsDema`/`TsWma`/`TsKama`）；[`expr/cs.py`](../expr/cs.py) `Neutralize`；[`expr/ts.py`](../expr/ts.py) `TsSkew`/`TsKurt`。
- **IR / API**：[`ir/analyzer.py`](../ir/analyzer.py)；[`api/operators/technical.py`](../api/operators/technical.py)、[`cs.py`](../api/operators/cs.py)、[`ts.py`](../api/operators/ts.py)、[`operator_registry.py`](../api/operator_registry.py)、[`api/operators/__init__.py`](../api/operators/__init__.py)。
- **后端**：[`backend/pandas_backend.py`](../backend/pandas_backend.py)（`_wilder_tr_arr`/`_wilder_atr_arr`/`_eval_hlc_series` 与各 `_op_ts_*`、`_op_neutralize`）。
- **测试**：[`tests/test_operators_extension.py`](../tests/test_operators_extension.py)、[`tests/test_dsl_parser.py`](../tests/test_dsl_parser.py)。
- **文档**：[`operators_semantics.md`](operators_semantics.md)、[`operators_roadmap.md`](operators_roadmap.md)、[`README.md`](../README.md)。

---

## 第 17 版更改-shw

**内容**：**远期 stub 大规模扩充**（仍不实现数值内核）：基本面 / 另类 / 微观结构统一为 **单 child + IR `op` 字符串**，`STUB_IR_OPS` 与 `expr` 侧 `*_STUB_OPS` 常集对齐；`PandasBackend` 对 `STUB_IR_OPS` 整集注册 `_stub`。

- **Expr**：[`expr/fundamental.py`](../expr/fundamental.py) `FundamentalStub` + `FUNDAMENTAL_STUB_OPS`；[`expr/alternative.py`](../expr/alternative.py) `AlternativeStub` + `ALTERNATIVE_STUB_OPS`；[`expr/microstructure.py`](../expr/microstructure.py) `MicrostructureStub` + `MICROSTRUCTURE_STUB_OPS`（取代原先各单类 Stub 的 IR 分支写法）。
- **API / IR**：[`api/operators/future_data.py`](../api/operators/future_data.py) 工厂函数全集；[`ir/analyzer.py`](../ir/analyzer.py)；[`api/operator_registry.py`](../api/operator_registry.py)；[`api/operators/__init__.py`](../api/operators/__init__.py) 动态 re-export。
- **后端**：[`backend/pandas_backend.py`](../backend/pandas_backend.py) `for op in STUB_IR_OPS`。
- **测试**：[`tests/test_operators_stub.py`](../tests/test_operators_stub.py) 对 `STUB_IR_OPS` 参数化；[`tests/test_dsl_parser.py`](../tests/test_dsl_parser.py) 增补解析样例。
- **文档**：[`operators_semantics.md`](operators_semantics.md)、[`operators_roadmap.md`](operators_roadmap.md)、[`factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md) / [`.txt`](factor_engine_llm_prompt.txt)、[`README.md`](../README.md)。

---

## 第 18 版更改-shw

**内容**：**技术指标第二波**：ADX/Aroon、Chaikin `ts_ad`/`ts_adosc`、`ts_sar`（无 TA-Lib 时为简化 PSAR）、`ts_cmo`、`ts_ppo`/`ts_apo`、`ts_ultosc`、`ts_stochrsi`、`ts_tema`/`ts_trima`/`ts_t3`；TA-Lib 优先，pandas/numpy 退化。

- **Expr / API**：[`expr/technical.py`](../expr/technical.py)；[`api/operators/technical.py`](../api/operators/technical.py)；[`ir/analyzer.py`](../ir/analyzer.py)；[`api/operator_registry.py`](../api/operator_registry.py)；[`api/operators/__init__.py`](../api/operators/__init__.py)。
- **后端**：[`backend/pandas_backend.py`](../backend/pandas_backend.py)（`_numpy_adx_line`、`_numpy_aroon`、`_chaikin_ad_from_hlcv`、`_numpy_sar`、`_numpy_ultosc`、`_numpy_t3_close` 与各 `_op_ts_*`）。
- **测试 / 文档**：[`tests/test_operators_extension.py`](../tests/test_operators_extension.py)、[`tests/test_dsl_parser.py`](../tests/test_dsl_parser.py)；[`operators_semantics.md`](operators_semantics.md)、[`operators_roadmap.md`](operators_roadmap.md)、[`README.md`](../README.md)。

---

## 第 19 版更改-shw

**内容**：**技术指标第三批**：`ts_bop`（open 用上一根 close 近似）、`ts_mom`、`ts_stochf`（`line=fastk|fastd`）、`ts_trix`、`ts_adxr`、`ts_dx`、`ts_rocr` / `ts_rocr100`、`ts_linearreg_slope` / `ts_linearreg_angle`；TA-Lib 优先，pandas/numpy 退化。

- **Expr / API**：[`expr/technical.py`](../expr/technical.py)；[`api/operators/technical.py`](../api/operators/technical.py)；[`ir/analyzer.py`](../ir/analyzer.py)；[`api/operator_registry.py`](../api/operator_registry.py)；[`api/operators/__init__.py`](../api/operators/__init__.py)。
- **后端**：[`backend/pandas_backend.py`](../backend/pandas_backend.py)（`_dmi_wilder_di_dx`、`_numpy_adxr`、滚动线性回归辅助与各 `_op_ts_*`）。
- **测试 / 文档**：[`tests/test_operators_extension.py`](../tests/test_operators_extension.py)、[`tests/test_dsl_parser.py`](../tests/test_dsl_parser.py)；[`operators_semantics.md`](operators_semantics.md)、[`operators_roadmap.md`](operators_roadmap.md)、[`README.md`](../README.md)、[`factor_engine_llm_prompt.md`](factor_engine_llm_prompt.md) / [`.txt`](factor_engine_llm_prompt.txt)。

---

*若后续继续迭代算子实现，请在本文件追加「第 20 版更改-shw」及之后条目。*
