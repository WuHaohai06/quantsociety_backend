# portfolio_alpha.risk

这个目录放组合策略层的风险模型、风险约束和相关实验实现。

## 当前状态

当前仓库里已经有稳定文档和较完整实现的是：

- [barra_model/README.md](barra_model/README.md)

## 适用位置

风险模块通常介于：

- 因子或 alpha 生成之后
- holdings 定稿或组合优化之前

也就是说，它更偏向 `portfolio_alpha` 的中后段，而不是原始因子生产。

## 建议阅读顺序

1. [../README.md](../README.md)
2. [barra_model/README.md](barra_model/README.md)

## 备注

如果你当前只是在跑最短 demo，可以先不进入 `risk/`，直接使用 `multiple_factor_composite` + `holdings_gen` 的默认链路。