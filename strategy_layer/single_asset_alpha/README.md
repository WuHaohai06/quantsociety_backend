# single_asset_alpha — 单标的择时信号与目标仓位模块

> 研究员 C (汤宏恩) 专属工作目录

## 模块定位

本模块是单标的择时路径的 **"策略大脑"**，负责将行情数据与因子数据提炼为交易信号，并转化为标准化的 **目标仓位 (target_position)** 文件交付给研究员 D (孙海崴) 的 Backtrader 回测框架。

**核心原则: 预测与执行完全解耦。** 本模块只计算 "该拿多少仓位"，不涉及任何执行层逻辑 (滑点、手续费、资金管理等)。

## 目录结构

```text
single_asset_alpha/
│
├── core/                           # 核心抽象层
│   ├── base_signal.py              # C-1 信号生成抽象基类
│   ├── base_position.py            # C-2 仓位映射抽象基类
│   └── schema.py                   # target_position 数据契约 (Schema)
│
├── config.py                       # YAML 配置 dataclass + 校验
├── config_runner.py                # 配置 → 对象装配 → pipeline 运行
├── data_loader/                    # 数据适配层
│   └── fetcher.py                  # 行情与因子数据加载器
│
├── strategies/                     # 具体策略实现
│   ├── signals/                    # C-1 信号池
│   │   ├── dual_ma_signal.py       # 双均线交叉信号
│   │   ├── macd_signal.py          # MACD 柱状图信号
│   │   ├── rsi_signal.py           # RSI 均值回复信号
│   │   ├── factor_threshold_signal.py  # 外部因子阈值信号
│   │   └── signal_combiner.py      # 多信号组合器
│   │
│   └── position_mappers/           # C-2 状态机池
│       ├── simple_mapper.py        # 固定阈值双阈值状态机
│       └── atr_volatility_mapper.py # ATR 波动率自适应状态机
│
├── pipeline.py                     # 【总控制台】串联 Data → Signal → Position → 落盘
├── integration/                  # 与研究员 D 回测层衔接（见下文「与研究员 D」）
│   └── backtest_bridge.py          # C 流水线 → ``single_asset_backtest.run_single_asset_backtest``
├── mock_delivery.py                # Sprint 0 Mock 交付脚本
│
├── examples/                       # 示例脚本
│   ├── configs/                    # 配置化运行示例 YAML
│   ├── simple_demo.py              # C-1/C-2 最小演示（不落盘回测）
│   ├── factor_lake_signal_demo.py  # 基于 factor_lake_root 的单资产因子信号示例
│   └── c_to_d_end_to_end.py        # C → D 全链路（信号→target_position→Backtrader 报告）
│
├── tests/                          # 单元测试
│   ├── test_signal_position.py     # 信号、仓位、未来函数防护测试
│   └── test_config_runtime.py      # 配置文件加载与 run_from_config 回归
│
├── run_from_config.py              # YAML 配置运行 CLI
└── README.md                       # 本文件
```

## 快速开始

### Sprint 0: Mock 交付 (给研究员 D)

```bash
cd quantsociety_backend_project
python strategy_layer/single_asset_alpha/mock_delivery.py
```

输出 `outputs/MOCK_000001.SZ_target_position.csv` 。

### 运行完整策略流水线

```bash
# 使用模拟数据
python -m strategy_layer.single_asset_alpha.pipeline --strategy combined --symbol 000001.SZ --format csv

# 可选参数
#   --strategy: dual_ma / macd / combined
#   --allow-short: 允许做空
#   --periods: 模拟数据天数
```

### 通过配置文件跑通 pipeline

```bash
cd quantsociety_backend_project
python strategy_layer/single_asset_alpha/run_from_config.py \
	strategy_layer/single_asset_alpha/examples/configs/dual_ma_mock.yaml
```

现成示例配置有三份：

- `examples/configs/dual_ma_mock.yaml`: 纯技术面双均线 + mock 行情
- `examples/configs/combined_mock.yaml`: 多技术信号组合 + ATR mapper + mock 行情
- `examples/configs/factor_threshold_factor_lake.yaml`: factor lake 多因子 + factor_threshold
- `examples/configs/aggregate_bars_dual_ma.yaml`: massive_parquet aggregate_bars 原生日频行情 + DualMA

配置化运行会继续沿用现有 `target_position` 输出，并额外在输出目录写一份 `config_snapshot.yaml`。

### 从 factor lake 走单资产因子信号

```bash
cd quantsociety_backend_project
python strategy_layer/single_asset_alpha/examples/factor_lake_signal_demo.py
```

这个示例会临时构造一个最小 factor lake，然后通过 `DataFetcher(factor_lake_root=..., factor_refs=...)`
把因子喂给 `FactorThresholdSignal`。团队后续新增示例时，默认应走这条入口，而不是旧的 `factor_root`
私有宽表路径。

### 运行测试

