# 算子语义与约定

> **第 5 版更改-shw**：与 WQ 算子库落地同步；语义与 DSL 限制见本文；完整变更列表见 [`changelog_shw.md`](changelog_shw.md)。
>
> **第 7 版更改-shw**：补充 **清洗 / 技术指标 / 上下文 / group_*** 的可执行语义与路线图链接；占位列表不再包含 `group_*`。
>
> **第 10 版更改-shw**：`bucket` / `trade_when` / `ts_step` / `hump` 已实装；**Bottleneck** 已用于 `ts_mean`/`ts_max`/`ts_min`；占位仅剩 **`vec_*`**。
>
> **第 17 版更改-shw**：远期数据层 stub 扩充为 **基本面 / 另类 / 微观结构** 多命名（仍统一 `NotImplementedError`）；权威列表见 **`STUB_IR_OPS`** 与 `expr.*_STUB_OPS` 常集。
>
> **第 19 版更改-shw**：技术指标 **第三批**（`ts_bop`/`ts_mom`/`ts_stochf`/`ts_trix`/`ts_adxr`/`ts_dx`/`ts_rocr`/`ts_rocr100`/`ts_linearreg_slope`/`ts_linearreg_angle`）；详见 `changelog_shw.md`「第 19 版」。

## Bar / 日历

- 引擎中间结果为 `(timestamp, instrument)` 的 MultiIndex Series。
- WorldQuant 文档中的 “days” 在本实现中对应 **数据行（bar）**，不是交易所日历日；`ts_*` 窗口长度 `d` 为 **每个标的上的连续 bar 数**。

## DSL（`parse_expr`）

- 基于 Python `ast.parse(..., mode="eval")`，因此 **`and` / `or` / `not` 不能作为函数名**；请使用 **`and_` / `or_` / `not_`**。
- 比较运算写 **`col("x") < col("y")`** 等形式；**不支持链式比较**（如 `a < b < c`）。
- 多元算术请用 **`add(...)` / `multiply(...)`** 等函数，而非 `and` 类关键字。

## 依赖

- `ts_quantile` 与截面 `quantile` 使用 **scipy** 的逆正态 CDF；安装可选依赖：`pip install "factor-engine[pandas]"`（已包含 `scipy`）。
- **TA-Lib**（可选）：扩展技术指标（含 MACD/ATR/STOCH/MFI/OBV、**ADX/Aroon/AD/ADOSC/SAR**、**CMO/PPO/APO/UltOsc/StochRSI**、**TEMA/TRIMA/T3**、**BOP/MOM/STOCHF/TRIX/ADXR/DX/ROCR/ROCR100/线性回归** 等）在已安装时优先走 C 实现；否则为 pandas/numpy 退化（`ts_kama` 无库时用 EMA 近似；**`ts_sar` 无库时用简化 PSAR，与 TA-Lib 数值可能略有差异**；**`ts_bop` 无真实 open 时用上一根 close 近似 open（首 bar 用自身 close），与标准 BOP 列契约不同**；**`ts_trix` 无库时为三重 EMA 的 1 期 ROC×100，与 TA-Lib 在边界上可能略有差异**）。`pip install "factor-engine[talib]"`（部分环境需系统 TA-Lib 库）。
- **Bottleneck**（可选）：`pip install "factor-engine[accel]"` 后，`ts_mean` / `ts_max` / `ts_min` 可走 `move_*`；`FACTOR_ENGINE_DISABLE_BOTTLENECK=1` 强制走 pandas。**Numba** 仍在路线图阶段 B。

## 数据清洗与工程算子（已实现）

- **清洗**：`pasteurize`（Inf→NaN，可选填常数）、`tail`（按日分位裁剪）、`protected_div` / `protected_log` / `protected_sqrt`。
- **技术指标（单序列）**：`ts_sma` / `ts_ema` / `ts_rsi` / `ts_bbands`；`ts_macd` / `ts_ppo` / `ts_apo`（`line="macd"|"signal"|"hist"` 或 `ppo`/`apo`/`signal`/`hist`）；`ts_roc(x,d)`；**`ts_mom(x,d)`**（价差动量，非百分比）；**`ts_rocr(x,d)`**、**`ts_rocr100(x,d)`**（变动率比 / 百分比形式，与 `ts_roc` 口径不同）；**`ts_trix(x,d)`**；**`ts_linearreg_slope(x,d)`**、**`ts_linearreg_angle(x,d)`**（滚动线性回归斜率 / 倾角，度）；`ts_dema` / `ts_wma` / `ts_kama` / **`ts_tema` / `ts_trima` / `ts_t3(x,d,vfactor=0.7)`**；`ts_ma_envelope(x, d, pct, band, use_ema)`；**`ts_cmo(x,d)`**；**`ts_stochrsi(x, timeperiod=14, fastk_period=5, fastd_period=3, line="fastk"|"fastd")`**；`ts_skew` / `ts_kurt`（滚动矩）。
- **技术指标（HLC / OHLCV）**：数据源须含对应列：`ts_trange` / `ts_atr` / `ts_natr(high,low,close,d)`；`ts_donchian(high,low,d,band)`；`ts_keltner(high,low,close,d,mult,band,atr_d)`；`ts_cci` / `ts_stoch` / **`ts_stochf(high,low,close, fastk_period=5, fastd_period=3, line="fastk"|"fastd")`** / `ts_willr`；**`ts_bop(high,low,close)`**（open 近似见上）；**`ts_adx(high,low,close,d,line="adx"|"plus_di"|"minus_di")`**；**`ts_dx(high,low,close,d)`**（方向运动指数，非 ADX）；**`ts_adxr(high,low,close,d)`**；**`ts_aroon(high,low,d,line="up"|"down"|"osc")`**；**`ts_ultosc(high,low,close,timeperiod1=7,timeperiod2=14,timeperiod3=28)`**；`ts_obv(close,volume)`；**`ts_ad` / `ts_adosc(high,low,close,volume, fast=3, slow=10)`**（Chaikin）；**`ts_sar(high,low, acceleration=0.02, maximum=0.2)`**；`ts_mfi(high,low,close,volume,d)`。
- **截面**：`neutralize(x, y)` — 每个 timestamp 上 **OLS 残差** `x - (α + βy)`；与 `orthogonalize`（过原点投影）不同。
- **上下文**：`orthogonalize(x, y)`（截面 Gram-Schmidt）、`change_instrument(x, "bench_col")`（除以按日聚合的基准列，约定见 [`adr_context_benchmark.md`](adr_context_benchmark.md)）。
- **分组**：`group_rank`、`group_neutralize`、`group_zscore`、`group_scale`、`group_mean`、`group_backfill`；与研究报告中的 **indneutralize** 对应关系：**`group_neutralize(x, sector)` ≈ 按行业去均值**。

