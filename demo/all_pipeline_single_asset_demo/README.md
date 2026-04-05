# Single Asset Pipeline Demo

这个目录新增了一条自包含的单资产端到端 demo：

1. 生成 mock 单资产 OHLCV 到 workspace_data
2. 用 factor_engine 物化多个日频因子到 factor lake
3. 用 single_asset_alpha 从 factor_lake 生成 target_position
4. 用 single_asset_backtest 生成单资产回测结果

代码入口：

- demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py
- demo/all_pipeline_single_asset_demo/single_asset_pipeline_demo.ipynb

## 运行方式

在仓库根目录执行：

```bash
python demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py
```

如果要把它当成 smoke test 跑，可以执行：

```bash
pytest demo/all_pipeline_single_asset_demo/test_single_asset_pipeline_demo.py -q
```

## 产物位置

这套 demo 的数据全部落在 workspace_data 下：

- mock 输入数据：workspace_data/demos/single_asset_pipeline_demo/inputs
- demo 汇总报告：workspace_data/demos/single_asset_pipeline_demo/reports/pipeline_summary.json
- factor lake：workspace_data/factors/lake
- 单资产 alpha 输出：workspace_data/strategy/single_asset_alpha/single_asset_pipeline_factor_timing_v1
- 单资产回测输出：workspace_data/backtests/single_asset/single_asset_factor_timing/e2e_demo