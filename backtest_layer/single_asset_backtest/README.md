# `single_asset_backtest` 子系统说明

本目录实现 **目标驱动** 的回测：**研究员产出「目标仓位 / 目标权重」**，引擎负责与行情对齐、执行（单资产走 Backtrader）、计费、汇总指标与审计元数据（**包名** `single_asset_backtest`；代码中仍保留 `build_backtest_report` / `compute_backtest_metrics` 等函数名，指「回测报告」语义而非旧包名）。  
本文按 **数据流顺序** 说明每一步在做什么、默认假设是什么、与「未来函数」和「实盘差异」相关的边界在哪里。

### 包名 vs 能力：也支持多资产

**`single_asset_backtest` 指的是「单标的那条执行路径」**（`run_single_asset_backtest` → Backtrader），不是「整个包只能跑单资产」。**同一包内**已实现 **多标的组合回测** **`run_multi_asset_backtest`**（`target_weights`、组合会计、执行层与成本、指纹与审计），与单资产 **共用** `BacktestConfig`、`build_backtest_report` 与冻结的 **`returns` / `metrics` / `summary`** 协议。包根 **`__init__.py`** 为控制对外表面积，只默认导出单资产入口；多资产请 **`from single_asset_backtest.runner import run_multi_asset_backtest`**（见下文 §3.2 与 **§9**）。

### 与研究员 C（信号 → `target_position`）的衔接

单标的择时 **C-1 / C-2**（信号与目标仓位生成，**不含 Backtrader**）在 monorepo **`strategy_layer/single_asset_alpha/`**：`pipeline.StrategyPipeline`、`core/schema.py` 冻结的 **`target_position`** 长表。产出的 DataFrame（含 `timestamp`、`target_position` 等）可直接作为本包 **`run_single_asset_backtest(..., target_position=...)`** 的输入；端到端封装见 **`strategy_layer/single_asset_alpha/integration/backtest_bridge.py`**（`run_pipeline_then_single_asset_backtest`）与示例 **`strategy_layer/single_asset_alpha/examples/c_to_d_end_to_end.py`**。该侧 README：**[`../../strategy_layer/single_asset_alpha/README.md`](../../strategy_layer/single_asset_alpha/README.md)**。

### 运行时代码路径（必读）

本包依赖 **`runtime.perf_config`**（`FACTOR_BACKTEST_EXECUTION_ENGINE` 等），与 **`factor_layer/factor_engine`** 同源。请在项目根执行前设置：

```bash
export PYTHONPATH="/path/to/quantsociety_backend_project:/path/to/quantsociety_backend_project/backtest_layer:/path/to/quantsociety_backend_project/factor_layer/factor_engine"
```

这样 `import strategy_layer.data`、`import single_asset_backtest` 与 `import runtime` 均可解析。

### 新人 5 分钟上手（从哪读、跑什么）

1. **装依赖**：单资产需要 **`pip install "factor-engine[backtest]"`**（含 Backtrader）；多资产同包即可，无需额外装 Numba（可选加速）。
2. **先读协议（5 分钟够扫一遍目录）**：打开 [`adr_backtest_target_position.md`](../../factor_layer/factor_engine/docs/adr_backtest_target_position.md)，只看 **输出三段结构** `returns` / `metrics` / `summary`、**`target_position` 范围 [-1,1]**、以及 **§13–§14**（滞后与多资产执行/指纹）— 避免和业务方各说各话。
3. **单资产跟代码**：入口 **`runner.run_single_asset_backtest`** → 策略在 **`strategy.py` / `strategy_library`** → 报告在 **`report.py`**；示例：**[`backtest_single_asset.py`](../examples/backtest_single_asset.py)**（需按上文配置 `PYTHONPATH`）。
4. **多资产跟代码**：入口 **`runner.run_multi_asset_backtest`**（`runner.py` 约后部）；示例：**[`backtest_multi_asset.py`](../examples/backtest_multi_asset.py)**。核心顺序在源码里已写死：**`asset_return` → 执行层得 `executed_weights` → `shift` → 毛/净收益**，与 **§9** 对照阅读最快。
5. **本地冒烟**：在仓库根目录 **`pytest backtest_layer/tests/test_backtest_*.py -q`**（`backtest_layer/tests/conftest.py` 会注入 `PYTHONPATH`；见 **§16**）。失败时先看是否缺 **`backtrader`** 或数据路径。
6. **接下来**：需要「全目录地图」读下面 **§0** 与 **§0.1**；因子引擎总索引：**[`factor_layer/factor_engine/docs/README.md`](../../factor_layer/factor_engine/docs/README.md)**。

### 给协作者：近期实现要点（扫一眼能懂「做了什么」）

- **单资产**：`run_single_asset_backtest` → Backtrader `target_position` 策略 → 报告；可选 **`target_lag_bars`**、融券事后近似、**`trade_ledger`**（工业指标用，`metrics_profile="fast"` 会强制关闭）。
- **单资产批量**：`run_single_asset_backtest_batch(tasks=[...], max_workers=...)`；`max_workers=1` 串行等价，`>1` 走任务级多进程并行，适合参数网格/滚动窗口，不建议用于单次短回测。
- **多资产**（与早期「仅矩阵 shift × 收益」相比已加强）：先对 **目标权重矩阵** 做 **逐 bar 执行层**（`runner.py` 内 `_apply_multi_asset_execution_and_cost_*`）：最小调仓阈值、可选 **ADV 参与率上限**、**佣金+点差 bps** 与 **线性/平方冲击** 成本；再得到 **`executed_weights`**，再 **`shift(portfolio_weight_lag_bars)`** 与 **`asset_return`** 相乘得到组合收益；权益为 **`(1+net_return).cumprod()`**。
- **性能**：多资产执行可选 **`python`（pandas 逐 bar）/ `numpy` / `numba` / `auto`**；注意 **`BacktestConfig.portfolio_execution_engine == "python"` 时实际请求会交给环境变量 `FACTOR_BACKTEST_EXECUTION_ENGINE`**（见 `runtime/perf_config.py`），便于在 CI/本机统一切换内核而不改业务 YAML。
- **审计**：`summary` 含 **时序语义**（`signal_timestamp` 等）、**`execution_effective_lag_bars`**、**`execution_engine_requested`/`resolved`**（仅 multi）、**`data_fingerprint`**；多资产指纹对 **执行后权重** 统计，与真实执行一致。

