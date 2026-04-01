# day_aggs_v1 量价因子批次

这组配置基于当前 factor_engine 已支持且已在真实数据上试跑通过的表达式，面向 cleaned day_aggs_v1 日线行情。

## 数据范围

- 当前默认 root 指向 `2026/03` 这一个月的 cleaned parquet：
  `/home/yluel/share/projects/massive_parquet/cleaned_massive_data/us_stocks_sip/day_aggs_v1/2026/03`
- 这样做是为了先保证一批量价因子可以稳定批量落盘到 factor lake。
- 如果后面要扩到更长时间范围，可以把各配置里的 `data_source.root` 改到更高层目录。

## 因子列表

- `day_aggs_v1_pv_close_mom_3_rank_v1`: 3 日收盘价动量截面排名
- `day_aggs_v1_pv_close_reversal_1_rank_v1`: 1 日价格反转截面排名
- `day_aggs_v1_pv_intraday_range_rank_v1`: 日内振幅截面排名
- `day_aggs_v1_pv_gap_rank_v1`: 开盘跳空截面排名
- `day_aggs_v1_pv_close_in_range_rank_v1`: 收盘位置截面排名
- `day_aggs_v1_pv_volume_level_rank_v1`: 成交量水平截面排名
- `day_aggs_v1_pv_volume_delta_1_rank_v1`: 成交量变化截面排名
- `day_aggs_v1_pv_transactions_level_rank_v1`: 成交笔数水平截面排名
- `day_aggs_v1_pv_transactions_delta_1_rank_v1`: 成交笔数变化截面排名
- `day_aggs_v1_pv_range_x_volume_rank_v1`: 振幅与成交量混合截面排名

## 批量落盘

```bash
cd factor_layer/factor_engine
python examples/materialize_config_directory.py examples/configs/day_aggs_v1_price_volume --lake-root /home/yluel/share/projects/factor_data
```