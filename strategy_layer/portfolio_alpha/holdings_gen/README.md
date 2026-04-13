# holdings_gen

把 strategy 层产出的组合信号表转换成 portfolio_backtest 可直接消费的 holdings 长表。

当前第一版专注于最短路径：

- 读取 multiple_factor_composite 的 composite_signal.parquet
- 按 selected_flag / side 生成每日目标权重
- 输出 trade_date / symbol / weight 三列的 holdings 文件
- 在代码结构上预留组合优化器和风控器接入点

## 当前输入契约

默认按 canonical signal 读取：

- timestamp
- symbol
- composite_score
- selected_flag
- side

其中只有 timestamp / symbol 是绝对必需的；如果没有 selected_flag，可以把 selection_mode 设成 all；如果没有 side，会回退到 default_side=LONG。

## 当前输出契约

默认输出 holdings/holdings.parquet，列为：

- trade_date
- symbol
- weight

这可以直接喂给 [backtest_layer/portfolio_backtest](../../../backtest_layer/portfolio_backtest/README.md) 的 holdings_df。

## 运行方式

```bash
cd /home/yluel/share/projects/quantsociety_backend_project && \
/home/yluel/share/projects/quantsociety_backend_project/.venv/bin/python \
strategy_layer/portfolio_alpha/holdings_gen/run_from_config.py \
strategy_layer/portfolio_alpha/holdings_gen/examples/from_composite_signal.yaml
```

## 配置重点

- inputs.signal.path: composite_signal 文件或目录
- construction.selection_mode: selected_flag 或 all
- construction.weighting_method: equal 或 score_proportional
- construction.long_budget / short_budget: 多头和空头预算
- optimizer.enabled / optimizer.name: 关闭时走原始权重；开启后可用 Barra 均值-方差优化
- optimizer.params:
  - barra_dir 或 factor_covariance_path / specific_risk_path / factor_exposure_path
  - ic（默认 0.05）
  - risk_aversion（默认 2.0）
  - name_cap（默认 0.05）
  - winsor_q（默认 0.01）
  - long_budget / short_budget（可覆盖 construction 中的预算）
  - sigma_mkt（可选；不填则按当日 specific risk 估计）
  - strict / fallback_to_input_on_fail（控制缺失 Barra 数据时的行为)
- risk_control.enabled / risk_control.name: 当前默认 noop，后续可扩展
- output.root: 输出目录

## Barra 优化模式

当 `optimizer.enabled=true` 且 `optimizer.name=barra`（或 `barra_mean_variance_ls`）时，`holdings_gen` 会在每个交易日上：

1. 对当日 alpha 做 winsorize + 横截面 Z-score
2. 按 `mu = zscore(alpha) * sigma_mkt * IC` 生成预期收益
3. 读取 Barra 的 `factor_covariance.parquet`、`specific_risk.parquet`、`cleaned_factors.parquet`
4. 使用 CVXPY 求解均值-方差优化：
   - long/short 约束
   - 单票上限（默认 5%）
   - 风险项使用 Barra 因子协方差 + 特异性风险

如果 Barra 输入不完整，默认会回退为原始 holdings 权重；也可以通过 `strict=true` 让它直接报错。