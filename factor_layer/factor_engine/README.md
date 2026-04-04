# Factor Engine

可扩展的量化因子引擎框架，支持表达式树构建、编译优化、多后端执行与配置驱动运行。

**文档索引**：算子语义与 DSL 约定见 [`docs/operators_semantics.md`](docs/operators_semantics.md)；Deep Research 对照路线图见 [`docs/operators_roadmap.md`](docs/operators_roadmap.md)；**华泰 GPT 因子工厂 2.0** 研报算子 ↔ 本引擎规范名见 [`docs/huatai_factor_factory_operator_catalog.md`](docs/huatai_factor_factory_operator_catalog.md)；**回测** `target_position` / 输出协议 / 信号时点 / 多资产执行与指纹见 [`docs/adr_backtest_target_position.md`](docs/adr_backtest_target_position.md)；**回测实现与长篇说明**见 monorepo [`../../backtest_layer/single_asset_backtest/README.md`](../../backtest_layer/single_asset_backtest/README.md)（包名 **`single_asset_backtest`**）；**各目录导读**见 [`docs/README.md`](docs/README.md)（索引到 `api/`、`backend/`、`expr/`、`ir/`、`planner/`、`runtime/`、`storage/`、`tests/`、`examples/` 等包内 `README.md`）；按版本整理的改动说明见 [`docs/changelog_shw.md`](docs/changelog_shw.md)（含 **第 N 版更改-shw** 标注）。

### 协作者速览（新人约 5 分钟）

1. **数据流（本仓库在干什么）**：`api`（`Factor` / DSL / `operators` 工厂）→ `expr`（表达式 AST）→ `ir`（`Analyzer.lower` 成 IR）→ `planner`（IR→`PlanNode`，可选 **CSE**）→ `backend`（在 **`storage`** 拉取的面板上执行）→ 得到 **MultiIndex 因子序列**；**编排入口**是 **`runtime/FactorEngine`**。
2. **规范从哪读**：算子含义以 [`docs/operators_semantics.md`](docs/operators_semantics.md) 为准；**按目录下钻**从 [`docs/README.md`](docs/README.md) 的表格点进各包 **`README.md`**（多数文首有 **「协作者速览」**）。
3. **动手跑**：最小脚本 [`examples/simple_factor.py`](examples/simple_factor.py)；配置驱动见 `examples/` 与 **`FactorEngine.run_from_config`**；**目标仓位回测**见 [`../../backtest_layer/single_asset_backtest/README.md`](../../backtest_layer/single_asset_backtest/README.md) 文首 **「新人 5 分钟上手」**。
4. **版本与变更**：[`docs/changelog_shw.md`](docs/changelog_shw.md)。

> **第 5 版更改-shw**：更新「支持的算子」「项目结构」与 `docs/` 索引，以反映 `api/operators/` 包、算子注册表及 WQ 风格扩展；细节仍以 `changelog_shw.md` 分版条为准。

> **第 7 版更改-shw**：落地 **清洗 / 技术指标 / 上下文 / group_*** 与 **子树缓存 MVP**；README 本节与结构树同步，详见 `changelog_shw.md`「第 7 版」。

> **第 8 版更改-shw**：对齐 **`docs/factor_engine_llm_prompt`（.md / .txt）** 中算子字典与 **`enable_cache`** 说明；**`test_dsl_parser`** 覆盖新 DSL；`changelog` 为第 3 版 **`group_*` 占位** 补历史脚注。详见 `changelog_shw.md`「第 8 版」。

> **第 9 版更改-shw**：**Bottleneck** 加速 `ts_mean` / `ts_max` / `ts_min`（安装 `factor-engine[accel]` 后生效）；可用环境变量 **`FACTOR_ENGINE_DISABLE_BOTTLENECK=1`** 对照测试或与 pandas 完全一致路径。详见 `changelog_shw.md`「第 9 版」。

> **第 10–14 版更改-shw**：`bucket` / `trade_when` / `ts_step(d,anchor)` / `hump` 已在 Pandas 实装；**`vec_avg` / `vec_sum`** 按路线图 **路径 B** 暂缓（需向量列契约）；**PolarsBackend** 子集（`column` / `literal` / 四则 / `rank` / `ts_mean` / `sin` / `cos`）；远期 **数据层 `*_stub`**（基本面 / 另类 / 微观，见 `api/operator_registry.STUB_IR_OPS`）仅编译 + stub；**`sin` / `cos`** 与 **Joblib** 多因子示例见 `examples/run_factors_joblib.py`。详见 `changelog_shw.md`。

