# single_asset_alpha 技术文档

> 研究员 C 单标的择时信号与目标仓位模块 — 完整技术手册

---

## 一、模块总览

### 1.1 定位

`single_asset_alpha` 是单标的择时/CTA 路径的**策略大脑**。它从行情数据和因子数据出发，经过信号计算和仓位映射两个阶段，最终输出标准化的 `target_position` 文件。这份文件是研究员 C 向研究员 D 交付的**唯一产物**，D 拿到后直接灌入 Backtrader 做执行回测。

整个模块的核心思想是 **预测与执行完全解耦**：

- **本模块只回答一个问题**：在 T+1 时刻，这个标的应该持有多少仓位？
- **本模块不关心的事情**：滑点多大、手续费多少、资金够不够买、订单能不能成交 —— 这些全部由 Backtrader 处理。

### 1.2 目录结构

```
strategy_layer/single_asset_alpha/
│
├── core/                               ← 核心抽象层（不可修改的契约）
│   ├── __init__.py
│   ├── base_signal.py                  ← C-1 信号生成抽象基类
│   ├── base_position.py                ← C-2 仓位映射抽象基类
│   └── schema.py                       ← target_position 数据契约
│
├── data_loader/                        ← 数据适配层
│   ├── __init__.py
│   └── fetcher.py                      ← 行情/因子数据加载 + 模拟数据生成
│
├── strategies/                         ← 具体策略实现（可任意扩展）
│   ├── signals/                        ← C-1 信号池
│   │   ├── dual_ma_signal.py           ← 双均线交叉
│   │   ├── macd_signal.py              ← MACD 柱状图
│   │   ├── rsi_signal.py               ← RSI 均值回复
│   │   ├── factor_threshold_signal.py  ← 外部因子阈值
│   │   └── signal_combiner.py          ← 多信号加权组合器
│   │
│   └── position_mappers/               ← C-2 状态机池
│       ├── simple_mapper.py            ← 固定阈值双阈值状态机
│       └── atr_volatility_mapper.py    ← ATR 波动率自适应状态机
│
├── pipeline.py                         ← 总控制台（串联全流程 + CLI 入口）
├── mock_delivery.py                    ← Sprint 0 Mock 交付脚本
│
├── examples/
│   └── simple_demo.py                  ← 最简示例
│
├── tests/
│   └── test_signal_position.py         ← 单元测试（20 个用例）
│
├── README.md
└── TECHNICAL_DOC.md                    ← 本文件
```

### 1.3 技术栈

| 依赖 | 用途 |
|:---|:---|
| Python 3.11+ | 运行时 |
| pandas | 核心数据结构 (DataFrame / Series) |
| numpy | 数值计算、tanh 压缩、数组操作 |
| pytest | 单元测试 |

**明确不使用**: Backtrader、任何交易执行框架、任何 ML 框架（当前版本）。

---

## 二、架构设计

### 2.1 分层架构

模块采用经典的三层分离设计：

```
┌─────────────────────────────────────────────────────────┐
│                    pipeline.py (总控)                     │
│    StrategyPipeline.run() 串联下面三层                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐        ┌─────────────────────┐    │
│  │   C-1 信号层     │ ────→  │   C-2 仓位映射层     │    │
│  │ BaseSignalGen.  │        │ BasePositionMapper  │    │
│  │   .generate()   │        │  .map_to_position() │    │
│  └────────┬────────┘        └──────────┬──────────┘    │
│           │                            │               │
│           │  pd.Series (signal)        │  pd.DataFrame  │
│           │  ∈ (-1, 1)                 │  (target_pos)  │
│           │                            │               │
├───────────┴────────────────────────────┴───────────────┤
│                  data_loader/fetcher.py                  │
│       DataFetcher: 屏蔽上游存储细节，提供统一接口          │
├─────────────────────────────────────────────────────────┤
│                    core/ (契约层)                         │
│  base_signal.py  |  base_position.py  |  schema.py      │
└─────────────────────────────────────────────────────────┘
```

