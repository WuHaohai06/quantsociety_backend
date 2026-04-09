# QuantSociety Backend Project

这是一个多模块量化研究后端工作区，覆盖数据获取与清洗、因子生成、因子评估与准入、策略层信号与持仓生成、以及单资产和组合回测。

仓库不是一个单一 Python 包，而是按研究链路拆成多个项目目录。阅读和使用时，建议先从一级目录 README 入手，再进入各子模块自己的详细文档。

## 项目地图

| 目录 | 作用 | 建议入口 |
| --- | --- | --- |
| [raw_data_layer/README.md](raw_data_layer/README.md) | 原始数据抓取、校验、清洗与样例数据 | `raw_data_fetching/`、`raw_data_cleaning/` |
| [factor_layer/README.md](factor_layer/README.md) | 因子计算、评估、准入、Agent 与特化因子项目 | `factor_engine/` |
| [strategy_layer/README.md](strategy_layer/README.md) | 单资产择时与组合策略层 | `single_asset_alpha/`、`portfolio_alpha/` |
| [backtest_layer/README.md](backtest_layer/README.md) | 单资产和组合回测、示例与测试 | `single_asset_backtest/`、`portfolio_backtest/` |
| [demo/README.md](demo/README.md) | 端到端 smoke demo 与 notebook 展示 | `all_pipeline_demo/`、`all_pipeline_single_asset_demo/` |
| `workspace_data/` | 统一运行时产物根目录 | demo 和配置驱动流水线默认写入 |

## 当前推荐使用的主链

### 1. 多因子组合主链

`raw_data_layer` → `factor_layer/factor_engine` → `factor_layer/factor_evaluation` → `factor_layer/factor_admission` → `strategy_layer/portfolio_alpha/multiple_factor_composite` → `strategy_layer/portfolio_alpha/holdings_gen` → `backtest_layer/portfolio_backtest`

推荐 smoke demo：

- [demo/all_pipeline_demo/README.md](demo/all_pipeline_demo/README.md)

### 2. 单资产择时主链

`raw_data / market_data` + `factor_lake` → `strategy_layer/single_asset_alpha` → `backtest_layer/single_asset_backtest`

推荐 smoke demo：

- [demo/all_pipeline_single_asset_demo/README.md](demo/all_pipeline_single_asset_demo/README.md)

### 3. 特化分钟级因子评估链

`factor_layer/factor_indicators_lysj` 当前维护一条分钟级期货因子评估链，重点是 NQ 的 VWAP Reversion 因子。

入口文档：

- [factor_layer/factor_indicators_lysj/README.md](factor_layer/factor_indicators_lysj/README.md)

## 常用入口

| 目标 | 入口 |
| --- | --- |
| 全链路组合 demo | `python demo/all_pipeline_demo/run_all_pipeline_demo.py` |
| 全链路单资产 demo | `python demo/all_pipeline_single_asset_demo/run_single_asset_pipeline_demo.py` |
| 因子配置运行 | `python factor_layer/factor_engine/examples/...` 或 `FactorEngine.run_from_config(...)` |
| 因子评估 | `python factor_layer/factor_evaluation/run_from_config.py <config.yaml>` |
| 因子准入 | `python factor_layer/factor_admission/run_from_config.py <config.yaml>` |
| 单资产策略流水线 | `python strategy_layer/single_asset_alpha/run_from_config.py <config.yaml>` |
| 组合信号合成 | `python strategy_layer/portfolio_alpha/multiple_factor_composite/run_from_config.py <config.yaml>` |
| 组合持仓生成 | `python strategy_layer/portfolio_alpha/holdings_gen/run_from_config.py <config.yaml>` |

## `workspace_data` 约定

新流程优先把运行时产物落到 `workspace_data/`，而不是散落在各个模块目录下。当前仓库里主要有这些约定路径：

- `workspace_data/demos/`：demo 汇总输入、配置快照和 summary
- `workspace_data/factors/lake/`：factor lake 与评估结果
- `workspace_data/strategy/`：策略层输出，例如组合信号、holdings、single_asset_alpha 结果
- `workspace_data/backtests/`：组合和单资产回测结果
- `workspace_data/cache/`：行情缓存和中间缓存

旧目录里仍保留一些历史 demo 的本地 `outputs/`、`cache/` 与 notebook 资产，属于兼容或历史记录，不再作为新的默认落盘路径。

## 阅读顺序

如果你第一次进入这个仓库，建议按下面顺序读：

1. [README.md](README.md)
2. [PM_PROJECT_OVERVIEW.md](PM_PROJECT_OVERVIEW.md)
3. [FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md)
4. [demo/README.md](demo/README.md)
5. [factor_layer/README.md](factor_layer/README.md)
6. [strategy_layer/README.md](strategy_layer/README.md)
7. [backtest_layer/README.md](backtest_layer/README.md)
8. [raw_data_layer/README.md](raw_data_layer/README.md)
9. [IMPLEMENTED_WORKFLOWS.md](IMPLEMENTED_WORKFLOWS.md)
10. [WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md)

## 环境与测试

- 很多脚本要求 `PYTHONPATH` 至少包含仓库根、`backtest_layer/`、`factor_layer/factor_engine/`。详细说明见对应子模块 README。
- 根目录的 [requirements-dev.txt](requirements-dev.txt) 提供 pytest 等开发依赖。
- 单资产回测与联调示例需要 Backtrader，可用 `pip install "factor-engine[backtest]"`。

常用测试命令：

```bash
pytest backtest_layer/tests -q -m "not integration"
pytest demo/all_pipeline_demo/test_all_pipeline_demo.py -q
pytest demo/all_pipeline_single_asset_demo/test_single_asset_pipeline_demo.py -q
```

## 当前状态

- `factor_layer/factor_engine/` 是目前最完整、最稳定的基础设施层。
- `strategy_layer/single_asset_alpha/` 与 `backtest_layer/single_asset_backtest/` 已形成可跑通的单资产 C→D 路径。
- `strategy_layer/portfolio_alpha/`、`backtest_layer/portfolio_backtest/` 和 `demo/all_pipeline_demo/` 已能串起组合研究主链。
- 仓库中存在历史 notebook、缓存和本地产物；提交前应结合 `.gitignore` 检查变更范围。