### 单资产性能优化指南（实践版）

> 目标：在不改变 `returns / metrics / summary` 输出契约与时序语义前提下，优先拿到稳定吞吐收益。

1. **单次迭代优先 `fast` 档**（少算，不改交易逻辑）

```python
from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_single_asset_backtest

report = run_single_asset_backtest(
    ohlcv=ohlcv,
    target_position=target_position,
    config=BacktestConfig(
        initial_cash=100_000.0,
        metrics_profile="fast",  # 与 core 同核心指标键，跳过扩展指标
        include_trade_ledger=True,  # fast 下会被强制关闭
    ),
)
```

2. **批量任务再开多进程**（参数网格 / 多窗口）

```python
from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.runner import run_single_asset_backtest_batch

tasks = [
    {
        "ohlcv": ohlcv,
        "target_position": target_position,
        "config": BacktestConfig(metrics_profile="fast", initial_cash=100_000.0),
    },
    {
        "ohlcv": ohlcv,
        "target_position": target_position,
        "config": BacktestConfig(metrics_profile="core", initial_cash=100_000.0),
    },
]
reports = run_single_asset_backtest_batch(tasks=tasks, max_workers=4)
```

3. **不要误用并行**
- 单次短回测通常先用 `max_workers=1`（进程启动与序列化可能抵消收益）。
- 只有任务数与样本规模足够大时，再放大 `max_workers`。
- `run_single_asset_backtest_batch` 输出顺序与输入一致，便于参数回填与复现实验表格。

---

## 0. 与 factor_engine 主因子链路的关系（必读）

| 维度 | 主因子引擎（`api`/`runtime`/…） | 本目录 `single_asset_backtest` |
|------|----------------------------------|-------------------|
| **输入** | `Factor(expr)` + 多标的面板数据 | **目标仓位/权重序列** + OHLCV |
| **输出** | MultiIndex **因子值** Series | **权益曲线、指标、summary、可选 artifacts** |
| **依赖** | 无 Backtrader 硬性要求 | 单资产路径 **依赖 `backtrader`** |

二者可 **串联**于研究流程：先在 **`FactorEngine`** 中产出信号或目标仓位（写 parquet/csv），再作为 **`target_position` / `target_weights`** 传入本目录。**不**在 `single_asset_backtest` 内编译 DSL 因子树。

**延伸阅读**：[`adr_backtest_target_position.md`](../../factor_layer/factor_engine/docs/adr_backtest_target_position.md)（协议冻结）、[`factor_engine/docs/README.md`](../../factor_layer/factor_engine/docs/README.md)。

### 0.1 本文结构导航

| 章节 | 内容 |
|------|------|
| 文首 | **新人 5 分钟上手**、**给协作者** |
| §1–2 | 依赖、入口、文件职责表 |
| §3 | 单资产 vs 多资产管线 |
| §4–7 | 配置、契约、IO、单资产逐步流程 |
| §8 | 指纹与可复现 |
| §9 | 多资产逐步流程 |
| §10–12 | 报告、指标、融券近似 |
| §13 | 前视边界 |
| §14 | **已实现功能全量清单**（入口、输出、指标键名，便于自查） |
| §15–16 | 延伸阅读、测试命令 |
| §17 | **协作补充**：C 侧衔接、排错、团队日志 |

---

## 1. 依赖与入口

| 依赖 | 作用 |
|------|------|
| **pandas** | 行情与目标序列对齐、矩阵组合回测 |
| **numpy** | 指标数值计算 |
| **backtrader** | 仅 **单资产** `run_single_asset_backtest` 需要；安装：`pip install "factor-engine[backtest]"` |

**公开入口（`single_asset_backtest/__init__.py`）**  
`BacktestConfig`、`run_single_asset_backtest`、`load_ohlcv`、`load_target_position`、`validate_target_position`、`align_target_position_to_index`、契约常量、`StrategyRegistry` / `StrategySpec` / `build_strategy_registry`。

**未在包根导出但已稳定使用**（需 `from single_asset_backtest.runner import ...` / `from single_asset_backtest.contracts import ...`）  
`run_multi_asset_backtest`、`validate_target_weights`、`align_target_weights_to_index`。

---

## 2. 文件职责一览

| 文件 | 职责 |
|------|------|
| `config.py` | 冻结配置数据类 `BacktestConfig`：资金、成本、数据路径、指标档位、组合参数、滞后 bar 等 |
| `contracts.py` | **输入契约**：`target_position` / `target_weights` 校验、时间索引、`ffill` 对齐；OHLCV 时间完整性；**冻结** `REQUIRED_*` 键与 `BACKTEST_SCHEMA_VERSION` |
| `io.py` | 从磁盘读 `target_position`；行情入口统一委托 **`strategy_layer.data.market_data`**，支持 `source_path`、`data_root` 自动发现与 `aggregate_bars_daily_summary` 标准化/缓存 |
| `runner.py` | **主流程**（代码量较大）：`run_single_asset_backtest`、`run_multi_asset_backtest`；多资产 **执行+成本** 三层实现（pandas / numpy / numba）；指纹、**时序审计**、**`PerfConfig` 与执行引擎解析**；单资产融券事后修正 |
| `report.py` | 将权益曲线、持仓、佣金、交易次数等 **组装成协议化 dict**，并调用 `metrics` |
| `metrics.py` | 按 `metrics_profile` 分层计算夏普、回撤、基准、工业扩展、交易微观等 |
| `strategy_registry.py` | 策略名 `@` 版本注册表，`get(name, version)` 未指定版本时取 **最新** 版本 |
| `strategy_library.py` | 内置策略工厂：`target_position`（外部目标仓位）与 `dual_ma`（最简双均线） |
| `strategy.py` | `TargetPositionStrategyMixin`：与 Backtrader 对接，记录 **trace**（权益、目标/实现仓位、佣金、成交笔数、可选 trade_ledger） |

---

## 3. 核心概念：两套管线

### 3.1 单资产（`run_single_asset_backtest`）

