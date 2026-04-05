# Backtest Layer

这一层负责把策略层交付的目标仓位或持仓结果转换成标准化回测产物，包括 `returns`、`metrics`、`summary` 以及必要的审计元数据。

## 目录结构

| 目录 | 作用 |
| --- | --- |
| [single_asset_backtest/README.md](single_asset_backtest/README.md) | 单资产 `target_position` 回测主实现；同包内也提供 `run_multi_asset_backtest` |
| [portfolio_backtest/README.md](portfolio_backtest/README.md) | 基于 holdings 长表构建组合回测产物，并做策略准入评估 |
| [examples/README.md](examples/README.md) | 单资产和多资产最小示例 |
| `tests/` | 单元测试、协议测试、C→D 回归和组合回测测试 |

## 两条使用路径

### 1. 单资产 `target_position` 路径

适合研究员 C 产出 `timestamp + target_position` 长表后，直接由 D 侧执行回测。

核心入口：

- `single_asset_backtest.runner.run_single_asset_backtest`
- `strategy_layer/single_asset_alpha/integration/backtest_bridge.py`

推荐先读：

- [single_asset_backtest/README.md](single_asset_backtest/README.md)

### 2. 组合 holdings 路径

适合策略层已经生成 `trade_date + symbol + weight` 的 holdings 长表，需要统一生成组合回测产物、再接策略准入评估。

核心入口：

- `portfolio_backtest.portfolio_backtest.PortfolioBacktestArtifactBuilder`
- `portfolio_backtest.strategy_registry.StrategyRegistryEvaluator`

推荐先读：

- [portfolio_backtest/README.md](portfolio_backtest/README.md)

## 示例和测试

最短上手路径：

```bash
python backtest_layer/examples/backtest_single_asset.py
python backtest_layer/examples/backtest_multi_asset.py
```

对应说明见：

- [examples/README.md](examples/README.md)

常用测试：

```bash
pytest backtest_layer/tests/test_backtest_single_asset.py -q
pytest backtest_layer/tests/test_backtest_multi_asset.py -q
pytest backtest_layer/tests/test_c_to_d_e2e_regression.py -q
```

## 与上下游的关系

- 上游单资产来自 [strategy_layer/single_asset_alpha/README.md](../strategy_layer/single_asset_alpha/README.md)
- 上游组合持仓来自 [strategy_layer/portfolio_alpha/README.md](../strategy_layer/portfolio_alpha/README.md)
- 下游 demo 入口见 [demo/README.md](../demo/README.md)

## 何时用哪个目录

- 你拿到的是 `target_position`：优先用 `single_asset_backtest/`
- 你拿到的是 holdings 长表：优先用 `portfolio_backtest/`
- 你只想快速看最小 runnable example：去 `examples/`
- 你要确认协议、滞后语义或指标口径：直接读 `single_asset_backtest/README.md`