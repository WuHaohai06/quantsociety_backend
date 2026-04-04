# Barra Model

`barra_model` 目录用于完成一条从原始数据到组合权重的简化 Barra 生产链路：

1. 对齐因子、收益率和市值数据
2. 用 WLS 估计因子收益与残差
3. 用全历史因子收益生成最新的因子协方差矩阵
4. 用全历史残差生成最新截面的特异性方差
5. 基于最新截面生成 alpha
6. 用结构化风险模型做组合优化
7. 计算最新截面的 benchmark 总风险

## 当前数据来源

当前这套流程默认使用两类上游输入：

- 因子数据：由 [factor_generate.py](/C:/Users/yixuanwang2/Desktop/to_wyx/to_wyx/quantsociety_backend_project/strategy_layer/portfolio_strategy/risk/barra_model/factor_generate.py) 生成的因子暴露数据，再作为 `barra_data.py` 的因子输入
- 市值数据：同样由 [factor_generate.py](/C:/Users/yixuanwang2/Desktop/to_wyx/to_wyx/quantsociety_backend_project/strategy_layer/portfolio_strategy/risk/barra_model/factor_generate.py) 产出，再作为 `barra_data.py` 的市值输入

也就是说，当前风险模型和优化流程依赖的是：
- `factor_generate` 产出的因子截面
- `factor_generate` 产出的 market cap 数据

## 当前工作流

### 1. 数据层：`barra_data.py`

输入：
- 原始因子 parquet
- 原始行情 parquet
- 市值 parquet

主要逻辑：
- 因子表统一为 `date + asset + factor columns`
- 行情表按 `ticker` 排序后计算 `next_ret = Price[t+1] / Price[t] - 1`
- 市值表统一为 `date + asset + market_cap`
- 以因子表为主表，分别左连接收益率和市值
- 严格校验三张输出表按 `date + asset` 一一对应

输出：
- `cleaned_factors.parquet`
- `cleaned_returns.parquet`
- `cleaned_market_cap.parquet`

### 2. 风险层：`barra_risk.py`

输入：
- `cleaned_factors.parquet`
- `cleaned_returns.parquet`
- `cleaned_market_cap.parquet`

主要逻辑：
- 同步剔除缺失 `next_ret` 或无效 `market_cap` 的样本
- 对每个交易日的因子暴露做 `3-sigma` 去极值和 `Z-Score`
- 用 `WLS` 做逐日截面回归
  - 回归权重是 `sqrt(market_cap)`
- 得到全历史：
  - `factor_returns`
  - `specific_returns`
- 因子协方差矩阵 `F`
  - 使用全历史 `factor_returns`
  - 采用 `EWMA`
  - 年化乘 `252`
- 特异性方差 `Δ`
  - 使用全历史 `specific_returns`
  - 对每只股票做 expanding std，到最新日为止
  - 仅输出最新交易日截面
  - 对缺失资产用最新截面中位数填充
  - 最终存的是年化特异性方差：`std^2 * 252`

输出：
- `factor_returns.parquet`
- `factor_covariance.parquet`
- `specific_returns.parquet`
- `specific_risk.parquet`

### 3. 风险调度层：`barra_model_run.py`

职责：
- 串起 `barra_data.py` 和 `barra_risk.py`
- 一次性产出最新截面优化所需的全部风险文件

当前模式：
- 不再做历史总风险聚合
- 只负责生成“最新可交易截面”的风险参数

### 4. Benchmark 风险：`benchmark_total_risk.py`

职责：
- 计算最新交易日全市场市值加权 benchmark 的总风险

输入：
- `cleaned_factors.parquet`
- `factor_covariance.parquet`
- `specific_risk.parquet`
- `market_cap_weights.parquet`

主要逻辑：
- 读取最新交易日截面的因子暴露矩阵 `X`
- 读取同日的市场市值
- 在截面内重新归一化成 `w_mkt`
- 用分步法计算：

```text
sigma^2 = (w^T X) F (X^T w) + sum(w_i^2 * delta_i)
sigma = sqrt(sigma^2)
```