- **输入**：一根标的的 OHLCV（索引为 `DatetimeIndex`）**或** 由配置从磁盘加载；**目标仓位** `target_position`（与行情时间对齐的一维权重序列，范围默认 `[-1,1]`）。
- **执行引擎**：Backtrader `Cerebro` + `PandasData` + 内置策略 **`target_position`**，用 `order_target_percent` 调仓。
- **输出**：统一 **报告 dict**（见第 10 节），并可能叠加 **融券成本近似**（见第 12 节）。

### 3.2 多资产组合（`run_multi_asset_backtest`）

- **输入**：多标的 OHLCV（内存 dict **或** 按 `symbols` 与配置多次 `load_ohlcv_from_config`）；**目标权重** `target_weights`（长表：`timestamp`, `symbol`, `target_weight` 或等价 MultiIndex Series）。
- **执行引擎**：**无 Backtrader**。先在 **共同时间轴** 上对每个 bar 做 **「目标 → 可执行权重」**（受最小调仓、可选 ADV 上限约束），得到 **`executed_weights`**；再算 **资产收益**；用 **`executed_weights` 滞后 `portfolio_weight_lag_bars` 根 bar** 与当期收益相乘得 **毛收益**，并减去 **成本序列**（bps + 可选冲击）得 **净收益**，最后复利成权益。
- **输出**：同一套 **报告 dict** 结构，并 **额外** 在 `returns` / `metrics` 里增加组合换手、成本、**参与度** 等字段（见第 9 节）。

---

## 4. `BacktestConfig` 字段说明（逐项）

以下为 `dataclass` 默认值；实际运行以你传入为准，且会 **原样进入** `summary["config"]`（`asdict`）。

### 4.1 资金与单资产交易成本

| 字段 | 含义 |
|------|------|
| `initial_cash` | 初始资金（float） |
| `commission` | Backtrader 经纪商 **比例佣金**（与 backtrader 文档一致，通常为 **每股/每单位成交额比例** 一类简化口径，见 Backtrader 版本说明） |
| `slippage_perc` | 若 `>0`，设置 **百分比滑点**（`set_slippage_perc`） |
| `rebalance_threshold` | 目标仓位与上一目标差异 **小于** 该阈值则 **不调仓**（减少微小换手） |
| `enforce_target_bounds` | 为 True 时校验目标是否在 `[-1,1]`（或裁剪，取决于 `validate_*` 的 strict） |

### 4.2 指标与无风险利率

| 字段 | 含义 |
|------|------|
| `metrics_profile` | `"fast"` / `"core"` / `"standard"` / `"industrial"`：控制 `metrics.py` 计算哪些键（见第 11 节）；其中 `fast` 与 `core` 输出同一必需指标集合，但跳过扩展计算以降低开销 |
| `risk_free_rate_annual` | **年化**无风险利率，用于夏普、Treynor、Omega 阈值等（单位为与年化收益一致的小数，如 `0.03` 表示 3%） |

### 4.3 数据加载（`load_ohlcv_from_config`）

| 字段 | 含义 |
|------|------|
| `market_data_mode` | 行情入口模式：`data_root`、`source_path`、`aggregate_bars_daily_summary`；留空时按 `data_root` 兼容旧行为 |
| `data_root` | `market_data_mode="data_root"` 时的数据根目录；按 `symbol + frequency` 自动发现标准 OHLCV 文件 |
| `source_path` | `market_data_mode="source_path"` 时直接读取的单文件路径（csv/parquet，需已是标准 OHLCV 列） |
| `market_data_cache_root` | 可选缓存目录；若配置，会把标准化后的单标的 OHLCV 缓存在 `{cache_root}/{dataset}/freq={freq}/{symbol}.parquet` |
| `aggregate_bars_root` | `market_data_mode="aggregate_bars_daily_summary"` 时的 aggregate_bars 根目录 |
| `aggregate_dataset` | aggregate_bars 数据集名，默认 `daily_market_summary` |
| `symbol` | 标的代码；用于文件自动发现、aggregate_bars 过滤与缓存文件命名 |
| `frequency` | 逻辑频率标签：`"1min"`…`"1d"`；用于路径与别名（**不是**在引擎内重采样 K 线） |
| `aggregate_symbol_column` | aggregate_bars 中的代码列名，默认 `ticker` |
| `aggregate_timestamp_column` | aggregate_bars 中的时间列名，默认 `align_time` |
| `aggregate_columns` | aggregate_bars OHLCV 映射，默认 `o/h/l/c/v -> open/high/low/close/volume` |
| `prefer_parquet` | 同目录多文件时优先 parquet 还是 csv |
| `max_rows` | 仅取 **最后** `max_rows` 行（tail），用于缩短样本 |
| `strict_real_data` | **True** 时：**禁止** 传入内存中的 inline OHLCV，**必须** 通过配置好的市场数据入口加载，避免「假数据混入」 |
| `strict_temporal_validation` | 传给 `validate_temporal_integrity`：是否严格检查重复时间戳、`arrival_time < event_time` 等 |

### 4.4 单资产多空与账本

| 字段 | 含义 |
|------|------|
| `allow_short` | False 时若目标为负会 **报错** |
| `borrow_rate_annual` | **年化**融券费率；若 `>0`，在单资产回测 **结束后** 按近似公式扣减权益并摊入 `commission_paid`（见第 12 节） |
| `short_margin_requirement` | 传给策略：空头目标不会低于 `-1 + short_margin_requirement`（预留保证金语义） |
| `include_trade_ledger` | True 时收集 **逐笔委托/平仓** 事件列表；`metrics_profile=="industrial"` 会自动开启；`metrics_profile=="fast"` 会强制关闭以保证低开销 |

### 4.5 多资产组合专用

