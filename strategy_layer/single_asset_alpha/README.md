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
│   ├── simple_demo.py              # C-1/C-2 最小演示（不落盘回测）
│   └── c_to_d_end_to_end.py        # C → D 全链路（信号→target_position→Backtrader 报告）
│
├── tests/                          # 单元测试
│   └── test_signal_position.py     # 信号、仓位、未来函数防护测试
│
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

