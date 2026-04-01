# Factor Engine

可扩展的量化因子引擎框架，支持表达式树构建、编译优化、多后端执行与配置驱动运行。

**文档索引**：算子语义与 DSL 约定见 [`docs/operators_semantics.md`](docs/operators_semantics.md)；Deep Research 对照路线图见 [`docs/operators_roadmap.md`](docs/operators_roadmap.md)；按版本整理的改动说明见 [`docs/changelog_shw.md`](docs/changelog_shw.md)（含 **第 N 版更改-shw** 标注）。

> **第 5 版更改-shw**：更新「支持的算子」「项目结构」与 `docs/` 索引，以反映 `api/operators/` 包、算子注册表及 WQ 风格扩展；细节仍以 `changelog_shw.md` 分版条为准。

> **第 7 版更改-shw**：落地 **清洗 / 技术指标 / 上下文 / group_*** 与 **子树缓存 MVP**；README 本节与结构树同步，详见 `changelog_shw.md`「第 7 版」。

> **第 8 版更改-shw**：对齐 **`docs/factor_engine_llm_prompt`（.md / .txt）** 中算子字典与 **`enable_cache`** 说明；**`test_dsl_parser`** 覆盖新 DSL；`changelog` 为第 3 版 **`group_*` 占位** 补历史脚注。详见 `changelog_shw.md`「第 8 版」。

> **第 9 版更改-shw**：**Bottleneck** 加速 `ts_mean` / `ts_max` / `ts_min`（安装 `factor-engine[accel]` 后生效）；可用环境变量 **`FACTOR_ENGINE_DISABLE_BOTTLENECK=1`** 对照测试或与 pandas 完全一致路径。详见 `changelog_shw.md`「第 9 版」。

> **第 10–14 版更改-shw**：`bucket` / `trade_when` / `ts_step(d,anchor)` / `hump` 已在 Pandas 实装；**`vec_avg` / `vec_sum`** 按路线图 **路径 B** 暂缓（需向量列契约）；**PolarsBackend** 子集（`column` / `literal` / 四则 / `rank` / `ts_mean` / `sin` / `cos`）；远期 **数据层 `*_stub`**（基本面 / 另类 / 微观，见 `api/operator_registry.STUB_IR_OPS`）仅编译 + stub；**`sin` / `cos`** 与 **Joblib** 多因子示例见 `examples/run_factors_joblib.py`。详见 `changelog_shw.md`。

> **第 15 版更改-shw**：为 `bucket` / `trade_when` / `ts_step` / `hump`、`ts_regression` / `ts_quantile`、`group_*`、`orthogonalize` / `change_instrument` 及远期 stub 等 **加长源码内中文说明**（`expr/`、`api/operators/`、`pandas_backend` 相关 docstring）。详见 `changelog_shw.md`「第 15 版」。

> **第 16 版更改-shw**：**技术指标大扩展**（`ts_atr`/`ts_donchian`/`ts_keltner`/`ts_macd`/`ts_cci`/`ts_stoch`/`ts_obv`/`ts_mfi`/`ts_dema` 等，见 `operators_semantics.md`）；**`neutralize`**（截面 OLS 残差）；**`ts_skew`/`ts_kurt`**。详见 `changelog_shw.md`「第 16 版」。
> **第 18 版更改-shw**：**技术指标第二波**（`ts_adx`/`ts_aroon`/`ts_ad`/`ts_adosc`/`ts_sar`/`ts_cmo`/`ts_ppo`/`ts_apo`/`ts_ultosc`/`ts_stochrsi`/`ts_tema`/`ts_trima`/`ts_t3`）。详见 `changelog_shw.md`「第 18 版」。

> **第 19 版更改-shw**：**技术指标第三批**（`ts_bop`/`ts_mom`/`ts_stochf`/`ts_trix`/`ts_adxr`/`ts_dx`/`ts_rocr`/`ts_rocr100`/`ts_linearreg_slope`/`ts_linearreg_angle`）。详见 `changelog_shw.md`「第 19 版」。

---

## 快速开始