| 字段 | 含义 |
|------|------|
| `portfolio_mode` | 字面语义：`"single"` / `"multi"`；**当前**多资产入口会 `BacktestConfig(portfolio_mode="multi")` 默认，逻辑上以 **调用的函数** 为准 |
| `portfolio_cost_model` | 组合成本模型：`simple_bps` / `linear_impact` / `square_impact` |
| `portfolio_commission_bps` | 组合换手 **`× 佣金率`**：`commission_rate = bps / 10000` |
| `portfolio_spread_bps` | 点差成本（与 commission 一起计入基础 bps 成本） |
| `portfolio_impact_coeff` | 冲击成本系数；在线性/平方冲击模型下生效 |
| `portfolio_adv_participation_cap` | ADV 参与率上限（按 `price*volume*cap/initial_cash` 转成单 bar 可执行权重变化上限） |
| `portfolio_min_trade_weight` | 最小调仓权重阈值，低于该阈值的 delta 直接忽略 |
| `portfolio_half_turnover` | True 时换手 `×0.5`（常见「单边/双边」口径差异） |
| `portfolio_execution_engine` | **`python` / `numpy` / `numba` / `auto`**。若配置为 **`python`**，**不**固定走 pandas 循环，而是把「请求」替换为 **`PerfConfig.from_env().backtest_execution_engine`**（环境变量 **`FACTOR_BACKTEST_EXECUTION_ENGINE`**，默认 `python`），便于全局切换内核。若配置为 **`numpy`/`numba`/`auto`**，则直接使用该字面值参与解析（`numba` 不可用时回退 `numpy`，`auto` 优先 `numba`）。 |

### 4.6 防前视 / 滞后

| 字段 | 含义 |
|------|------|
| `target_lag_bars` | **仅单资产**：对齐行情后的目标序列再 **`shift(target_lag_bars)`**，空缺填 0。用于显式「晚一根 K 线才执行上一根信号」 |
| `portfolio_weight_lag_bars` | **仅多资产**：**`realized_weights = executed_weights.shift(portfolio_weight_lag_bars)`**（`executed_weights` 为执行层输出），**必须 ≥ 1**；默认 1 表示用 **上一 bar 已实现执行权重** 乘 **当期** 资产收益 |

---

## 5. 契约层：`contracts.py` 在干什么

### 5.1 `target_position`（单资产）

1. **输入形态**：`pd.Series`（需含列名或 `target_position`）或 `DataFrame`，必须有 **`target_position` 列**，或索引为 `DatetimeIndex` 的一列数据。
2. **`_to_timestamp_index`**：  
   - 若已是 `DatetimeIndex`：统一转 **无时区** `Timestamp`；  
   - 否则必须有 **`timestamp` 列**，解析后设为索引。
3. **校验**：索引 **不允许重复**；非单调则 **排序**。
4. **数值**：转 numeric → **`ffill`** → 首部缺失填 **0**；若仍有 NaN 则报错。
5. **边界**：`enforce_bounds` 且 `strict`：超出 `[-1,1]` 抛错；非 strict 则 **clip**。
6. **`align_target_position_to_index(index)`**：对 **行情索引** `reindex` → **`ffill`** → 缺失填 0，保证 **每一根 bar 都有目标值**（稀疏信号会变成「沿用上一次」）。

### 5.2 `target_weights`（多资产）

1. **输入**：  
   - DataFrame 列：`timestamp`, `symbol`, `target_weight`；或  
   - Series，且 **MultiIndex 名为** `['timestamp','symbol']`。
2. **校验**：无重复 `(timestamp, symbol)`；无 NaN；单标的权重在 `[-1,1]`（在 strict 下）。
3. **总杠杆**：每个 `timestamp` 上 **`abs(weight).sum()`** 不得超过 `max_gross_leverage`（默认 **1.0**），否则报错。
4. **`align_target_weights_to_index(index, symbols)`**：  
   - 先 pivot 成「时间 × 标的」矩阵；  
   - 对 **时间** `reindex` 到行情索引 → **按行 ffill** → 再 **按列对齐 symbols**；  
   - 最终摊平成 `(timestamp, symbol)` 与 **全组合 `(时间×标的)` 笛卡尔积** 对齐，缺失为 0。

### 5.3 `validate_temporal_integrity`（OHLCV 表）

- 若存在 **`event_time`** 与 **`arrival_time`**：检查 **`arrival_time >= event_time`**，否则在 strict 下报错（防 **因果倒置**）。
- 若存在 **`timestamp` 列**：strict 下 **不允许重复 timestamp**。

### 5.4 协议版本与必需键

- `BACKTEST_SCHEMA_VERSION`：当前 **`"1.0"`**。
- `REQUIRED_RETURNS_KEYS` / `REQUIRED_METRICS_KEYS` / `REQUIRED_SUMMARY_KEYS`：`report.build_backtest_report` 用来 **断言** 输出不缺键（扩展字段可增，但 **这些键必须存在**）。

---

## 6. 数据 IO：`io.py`

### 6.1 `load_target_position(path)`

读 csv/parquet → 直接走 **`validate_target_position`** → 返回 **Series**。

### 6.2 `load_ohlcv(path)`

1. 薄封装委托 **`strategy_layer.data.load_standard_ohlcv`**。
2. 读表 → `validate_temporal_integrity`。
3. 必须有列：`timestamp`, `open`, `high`, `low`, `close`。
4. `timestamp` → 无时区索引，**排序**。
5. 无 `volume` 则补 **0.0**。
6. `max_rows`：取 **尾部** 若干行。
7. 返回列：**`open, high, low, close, volume`**。

### 6.3 `load_ohlcv_from_config(config)`

要求 **`symbol` 与 `frequency` 非空**，并统一委托 **`strategy_layer.data.load_single_asset_ohlcv`**：

1. `market_data_mode="source_path"`：直接读取 `source_path`，要求文件已经是标准 OHLCV 列。
2. `market_data_mode="data_root"`（或留空）：沿用旧的目录/文件名自动发现逻辑，包括频率别名与黄金等前缀兼容。
3. `market_data_mode="aggregate_bars_daily_summary"`：从 `aggregate_bars_root/aggregate_dataset` 的 yearly 多 ticker parquet 中按 `symbol` 过滤，映射列后输出标准 OHLCV。
4. 若设置 `market_data_cache_root`，标准化结果会按 symbol/frequency 写入共享缓存；下次优先命中缓存，再回源。

---

## 7. 单资产执行流程（`run_single_asset_backtest`）逐步

以下按 **真实执行顺序** 编号。

1. **导入 backtrader**；失败则提示安装 `[backtest]`。
2. **`config = config or BacktestConfig()`**。
3. **`strict_real_data` 且传了 `ohlcv`** → **报错**（强制只从磁盘加载）。
4. **准备 `feed_frame`**：  
   - `ohlcv is None` → `load_ohlcv_from_config(config)`；  
   - 否则拷贝、按索引排序；必须是 **`DatetimeIndex`**；去时区；缺 `volume` 补 0；`max_rows` 则 **tail**。