**层间通信规则**：

| 边界 | 数据格式 | 说明 |
|:---|:---|:---|
| DataFetcher → Signal | `pd.DataFrame` (OHLCV) | 索引为 DatetimeIndex |
| Signal → PositionMapper | `pd.Series` (signal) | 连续值，经 tanh 压缩到 (-1,1) |
| PositionMapper → Pipeline | `pd.DataFrame` | 含 target_position, signal_value, action_name 三列 |
| Pipeline → 文件 | `.parquet` / `.csv` | 符合 TargetPositionSchema 的标准格式 |

### 2.2 类继承关系

```
ABC
├── BaseSignalGenerator          ← core/base_signal.py
│   ├── DualMASignal             ← strategies/signals/dual_ma_signal.py
│   ├── MACDSignal               ← strategies/signals/macd_signal.py
│   ├── RSISignal                ← strategies/signals/rsi_signal.py
│   ├── FactorThresholdSignal    ← strategies/signals/factor_threshold_signal.py
│   └── SignalCombiner           ← strategies/signals/signal_combiner.py
│
└── BasePositionMapper           ← core/base_position.py
    ├── ThresholdPositionMapper  ← strategies/position_mappers/simple_mapper.py
    └── ATRVolatilityMapper      ← strategies/position_mappers/atr_volatility_mapper.py
```

每个具体类只需实现一个抽象方法（`generate()` 或 `map_to_position()`），参数全部通过 `params: dict` 传入。

---

## 三、数据流详解

### 3.1 端到端数据流

以"双均线 + 固定阈值"策略为例，完整数据流如下：

```
[上游数据]                [C-1 信号层]              [C-2 仓位层]            [输出]
                                                                    
 OHLCV parquet   ──→  DataFetcher  ──→  DualMASignal  ──→  ThresholdMapper  ──→  target_position
   (日频行情)       .load_market_data()    .generate()       .map_to_position()      .parquet/.csv
                                                                    
                  pd.DataFrame          pd.Series           pd.DataFrame       pd.DataFrame
                  索引: datetime         索引: datetime      索引: datetime      列: timestamp,
                  列: OHLCV             值: (-1, 1)         列: target_pos,       symbol,
                                        NaN保留               signal_value,       target_position,
                                                              action_name        signal_value,
                                                                                  action_name
                                                            ★ 此处执行 shift(1)
                                                              防未来函数
```

### 3.2 关键数据变换细节

#### 阶段 1：原始行情 → 信号值

以 `DualMASignal` 为例，计算过程为：

```python
close = market_data["close"]

# Step A：计算快慢均线
fast_ma = close.rolling(window=5).mean()     # 5 日均线
slow_ma = close.rolling(window=20).mean()    # 20 日均线

# Step B：归一化差值（消除价格量级影响）
signal = (fast_ma - slow_ma) / slow_ma      # 相对偏差

# Step C：自适应缩放（用 rolling std 归一化）
rolling_std = signal.rolling(window=40).std()
signal_normalized = signal / rolling_std

# Step D：tanh 压缩到 (-1, 1)
output = tanh(signal_normalized)
```

**为什么用 tanh 压缩**？

- 保证所有信号类型输出值域一致 → 方便多信号加权组合
- 极端值被压缩，不会因单个异常 bar 产生畸形信号
- tanh 是单调函数，不改变信号的相对大小排序

#### 阶段 2：信号值 → 目标仓位

以 `ThresholdPositionMapper` 为例，状态机逻辑为：

```
         信号 >= 0.3
  空仓 ──────────────→ 多头 (position = 1.0)
   ↑                     │
   │    信号 <= -0.1     │
   └─────────────────────┘
```

这里体现了**双阈值滞回机制**：

- 开仓阈值 = 0.3（必须涨到 0.3 才开仓）
- 平仓阈值 = -0.1（必须跌到 -0.1 才平仓）
- 中间区域 [-0.1, 0.3) 维持现有状态