```python
from api.columns import col
from api.operators import rank, ts_mean
from api.factor import Factor
from backend.pandas_backend import PandasBackend
from runtime.engine import FactorEngine
from storage.kline_parquet_source import KlineParquetSource

source = KlineParquetSource(root="/data/us_stocks_sip/day_aggs_v1", max_files=5)
engine = FactorEngine(backend=PandasBackend(), data_source=source)

factor = Factor(name="mom3_rank", expr=rank(ts_mean(col("close"), 3)))
result = engine.run(factor)
print(result["result"].head())
```

---

## 配置驱动运行

引擎支持通过 YAML 文件描述因子和数据源，无需编写 Python 代码即可运行。

**步骤：**
1. 编写包含 `factor`、`data_source`、`backend`、`engine` 四个字段的 YAML 文件。
2. 调用 `FactorEngine.run_from_config(path)` 或 `FactorEngine.from_config(path)` 获取引擎实例。

如果希望配置文件直接完成计算到落盘，可以额外添加 `materialization` 段，然后调用 `FactorEngine.materialize_from_config(path)`，或运行 [examples/materialize_from_config.py](/home/yluel/share/projects/quantsociety_backend_project/factor_layer/factor_engine/examples/materialize_from_config.py)。

**支持的数据源类型：**

| 类型 | 说明 |
|---|---|
| `parquet_kline` | K线格式 parquet，适用于 `us_stocks_sip` |
| `multi_parquet` | 通用多文件 parquet，适用于各类 fundamentals |
| `parquet` | 单文件或简单目录 parquet |
| `cleaned_parquet` | 清洗层标准 parquet，默认读取 `align_time` + `ticker` |
| `composite` | 组合数据源，以锚点源为基准对齐其他数据源的列空间 |

**配置示例（日K线动量因子）：**

```yaml
factor:
  name: day_aggs_rank_ts_mean_close_3
  expr: rank(ts_mean(col("close"), 3))
  freq: 1d
  universe: equities
  description: 日K线 - 3日收盘价均线截面排名，动量方向因子

data_source:
  type: parquet_kline
  root: /data/us_stocks_sip/day_aggs_v1
  instrument_column: ticker
  timestamp_column: window_start
  fields:
    close: close
  max_files: 5

backend:
  type: pandas

engine:
  enable_cache: true
```

**配置示例（fundamentals 基本面因子）：**

```yaml
factor:
  name: balance_sheet_rank_total_assets
  expr: rank(col("total_assets"))
  freq: 1d
  description: 资产负债表 - 总资产截面排名，越高代表规模越大

data_source:
  type: multi_parquet
  root: /data/fundamentals/balance_sheet
  timestamp_col: period_end
  instrument_col: tickers
  max_files: 3

backend:
  type: pandas
```

**配置示例（cleaned parquet 单数据源）：**

```yaml
factor:
  name: cleaned_day_aggs_rank_close
  expr: rank(col("close"))
  freq: 1d

data_source:
  type: cleaned_parquet
  root: /data/cleaned_massive_data/us_stocks_sip/day_aggs_v1
  # 默认使用 align_time / ticker，也可显式覆盖：
  # timestamp_col: align_time
  # instrument_col: ticker

backend:
  type: pandas
```

**配置示例（配置到落盘）：**

```yaml
factor:
  name: cleaned_day_aggs_rank_ts_mean_close_3_v1
  expr: rank(ts_mean(col("close"), 3))
  freq: 1d

data_source:
  type: cleaned_parquet
  root: /data/cleaned_massive_data/us_stocks_sip/day_aggs_v1

backend:
  type: pandas

engine:
  enable_cache: true

materialization:
  lake_root: /tmp/factor_engine_demo_lake
  factor_id: cleaned_day_aggs_rank_ts_mean_close_3_v1
  description: 配置驱动计算到落盘示例
```

执行方式：

```bash
cd factor_layer/factor_engine
python examples/materialize_from_config.py examples/config_driven_materialize_factor.yaml
```

**配置示例（锚定日线价格并拼接基本面列空间）：**