5. **`validate_target_position`** → **`align_target_position_to_index(feed_frame.index)`**。
6. **`target_lag_bars`**：若 `>0`，对对齐后的序列 **`shift(lag).fillna(0)`**（**指纹与策略均使用滞后后的序列**）。
7. **`build_strategy_registry(bt)`** → **`registry.get(strategy_name, strategy_version)`**；未注册则报错。
8. 合并 **`runtime_params`**：`target_series` = 对齐（及滞后）后的序列；`rebalance_threshold` / `allow_short` / `short_margin_requirement` 来自 config 或 `strategy_params` 覆盖。
9. 生成 **`strategy_instance_id`**（uuid hex），并准备写入 summary 的 **`strategy_summary_params`**（含 **`target_lag_bars`**）。
10. **`Cerebro(stdstats=False)`**，喂入 **`PandasData`**，列仅限 **`open, high, low, close, volume`**。
11. **Broker**：`setcash`、`setcommission`；`slippage_perc>0` 则设滑点。
12. **`addstrategy`** → **`cerebro.run()`**。
13. 从 **`strategy.trace`** 取出时间戳、权益、实现仓位、目标仓位、佣金、成交笔数、可选 **trade_ledger**。
14. **`build_backtest_report(...)`**：  
    - `trade_ledger`：`metrics_profile=="fast"` 时强制不传；否则当 `include_trade_ledger` **或** `metrics_profile=="industrial"` 时传入。  
    - **`reproducibility_metadata`**：含 `mode=single`、`run_id`、`data_fingerprint`（见第 8 节）、依赖版本、`git_sha`。
15. **若 `borrow_rate_annual > 0`**：在报告生成后做 **事后扣减**（见第 12 节），**不**在 Backtrader 内逐日模拟融券。

### 7.1 内置策略 `target_position`（`strategy_library` + `strategy.py`）

每个 bar 的 **`next()`**：

1. 取当前 bar 时间戳 `ts`（无时区）。
2. **`target = target_series.get(ts, 0.0)`**（pandas Series 按时间索引取值）。
3. 检查做空许可与 **`short_margin_requirement`** 裁剪。
4. 若 **`abs(target - last_target) < rebalance_threshold`**：**不调仓**，但仍 **记录 bar**（见下）。
5. 否则 **`order_target_percent(target)`**，更新 `last_target`，再记录。

**`TargetPositionStrategyMixin._record_bar`**：**调仓与不调仓**两个分支都会调用，因此 **每一根 bar** 都有一条 trace（权益与目标对齐）：

- **`broker.getvalue()`** 作为 **权益**；
- **`close`** 计算 **持仓市值 / 权益 = realized_weight**（实现仓位权重）；
- 将 `timestamp`、权益、实现权重、**目标权重** 追加到 trace。

**`notify_order` / `notify_trade`**：在开启 ledger 时追加 **订单成交** 与 **trade 平仓** 记录，并维护 **MFE/MAE/持仓 bar 数** 等供工业层交易指标使用。

---

## 8. 可复现元数据与 `data_fingerprint`

### 8.1 `_build_reproducibility_metadata` + timing audit

每次运行在 `summary` 注入：

- **`run_id`**：新 uuid（**每次不同**）。
- **`data_fingerprint`**：见下。
- **`dependency_versions`**：`python`、`pandas`、`numpy`、`backtrader` 的版本（未安装为 `null`）。
- **`git_sha`**：自 `runner.py` 向上查找含 **`.git`** 的目录作为仓库根后执行 `git rev-parse HEAD`；失败则为 `null`。
- **`signal_timestamp`**：信号时间语义标注（当前为 `bar_close_t`）。
- **`decision_timestamp`**：决策时间语义标注（当前为 `bar_close_t`）。
- **`execution_effective_lag_bars`**：收益归因使用的有效滞后 bar 数（single=`target_lag_bars`，multi=`portfolio_weight_lag_bars`）。
- **`return_attribution`**：收益归因公式（如 `weights(t-1) * returns(t)`）。
- **`execution_engine_requested`**：多资产执行层 **解析后的** 请求内核。若 YAML 中 **`portfolio_execution_engine` 为 `python`**，该值来自 **`PerfConfig.from_env().backtest_execution_engine`**（环境变量 **`FACTOR_BACKTEST_EXECUTION_ENGINE`**），而不是字面保留 `python`；若 YAML 为 **`numpy`/`numba`/`auto`**，则与配置一致后再参与解析。
- **`execution_engine_resolved`**：最终实际执行内核（`python` / `numpy` / `numba`）：`numba` 不可用时回退 `numpy`，`auto` 优先 `numba`。

### 8.2 指纹算法（**不是**原始文件字节 hash）

- **单资产**：JSON 可序列化字典，包含：模式 `single`、bar 数、起止时间、OHLCV 列名、**每列** `_safe_series_stats`（sum/mean/std/first/last）、**目标序列**同样统计量 → **UTF-8 JSON（sort_keys）→ SHA256 hex**。
- **多资产**：模式 `multi`、标的排序、bar 数、起止时间、各标的 **close** 统计、**`executed_weights`（执行后权重矩阵）各列** `_safe_series_stats` → 同上（与 `runner._multi_asset_fingerprint(feeds, executed_weights)` 一致，**不是**对原始 `weight_matrix` 指纹）。

**用途**：同一条数据管线、同一套输入在统计意义上应得到 **相同指纹**；便于回归对比。**若仅浮点噪声变化而统计量不变，指纹可能不变**；若需文件级校验，应在数据管线另做 **文件 hash**。

---

## 9. 多资产执行流程（`run_multi_asset_backtest`）逐步

1. **`config` 默认** `BacktestConfig(portfolio_mode="multi")`。
2. **`_load_multi_asset_ohlcv`**：  
   - `strict_real_data` 且传入 **inline** `ohlcv_by_symbol` → **报错**；  
   - 有 dict：对每个标的 **`_normalize_ohlcv_frame`**（索引转无时区、缺 volume、tail）；  
   - 无 dict：必须提供 **`symbols` 列表**，对每个 symbol **`replace(config, symbol=...)`** 后 **`load_ohlcv_from_config`**。
