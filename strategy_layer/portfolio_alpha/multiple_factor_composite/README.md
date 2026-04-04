# multiple_factor_composite

独立于 factor_engine 的多因子信号合成模块。

目标是消费已经落盘好的 factor lake 因子资产，在策略层完成：

- 多因子读取与对齐
- 股票池与辅助数据合并
- 去极值、标准化、缺失值处理
- 因子中性化
- 因子正交化
- 等权、自定义权重、IC 加权
- 输出组合信号和中间面板文件

## 运行方式

```bash
cd /home/yluel/share/projects/quantsociety_backend_project/strategy_layer/portfolio_alpha/multiple_factor_composite && \
/home/yluel/share/projects/quantsociety_backend_project/.venv/bin/python run_from_config.py \
examples/day_aggs_v1_fundamental_signal.yaml
```

## 主要产物

- panels/raw_factor_panel.parquet
- panels/preprocessed_factor_panel.parquet
- panels/neutralized_factor_panel.parquet
- panels/orthogonalized_factor_panel.parquet
- weights/weight_history.parquet
- signals/composite_signal.parquet
- manifest.json

## 配置重点

- source.factor_lake_root: 因子 lake 根目录
- factors: 输入因子列表，可区分 compose=true/false
- auxiliary_sources: 行业、标签、股票池等辅助数据；默认按 timestamp/symbol 读取，旧数据可显式传 timestamp_col/symbol_col
- neutralization.steps: group_demean / ols
- orthogonalization.steps: sequential / symmetric
- composition.weighting: equal / custom / ic
- output.root: 输出目录

## 内部数据契约

- 模块内 canonical panel 统一使用 timestamp 和 symbol 两列
- factor lake 物理落盘仍然是 factor_engine 的 datetime/asset/value，但在 reader 边界就会转成 timestamp/symbol
- signals/composite_signal.parquet 与各类中间 panel 现在也统一输出 timestamp/symbol