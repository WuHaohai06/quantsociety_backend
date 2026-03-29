# 算子路线图：Deep Research ↔ 实现状态

> **第 7 版更改-shw**：新增本文档，将研究报告中的算子主题与仓库内算子名、实现状态做对照，便于挖掘引擎与回测管线规划。

## 图例

| 状态 | 含义 |
|------|------|
| 已实现 | `PandasBackend` 可执行 |
| 部分/可选 | 依赖可选包（如 TA-Lib）或有退化路径 |
| 仅编译 | Expr/IR/DSL 可用，执行 `NotImplementedError` |
| 需数据层 | 依赖 PiT/LOB/NLP 等专用数据，当前仅文档规划 |

## BrainCategory 扩展说明

注册表枚举除 WQ 七类外，增加与研究报告对齐的维度：**技术指标**、**数据清洗**、**工程上下文**；远期：**微观结构**、**基本面**、**另类数据**（见 `api/operator_registry.BrainCategory`）。

## 研究主题 ↔ 算子 ↔ 状态

| 研究主题 | 算子 / 能力 | 状态 |
|----------|-------------|------|
| 基础数学 / 逻辑 | `abs` `log` `sqrt` `sign` `nary_*` `densify` `if_else` 比较 `and_`/`or_`/`not_` | 已实现 |
| 横截面相对化 | `rank` `zscore` `normalize` `quantile` `scale` `winsorize` | 已实现 |
| 时序滚动 | `ts_mean` `ts_std_dev` `ts_max` `ts_min` `delay` `ts_delta` `ts_corr` … | 已实现 |
| 威廉 %R / 随机指标 / CCI / ROC / MACD | `ts_willr` `ts_stoch` `ts_cci` `ts_roc` `ts_macd` 等（HLC 列契约） | 已实现（TA-Lib 优先 + pandas 退化） |
| 趋势强度 / Aroon / Chaikin / SAR | `ts_adx` `ts_aroon` `ts_ad` `ts_adosc` `ts_sar` | 已实现（TA-Lib 优先；SAR 无库为简化 PSAR） |
| 动量扩展 | `ts_cmo` `ts_ppo` `ts_apo` `ts_ultosc` `ts_stochrsi` | 已实现 |
| 第三批（BOP/MOM/STOCHF/TRIX/DMI 派生/ROCR/线性回归） | `ts_bop` `ts_mom` `ts_stochf` `ts_trix` `ts_adxr` `ts_dx` `ts_rocr` `ts_rocr100` `ts_linearreg_slope` `ts_linearreg_angle` | 已实现（TA-Lib 优先 + 退化） |
| Overlap 加深 | `ts_tema` `ts_trima` `ts_t3` | 已实现 |
| 通道 / 波动 | `ts_donchian` `ts_keltner` `ts_ma_envelope` `ts_atr` `ts_natr` `ts_trange` | 已实现 |
| 成交量类 | `ts_obv` `ts_mfi` | 已实现（需 `volume` 列） |
| 滚动高阶矩 | `ts_skew` `ts_kurt` | 已实现 |
| 截面 OLS 中性化 | `neutralize(x,y)` | 已实现 |
| 数据清洗 / 数值安全 | `pasteurize` `tail` `protected_div` `protected_log` `protected_sqrt` | 已实现 |
| 技术指标（TA-Lib 类） | `ts_sma` `ts_ema` `ts_bbands` `ts_rsi` 及上表扩展（DEMA/WMA/KAMA 等） | 部分/可选（TA-Lib） |
| 分组（行业中性 / 组内排名） | `group_rank` `group_neutralize` `group_zscore` `group_scale` `group_mean` `group_backfill` | 已实现 |
| 与 WQ `indneutralize` | 与 **`group_neutralize(x, sector)`** 语义一致：组内去均值 | 说明 |
| 工程上下文 | `orthogonalize`（截面 Gram-Schmidt）`change_instrument`（基准列约定） | 已实现 |
| 表达式子树缓存 | `ExecutionContext.cache` + `PandasBackend` 结构键缓存 | MVP 已实现 |
| 三角函数 sin/cos | `sin` `cos`（DSL 同名） | 已实现（Pandas / Polars 子集） |
| 向量 rolling | `vec_avg` `vec_sum` | 仅编译 + stub（路径 B：需 Parquet 向量列 / ndarray 契约后再实装） |
| LOB / VPIN / 高频微观 | `lob_ofi_stub`、`micro_vpin_stub`、`micro_spread_stub` 等（见 `MICROSTRUCTURE_STUB_OPS`） | 仅接口 stub（执行 `NotImplementedError`） |
| PiT / 财报 / 分析师 / 内部人 | `fundamental_*_stub`、`days_since_*`、`analyst_*`、`insider_*` 等（见 `FUNDAMENTAL_STUB_OPS`） | 仅接口 stub |
| 另类 / NLP / ESG / 供应链 | `alt_*_stub`（见 `ALTERNATIVE_STUB_OPS`） | 仅接口 stub |
| Welford / RLS 显式算子 | — | 规划中（可与 `ts_*` 内部优化合并） |
| PolarsBackend | `column` `literal` `add`/`sub`/`mul`/`div` `rank` `ts_mean` `sin` `cos` | 部分/可选（子集；安装 `factor-engine[polars]`） |
| 量纲 / AST-TED / 复杂度惩罚 | planner / 挖掘引擎层 | 系统层（非单点 op） |

## 可选加速依赖（阶段 A）

| 包 | 用途 |
|----|------|
| `TA-Lib` | 上述技术指标中 MACD/CCI/STOCH/MFI/OBV/DEMA/WMA/KAMA 等优先走 C 实现；无库时多数有 pandas 退化 |
| `Bottleneck` | `ts_mean` / `ts_max` / `ts_min` 已接线可选 `move_*`（见 `pandas_backend`；可 `FACTOR_ENGINE_DISABLE_BOTTLENECK=1` 关闭） |
| `numba` | 后续阶段（报告第五部分） |
| `polars` | PolarsBackend 子集（见上表） |
| `joblib` | 多因子层并行示例（`examples/run_factors_joblib.py`），非 rolling 内并行 |

## 相关文档

- [`operators_semantics.md`](operators_semantics.md) — Bar/截面语义、DSL 限制  
- [`adr_context_benchmark.md`](adr_context_benchmark.md) — `change_instrument` 基准列约定  
- [`changelog_shw.md`](changelog_shw.md) — 版本记录  