输出：
- 控制台打印 benchmark 年化总风险
- `benchmark_total_risk.txt`


### 5. Alpha 层：`alpha_generate.py`

输入：
- `cleaned_factors.parquet`

主要逻辑：
- 只取最新交易日
- 读取 `Value / Momentum / Size`
- 做 `3-sigma` 去极值和 `Z-Score`
- 按下式生成 raw alpha：

```text
Raw_Alpha = 0.4 * Value + 0.4 * Momentum - 0.2 * Size
```

- 将 alpha 截面标准差缩放到日度 `0.10 / sqrt(252)`
- 加入小扰动 `N(0, 0.001)`

输出：
- `alpha_vector.parquet`

字段：
- `asset`
- `expected_ret`

### 6. 优化层：`optimization.py`

输入均来自 `work_dir`：
- `alpha_vector.parquet`
- `factor_covariance.parquet`
- `specific_risk.parquet`
- `cleaned_factors.parquet`

主要逻辑：
- 自动识别 `cleaned_factors.parquet` 的最新交易日
- 取该日的最新因子暴露矩阵 `X`
- 将 alpha、`F`、`Δ`、`X` 对齐到同一资产池
- 若某资产缺失特异性方差，则用截面中位数填充
- 用 `cvxpy` 解均值-方差优化

目标函数：

```text
maximize w^T alpha - lambda / 2 * sigma^2
```

其中：

```text
sigma^2 = (X^T w)^T F (X^T w) + sum(w_i^2 * delta_i)
```

约束：
- `sum(w) == 1`
- `w >= 0`
- `w <= 0.08`

输出：
- `optimal_weights.parquet`

字段：
- `asset`
- `weight`


## 推荐运行顺序

### 第一步：生成风险参数

```bash
python barra_model_run.py
```

产出：
- `cleaned_factors.parquet`
- `cleaned_returns.parquet`
- `cleaned_market_cap.parquet`
- `factor_returns.parquet`
- `factor_covariance.parquet`
- `specific_returns.parquet`
- `specific_risk.parquet`

### 第二步：计算 benchmark 风险

```bash
python benchmark_total_risk.py
```

产出：
- 控制台 benchmark 风险
- `benchmark_total_risk.txt`

### 第三步：生成 alpha

```bash
python alpha_generate.py
```

产出：
- `alpha_vector.parquet`

### 第四步：组合优化

```bash
python optimization.py
```

产出：
- `optimal_weights.parquet`

## 关键文件说明

- `alpha_generate.py`
  最新截面 alpha 生成脚本
- `alpha_generator.py`
  旧版 alpha 脚本，当前流程不依赖
- `barra_data.py`
  数据对齐层
- `barra_risk.py`
  风险估计层
- `barra_model_run.py`
  风险模型总调度入口
- `benchmark_total_risk.py`
  benchmark 年化总风险计算
- `optimization.py`
  均值-方差优化器
- `factor_generate.py`
  目录中旧文件，当前主流程不依赖

## 当前产物口径

- `factor_covariance.parquet`
  年化因子协方差矩阵，基于全历史 `factor_returns` 的 EWMA 估计

- `specific_risk.parquet`
  最新交易日截面的年化特异性方差，不是波动率，也不是全历史面板

- `alpha_vector.parquet`
  最新交易日截面的预期收益向量

- `optimal_weights.parquet`
  在当前 alpha 和当前结构化风险矩阵下得到的最优权重

## 运行依赖

建议环境至少安装：
- `pandas`
- `numpy`
- `pyarrow`
- `statsmodels`
- `cvxpy`

## 注意事项

- `alpha_generate.py` 依赖 `cleaned_factors.parquet` 中存在 `Value / Momentum / Size`
- `optimization.py` 与 `benchmark_total_risk.py` 都依赖 `specific_risk.parquet` 已经生成
- 当前优化器和 benchmark 脚本默认读取 `C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx`
- 若切换实验目录，请优先修改对应脚本中的默认路径或显式传入 `work_dir`
