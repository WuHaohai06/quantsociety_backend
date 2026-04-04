# strategy_layer.data

strategy_layer 与 backtest_layer 共用的数据访问层。

当前包含两类公共模块：

- factor_panel: 因子 lake 的 canonical timestamp/symbol 读取与拼 panel
- market_data: 单标标准 OHLCV 读取、aggregate_bars 标准化与可选缓存

## Canonical Schema

公共层输出统一使用稀疏 panel，不补全 `timestamp × symbol` 的完整笛卡尔积。

字段如下：

- `timestamp`: 时间列
- `symbol`: 标的列
- 其余列: 因子列

约束如下：

- 主键为 `timestamp + symbol`
- 不允许重复主键
- 输出始终使用 `timestamp` / `symbol` 命名，不继续向下游暴露 factor lake 的 `datetime` / `asset`
- `symbols` 过滤是公共接口的正式参数，单资产路径必须尽早传入，不能先构全市场再裁剪

## Factor APIs

- `load_factor_long(lake_root, factor_id, *, start=None, end=None, symbols=None)`
- `build_factor_panel(lake_root, factors, *, start=None, end=None, symbols=None, align_method="outer", anchor_factor=None)`
- `project_single_asset(panel, symbol)`

## Market APIs

- `load_standard_ohlcv(path, *, strict_temporal_validation=True, max_rows=None)`
- `load_single_asset_ohlcv(symbol=..., mode=..., ...)`

## 设计边界

这层不负责：

- 股票池过滤
- auxiliary merge
- neutralization / orthogonalization
- single_asset 的行情对齐
- target_position / target_weight 生成