# Backtest Examples

这个目录放回测层最小示例脚本，适合快速验证环境、理解输入形态和熟悉输出结构。

## 脚本说明

| 脚本 | 用途 |
| --- | --- |
| `backtest_single_asset.py` | 演示如何传入 `target_position` 跑单资产回测 |
| `backtest_multi_asset.py` | 演示如何传入 `target_weights` 跑多资产组合回测 |

## 运行前置条件

- 在仓库根执行，确保 `PYTHONPATH` 能解析仓库根、`backtest_layer/` 和 `factor_layer/factor_engine/`
- 单资产示例依赖 Backtrader，可使用 `pip install "factor-engine[backtest]"`

## 运行方式

```bash
python backtest_layer/examples/backtest_single_asset.py
python backtest_layer/examples/backtest_multi_asset.py
```

## 建议阅读顺序

1. 先看 [../README.md](../README.md)
2. 单资产细节看 [../single_asset_backtest/README.md](../single_asset_backtest/README.md)
3. 组合 holdings 产物逻辑看 [../portfolio_backtest/README.md](../portfolio_backtest/README.md)