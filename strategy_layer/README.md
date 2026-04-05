# Strategy Layer

这一层负责把因子值、行情和辅助数据转成可执行的策略层输出。当前主要有两条路径：

- 单资产择时路径：信号 → `target_position`
- 组合策略路径：多因子面板 → composite signal → holdings

## 目录结构

| 目录 | 作用 |
| --- | --- |
| [single_asset_alpha/README.md](single_asset_alpha/README.md) | 单标的 C 侧流水线，输出 `target_position` |
| [portfolio_alpha/README.md](portfolio_alpha/README.md) | 组合策略层，输出 composite signal 和 holdings |
| `data/` | 行情与因子读取的共享数据层 |
| `outputs/` | 历史或本地产物 |

## 两条主路径

### 1. 单资产路径

适用于“一个标的、一条择时信号、一个 `target_position` 长表”的研究链路。

入口和文档：

- [single_asset_alpha/README.md](single_asset_alpha/README.md)

下游通常接：

- [../backtest_layer/single_asset_backtest/README.md](../backtest_layer/single_asset_backtest/README.md)

### 2. 组合路径

适用于多因子、多标的组合研究。

入口和文档：

- [portfolio_alpha/README.md](portfolio_alpha/README.md)

下游通常接：

- [../backtest_layer/portfolio_backtest/README.md](../backtest_layer/portfolio_backtest/README.md)

## 当前推荐的工作顺序

### 组合策略

1. `multiple_factor_composite` 读取 factor lake，生成组合信号
2. `holdings_gen` 把组合信号变成 holdings 长表
3. 如需风险模型，可在 `risk/` 下接 Barra 或其它约束模块
4. 将 holdings 交给回测层

### 单资产择时

1. `single_asset_alpha` 读取行情和因子
2. 先做信号，再映射为 `target_position`
3. 将结果交给回测层或 bridge

## 端到端示例

- 组合全链路 demo： [../demo/all_pipeline_demo/README.md](../demo/all_pipeline_demo/README.md)
- 单资产全链路 demo： [../demo/all_pipeline_single_asset_demo/README.md](../demo/all_pipeline_single_asset_demo/README.md)