这样做的目的是：**防止信号在阈值附近来回震荡导致频繁换手**。

#### 阶段 3：shift(1) 防未来函数

这是整个模块最关键的一步。在 `map_to_position()` 内部完成所有状态判定后，最终输出前统一执行：

```python
df["target_position"] = df["target_position"].shift(1).fillna(0.0)
df["signal_value"]    = df["signal_value"].shift(1).fillna(0.0)
```

**含义**：T 日收盘价算出的信号，对应 T+1 日的仓位。第一天永远是空仓。

---

## 四、核心模块详解

### 4.1 `core/base_signal.py` — 信号生成基类

```python
class BaseSignalGenerator(ABC):
    def __init__(self, params: dict, name: str | None = None)
    def generate(self, market_data, factor_data=None) -> pd.Series  # 抽象方法
    def validate_market_data(self, market_data) -> None              # 校验辅助
```

**设计约束**：

| 规则 | 原因 |
|:---|:---|
| 子类禁止写 `for` 循环 | 强制向量化，保证 500+ 标的批量计算的性能 |
| 所有参数走 `params` dict | 零 magic number，便于策略库网格寻优 |
| 输出保留 NaN | 预热期不足时不造假信号，由下游统一处理 |
| 不做仓位映射 | 职责单一原则，信号和仓位逻辑分离 |

### 4.2 `core/base_position.py` — 仓位映射基类

```python
class BasePositionMapper(ABC):
    def __init__(self, params: dict, name: str | None = None)
    def map_to_position(self, signals, market_data) -> pd.DataFrame  # 抽象方法
    
    @staticmethod
    def apply_shift(df, shift_bars=1) -> pd.DataFrame   # 防未来函数
    
    @staticmethod
    def debounce(df) -> pd.DataFrame                     # 防抖（去重复行）
```

**`apply_shift` 原理**：

```
原始计算结果:           shift(1) 后:
  T0: signal=0.8 → pos=1.0     T0: pos=0.0  (空仓，因为 T-1没信号)
  T1: signal=0.9 → pos=1.0     T1: pos=1.0  (T0信号生效)
  T2: signal=-0.5 → pos=0.0    T2: pos=1.0  (T1信号生效)
  T3: signal=-0.8 → pos=0.0    T3: pos=0.0  (T2信号生效)
```

**`debounce` 原理**：

只保留 `target_position` 发生变化的行。比如连续 50 天都是 pos=1.0，则只保留第 1 天。用于落盘时减少文件体积（500 行 → ~20 行）。

### 4.3 `core/schema.py` — 数据契约

```python
class ActionName(str, Enum):
    HOLD, ENTRY_LONG, EXIT_LONG, ENTRY_SHORT, EXIT_SHORT, STOP_LOSS, TAKE_PROFIT

class TargetPositionSchema:
    REQUIRED_COLUMNS = ("timestamp", "symbol", "target_position")
    OPTIONAL_COLUMNS = ("signal_value", "action_name")
    
    def validate(df, strict=True) -> list[str]     # 校验
    def format_output(df, symbol) -> pd.DataFrame   # 格式化输出
```

**validate() 的 4 项检查**：

1. 必要列是否存在 (`timestamp`, `symbol`, `target_position`)
2. `timestamp` 是否为 datetime 类型
3. `target_position` 是否在 [-1.0, 1.0] 范围内 (strict 模式)
4. `target_position` 是否包含 NaN

### 4.4 `data_loader/fetcher.py` — 数据加载器

```python
class DataFetcher:
    def load_market_data(symbol, start_date, end_date, freq, source_path) -> pd.DataFrame
    def load_factor_data(symbol, factor_names, start_date, end_date) -> pd.DataFrame | None
    
    @staticmethod
    def generate_sample_data(symbol, periods, start_date, seed) -> pd.DataFrame
```

**`generate_sample_data` 模拟数据原理**：