> **第 15 版更改-shw**：为 `bucket` / `trade_when` / `ts_step` / `hump`、`ts_regression` / `ts_quantile`、`group_*`、`orthogonalize` / `change_instrument` 及远期 stub 等 **加长源码内中文说明**（`expr/`、`api/operators/`、`pandas_backend` 相关 docstring）。详见 `changelog_shw.md`「第 15 版」。

> **第 16 版更改-shw**：**技术指标大扩展**（`ts_atr`/`ts_donchian`/`ts_keltner`/`ts_macd`/`ts_cci`/`ts_stoch`/`ts_obv`/`ts_mfi`/`ts_dema` 等，见 `operators_semantics.md`）；**`neutralize`**（截面 OLS 残差）；**`ts_skew`/`ts_kurt`**。详见 `changelog_shw.md`「第 16 版」。
> **第 18 版更改-shw**：**技术指标第二波**（`ts_adx`/`ts_aroon`/`ts_ad`/`ts_adosc`/`ts_sar`/`ts_cmo`/`ts_ppo`/`ts_apo`/`ts_ultosc`/`ts_stochrsi`/`ts_tema`/`ts_trima`/`ts_t3`）。详见 `changelog_shw.md`「第 18 版」。

> **第 19 版更改-shw**：**技术指标第三批**（`ts_bop`/`ts_mom`/`ts_stochf`/`ts_trix`/`ts_adxr`/`ts_dx`/`ts_rocr`/`ts_rocr100`/`ts_linearreg_slope`/`ts_linearreg_angle`）。详见 `changelog_shw.md`「第 19 版」。

> **第 20 版更改-shw**：**华泰研报算子对照**（[`huatai_factor_factory_operator_catalog.md`](docs/huatai_factor_factory_operator_catalog.md)、[`adr_huatai_factor_factory_operators.md`](docs/adr_huatai_factor_factory_operators.md)）；不新增重复 DSL。详见 `changelog_shw.md`「第 20 版」。

> **第 21 版更改-shw**：曾新增独立华泰对照 py（已由 **第 22 版** 替代为融入 `api/operators` / `expr`）。

> **第 22 版更改-shw**：华泰算子 **融入** 现有模块（docstring 标注来源）；新增算术 **`exp`**、**`INTRADAY_STUB_OPS`**（[`expr/intraday.py`](expr/intraday.py)、[`api/operators/intraday.py`](api/operators/intraday.py)）；删除 `api/htsc_factor_factory_reference.py`。详见 `changelog_shw.md`「第 22 版」。

> **第 23 版更改-shw**：**性能与后端选项**——[`planner/cse.py`](planner/cse.py) 多因子 **CSE** + [`FactorEngine.run_many`](runtime/engine.py)；[`backend/pandas_compat.py`](backend/pandas_compat.py) 可选 **Modin**（`pandas_modin` / `FACTOR_ENGINE_USE_MODIN`）；[`PolarsBackend`](backend/polars_backend.py) 扩展算子子集 + **`polars_lazy` / `FACTOR_ENGINE_POLARS_LAZY`**；[`runtime/perf_config.py`](runtime/perf_config.py)；脚本 [`scripts/profile_pandas_backend.py`](scripts/profile_pandas_backend.py)、[`scripts/bench_pandas_vs_modin.py`](scripts/bench_pandas_vs_modin.py)。详见 `changelog_shw.md`「第 23 版」。