```bash
cd quantsociety_backend_project
python -m pytest strategy_layer/single_asset_alpha/tests/ -v
```

## target_position 数据契约 (冻结版)

| 字段名 | 类型 | 说明 | 示例 |
|:---|:---|:---|:---|
| `timestamp` | datetime | 指令执行时间 (T+1 开盘) | `2024-04-03 15:00:00` |
| `symbol` | string | 标的代码 | `000001.SZ` |
| `target_position` | float | 目标资金权重 ∈ [-1, 1] | `0.5` |
| `signal_value` | float | *(可选)* 原始信号值 | `0.85` |
| `action_name` | string | *(可选)* 状态机动作名 | `ENTRY_LONG` |

### 动作名枚举

| 枚举值 | 含义 |
|:---|:---|
| `HOLD` | 维持当前仓位 |
| `ENTRY_LONG` | 开多 |
| `EXIT_LONG` | 平多 |
| `ENTRY_SHORT` | 开空 |
| `EXIT_SHORT` | 平空 |
| `STOP_LOSS` | 止损 |
| `TAKE_PROFIT` | 止盈 |

## 模块设计要点

### C-1: 信号生成层

- 所有信号实现继承 `BaseSignalGenerator` 抽象基类
- **强制向量化**：使用 Pandas `.shift()`, `.rolling()`, `.ewm()` 等操作
- 输出为连续信号 `pd.Series`，经 `tanh()` 压缩到 `(-1, 1)`
- 支持单信号和多信号加权组合

### C-2: 仓位映射层

- 所有映射器继承 `BasePositionMapper` 抽象基类
- **双阈值滞回机制**：避免信号在阈值附近震荡导致频繁换手
- **ATR 自适应**：高波动放宽阈值，低波动收紧阈值
- **仓位缩放**：基于目标波动率 / 风险平价

### ⚠️ 未来函数防护

- **T 日收盘信号 → T+1 开盘执行**
- 所有仓位映射器在最终输出前统一执行 `.shift(1)`
- 单元测试中包含专门的 look-ahead bias 检测用例

### 参数配置化

- 所有超参数通过 `params: dict` 传入
- 零 magic number（如 `if close > 5.5`）
- 便于后续策略库网格寻优和前端配置

## 与研究员 D（回测层）代码衔接

研究员 D 的实现位于 monorepo **`backtest_layer/single_asset_backtest/`**（`run_single_asset_backtest`、契约与报告协议），与本文档冻结的 **`target_position` 列约定**一致：`timestamp` + `target_position`（`[-1,1]`），可选 `symbol` / `signal_value` / `action_name`。

| 步骤 | 代码位置 |
|:---|:---|
| C-1 信号 | `core/base_signal.py`，`strategies/signals/` |
| C-2 目标仓位 | `core/base_position.py`，`strategies/position_mappers/` |
| 落盘 Schema | `core/schema.py`（`TargetPositionSchema`） |
| 串联流水线 | `pipeline.py`（`StrategyPipeline.run`） |
| **→ D 回测** | `integration/backtest_bridge.py` 中 **`run_pipeline_then_single_asset_backtest`**：同一 `market_data` 上先跑 C 再调 `run_single_asset_backtest` |
| 一键示例 | `examples/c_to_d_end_to_end.py`（需 `pip install "factor-engine[backtest]"` 与文首 `PYTHONPATH`） |

D 侧详细说明：**[`../../backtest_layer/single_asset_backtest/README.md`](../../backtest_layer/single_asset_backtest/README.md)**；协议 ADR：**[`../../factor_layer/factor_engine/docs/adr_backtest_target_position.md`](../../factor_layer/factor_engine/docs/adr_backtest_target_position.md)**。

## 环境与依赖

| 场景 | 说明 |
|:---|:---|
| 仅跑本模块（`pipeline` / `mock_delivery` / `pytest strategy_layer/single_asset_alpha/tests`） | 依赖 **pandas / numpy**；在项目根执行时保证 **`sys.path`** 含仓库根（示例脚本已处理）。 |
| 跑 **C → D 端到端**（`integration`、`examples/c_to_d_end_to_end.py`） | 需 **`pip install "factor-engine[backtest]"`**；并令 `PYTHONPATH` 含 **`backtest_layer`** 与 **`factor_layer/factor_engine`**（与 D 侧 README 文首一致）。 |
| 从因子库读 **factor_data** | 默认配置 **`DataFetcher(factor_lake_root=..., factor_refs=...)`**；`factor_refs` 可直接写因子 ID，也可用 `FactorRef(factor_id, alias)` 指定单资产侧列名。旧的 `factor_root` 私有宽表路径只保留兼容，不再作为新示例入口。 |

## factor lake 推荐接入方式

```python
from strategy_layer.data import FactorRef
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher

fetcher = DataFetcher(
	factor_lake_root="/path/to/factor_lake",
	factor_refs=[
		FactorRef("my_factor_v1", "alpha_score"),
		"timing_factor_v2",
	],
)

factor_data = fetcher.load_factor_data(symbol="000001.SZ")
```