```python
# 几何布朗运动模拟价格
daily_returns = N(μ=0.0003, σ=0.02)        # 日收益率 ~ 正态分布
prices = P₀ × exp(cumsum(returns))          # 累积收益 → 价格路径

# OHLCV 构造
open  = close × (1 + U(-0.01, 0.01))       # 开盘价 = 收盘价 + 微小偏移
high  = close × (1 + U(0.005, 0.025))      # 最高价 = 收盘价上浮
low   = close × (1 - U(0.005, 0.025))      # 最低价 = 收盘价下浮
volume = randint(100K, 10M)                 # 成交量随机
```

### 4.5 信号实现对比

| 信号 | 输入 | 核心算法 | 信号特点 |
|:---|:---|:---|:---|
| `DualMASignal` | close | (MA_fast − MA_slow) / MA_slow → 归一化 → tanh | 趋势跟踪，延迟较大 |
| `MACDSignal` | close | MACD_histogram / rolling_std → tanh | 趋势+动量，灵敏度中等 |
| `RSISignal` | close | −(RSI − 50) / 20 → tanh | 均值回复，逆势 |
| `FactorThresholdSignal` | 因子数据 | rolling_zscore → 加权合成 → tanh | 取决于因子质量 |
| `SignalCombiner` | 多个信号 | 加权平均 或 排名平均 → tanh | 多信号融合，更稳健 |

**SignalCombiner 用法示例**：

```python
combiner = SignalCombiner(
    signal_generators=[DualMASignal(...), MACDSignal(...), RSISignal(...)],
    weights=[0.4, 0.4, 0.2],  # 均线和 MACD 为主，RSI 辅助
)
combined_signal = combiner.generate(market_data)
```

### 4.6 仓位映射器对比

| 映射器 | 阈值机制 | 仓位大小 | 适用场景 |
|:---|:---|:---|:---|
| `ThresholdPositionMapper` | 固定数值阈值 | 固定 (1.0 或自定义) | 信号已经过充分归一化 |
| `ATRVolatilityMapper` | 动态阈值 (随 ATR 缩放) | 动态 (波动率目标制) | 信号未归一化 或 需要风险控制 |

**ATRVolatilityMapper 的两个自适应机制**：

```
1. 动态阈值:
   threshold = base_threshold × (ATR / ATR_median) ^ scale_factor
   
   高波动期: ATR↑ → 阈值放大 → 更难触发开仓 → 减少噪声交易
   低波动期: ATR↓ → 阈值缩小 → 更容易开仓 → 把握趋势

2. 仓位缩放:
   position_size = target_volatility / realized_volatility
   
   高波动标的: 仓位小 → 等波动暴露
   低波动标的: 仓位大 → 充分利用资金
   
   最终 clip 到 [min_position, max_position]
```

### 4.7 `pipeline.py` — 总控制台

`StrategyPipeline.run()` 按 5 步顺序执行：

```
Step 1/5: 数据加载   → DataFetcher.load_market_data()
Step 2/5: 信号生成   → SignalGenerator.generate()         [C-1]
Step 3/5: 仓位映射   → PositionMapper.map_to_position()   [C-2]
Step 4/5: 格式化校验 → TargetPositionSchema.format_output() + .validate()
Step 5/5: 落盘交付   → .to_parquet() 或 .to_csv()
```

每次运行产出 3 个文件：

| 文件 | 用途 |
|:---|:---|
| `{symbol}_target_position_full.parquet` | 完整时间序列（每个 bar 一行） |
| `{symbol}_target_position_debounced.parquet` | 仅仓位变化点（给 D 看交易明细） |
| `{symbol}_run_meta.json` | 运行元信息（参数、统计、时间范围） |

**预制策略工厂**（快速创建常用组合）：

```python
create_dual_ma_strategy(symbol="000001.SZ", fast_window=5, slow_window=20)
create_macd_strategy(symbol="000001.SZ", fast_period=12, slow_period=26)
create_combined_strategy(symbol="000001.SZ", use_atr_mapper=True)
```

---

## 五、target_position 数据契约

### 5.1 字段定义