> **第 24 版更改-shw**：新增 **`backtest/` 单标回测子系统**（Backtrader 可选依赖）、冻结 `target_position` 对接 ADR，并补充最小示例与测试。详见 `changelog_shw.md`「第 24 版」。
>
> **第 25 版更改-shw**：回测补齐 **D-3 策略注册/策略库**（`strategy_name`/`strategy_version`/`strategy_params`/`strategy_instance_id`）并引入 **分层指标 profile**（`core`/`standard`/`industrial`，覆盖 `sortino`/`calmar`/`var_95`/`cvar_95` 等扩展指标）。详见 `changelog_shw.md`「第 25 版」。
>
> **第 26 版更改-shw**：回测补充 **信号时点与防前视**（`BacktestConfig.target_lag_bars`、`portfolio_weight_lag_bars`）、**可复现指纹**说明，并整理 README 回测章节与 ADR §13。详见 `changelog_shw.md`「第 26 版」。
>
> **第 27 版更改-shw**：为 **`api/`、`backend/`、`expr/`、`ir/`、`planner/`、`runtime/`、`storage/`、`scripts/`、`tests/`、`examples/`、`docs/`** 等目录各增 **`README.md`**，并在 [`docs/README.md`](docs/README.md) 汇总索引。详见 `changelog_shw.md`「第 27 版」。
>
> **第 28 版更改-shw**：各包 **`README.md` 深度扩写**（架构说明、逐文件表、数据流、契约与测试索引）；新增 **`docs/_refs/README.md`**；**`backtest/README.md`** 增补与主因子链路对照及章节导航。详见 `changelog_shw.md`「第 28 版」。
>
> **第 29 版更改-shw**：**多资产回测文档与实现对齐**——`backtest/README.md`、`docs/adr_backtest_target_position.md`、根 `README.md` 统一叙述 **执行层 → `executed_weights` → 滞后 → 毛/净收益**；明确 **`portfolio_execution_engine: python`** 与 **`FACTOR_BACKTEST_EXECUTION_ENGINE`** 的关系及 **多资产 `data_fingerprint` 基于执行后权重**。详见 `changelog_shw.md`「第 29 版」。
>
> **第 30 版更改-shw**：根目录与各包 **`README.md`** 增加 **「协作者速览（约 5 分钟）」**；**`docs/README.md`** 说明该约定。详见 `changelog_shw.md`「第 30 版」。

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

**支持的数据源类型：**

| 类型 | 说明 |
|---|---|
| `parquet_kline` | K线格式 parquet，适用于 `us_stocks_sip` |
| `multi_parquet` | 通用多文件 parquet，适用于各类 fundamentals |
| `parquet` | 单文件或简单目录 parquet |

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