约定如下：

- `factor_lake_root` 指向 factor_engine 的 lake 根目录
- `factor_refs` 控制单资产侧最终看到的列名
- `factor_names=[...]` 传给 `load_factor_data()` 时，若 `factor_refs` 配了 alias，会按 alias 取子集
- 若只跑技术面信号，可不配置任何因子源

## 配置文件接口（V1）

配置文件入口现在支持：

- `meta`: `strategy_id` / `version` / `description`
- `instrument`: 单一 `symbol`
- `market_data`: `data_root`、`source_path`、`mock` 或 `aggregate_bars_daily_summary`，并可选 `cache_root`
- `factor_source`: `none`、`factor_lake`、`source_path`、`legacy_factor_root`
- `signal`: `dual_ma` / `macd` / `rsi` / `factor_threshold` / `combined`
- `position_mapper`: `threshold` / `atr_volatility`
- `run`: `start_date` / `end_date`
- `output`: 输出目录、格式与是否保存 full/debounced

配置设计原则：

- 保留现有 Python API，不把 `StrategyPipeline` 改造成只认配置
- 白名单映射信号与 mapper 类型，不允许任意类路径反射
- `combined` 允许递归子信号配置
- `factor_threshold` 与 `factor_lake_root` 直接对接，支持 `factor_refs` + alias
- `market_data` 统一委托 **`strategy_layer.data.market_data.load_single_asset_ohlcv`**，与 D 侧 `single_asset_backtest` 共用同一行情标准化入口
- `aggregate_bars_daily_summary` 原生适配 massive_parquet 的 yearly 多 ticker 日频汇总表，经公共 loader 转换为标准 OHLCV；若配置 `cache_root`，会把标准化结果缓存为项目内可复用的单标的 parquet

## C → D 一键跑通（端到端）

在 **monorepo 根目录**：

```bash
export PYTHONPATH="$PWD:$PWD/backtest_layer:$PWD/factor_layer/factor_engine"
pip install "factor-engine[backtest]"   # 未装过时
python strategy_layer/single_asset_alpha/examples/c_to_d_end_to_end.py
```

等价 API：`from strategy_layer.single_asset_alpha.integration import run_pipeline_then_single_asset_backtest`（参数见 `integration/backtest_bridge.py`）。

## 与 D 侧的滞后约定（务必对齐）

| 侧 | 机制 | 说明 |
|:---|:---|:---|
| **C** | `position_mappers` 内 **`shift_bars`（默认 1）** | 表示「信号在 T 可得 → 仓位在 T+1 起生效」类语义。 |
| **D** | **`BacktestConfig.target_lag_bars`** | 在已与 OHLCV 对齐的 `target_position` 上 **再** `shift`。 |

**不要两边同时叠满**：若 C 已 `shift(1)`，D 侧一般 **`target_lag_bars=0`**；若 C 输出当日对齐、不做 shift，再交给 D 统一滞后，则 **`target_lag_bars≥1`**。与研究员 D 约定一种默认即可。

### C→D 性能与调用边界（建议）

- **单次研究迭代优先速度**：D 侧可用 `BacktestConfig(metrics_profile="fast")`，该档位保持核心指标契约，同时强制关闭 trade ledger，减少不必要开销。
- **参数网格 / 多窗口批量**：优先用 D 侧 `run_single_asset_backtest_batch(tasks=[...], max_workers>1)` 做任务级并行；输入任务的顺序会被保留到输出。
- **单次短回测**：不建议盲目开多进程。进程启动与序列化成本可能大于收益，先用 `max_workers=1` 复现基线再放大。
- **文档入口**：D 侧的完整性能说明、批量 API 约束与示例见 `backtest_layer/single_asset_backtest/README.md` 的「单资产性能优化指南（实践版）」。

## 常见问题

- **`ModuleNotFoundError: single_asset_backtest` / `runtime`**：未配置 `PYTHONPATH`，见上文「环境与依赖」。  
- **`ImportError: backtrader`**：未安装 `factor-engine[backtest]`。  
- **因子列名和 factor_id 对不上**：若你在 `factor_refs` 里用了 alias，后续 `factor_names=[...]` 也应传 alias，而不是 factor lake 里的原始 factor_id。  
- **Schema 校验报 `target_position` 越界**：检查 C-2 输出是否在 **[-1, 1]**；或 D 侧暂时 `enforce_target_bounds=False`（不推荐长期）。  
- **回测结果与预期差一截 bar**：先核对 **行情索引** 与 **`timestamp` 列**是否同一交易日历、频率是否一致。

## 团队文档与进度

协作说明与阶段产出可记在仓库根 **`GROUP_DEVELOP_LOG.md`**（新记录写在文件**最上面**）；本模块对接人见文首研究员标注。

