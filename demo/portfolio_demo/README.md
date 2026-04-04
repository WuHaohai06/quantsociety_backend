# Portfolio Demo

这个 demo 展示一条完整的 portfolio 链路：

1. 生成一个小型 demo factor lake 与 mock kline
2. 运行 multiple_factor_composite 产出组合信号
3. 运行 holdings_gen 把信号转换为 holdings
4. 运行 portfolio_backtest 输出回测结果

## 运行方式

```bash
cd /home/yluel/share/projects/quantsociety_backend_project && \
/home/yluel/share/projects/quantsociety_backend_project/.venv/bin/python \
demo/portfolio_demo/portfolio_end_to_end_demo.py
```

Notebook 版本：

- [demo/portfolio_demo/portfolio_end_to_end_demo.ipynb](demo/portfolio_demo/portfolio_end_to_end_demo.ipynb)

如果当前环境不使用仓库根目录 .venv，也可以用你当前已经配置好的 Python 环境直接运行同一个脚本。

## 目录说明

- configs/: 三段流程对应的 YAML 配置
- factor_lake/: 运行 demo 时自动生成的小型因子 lake
- inputs/: 运行 demo 时自动生成的 mock kline
- outputs/: composite、holdings、backtest 三段产物

## 关键配置

- [configs/composite_signal.yaml](configs/composite_signal.yaml): 多因子信号合成
- [configs/holdings_from_signal.yaml](configs/holdings_from_signal.yaml): signal -> holdings
- [configs/portfolio_backtest.yaml](configs/portfolio_backtest.yaml): holdings + kline -> 回测

## 产物位置

- composite signal: outputs/composite_signal_run/signals/composite_signal.parquet
- holdings: outputs/holdings_run/holdings/holdings.parquet
- backtest summary: outputs/backtest_run/demo_portfolio_multi_factor/demo_portfolio_e2e/summary.csv

这个 demo 当前是 long-only 等权示例，目的是验证三段接口可以直接打通。后续如果要接优化器或风控器，可以先从 holdings_gen 的 optimizer/risk_control 扩展点往里接。