3. 计算所有 feed **时间索引交集**；若为空 → **报错**；各 feed **`reindex(common_index)`**（对齐后价格行一致）。
4. **`ordered_symbols`**：来自参数 `symbols` 或 `feeds` 的键顺序。
5. **`validate_target_weights`** → **`align_target_weights_to_index(base_index, ordered_symbols)`** → **`unstack` 成 `weight_matrix`**（时间 × 标的）。
6. 拼 **`close_matrix`** / **`volume_matrix`**，**close** 若有缺失 → **报错**。
7. **`asset_return = close_matrix.pct_change().fillna(0)`**。
8. **`_apply_multi_asset_execution_and_cost(...)`**（`portfolio_execution_engine` 解析见 §4.5；内核为 pandas 逐 bar / numpy / numba）：由 **`weight_matrix`（目标）**、价格与成交量得到 **`executed_weights`**、**`turnover`**、**`cost_return`**（每 bar 成本收益率）、**`participation`**。逐 bar：`desired - prev` → 最小调仓阈值 → 可选 ADV 上限 → 换手与成本模型（bps + 可选线性/平方冲击）。
9. **`realized_weights = executed_weights.shift(portfolio_weight_lag_bars).fillna(0)`**；**`portfolio_weight_lag_bars < 1` → 报错**。
10. **`gross_return = (realized_weights * asset_return).sum(axis=1)`**。
11. **`net_return = gross_return - cost_return`**。
12. **权益曲线**：**`(1 + net_return).cumprod() * initial_cash`**。
13. **`portfolio_cost = cost_return * equity_prev`**（上一期权益）；**`commission_paid`** 为 **`portfolio_cost.sum()`**。
14. **`realized_position` / `target_position`**：`realized_position = realized_weights` 按行求和；`target_position = weight_matrix` 按行求和（统一报告形状）。
15. **`trades`**：**`turnover > 1e-12` 的 bar 数**（**不是**单资产委托笔数）。
16. **`build_backtest_report`** + **`data_fingerprint`**（多资产基于 **`executed_weights`** 列统计，见 §8.2）+ **`execution_engine_requested`/`resolved`** + timing audit。
17. **额外写入**：
    - `returns.portfolio_turnover`、`returns.portfolio_cost`、`returns.portfolio_participation`
    - `metrics.portfolio_turnover_total`、`metrics.portfolio_cost_total`、`metrics.portfolio_participation_max`。

---

## 10. 报告组装：`report.py`

1. 对 **`equity_curve` / `realized_position` / `target_position`** 排序并转 float。
2. **`period_return = equity_curve.pct_change().fillna(0)`**。
3. **`returns`** 固定含：`equity_curve`、`period_return`、`realized_position`。
4. **`compute_backtest_metrics(...)`**（见第 11 节）。
5. **`summary`**：含 `schema_version`、起止时间、bar 数、初末权益、**完整 `config` 快照**、最后一根 **目标仓位**；再 **`update` 策略元数据**与 **`reproducibility_metadata`**。
6. 若有 **`trade_ledger`**，则 **`artifacts.trade_ledger`**。
7. **校验** `REQUIRED_*` 键齐全，否则 **`RuntimeError`**。

---

## 11. 指标：`metrics.py` 分层说明

### 11.1 年化因子 `annualization_factor(index)`

- 用索引 **时间差的中位数** 估计 **每年有多少根 bar**：`252 * bars_per_day`（日内按纳秒推算）。
- 少于 2 根或差分异常时回退 **252**。

### 11.2 全档共有（`core` 起）

- **总收益**：`末/初 - 1`。
- **年化收益**：**复利**形式 `(1+总收益)^(ann/len) - 1`（与样本长度、ann 相关）。
- **波动率**：`period_return` 标准差 × `sqrt(ann)`。
- **夏普**：`(annual_return - risk_free_rate_annual) / vol`。
- **最大回撤**：基于权益曲线 **cummax** 的 **`equity/cummax - 1`** 最小值。
- **换手**：**`realized_position.diff().abs()`**，首根用 **`abs(realized)`**；为 **全样本求和**（非年化），含义是 **仓位权重变化绝对值之和** 的简化指标。
- **`trades`**、**`commission_paid`**：由上游传入。

### 11.3 `standard` 在 core 上增加

- **下行波动**（仅负收益段）、**Sortino**、**Calmar**、**bar 正收益比例**。
- **Alpha/Beta**：对 **benchmark** 与策略 **`period_return` inner join** 后协方差/方差；**Alpha** 为 **周期均值调整 × ann**（实现以代码为准）。
- **容量估计**、**换手敏感性**（佣金倍数情景）。
- **基准扩展**：信息比率、跟踪误差、Treynor、上下行 capture、R² 等（均依赖 **对齐后的 benchmark**）。

### 11.4 `industrial` 在 standard 上再增加

- 偏度、峰度、**VaR/CVaR（5%）**、回撤持续时间、平均回撤、佣金/换手比、**年化换手**。
- **Ulcer**、MAR、Sterling、Burke、**Omega**（阈值与无风险/ann 相关）、尾部比、**Hurst**（短序列可能为 0）、**time_in_market / exposure**（基于 `realized_position`）。
- **`_trade_metrics`**：基于 **平仓事件** 的胜率、盈亏比、连亏、持仓 bar、期望、Kelly、MFE/MAE 等（无 ledger 则全 0）。

---

## 12. 单资产融券成本（事后近似）

当 **`borrow_rate_annual > 0`** 且权益序列非空：

- `avg_short = mean(max(-realized_position, 0))`（空头暴露强度近似）。
- `borrow_cost = initial_cash * avg_short * borrow_rate_annual * (bars / 252)`。
- 若 `borrow_cost > 0`：  
  - **`metrics["commission_paid"]`** 加上该成本；  
  - **`summary["final_equity"]`** 减去该成本；  
  - **`metrics["total_return"]`** 按 **新 final_equity** 相对 **initial_cash** 重算。

这是 **研究用近似**，**不是** 逐日融券或保证金仿真。

---

## 13. 与「未来函数」相关的边界（必读）

