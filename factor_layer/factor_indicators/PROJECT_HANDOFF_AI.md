# Factor Indicators 项目交接文档（AI-Friendly）

## 1. 项目目标
本项目用于评估分钟级期货因子（当前为 NQ 的 VWAP Reversion 因子），提供：
- 因子有效性统计：IC、RankIC、ICIR、RankICIR、IC 胜率
- 分层回测：10 组分层收益（可按 N 期转成单期收益）
- 多空持有回测：严格仓位状态机（-1/0/+1）
- 交易成本回测：支持单边手续费（当前默认 0.00002）
- 可视化仪表盘：Streamlit + Plotly

文档面向下一个开发者，强调可维护性、数据契约、关键公式和扩展点。

## 2. 当前目录结构
- .venv/: Python 虚拟环境
- NQ/: 原始分钟级分区数据（按月）
- NQ.parquet: 汇总行情（历史存在）
- NQ_vwap.parquet: 回测用 VWAP 序列（timestamp, vwap）
- factor_output.parquet: 因子输出（timestamp, factor）
- factor_vwap_reversion.py: 因子生成脚本
- factor_evaluation_framework.py: 核心评估框架
- factor_eval_dashboard.py: Streamlit 可视化看板
- evaluation_output/: 评估结果导出目录（包含历史版本输出）

说明：evaluation_output 内可见旧 horizon 文件（如 h15/h30），当前框架默认 horizon 为 1/5/10/20。

## 3. 运行入口
### 3.1 因子生成
执行 factor_vwap_reversion.py：
- 读取 NQ 原始分钟数据
- 计算日内累计 VWAP 偏离因子
- 输出 factor_output.parquet

### 3.2 批量评估与导出
执行 factor_evaluation_framework.py：
- 加载 factor_output.parquet 和 NQ_vwap.parquet
- 对每个 horizon 计算完整指标
- 输出 evaluation_output 下的 CSV

### 3.3 可视化面板
执行 factor_eval_dashboard.py（streamlit run）：
- 展示无手续费与有手续费（单边）两套持有回测结果
- 支持 N=1/5/10/20 的对比

## 4. 数据契约
### 4.1 输入数据
- 因子文件：factor_output.parquet
  - 必需列：timestamp, factor
- VWAP 文件：NQ_vwap.parquet
  - 必需列：timestamp, vwap

### 4.2 时间对齐规则
在 factor_evaluation_framework.py 中：
- 先按时间戳去重（保留最后一条）
- 取 factor 与 vwap 的重叠时间区间
- 用并集索引重建时间轴后再对齐

## 5. 核心模块说明
## 5.1 因子生成模块（factor_vwap_reversion.py）
- 因子定义：-(close - cum_vwap) / cum_vwap
- 逻辑含义：价格高于 VWAP 越多，因子越偏负（预期回归）
- 暖启动处理：每天前 5 条置 NaN
- 自带日度 Spearman IC 报告（独立于评估框架）

## 5.2 评估框架模块（factor_evaluation_framework.py）
主要配置由 EvalConfig 控制：
- horizons: 默认 (1, 5, 10, 20)
- zscore_window: 默认 200
- winsor_quantile: 默认 1%
- n_quantiles: 默认 10
- min_obs_per_day: 默认 30
- holding_fee_rate: 默认 0.00002（单边手续费）

关键流程：
1. rolling_zscore 预处理因子
2. 构建前瞻收益 target_ret_n
3. 剔除每个交易日尾部不足 horizon 的样本
4. 日内 winsorize 去极值
5. 计算 daily IC / daily RankIC
6. 分层回测（N 期收益折算单期）
7. 持有回测（无手续费）
8. 持有回测（有手续费）
9. 汇总 summary 与各类序列结果

## 5.3 可视化模块（factor_eval_dashboard.py）
页面包含：
1. Metrics Decay by N
2. Layered Backtest 单期收益柱图
3. Long-Short 衰减曲线
4. Holding PnL Curves（无手续费）+ 各 N 指标
5. Holding PnL Curves After Fee（有手续费）+ 各 N 指标
6. Data Tables（含手续费前后明细）