`examples/configs/` 目录下收录了覆盖全部 11 个数据集的配置文件（见下文[数据集列表](#数据集列表)）。

---

## 支持的算子

引擎已按 **WorldQuant BRAIN** 风格扩展算子：Arithmetic / Logical / Time Series / Cross Sectional 在 `PandasBackend` 中已实现；**Group（`group_*`）**、**清洗**、**技术指标**、**上下文**同上。**Transformational**：`bucket`、`trade_when` 已可执行；**`ts_step` / `hump`** 已实装（API 与语义见 `docs/operators_semantics.md` 与 ADR）。**`sin` / `cos` / `exp`** 已实装。**Vector**：`vec_avg` / `vec_sum` 仍为占位（需向量列数据契约，见路线图路径 B）。**远期数据层**：`fundamental_*_stub` / `alt_*_stub` / `micro_*_stub` / `lob_ofi_stub` / `intraday_*_stub` 等（`STUB_IR_OPS`）仅接口占位。**PolarsBackend** 覆盖 **常用子集**（含 `column` / `literal` / 四则 / `rank` / `zscore` / `ts_mean` / `ts_delay` / `ts_std` / `ts_sum` / 一元 `abs`·`log`·`sqrt`·`sign`·`sin`·`cos`·`exp` 等；`build_backend("polars_lazy")` 或 `FACTOR_ENGINE_POLARS_LAZY=1` 走 **LazyFrame**），其余算子仍会 `NotImplementedError`。

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

**可选依赖**：`pip install "factor-engine[pandas]"`（含 scipy）；`[talib]`、`[accel]`（**bottleneck** 已用于 `ts_mean`/`ts_max`/`ts_min` 滚动加速；**numba** 可选：`FACTOR_ENGINE_USE_NUMBA=1` 时 `ts_mean` 可走 Numba 滑动均值，另可设 **`FACTOR_ENGINE_DISABLE_NUMBA=1`**）；**`[polars]`**（Polars 子集后端，可选 **`FACTOR_ENGINE_POLARS_LAZY=1`** 走 LazyFrame 延迟计算再 `collect`）；**`[modin]`**（`pip install "factor-engine[modin]"` 后设 **`FACTOR_ENGINE_USE_MODIN=1`** 或使用配置 **`backend.type: pandas_modin`**，使 `PandasBackend` 通过 `modin.pandas` 解析；MultiIndex/rolling 边缘行为可能与 pandas 略有差异，CI 默认仍用纯 pandas）；**`[parallel]`**（Joblib；`FactorEngine.run_many` / `run_many_parallel` 多因子，编译期 **CSE** 去重子式，见 `runtime/perf_config.py` 中 **`FACTOR_ENGINE_DISABLE_CSE`**、**`FACTOR_ENGINE_MAX_WORKERS`**、**`FACTOR_ENGINE_INSTRUMENT_CHUNK`**、**`FACTOR_ENGINE_MAX_MEMORY_MB`**）；**`[backtest]`**（Backtrader 单标回测路径，入口见 **`single_asset_backtest.runner.run_single_asset_backtest`** 与 monorepo [`../../backtest_layer/examples/backtest_single_asset.py`](../../backtest_layer/examples/backtest_single_asset.py)；另含组合会计多标回测入口 **`single_asset_backtest.runner.run_multi_asset_backtest`**，输入 `target_weights(timestamp,symbol,target_weight)`；支持 `strategy_name/strategy_version/strategy_params` 与 `BacktestConfig.metrics_profile=core|standard|industrial`）。调试对齐时可设 **`FACTOR_ENGINE_DISABLE_BOTTLENECK=1`**。性能剖析脚本：`scripts/profile_pandas_backend.py`；Pandas 与 Modin 对比：`scripts/bench_pandas_vs_modin.py`。

**回测接口与语义 ADR**：[`docs/adr_backtest_target_position.md`](docs/adr_backtest_target_position.md)（输出协议、策略版本、真实数据路径、分层指标、可复现字段、**信号时点 / 防前视** §13、**多资产执行与指纹** §14）。**逐步数据流与模块说明（可替代通读源码）**：[`../../backtest_layer/single_asset_backtest/README.md`](../../backtest_layer/single_asset_backtest/README.md)。

### 多资产组合回测（Portfolio Mode）

当前多资产路径采用**组合会计口径**（research/audit friendly），并保持冻结协议 `returns/metrics/summary` 必需键不变。

- 执行入口：`single_asset_backtest.runner.run_multi_asset_backtest`
- 目标权重输入：`target_weights`，支持：
  - DataFrame 列：`timestamp`, `symbol`, `target_weight`
  - 或 MultiIndex Series：`['timestamp','symbol']`
- 契约处理：按时间对齐后 `ffill`，缺失补 `0.0`，并做权重边界与每时点 gross leverage 校验
- 组合收益口径：`realized_weights = executed_weights.shift(portfolio_weight_lag_bars)` 后与当期资产收益相乘；**默认 `portfolio_weight_lag_bars=1`**（即 **t−1** 权重 × **t** 期收益），**不允许为 0**（避免组合层面零滞后前视）
- 组合执行约束：
  - `portfolio_min_trade_weight`：最小调仓阈值（小于阈值的 delta 直接忽略）
  - `portfolio_adv_participation_cap`：按 `price*volume*cap/initial_cash` 约束每 bar 可执行权重变化
- 成本模型（`portfolio_cost_model`）：
  - `simple_bps`：`(commission_bps + spread_bps) * turnover`
  - `linear_impact`：在 `simple_bps` 基础上叠加线性冲击项（受 `portfolio_impact_coeff` 与参与率影响）
  - `square_impact`：在 `simple_bps` 基础上叠加平方冲击项（受 `portfolio_impact_coeff` 与参与率影响）
- 执行内核选择（`portfolio_execution_engine`）：`python` / `numpy` / `numba` / `auto`。若 YAML 写 **`python`**，实际参与解析的请求来自环境变量 **`FACTOR_BACKTEST_EXECUTION_ENGINE`**（`PerfConfig.from_env().backtest_execution_engine`，默认 `python`），便于不改业务配置切换内核；若写 **`numpy`/`numba`/`auto`**，则按该字面值解析（`numba` 不可用时回退 `numpy`，`auto` 优先 `numba`）。`summary` 记录 **requested/resolved**

输出在不破坏冻结必需键前提下增量包含：
- `returns.portfolio_turnover`
- `returns.portfolio_cost`
- `returns.portfolio_participation`
- `metrics.portfolio_turnover_total`
- `metrics.portfolio_cost_total`
- `metrics.portfolio_participation_max`
- `summary.mode = "multi"`

### 单资产：信号时点与 `target_lag_bars`

单资产路径**不能**自动检测因子是否误用「当日收盘后才可得」的信息；若因子层已对信号滞后，请保持 **`target_lag_bars=0`**（默认），避免双重滞后。

- **`BacktestConfig.target_lag_bars`**：在与行情对齐并 `ffill` 之后，对目标仓位再 **`shift(target_lag_bars)`**（空缺填 `0`）。设为 **`1`** 时，第 `t` 根 K 线使用原序列在 `t−1` 的值。该字段写入 `summary.strategy_params`，并参与 **`data_fingerprint`**（与**滞后后的有效目标**一致）。

### 回测可复现元数据（single / multi）

`run_single_asset_backtest` 与 `run_multi_asset_backtest` 均会在 `summary` 注入审计字段：

- `run_id`：单次运行唯一 ID（每次运行不同）
- `mode`：`single` 或 `multi`
- `data_fingerprint`：对 OHLCV 与目标序列做**结构化统计摘要**后 SHA256；**同逻辑输入应稳定**；**不是**原始文件字节级 hash
- `dependency_versions`：至少包含 `python`、`pandas`、`numpy`、`backtrader`（未安装时为 `null`）
- `git_sha`：当前仓库提交（best-effort，获取失败时为 `null`）
- `signal_timestamp`：信号时间语义标注（当前为 `bar_close_t`）
- `decision_timestamp`：决策时间语义标注（当前为 `bar_close_t`）
- `execution_effective_lag_bars`：收益归因使用的有效滞后 bar 数（single 来自 `target_lag_bars`，multi 来自 `portfolio_weight_lag_bars`）
- `return_attribution`：收益归因公式字符串（如 `weights(t-1) * returns(t)`）
- `execution_engine_requested`：多资产执行层请求内核（来自配置或环境变量）
- `execution_engine_resolved`：当前实际执行内核（`python` / `numpy` / `numba`）


### 真实黄金回测（IBKR）

工业回测建议使用 `BacktestConfig.strict_real_data=True`，该模式下回测器只会从 `data_root` 加载真实 OHLCV，传入 inline `ohlcv` 会直接报错，不存在 synthetic/fallback 路径。

- 数据抓取脚本：`/home/yluel/share/data/ibkr/fetch_gold_data.py`
- 默认落盘目录：`/home/yluel/share/data/ibkr/gold`
- 文件命名兼容：`XAU_1_hour_30_D.parquet`、`XAUUSD_*.parquet` 等（按 `symbol+frequency` 别名自动匹配）

最小配置示例：

```python
from single_asset_backtest.config import BacktestConfig

cfg = BacktestConfig(
    strict_real_data=True,
    data_root="/home/yluel/share/data/ibkr",
    symbol="XAUUSD",
    frequency="1h",
    metrics_profile="industrial",
    include_trade_ledger=True,
)
```

运行示例（在 **monorepo 根目录**，且 `PYTHONPATH` 含 `backtest_layer` 与 `factor_layer/factor_engine`，见 [`../../backtest_layer/single_asset_backtest/README.md`](../../backtest_layer/single_asset_backtest/README.md) 文首）：

```bash
python backtest_layer/examples/backtest_single_asset.py
```


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
│   ├── operator_registry.py    #   DSL 白名单与 STUB_IR_OPS（vec_*、远期 stub、intraday_*_stub）
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
│   ├── intraday.py             #   分钟/日内序列类占位 Expr（华泰图表 11 语义）
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
│   ├── optimizer.py            #   逻辑计划优化（常量折叠等）
│   ├── plan_hash.py            #   计划子树结构化哈希（缓存键 / CSE）
│   ├── cse.py                  #   多因子公共子式消除（CSE → plan_ref）
│   ├── rules.py                #   优化规则抽象（Rule）
│   ├── physical_plan.py        #   物理计划
│   └── dag.py                  #   多因子 DAG 计划（DAGPlan / FactorPlan）
│
├── backend/                    # 执行后端
│   ├── base.py                 #   Backend 抽象基类
│   ├── pandas_compat.py        #   可选 Modin / 标准 pandas 惰性解析
│   ├── pandas_backend.py       #   PandasBackend（主力后端）
│   ├── polars_backend.py       #   PolarsBackend（子集；可选 LazyFrame）
│   ├── numba_kernels.py        #   可选 Numba 滑动核
│   ├── debug_backend.py        #   DebugBackend（打印计划树，调试用）
│   ├── context.py              #   ExecutionContext（运行时上下文）
│   ├── kernels.py              #   KernelRegistry（算子→函数映射）
│   └── factory.py              #   build_backend（含 pandas_modin / polars_lazy）
│
├── storage/                    # 存储与数据源层
│   ├── datasource.py           #   DataSource 抽象基类
│   ├── kline_parquet_source.py #   KlineParquetSource（K线 parquet）
│   ├── parquet_source.py       #   ParquetSource（通用 parquet）
│   ├── factory.py              #   build_data_source()
│   ├── cache.py                #   CacheManager（列缓存）
│   ├── materializer.py         #   Materializer
│   └── result_store.py         #   ResultStore 抽象
│
├── runtime/                    # 运行时编排层
│   ├── engine.py               #   FactorEngine（compile / run / compile_many / run_many）
│   ├── perf_config.py          #   性能与环境变量（并行、CSE、Modin/Numba 提示）
│   ├── config.py               #   YAML 配置数据类 + load_config()
│   ├── registry.py             #   Registry
│   ├── exceptions.py           #   FactorEngineError
│   └── real_data_factor_smoke.py # DatasetSpec / MultiParquetSeriesSource / smoke 工具
│
├── （回测实现已迁至 monorepo **`../../backtest_layer/single_asset_backtest/`**，示例见 **`../../backtest_layer/examples/`**，测试见 **`../../backtest_layer/tests/test_backtest_*.py`**）
│
├── examples/                   # 示例脚本与配置
│   ├── simple_factor.py        #   最简因子示例
│   ├── pandas_factor.py        #   Pandas 后端示例
│   ├── multi_factor_dag.py     #   多因子 DAG 示例
│   ├── run_factors_joblib.py   #   Joblib 多因子并行示例
│   ├── profile_pandas_backend.py # cProfile 热点（Pandas 路径）
│   ├── bench_pandas_vs_modin.py  # Pandas vs Modin 耗时对比（可选 modin）
│   ├── config_driven_factor.yaml   # 配置驱动示例（K线）
│   ├── notebook_config_smoke.yaml  # Notebook smoke 配置
│   └── configs/                #   11 个数据集的因子配置文件
│       ├── fundamentals_*.yaml
│       └── us_stocks_sip_*.yaml
│
├── tests/                      # 测试套件（回测专项在 monorepo ../../backtest_layer/tests/）
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
│   ├── huatai_factor_factory_operator_catalog.md  # 华泰 GPT 因子工厂 2.0 ↔ DSL 对照（去重）
│   ├── adr_huatai_factor_factory_operators.md     # 华泰算子 ADR（命名与扩展策略）
│   ├── adr_context_benchmark.md # change_instrument 基准列 ADR
│   ├── adr_backtest_target_position.md # 回测 target_position / 组合权重 / 可复现 / 信号时点 ADR
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
cd /path/to/factor_engine
PYTHONPATH=. pytest tests/

# 回测专项测试（位于 monorepo backtest_layer/tests/；需安装 factor-engine[backtest]）
cd /path/to/quantsociety_backend_project
pytest backtest_layer/tests/test_backtest_*.py -q

# 运行真实 parquet 集成测试（需要 massive_parquet 数据集）
RUN_REAL_PARQUET_SMOKE=1 pytest tests/test_real_data_factor_smoke.py -v
```

回测专项测试依赖 **`backtrader`**（`pip install "factor-engine[backtest]"`）；`backtest_layer/tests/conftest.py` 会注入 `PYTHONPATH`，一般无需手写。

---

## 执行流程

```
Factor(expr)
    │
    ▼ Analyzer
  IR Nodes  ─── 依赖列分析 ──▶ 数据源拉取
    │
    ▼ Lowerer
 LogicalPlan (PlanNode)
    │
    ▼ Optimizer
 OptimizedPlan
    │
    ▼ Backend.execute()
 pd.Series (MultiIndex: timestamp × instrument)
```

**多因子**：`compile_many` 可做 **CSE**（重复子式 → `DAGPlan.shared_nodes` + `plan_ref`），**`run_many`** 先算共享子式再算各因子根。YAML 中 `backend.type` 除 `pandas` / `polars` 外还可写 **`pandas_modin`**、**`polars_lazy`**（见上文可选依赖）。