1. **引擎不验证** 你的因子是否用了 **当前 bar 收盘后才可得** 的信息；**`target_lag_bars`** 只是 **机械滞后**，用于团队内固定一种「晚一根执行」的约定。
2. **多资产**：组合层 **`realized_weights`** 来自 **`executed_weights.shift(portfolio_weight_lag_bars)`**（执行层输出再滞后），**不是**对原始目标矩阵直接 `shift`。通过 **`portfolio_weight_lag_bars ≥ 1`** 保证 **不用「未滞后的执行权重」乘当期收益**（默认 1 即常见 **上一 bar 执行权重 × 当期资产收益**）。
3. **单资产 Backtrader** 的成交时刻与 **cheat-on-close** 等 **未在本 README 展开**；若与「收盘信号、次日开盘成交」等严格对齐，需在策略/参数层另行统一。
4. **基准序列** 必须与 **`period_return` 时间对齐**；否则 **alpha/β** 等会失真。

---

## 14. 已实现功能全量清单（对照 `single_asset_backtest/`，便于自查）

下面按 **「你能用什么」** 汇总；若本文前文章节与下表冲突，**以源码与 ADR 为准**，并建议更新 README。

### 14.1 入口函数

| 函数 | 说明 |
|------|------|
| `run_single_asset_backtest` | 单标的 + Backtrader；参数含 `ohlcv`、`target_position`、`config`、`strategy_name` / `strategy_version` / `strategy_params`、**`benchmark_return`**、**`avg_daily_volume`**（容量估计用） |
| `run_single_asset_backtest_batch` | 单标的批量入口；输入任务列表，`max_workers=1` 串行，`max_workers>1` 任务级多进程并行；输出顺序与输入一致 |
| `run_multi_asset_backtest` | 组合向量回测；参数含 `ohlcv_by_symbol` 或 `symbols` + `config`、`target_weights` |
| `build_backtest_report` | 低层组装报告（一般由 `runner` 调用） |
| `load_ohlcv` / `load_ohlcv_from_config` | 读行情 |
| `load_target_position` | 读目标仓位文件 |
| `validate_target_position` / `align_target_position_to_index` | 单资产目标契约与对齐 |
| `validate_target_weights` / `align_target_weights_to_index` | 多资产权重契约；**`validate_target_weights(..., max_gross_leverage=1.0)`** 可收紧总杠杆 |

**包根 `__init__.py` 当前导出**：未包含 `run_multi_asset_backtest` 与多资产契约函数，需 `from single_asset_backtest.runner import ...` / `from single_asset_backtest.contracts import ...`。

### 14.2 单资产策略与执行

| 能力 | 说明 |
|------|------|
| 内置策略 | `target_position@1.0`（`strategy_library`） |
| 策略注册 | `StrategyRegistry`：按 **name + version**，未指定 version 取 **最新** |
| 调仓 | `order_target_percent`；**`rebalance_threshold`** 抑制微小调仓 |
| 成本 | `commission`、`slippage_perc`（Backtrader broker） |
| 做空 | **`allow_short`**、**`short_margin_requirement`**（裁剪空头目标） |
| 目标滞后 | **`target_lag_bars`**（对齐后再 `shift`；参与 **data_fingerprint**） |
| 严格真数据 | **`strict_real_data`** 禁止 inline OHLCV |
| 交易账本 | `include_trade_ledger=True` 可显式开启；`metrics_profile="industrial"` 自动开启；`metrics_profile="fast"` 强制关闭 |
| 融券近似 | **`borrow_rate_annual > 0`** 时事后扣减（§12） |

### 14.3 多资产组合

| 能力 | 说明 |
|------|------|
| 收益 | 先 **`executed_weights`**（执行层），再 **`realized_weights = executed_weights.shift(portfolio_weight_lag_bars)`**；**`gross = sum(realized * asset_return)`**，**`net = gross - cost_return`**；**`portfolio_weight_lag_bars`（≥1，默认 1）** |
| 执行约束 | `portfolio_min_trade_weight`（最小调仓阈值）、`portfolio_adv_participation_cap`（按 ADV 约束每 bar 可执行权重变化） |
| 执行内核 | **`portfolio_execution_engine`**：`python` 时实际请求来自 **`FACTOR_BACKTEST_EXECUTION_ENGINE`**；`numpy`/`numba`/`auto` 按配置解析（见 §4.5）；`summary` 含 **requested/resolved** |
| 成本 | 基础 bps 成本（`portfolio_commission_bps` + `portfolio_spread_bps`）+ 可选冲击成本 |
| 成本模型字段 | `portfolio_cost_model`（`simple_bps` / `linear_impact` / `square_impact`）+ `portfolio_impact_coeff` |
| 输出增量 | `returns.portfolio_turnover`、`returns.portfolio_cost`、`returns.portfolio_participation`；`metrics.portfolio_turnover_total`、`metrics.portfolio_cost_total`、`metrics.portfolio_participation_max` |
| 严格真数据 | 禁止 inline `ohlcv_by_symbol`，必须从磁盘按标的加载 |

### 14.4 报告结构（协议）

| 顶层键 | 内容 |
|--------|------|
| `returns` | 至少含 `equity_curve`、`period_return`、`realized_position`；多资产可额外含 `portfolio_*` |
| `metrics` | 至少含 `REQUIRED_METRICS_KEYS` 所列核心键；分层扩展见下表 |
| `summary` | 至少含 `REQUIRED_SUMMARY_KEYS`；通常还有策略元数据、**`run_id`/`mode`/`data_fingerprint`/`dependency_versions`/`git_sha`** 等 |
| `artifacts` | 可选 **`trade_ledger`** |

冻结常量见 **`contracts.py`**：`BACKTEST_SCHEMA_VERSION`、`REQUIRED_RETURNS_KEYS`、`REQUIRED_METRICS_KEYS`、`REQUIRED_SUMMARY_KEYS`。

### 14.5 指标键名按 `metrics_profile`（与 `metrics.py` 一致）

**`core` / `fast`**：`total_return`、`annual_return`、`volatility`、`sharpe`、`max_drawdown`、`turnover`、`trades`、`commission_paid`（`fast` 与 `core` 指标键与数值语义一致，差异仅在跳过扩展指标与禁用 ledger 以降低开销）。

**`standard`**：在 core 上增加（含但不限于）  
`downside_volatility`、`sortino`、`calmar`、`hit_rate_bar`、`alpha`、`beta`、`capacity_estimate`、`turnover_sensitivity`（dict）、**`information_ratio`、`tracking_error`、`treynor`、`up_market_capture`、`down_market_capture`、`r_squared`**（依赖 **`benchmark_return`**；无基准时为 0）。