缓存机制：
- 使用 st.cache_data
- 通过 _CACHE_VERSION 手动失效缓存（当前 v9）

## 6. 关键计算口径
### 6.1 前瞻收益口径（因子 t 时刻）
target_ret_n 使用 VWAP：
- 计算区间为 [t+1, t+1+N]
- 形式为 vwap.shift(-(N+1)) / vwap.shift(-1) - 1

### 6.2 分层回测口径
- 因子按横截面分 10 组
- 先计算 N 期均值收益
- 再折算为单期收益，便于不同 N 横向比较

### 6.3 多空持有状态机
- 触发：Group10 开多，Group1 开空
- 入场延迟：信号 t 触发，t+1 开始持有
- 仓位仅允许 -1/0/+1
- 每次持有严格 horizon 条 bar
- 持有窗口内忽略新信号
- 同时触发时多头优先

### 6.4 交易成本口径
apply_holding_transaction_cost 中：
- 按仓位绝对变化收单边手续费
- 单边费率：holding_fee_rate（默认 0.00002）
- 每 bar 成本 = abs(delta_position) * fee_rate
- 开仓或平仓计 1 次
- 反手（例如 +1 到 -1）计 2 次

### 6.5 累计净值口径
- cum_pnl 为权益曲线（初始值基于 1）
- 累计总收益 = 最终权益 - 1

### 6.6 持有回测统计指标
holding_backtest_stats 返回：
- holding_sharpe
- holding_max_drawdown
- holding_annual_return
- holding_turnover
- holding_avg_daily_trades
- holding_win_rate
- holding_profit_loss_ratio

其中：
- holding_turnover = sum(abs(delta_position)) / sum(abs(position))
- holding_avg_daily_trades = 按日汇总的交易笔数均值
  - 开/平各记 1
  - 反手记 2

## 7. 返回结果结构（开发接口约定）
run_evaluation(cfg) 返回 Dict[horizon, payload]，payload 包含：
- summary: 汇总字典
- daily_ic: 日度 IC 序列
- daily_rank_ic: 日度 RankIC 序列
- layered_single_period: 分层单期收益
- holding_pnl: 无手续费持有序列
- holding_stats: 无手续费统计
- holding_pnl_with_cost: 有手续费持有序列
- holding_stats_with_cost: 有手续费统计

summary 额外包含：
- holding_total_return
- holding_total_return_with_cost
- 以及手续费统计的 with_cost 后缀字段

## 8. 已知问题与注意事项
- 端口冲突：8501 可能被占用，启动 Streamlit 失败时切换端口
- 大数据量图表：原始分钟级曲线体量大，dashboard 已对净值按日下采样
- 缓存一致性：指标字段变更后务必提升 _CACHE_VERSION
- evaluation_output 历史文件混有旧 horizon，分析时注意版本口径
- 交易成本非常敏感：高频换手会显著侵蚀收益

## 9. 推荐的后续开发任务
- 增加多费率敏感性面板（0, 2e-5, 5e-5, 1e-4）
- 将 save_results 扩展为同时导出有手续费版本持有曲线
- 增加单元测试：
  - 状态机仓位边界测试
  - 交易成本计数规则测试（开平/反手）
  - 统计口径回归测试
- 增加配置文件化（yaml 或 toml），替代硬编码参数
- 增加异常监控与日志（输入列缺失、时间戳异常、NaN 比例）

## 10. 快速交接清单
- 确认 Python 环境与依赖可用（pandas, numpy, streamlit, plotly, pyarrow）
- 先运行 framework 脚本，确认 CSV 输出
- 再运行 dashboard，确认 5 个可视区块均正常
- 验证无手续费与有手续费两套统计均包含 holding_avg_daily_trades
- 修改任何统计字段后同步更新：
  - dashboard 的列定义
  - metric_name_map
  - _CACHE_VERSION

---
文档生成时间：2026-03-27