| 字段 | 类型 | 必需 | 说明 | 示例 |
|:---|:---|:---|:---|:---|
| `timestamp` | datetime | ✅ | 指令执行时间 (T+1 开盘) | `2024-04-03 00:00:00` |
| `symbol` | string | ✅ | 标的代码 | `000001.SZ` |
| `target_position` | float | ✅ | 目标资金权重 ∈ [-1, 1] | `0.5` |
| `signal_value` | float | ❌ | 原始信号值，供归因 | `0.85` |
| `action_name` | string | ❌ | 状态机动作名 | `ENTRY_LONG` |

### 5.2 target_position 取值语义

| 值 | 含义 |
|:---|:---|
| `1.0` | 满仓做多 |
| `0.5` | 半仓做多 |
| `0.0` | 空仓（不持有） |
| `-0.5` | 半仓做空 |
| `-1.0` | 满仓做空 |

研究员 D 在 Backtrader 中使用 `order_target_percent(target_position)` 消费此字段。

### 5.3 action_name 枚举

| 枚举值 | 含义 | 触发条件示例 |
|:---|:---|:---|
| `HOLD` | 维持当前仓位 | 信号在开平仓阈值之间 |
| `ENTRY_LONG` | 开多 | 空仓 且 signal ≥ long_entry |
| `EXIT_LONG` | 平多 | 多头 且 signal ≤ long_exit |
| `ENTRY_SHORT` | 开空 | 空仓 且 signal ≤ short_entry |
| `EXIT_SHORT` | 平空 | 空头 且 signal ≥ short_exit |
| `STOP_LOSS` | 止损 | (预留，当前未使用) |
| `TAKE_PROFIT` | 止盈 | (预留，当前未使用) |

---

## 六、关键设计决策与避坑指南

### 6.1 为什么状态机用 for 循环？

本模块的核心原则是"全面向量化"，但 `ThresholdPositionMapper` 和 `ATRVolatilityMapper` 中存在一个 `for` 循环。这是**刻意的例外**，原因如下：

状态机具有**路径依赖性**：T 时刻的仓位不仅取决于 T 时刻的信号，还取决于 T-1 时刻的仓位状态。例如：

```
信号 = 0.2，开多阈值 = 0.3，平多阈值 = -0.1

如果当前空仓: 0.2 < 0.3，不开仓 → 维持空仓
如果当前多头: 0.2 > -0.1，不平仓 → 维持多头

同一个信号值，结果取决于历史状态。
```

这种路径依赖无法用纯向量化表达。但循环使用的是 numpy 数组而非 pandas，性能影响极小（500 个 bar 约 0.1ms）。

### 6.2 未来函数检测方法

单元测试 `TestLookAheadBias` 中有 3 个专门的检测用例：

```python
def test_shift_applied():
    # 第一行 target_position 必须为 0.0（因为前面没有信号）
    assert result["target_position"].iloc[0] == 0.0

def test_signal_precedes_position():
    # 构造在第 50 bar 突变的信号
    signals.iloc[50:] = 0.8
    # 验证仓位变化发生在第 51 bar，而非第 50 bar
    assert result["target_position"].iloc[50] == 0.0
    assert result["target_position"].iloc[51] == 1.0
```

### 6.3 tanh 压缩的注意事项

所有信号输出都经过 `np.tanh()` 压缩。这意味着：

- 信号值**永远不会**精确地等于 -1 或 +1（只能无限逼近）
- 阈值设定应适配此特性：比如设 0.3 而非 1.0 作为开仓阈值
- 不同信号合成时，因为值域统一，可以直接做加权平均

### 6.4 频率无关设计

模块不限制数据频率（日频、分钟频、tick 级均可），信号和状态机都是按 bar 计算。唯一需要注意的是 `ATRVolatilityMapper` 中的年化系数参数：

```python
ATRVolatilityMapper(params={
    "annualize_factor": 252,        # 日频 (默认)
    # "annualize_factor": 252*390,  # A股分钟频
    # "annualize_factor": 252*24,   # 24h crypto
})
```

