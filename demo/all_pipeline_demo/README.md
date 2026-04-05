# All Pipeline Demo

这个目录放的是一条完整的端到端 smoke pipeline：

1. 生成 mock kline 数据到 workspace_data
2. 用 factor_engine 计算并物化两个日频因子
3. 用 factor_evaluation 评估两个因子
4. 用 factor_admission 写入入库决策
5. 用 multiple_factor_composite 生成组合信号
6. 用 holdings_gen 生成持仓
7. 用 portfolio_backtest 生成组合回测结果

代码入口：

- demo/all_pipeline_demo/run_all_pipeline_demo.py
- demo/all_pipeline_demo/all_pipeline_demo.ipynb

## 运行方式

在仓库根目录执行：

```bash
python demo/all_pipeline_demo/run_all_pipeline_demo.py
```

如果要把它当成 smoke test 跑，可以执行：

```bash
pytest demo/all_pipeline_demo/test_all_pipeline_demo.py -q
```

如果你当前使用的是仓库里已经配置好的 Conda 环境，也可以直接沿用当前 Python 环境运行同一个脚本。

## 产物位置

这套 demo 的数据全部落在 workspace_data 下：

- mock 输入数据：workspace_data/demos/all_pipeline_demo/inputs
- demo 汇总报告：workspace_data/demos/all_pipeline_demo/reports/pipeline_summary.json
- factor lake：workspace_data/factors/lake
- factor evaluations：workspace_data/factors/lake/evaluations
- composite signal：workspace_data/strategy/composite_signals/all_pipeline_signal_v1
- holdings：workspace_data/strategy/holdings/all_pipeline_holdings_v1
- backtest：workspace_data/backtests/portfolio/all_pipeline_strategy/e2e_demo

## Notebook

Notebook 会直接调用 run_all_pipeline_demo.py 重新跑一遍流程，然后读取 workspace_data 下的结果做展示和画图。