```yaml
factor:
  name: day_aggs_close_over_pe
  expr: col("close") / col("pe")
  freq: 1d

data_source:
  type: composite
  anchor: price
  anchor_column: close
  aliases:
    pe: fundamental.price_to_earnings
  sources:
    price:
      type: cleaned_parquet
      root: /data/cleaned_massive_data/us_stocks_sip/day_aggs_v1
    fundamental:
      type: multi_parquet
      root: /data/fundamentals/financials_ratios
      timestamp_col: date
      instrument_col: ticker
  joins:
    fundamental:
      method: asof_backward

backend:
  type: pandas

engine:
  enable_cache: true
```

`examples/configs/` 目录下收录了覆盖全部 11 个数据集的配置文件（见下文[数据集列表](#数据集列表)）。这些配置现在默认使用 `cleaned_parquet` 数据源风格，并额外包含可选的 `materialization` 段，可直接用于 `FactorEngine.materialize_from_config()`。

---

## 支持的算子

引擎已按 **WorldQuant BRAIN** 风格扩展算子：Arithmetic / Logical / Time Series / Cross Sectional 在 `PandasBackend` 中已实现；**Group（`group_*`）**、**清洗**、**技术指标**、**上下文**同上。**Transformational**：`bucket`、`trade_when` 已可执行；**`ts_step` / `hump`** 已实装（API 与语义见 `docs/operators_semantics.md` 与 ADR）。**`sin` / `cos`** 已实装。**Vector**：`vec_avg` / `vec_sum` 仍为占位（需向量列数据契约，见路线图路径 B）。**远期数据层**：`fundamental_*_stub` / `alt_*_stub` / `micro_*_stub` / `lob_ofi_stub` 等（`STUB_IR_OPS`）仅接口占位。**PolarsBackend** 支持上述子集，其余算子仍会报错。

**常用示例**：

| 算子 | 类型 | 说明 |
|---|---|---|
| `col("field")` | 引用 | 读取数据源中的一列 |
| `rank(x)` | 截面 | 每个时间截面内百分位排名 [0,1] |
| `zscore(x)` | 截面 | 每个时间截面内 Z-score 标准化 |
| `ts_mean(x, d)` | 时序 | 滚动均值（窗口 `d` 为 bar 数） |
| `ts_std_dev(x, d)` / `ts_std(x, d)` | 时序 | 滚动标准差（别名兼容） |
| `ts_max(x, d)` / `ts_min(x, d)` | 时序 | 滚动最大/最小 |
| `ts_delay(x, d)` / `delay(x, periods)` | 时序 | 滞后 |
| `group_rank(x, g)` 等 | 分组 | 同日同组内排名/中性化/Z-score 等（≈ 行业中性可参考 `group_neutralize`） |
| `pasteurize` / `protected_div` 等 | 清洗 | Inf/除零安全，便于自动挖掘 |
| `ts_sma` / `ts_rsi` / `ts_bbands` 等 | 技术指标 | 可选 TA-Lib 加速 |
| `orthogonalize` / `change_instrument` | 上下文 | 截面正交化、相对基准列 |
| 四则运算 `+ - * /` | 算术 | 逐元素运算；多元可用 `add`/`multiply`/`subtract` 等 |
| `sin(x)` / `cos(x)` | 算术 | 逐元素三角函数（DSL：`sin` / `cos`） |
| `ts_atr` / `ts_adx` / `ts_dx` / `ts_aroon` / `ts_ad` / `ts_sar` / `ts_macd` / `ts_ppo` / `ts_t3` / `ts_bop` / `ts_rocr` / `neutralize` 等 | 技术 / 截面 | 通道、趋势强度、量价、动量、Overlap 与 **OLS 中性化**；HLC/V 列见 `operators_semantics.md` |

**可选依赖**：`pip install "factor-engine[pandas]"`（含 scipy）；`[talib]`、`[accel]`（**bottleneck** 已用于 `ts_mean`/`ts_max`/`ts_min` 滚动加速，**numba** 预留给后续热点）；**`[polars]`**（Polars 子集后端）；**`[parallel]`**（Joblib，见 `examples/run_factors_joblib.py`）。调试对齐时可设 **`FACTOR_ENGINE_DISABLE_BOTTLENECK=1`**。

**完整列表、DSL 限制（如 `and_`/`or_`/`not_`）与占位算子**：见 [`docs/operators_semantics.md`](docs/operators_semantics.md)。**路线图**：见 [`docs/operators_roadmap.md`](docs/operators_roadmap.md)。**版本级变更记录**：见 [`docs/changelog_shw.md`](docs/changelog_shw.md)。

---

## 数据集列表

| 配置文件 | 数据集 | 因子示例 |
|---|---|---|
| `fundamentals_balance_sheet.yaml` | 资产负债表 | `rank(total_assets)` |
| `fundamentals_cash_flow_statement.yaml` | 现金流量表 | `zscore(net_cash_from_operating_activities)` |
| `fundamentals_financials_ratios.yaml` | 财务比率 | `rank(price_to_earnings)` |
| `fundamentals_income_statement.yaml` | 利润表 | `zscore(revenue)` |
| `fundamentals_short_interest.yaml` | 融券兴趣 | `rank(days_to_cover)` |
| `fundamentals_short_volume.yaml` | 融券成交量 | `zscore(short_volume_ratio)` |
| `fundamentals_stocks_floats.yaml` | 流通股 | `zscore(free_float_percent)` |
| `us_stocks_sip_day_aggs_v1.yaml` | 日K线 | `rank(ts_mean(close, 3))` |
| `us_stocks_sip_minute_aggs_v1.yaml` | 分钟K线 | `rank(ts_mean(close, 5))` |
| `us_stocks_sip_quotes_v1.yaml` | 报价 | `zscore(bid_price / ask_price)` |
| `us_stocks_sip_trades_v1.yaml` | 逐笔成交 | `rank(price)` |

详细字段说明见 `docs/massive_parquet_data_dictionary.md`。

---

## 项目结构

```
factor_engine/
│
├── api/                        # 用户接口层
│   ├── columns.py              #   col() 列引用工厂
│   ├── operators/              #   算子包（arithmetic / logical / ts / cs / group / cleaning / technical / context / …）
│   ├── operator_registry.py    #   DSL 白名单与 STUB_IR_OPS（vec_* 与远期 stub）
│   ├── factor.py               #   Factor 数据类（name + expr）
│   └── dsl_parser.py           #   字符串表达式解析器（parse_expr / parse_factor）
│
├── expr/                       # 表达式树节点
│   ├── base.py                 #   Expr 抽象基类
│   ├── column.py               #   ColumnRef
│   ├── arithmetic.py           #   算术：二元 + 一元/多元（Nary*、densify 等）
│   ├── logical.py              #   逻辑与比较节点
│   ├── cs.py                   #   截面：Rank / ZScore / normalize / quantile 等
│   ├── ts.py                   #   时序：ts_mean / ts_std_dev / ts_max / ts_min 等
│   ├── vector.py               #   向量算子 Expr（执行占位，路径 B）
│   ├── transformational.py     #   bucket / trade_when Expr
│   ├── microstructure.py       #   远期微观结构占位 Expr
│   ├── fundamental.py          #   远期基本面占位 Expr
│   ├── alternative.py          #   远期另类数据占位 Expr
│   ├── group.py                #   group_* Expr（Pandas 已实现）
│   ├── cleaning.py             #   清洗与保护算子 Expr
│   ├── technical.py            #   技术指标 Expr（可选 TA-Lib）
│   ├── context.py              #   正交化 / 换基准 Expr
│   ├── literal.py              #   常量 Literal
│   └── metadata.py             #   节点元数据
│
├── ir/                         # 中间表示层（IR）
│   ├── nodes.py                #   IR 节点定义
│   ├── types.py                #   类型系统
│   ├── schema.py               #   Schema 推导
│   └── analyzer.py             #   Expr → IR 转换与依赖分析
│
├── planner/                    # 编译与规划层
│   ├── logical_plan.py         #   逻辑计划节点（PlanNode）
│   ├── lowerer.py              #   IR → 逻辑计划（Lowerer）
│   ├── optimizer.py            #   逻辑计划优化（Optimizer + Rules）
│   ├── rules.py                #   优化规则抽象（Rule）
│   ├── physical_plan.py        #   物理计划
│   └── dag.py                  #   多因子 DAG 计划（DAGPlan / FactorPlan）
│
├── backend/                    # 执行后端
│   ├── base.py                 #   Backend 抽象基类
│   ├── pandas_backend.py       #   PandasBackend（主力后端）
│   ├── polars_backend.py       #   PolarsBackend（核心子集）
│   ├── debug_backend.py        #   DebugBackend（打印计划树，调试用）
│   ├── context.py              #   ExecutionContext（运行时上下文）
│   ├── kernels.py              #   KernelRegistry（算子→函数映射）
│   └── factory.py              #   build_backend()
│
├── storage/                    # 存储与数据源层
│   ├── datasource.py           #   DataSource 抽象基类
│   ├── kline_parquet_source.py #   KlineParquetSource（K线 parquet）
│   ├── cleaned_parquet_source.py # CleanedParquetSource（清洗层 parquet）
│   ├── parquet_source.py       #   ParquetSource（通用 parquet）
│   ├── factory.py              #   build_data_source()
│   ├── cache.py                #   CacheManager（列缓存）
│   ├── materializer.py         #   Materializer
│   └── result_store.py         #   ResultStore 抽象
│
├── runtime/                    # 运行时编排层
│   ├── engine.py               #   FactorEngine（核心入口）
│   ├── config.py               #   YAML 配置数据类 + load_config()
│   ├── registry.py             #   Registry
│   ├── exceptions.py           #   FactorEngineError
│   └── real_data_factor_smoke.py # DatasetSpec / MultiParquetSeriesSource / smoke 工具
│
├── examples/                   # 示例脚本与配置
│   ├── simple_factor.py        #   最简因子示例
│   ├── pandas_factor.py        #   Pandas 后端示例
│   ├── multi_factor_dag.py     #   多因子 DAG 示例
│   ├── run_factors_joblib.py   #   Joblib 多因子并行示例
│   ├── config_driven_factor.yaml   # 配置驱动示例（K线）
│   ├── notebook_config_smoke.yaml  # Notebook smoke 配置
│   └── configs/                #   11 个数据集的因子配置文件
│       ├── fundamentals_*.yaml
│       └── us_stocks_sip_*.yaml
│
├── tests/                      # 测试套件
│   ├── test_expr.py            #   表达式树单元测试
│   ├── test_planner.py         #   编译规划测试
│   ├── test_backend.py         #   后端执行测试
│   ├── test_pandas_backend.py  #   Pandas 后端详细测试
│   ├── test_dsl_parser.py      #   DSL 解析器测试
│   ├── test_config_runtime.py  #   配置加载与运行时测试
│   ├── test_end_to_end.py      #   端到端集成测试
│   ├── test_factor_templates.py #  11 类数据集合成数据参数化测试
│   ├── test_operators_*.py     #  算子分类单测（含 extension：清洗/技术/分组/缓存）
│   ├── test_polars_backend.py  #  Polars 子集对齐（importorskip polars）
│   ├── helpers.py              #  测试共享（如 InMemorySeriesSource）
│   └── test_real_data_factor_smoke.py # 真实 parquet 集成测试（需 RUN_REAL_PARQUET_SMOKE=1）
│
├── docs/
│   ├── operators_semantics.md   # 算子语义、DSL、依赖与占位说明
│   ├── operators_roadmap.md     # Deep Research ↔ 算子 ↔ 实现状态
│   ├── adr_context_benchmark.md # change_instrument 基准列 ADR
│   ├── changelog_shw.md       # 变更记录（第 N 版更改-shw）
│   ├── massive_parquet_data_dictionary.json  # 数据字典（JSON）
│   └── massive_parquet_data_dictionary.md    # 数据字典（Markdown，含中文释义）
│
└── factor_generation_process.ipynb  # 因子生成过程演示 Notebook
```

---

## 运行测试

```bash
# 运行全部单元测试（不含真实数据）
pytest tests/

# 运行真实 parquet 集成测试（需要 massive_parquet 数据集）
RUN_REAL_PARQUET_SMOKE=1 pytest tests/test_real_data_factor_smoke.py -v
```

---

## 执行流程

```
Factor(expr)
    │
    ▼ Analyzer
  IR Nodes  ─── 依赖列分析 ──▶ 数据源拉取
    │
    ▼ Lowerer
 LogicalPlan
    │
    ▼ Optimizer
 OptimizedPlan
    │
    ▼ Backend.execute()
 pd.Series (MultiIndex: timestamp × instrument)
```