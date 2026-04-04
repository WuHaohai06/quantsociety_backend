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
- optimizer / risk_control: 当前默认 noop，后续可扩展
- output.root: 输出目录

## 扩展点

- optimizer.py: 预留组合优化器入口，未来可接入 Barra 或约束优化
- risk_control.py: 预留风控器入口，未来可接入行业/风格/单票约束

当前如果把 optimizer.enabled 或 risk_control.enabled 打开，并填入非 noop 名称，会明确抛出 NotImplementedError，避免静默跑偏。