## Transformational / 状态时序（已实现）

### `bucket(x, range=..., buckets=..., skipBoth=..., NaNGroup=...)`

- 每个 **timestamp** 截面上，对 `x` 做 **rank(pct)**，再映射为 **浮点桶 id**（从 0 起）。
- **`buckets="N"`**（正整数）：将分位 `r∈[0,1)` 映射为 `floor(r*N)` 钳制到 `[0,N-1]`（近似等频）；**优先于** `range`。
- **`range="0.2,0.4,..."`**：逗号分隔 **开区间 (0,1)** 的升序分位切分点；桶 id = `searchsorted(cuts, r, side="right")`，共 `len(cuts)+1` 档。
- **`skipBoth=True`**：最低与最高桶内的 **有效** 观测输出 **NaN**（中间桶保留）。
- **`NaNGroup=True`**：输入 NaN 输出 **-1.0** 作为「NaN 组」标记；`False` 则输出 NaN。

### `trade_when(trigger, alpha, exit_)`

- 见 [`adr_trade_when.md`](adr_trade_when.md)。

### `ts_step(d, anchor)` / `hump(x, hump=0.01)`

- 见 [`adr_ts_step_hump.md`](adr_ts_step_hump.md)。

## 子树缓存（MVP）

- 若 `FactorEngine(..., cache=CacheManager())` 或配置 `engine.enable_cache: true`，`PandasBackend` 对 **结构相同** 的子计划节点结果做内存复用（键为 `op + attrs + 子树形状`，与列指纹无关的 MVP）。

## 路线图

- 研究主题 ↔ 算子覆盖 ↔ 远期数据层算子：见 [`operators_roadmap.md`](operators_roadmap.md)。

## 占位算子

以下算子在 IR/DSL 中可用，但 **PandasBackend** 会抛出 `NotImplementedError`，详见 `api/operator_registry.STUB_IR_OPS`：

- **Vector**：`vec_avg`, `vec_sum`（需 **向量列数据契约**，见路线图「路径 B」说明；当前不对普通标量列做假实现）。
- **远期数据层（占位）**：不假装已有 LOB / PiT / NLP / tick 专用列；均为 **单参数** `xxx_stub(child)`，语义名供 DSL/GP 使用。权威集合 = `STUB_IR_OPS` \ {`vec_*`}，与下列常集并集一致：
  - **基本面 / 事件 / 分析师等**：`expr.fundamental.FUNDAMENTAL_STUB_OPS`（如 `fundamental_yoy_stub`、`days_since_filing_stub`、`analyst_dispersion_stub` …）。
  - **另类 / ESG / 供应链等**：`expr.alternative.ALTERNATIVE_STUB_OPS`（如 `alt_sentiment_ema_stub`、`alt_esg_score_stub` …）。
  - **微观结构 / 事件掩码**：`expr.microstructure.MICROSTRUCTURE_STUB_OPS`（如 `lob_ofi_stub`、`micro_vpin_stub`、`event_window_mask_stub` …）。
  - **分钟 / 日内序列（华泰《GPT 因子工厂 2.0》图表 11 类语义）**：`expr.intraday.INTRADAY_STUB_OPS`（如 `intraday_explode_return_stub`、`intraday_tp_sample_stub` …）；需分钟 OHLCV 或逐笔 schema，与 LOB 类微观 stub 分工见 `expr/intraday.py` 模块注释。

### 远期 stub 数据契约（概要）

| 约定 | 说明 |
|------|------|
| 输入形态 | 默认 **一个 child**：多为已与 `(timestamp, instrument)` 对齐的 **浮点列**；多字段比率、惊喜、应计等应在 **数据层预计算为单列** 再传入。 |
| 频率 | 财报类多为 **季频/事件对齐到日 bar**；tick 类需 **与报价/成交采样一致** 的列，由数据源文档约定。 |
| PiT | 凡涉财报、指引、一致预期，须满足 **可得日 / 披露日** asof，引擎 stub **不** 代做 join。 |
| 与 `ts_*` | 衰减、差分等通用时序请用已有 `ts_delta` / `ts_decay_linear` 等组合；stub 仅提供 **语义标签**。 |