---

## 七、扩展指南

### 7.1 添加新信号

1. 在 `strategies/signals/` 下新建文件
2. 继承 `BaseSignalGenerator`
3. 实现 `generate()` 方法
4. 确保输出为 `pd.Series`，值域经 `tanh()` 压缩

```python
from strategy_layer.single_asset_alpha.core.base_signal import BaseSignalGenerator

class MyNewSignal(BaseSignalGenerator):
    def generate(self, market_data, factor_data=None):
        self.validate_market_data(market_data)
        
        window = self.params.get("window", 10)
        close = market_data["close"]
        
        # 你的信号逻辑（必须向量化）
        raw = close.pct_change(window)
        
        signal = np.tanh(raw / raw.rolling(50).std())
        signal.name = self.name
        return signal
```

### 7.2 添加新状态机

1. 在 `strategies/position_mappers/` 下新建文件
2. 继承 `BasePositionMapper`
3. 实现 `map_to_position()` 方法
4. **务必在返回前调用 `self.apply_shift()`**

```python
from strategy_layer.single_asset_alpha.core.base_position import BasePositionMapper

class MyMapper(BasePositionMapper):
    def map_to_position(self, signals, market_data):
        # ... 你的状态机逻辑 ...
        
        df = pd.DataFrame({...}, index=signals.index)
        
        # ★ 一定要加这一行
        df = self.apply_shift(df, shift_bars=self.params.get("shift_bars", 1))
        return df
```

### 7.3 组合已有组件搭建新策略

```python
from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline
from strategy_layer.single_asset_alpha.strategies.signals.macd_signal import MACDSignal
from strategy_layer.single_asset_alpha.strategies.position_mappers.atr_volatility_mapper import ATRVolatilityMapper

pipeline = StrategyPipeline(
    symbol="BTC-USDT",
    signal_generator=MACDSignal(params={"fast_period": 8, "slow_period": 21}),
    position_mapper=ATRVolatilityMapper(params={
        "base_long_threshold": 0.3,
        "target_volatility": 0.20,
        "annualize_factor": 365 * 24,  # 小时级 crypto
        "allow_short": True,
    }),
    output_dir="outputs/crypto",
)

result = pipeline.run(market_data=my_btc_data, output_format="csv")
```

---

## 八、测试覆盖

20 个单元测试分为 5 组：

| 测试类 | 用例数 | 覆盖范围 |
|:---|:---|:---|
| `TestSignalGenerators` | 7 | 输出类型、值域、组合器、输入校验 |
| `TestPositionMappers` | 4 | 输出列、值域、做空约束、ATR 映射器 |
| `TestLookAheadBias` | 3 | shift 验证、信号先于仓位、统计检验 |
| `TestSchema` | 3 | 合法数据、缺列检测、越界检测 |
| `TestPipelineIntegration` | 2 | 双均线策略端到端、组合策略端到端 |
| *防抖 (debounce)* | 1 | 防抖后行数 ≤ 原始行数 |

运行命令：

```bash
cd quantsociety_backend_project
python -m pytest strategy_layer/single_asset_alpha/tests/ -v
```

---

## 九、运行方式汇总

| 场景 | 命令 |
|:---|:---|
| 最简示例 | `python strategy_layer/single_asset_alpha/examples/simple_demo.py` |
| Mock 交付 | `python strategy_layer/single_asset_alpha/mock_delivery.py` |
| 双均线策略 | `python -m strategy_layer.single_asset_alpha.pipeline --strategy dual_ma` |
| MACD 策略 | `python -m strategy_layer.single_asset_alpha.pipeline --strategy macd` |
| 组合策略 | `python -m strategy_layer.single_asset_alpha.pipeline --strategy combined` |
| 允许做空 | 加 `--allow-short` |
| CSV 输出 | 加 `--format csv` |
| 运行测试 | `python -m pytest strategy_layer/single_asset_alpha/tests/ -v` |
