# day_aggs_v1 基本面因子批次

这组配置使用 composite 数据源方案，以 cleaned day_aggs_v1 日线行情作为锚点源，
再把 cleaned fundamentals 数据通过 asof_backward 方式对齐到日线时间轴。

## 数据范围

- 所有配置统一覆盖 2016-01-01 到 2025-12-31 23:59:59。
- 价格锚点源：/home/yluel/share/projects/massive_parquet/cleaned_massive_data/us_stocks_sip/day_aggs_v1
- 基本面辅助源：/home/yluel/share/projects/massive_parquet/cleaned_massive_data/fundamentals/*

## 因子列表

- day_aggs_v1_fundamental_earnings_yield_rank_2016_2025_v1: PE 倒数截面排名
- day_aggs_v1_fundamental_roe_rank_2016_2025_v1: ROE 截面排名
- day_aggs_v1_fundamental_low_leverage_rank_2016_2025_v1: 低杠杆截面排名
- day_aggs_v1_fundamental_asset_scale_rank_2016_2025_v1: 总资产规模截面排名
- day_aggs_v1_fundamental_book_strength_rank_2016_2025_v1: 权益相对负债强度截面排名
- day_aggs_v1_fundamental_operating_cashflow_rank_2016_2025_v1: 经营现金流截面排名
- day_aggs_v1_fundamental_cash_reinvestment_rank_2016_2025_v1: 经营现金流减投资现金流截面排名
- day_aggs_v1_fundamental_revenue_scale_rank_2016_2025_v1: 营收规模截面排名
- day_aggs_v1_fundamental_operating_margin_proxy_rank_2016_2025_v1: 营业利润率代理截面排名
- day_aggs_v1_fundamental_float_tightness_rank_2016_2025_v1: 流通盘紧致度截面排名

## 批量落盘

```bash
cd /home/yluel/share/projects/quantsociety_backend_project/factor_layer/factor_engine && \
/home/yluel/share/projects/quantsociety_backend_project/.venv/bin/python \
examples/materialize_config_directory.py \
examples/configs/day_aggs_v1_fundamental \
--lake-root /home/yluel/share/projects/factor_data \
--log-level INFO \
--log-file /home/yluel/share/projects/factor_data/logs/day_aggs_v1_fundamental_2016_2025_materialize.log
```