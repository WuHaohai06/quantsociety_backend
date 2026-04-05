# portfolio_alpha

这个目录承载组合策略层的主流程，目标是把多因子输入逐步加工成组合可执行的 holdings。

## 目录结构

| 目录 | 作用 |
| --- | --- |
| [multiple_factor_composite/README.md](multiple_factor_composite/README.md) | 因子读取、预处理、中性化、正交化与组合信号合成 |
| [holdings_gen/README.md](holdings_gen/README.md) | 将组合信号转换成 holdings 长表 |
| [risk/README.md](risk/README.md) | 风险模型与约束模块，当前以 `barra_model/` 为主 |

## 当前主链

`factor_lake` → `multiple_factor_composite` → `composite_signal.parquet` → `holdings_gen` → `holdings.parquet` → 回测层

## 推荐入口

### 1. 组合信号合成

```bash
python strategy_layer/portfolio_alpha/multiple_factor_composite/run_from_config.py path/to/config.yaml
```

### 2. 持仓生成

```bash
python strategy_layer/portfolio_alpha/holdings_gen/run_from_config.py path/to/config.yaml
```

### 3. 风险模型与优化

当前 `risk/` 下主要是 `barra_model/`，适合在 holdings 生成前或组合优化阶段引入因子风险与约束。

## 你应该先读哪个目录

- 只关心信号合成：先读 [multiple_factor_composite/README.md](multiple_factor_composite/README.md)
- 已有 composite signal，想直接生成 holdings：先读 [holdings_gen/README.md](holdings_gen/README.md)
- 想看风险模型和优化：先读 [risk/README.md](risk/README.md)

## 与上下游的关系

- 上游因子通常来自 [../../factor_layer/factor_engine/README.md](../../factor_layer/factor_engine/README.md)
- 下游回测通常来自 [../../backtest_layer/portfolio_backtest/README.md](../../backtest_layer/portfolio_backtest/README.md)
- 端到端演示见 [../../demo/all_pipeline_demo/README.md](../../demo/all_pipeline_demo/README.md) 和 [../../demo/portfolio_demo/README.md](../../demo/portfolio_demo/README.md)