**`industrial`**：在 standard 上再增加（含但不限于）  
`skew`、`kurtosis`、`var_95`、`cvar_95`、`max_drawdown_duration_bars`、`avg_drawdown`、`commission_to_turnover`、`turnover_annualized`、`ulcer_index`、`mar_ratio`、`sterling_ratio`、`burke_ratio`、`tail_ratio`、`omega_ratio`、`recovery_factor`、`hurst_exponent`、`time_in_market`、`exposure`，以及 **`_trade_metrics`** 产出：**`win_rate_trade`、`profit_factor`、`max_consecutive_losses`、`avg_holding_period_bars`、`expectancy`、`kelly_fraction`、`avg_mfe`、`avg_mae`**（无 **`trade_ledger`** 平仓事件时多为 0）。

**无风险利率**：**`risk_free_rate_annual`** 参与夏普、Treynor、Omega 阈值等。

### 14.6 IO 与数据发现

| 能力 | 说明 |
|------|------|
| 格式 | OHLCV：`timestamp` + OHLC（**volume** 可缺省补 0）；`target_position`：列或索引时间 |
| 路径发现 | **`data_root/symbol/frequency`**、扁平 `{symbol}_{frequency}*`、**黄金别名**（`gold` 子目录、XAU/XAUUSD/GOLD、**频率字符串别名**如 `1h`↔`1_hour`） |
| 时间校验 | **`strict_temporal_validation`**：`timestamp` 重复、**`arrival_time < event_time`** 等 |

### 14.7 本文未逐行展开但已实现的部分

- Backtrader **具体成交时刻**（默认是否下一根成交等）：以 **Backtrader 版本与 broker 设置** 为准；README **§13** 已提示与 cheat-on-close 相关边界。  
- **多资产 `trades` 含义**：换手大于阈值的 **bar 数**，与单资产 **委托笔数** 不同（§9）。  
- **环境变量 `FACTOR_BACKTEST_EXECUTION_ENGINE`**：当 YAML 中 **`portfolio_execution_engine: python`** 时，真正参与解析的请求内核来自此处（见 `runtime/perf_config.py`），便于不改业务配置切换 **pandas / numpy / numba / auto**。

若你希望 **某一节与 `metrics.py` 逐行同步**，维护方式建议是：指标列表以 **`compute_backtest_metrics` 返回 dict 的键** 为单一事实来源，或从测试 **`test_backtest_metrics_extended.py`** 断言同步。

---

## 15. 建议阅读顺序（与本文关系）

1. 本文（全局数据流）。  
2. 冻结协议与业务措辞：[`factor_layer/factor_engine/docs/adr_backtest_target_position.md`](../../factor_layer/factor_engine/docs/adr_backtest_target_position.md)。  
3. 示例：[`backtest_single_asset.py`](../examples/backtest_single_asset.py)、[`backtest_multi_asset.py`](../examples/backtest_multi_asset.py)。  
4. 需要改执行细节时再对照本目录 **`runner.py` / `strategy.py`** 源码。

---

## 16. 运行相关测试

回测专项测试位于 **`backtest_layer/tests/`**（`test_backtest_*.py`）；`conftest.py` 会把 **仓库根**、**`backtest_layer`** 与 **`factor_layer/factor_engine`** 加入 `sys.path`，一般无需手写 `PYTHONPATH`。在 **仓库根** 执行：

```bash
cd /path/to/quantsociety_backend_project
pytest backtest_layer/tests/test_backtest_*.py -q
```

若不用 pytest 而直接跑脚本，仍建议按文首 **`export PYTHONPATH=...repo_root:...backtest_layer:...factor_engine`**。需已安装 **`backtrader`**（`pip install "factor-engine[backtest]"`）。

---

## 17. 协作补充（研究员 C、排错、团队日志）

### 17.1 与研究员 C（`single_asset_alpha`）的输入

- **推荐交付**：由 C 的 **`TargetPositionSchema.format_output`** 得到的长表（含 `timestamp`、`symbol`、`target_position`）；D 侧 **`validate_target_position`** 会取 `target_position` 列并对齐到行情索引。  
- **端到端**：同一根 OHLCV 上先 C 后 D，见 **`strategy_layer/single_asset_alpha/integration/backtest_bridge.py`** 与示例 **`strategy_layer/single_asset_alpha/examples/c_to_d_end_to_end.py`**（C 侧 README 有环境与滞后说明）。  
- **滞后**：C 的 **`shift_bars`** 与 **`BacktestConfig.target_lag_bars`** 不要重复叠满，见 C 侧 README **「与 D 侧的滞后约定」**。
- **双 lag 保护**：若你通过 C→D bridge（`run_pipeline_then_single_asset_backtest`）联跑，桥接层会在 **`shift_bars>0` 且 `target_lag_bars>0`** 时直接抛出 `ValueError("Detected double lag ...")`；修复方式是二选一：要么保留 C 侧 shift、把 D 侧 lag 设 0，要么反过来。

### 17.2 常见问题（排错顺序）

1. **`import strategy_layer.data` / `import single_asset_backtest` / `import runtime` 失败**：检查 `PYTHONPATH` 是否同时包含 **仓库根**、**`backtest_layer`** 与 **`factor_layer/factor_engine`**（文首「运行时代码路径」）。  
2. **单资产回测报错缺 `backtrader`**：`pip install "factor-engine[backtest]"`。  
3. **`target_position` 与行情对不齐**：确认 **时间索引 / `timestamp` 列**与 OHLCV **频率、日历**一致；契约侧会对齐并 `ffill`，但错频会得到错误经济含义。  
4. **多资产执行结果与配置不一致**：当 **`portfolio_execution_engine == "python"`** 时，实际内核可能由环境变量 **`FACTOR_BACKTEST_EXECUTION_ENGINE`** 决定（见 **`runtime/perf_config.py`**），`summary` 中会写 **requested / resolved**。

### 17.3 团队进度与变更说明

阶段进展与可复用的 **git commit 说明**可写在仓库根 **`GROUP_DEVELOP_LOG.md`**（约定：**新记录写在文件最上方**）。与本子系统相关的协议仍以 **`docs/adr_backtest_target_position.md`** 与本文为准。
