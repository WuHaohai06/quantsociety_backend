# `tests` — 测试套件（详尽说明）

本目录为 **pytest** 单元与集成测试，用于 **回归** `expr` → `ir` → `planner` → `backend` → `runtime` 全链路，以及 **回测**、**DSL**、**配置** 等。

### 协作者速览（约 5 分钟）

1. **本目录在干什么**：**行为规格** —— 改 `expr`/`backend`/DSL 时先看/补这里；失败即 **回归**。
2. **怎么跑**：仓库根 **`PYTHONPATH=. pytest tests/ -q`**；部分用例 **`importorskip`**（polars、modin、backtrader 等），未装依赖会 **跳过** 而非失败。
3. **从哪定位**：下面 **§2 按文件模式表**（`test_pandas_backend` 等）；**回测专项**在 monorepo [`../../../backtest_layer/tests/`](../../../backtest_layer/tests/)。
4. **真实数据**：**`test_real_data_factor_smoke`** 需显式环境变量与本地路径，默认 **不跑**。

---

## 1. 运行方式

在 **仓库根目录**：

```bash
PYTHONPATH=. pytest tests/ -q
```

- **覆盖率**：核心路径在 CI 中应全绿；部分测试 **`pytest.importorskip`**（polars、modin、bottleneck、backtrader）。  
- **真实数据**：`test_real_data_factor_smoke.py` 需 **`RUN_REAL_PARQUET_SMOKE=1`** 与本地数据路径。

---

## 2. 按文件/前缀分类（维护时快速定位）

| 文件模式 | 覆盖范围 |
|----------|----------|
| `test_expr.py` | 表达式树构造与属性 |
| `test_planner.py` | Lowerer、Optimizer、计划结构 |
| `test_backend.py` | Backend 抽象与入口 |
| `test_pandas_backend.py` | Pandas 主路径算子 |
| `test_polars_backend.py` | Polars 子集对齐 |
| `test_pandas_compat.py` | Modin / pandas 兼容 |
| `test_dsl_parser.py` | 字符串 DSL 白名单与解析 |
| `test_config_runtime.py` | YAML → `FactorEngineConfig` / `from_config` |
| `test_end_to_end.py` | 小样本端到端 |
| `test_cse_run_many.py` | 多因子 CSE 与 `run_many` |
| `test_operators_*.py` | 算术/时序/截面/逻辑/扩展/变换等 |
| `test_intraday_stub.py` / `test_operators_stub.py` | 占位算子行为 |
| `test_bottleneck_ts_roll.py` | Bottleneck 加速路径 |
| `test_trade_when_ts_hump.py` | `trade_when`、`ts_step`、`hump` |
| `test_factor_templates.py` | 多数据集模板参数化 |
| （回测） | 见 monorepo **`../../../backtest_layer/tests/test_backtest_*.py`**（需 **`backtrader`**：`pip install "factor-engine[backtest]"`） |
| `test_real_data_factor_smoke.py` | 真实 parquet（可选） |

---

## 3. [`helpers.py`](helpers.py)

- **内存数据源**、**合成 MultiIndex** 等夹具，减少测试对磁盘的依赖。

---

## 4. 编写新测试的建议

1. **算子新增**：在对应 **`test_operators_*`** 与 **`test_pandas_backend`** 增加最小复现。  
2. **DSL 新增**：更新 **`test_dsl_parser`** 白名单相关用例。  
3. **计划/CSE 变更**：**`test_cse_run_many`**、**`test_planner`**。  
4. **回测协议变更**：在 **`backtest_layer/tests/`**（如 **`test_backtest_report_schema`**）与契约常量对齐。

---

## 5. 延伸阅读

- 根 [`README.md`](../README.md)「运行测试」  
- 各包 [`README.md`](../docs/README.md)  
