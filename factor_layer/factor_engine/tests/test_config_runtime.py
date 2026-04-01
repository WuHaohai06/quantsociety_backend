from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
yaml = pytest.importorskip("yaml")

from runtime.engine import FactorEngine


def test_run_from_config_with_kline_parquet_source(tmp_path: Path):
    root = tmp_path / 'day_aggs_v1' / '2024' / '01'
    root.mkdir(parents=True)

    for day, rows in {
        '2024-01-01': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-02': [('AAA', 11.0), ('BBB', 19.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'ticker': [ticker for ticker, _ in rows],
                'window_start': [pd.Timestamp(day, tz='UTC').value for _ in rows],
                'close': [close for _, close in rows],
                'open': [close for _, close in rows],
                'high': [close + 1 for _, close in rows],
                'low': [close - 1 for _, close in rows],
                'volume': [1000.0 for _ in rows],
                'transactions': [10.0 for _ in rows],
            }
        )
        frame.to_parquet(root / f'{day}.parquet', index=False)

    config_path = tmp_path / 'factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'mom_2_rank',
                    'expr': 'rank(ts_mean(col("close"), 2))',
                },
                'data_source': {
                    'type': 'parquet_kline',
                    'root': str(tmp_path / 'day_aggs_v1'),
                    'instrument_column': 'ticker',
                    'timestamp_column': 'window_start',
                    'fields': {'close': 'close'},
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
            }
        )
    )

    out = FactorEngine.run_from_config(config_path)
    result = out['result']

    assert out['factor'].name == 'mom_2_rank'
    assert out['analysis'].lookback == 2
    assert result.loc[(pd.Timestamp('2024-01-03'), 'AAA')] == 0.5
    assert result.loc[(pd.Timestamp('2024-01-03'), 'BBB')] == 1.0


def test_run_from_config_with_multi_parquet_source(tmp_path: Path):
    root = tmp_path / 'financials_ratios'
    root.mkdir(parents=True)

    for day, rows in {
        '2024-01-01': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-02': [('AAA', 11.0), ('BBB', 19.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'ticker': [ticker for ticker, _ in rows],
                'date': [day for _ in rows],
                'price_to_earnings': [value for _, value in rows],
            }
        )
        frame.to_parquet(root / f'{day}.parquet', index=False)

    config_path = tmp_path / 'multi_parquet_factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'pe_rank',
                    'expr': 'rank(col("price_to_earnings"))',
                },
                'data_source': {
                    'type': 'multi_parquet',
                    'root': str(root),
                    'timestamp_col': 'date',
                    'instrument_col': 'ticker',
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
            }
        )
    )

    out = FactorEngine.run_from_config(config_path)
    result = out['result']

    assert out['factor'].name == 'pe_rank'
    assert result.loc[(pd.Timestamp('2024-01-03'), 'AAA')] == 0.5
    assert result.loc[(pd.Timestamp('2024-01-03'), 'BBB')] == 1.0


def test_run_from_config_with_cleaned_parquet_source(tmp_path: Path):
    root = tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1' / '2024' / '01'
    root.mkdir(parents=True)

    for day, rows in {
        '2024-01-01': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-02': [('AAA', 11.0), ('BBB', 19.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'source': ['us_stocks_sip/day_aggs_v1' for _ in rows],
                'dataset_type': ['market_bar' for _ in rows],
                'frequency': ['daily' for _ in rows],
                'ticker': [ticker for ticker, _ in rows],
                'align_time': [pd.Timestamp(day, tz='UTC') for _ in rows],
                'primary_key': [f'{day}:{ticker}' for ticker, _ in rows],
                'close': [close for _, close in rows],
                'volume': [1000.0 for _ in rows],
            }
        )
        frame.to_parquet(root / f'{day}.parquet', index=False)

    config_path = tmp_path / 'cleaned_factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'cleaned_mom_2_rank',
                    'expr': 'rank(ts_mean(col("close"), 2))',
                },
                'data_source': {
                    'type': 'cleaned_parquet',
                    'root': str(tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1'),
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
            }
        )
    )

    out = FactorEngine.run_from_config(config_path)
    result = out['result']

    assert out['factor'].name == 'cleaned_mom_2_rank'
    assert out['config'].data_source.type == 'cleaned_parquet'
    assert out['analysis'].lookback == 2
    assert result.loc[(pd.Timestamp('2024-01-03'), 'AAA')] == 0.5
    assert result.loc[(pd.Timestamp('2024-01-03'), 'BBB')] == 1.0


def test_run_from_config_with_composite_data_source(tmp_path: Path):
    price_root = tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1' / '2024' / '01'
    price_root.mkdir(parents=True)
    fundamental_root = tmp_path / 'financials_ratios'
    fundamental_root.mkdir(parents=True)

    for day, rows in {
        '2024-01-02': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'source': ['us_stocks_sip/day_aggs_v1' for _ in rows],
                'dataset_type': ['market_bar' for _ in rows],
                'frequency': ['daily' for _ in rows],
                'ticker': [ticker for ticker, _ in rows],
                'align_time': [pd.Timestamp(day, tz='UTC') for _ in rows],
                'primary_key': [f'{day}:{ticker}' for ticker, _ in rows],
                'close': [close for _, close in rows],
            }
        )
        frame.to_parquet(price_root / f'{day}.parquet', index=False)

    for day, rows in {
        '2024-01-01': [('AAA', 2.0), ('BBB', 5.0)],
        '2024-01-03': [('AAA', 3.0), ('BBB', 6.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'ticker': [ticker for ticker, _ in rows],
                'date': [day for _ in rows],
                'price_to_earnings': [value for _, value in rows],
            }
        )
        frame.to_parquet(fundamental_root / f'{day}.parquet', index=False)

    config_path = tmp_path / 'composite_factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'close_over_pe',
                    'expr': 'col("close") / col("pe")',
                },
                'data_source': {
                    'type': 'composite',
                    'anchor': 'price',
                    'anchor_column': 'close',
                    'aliases': {'pe': 'fundamental.price_to_earnings'},
                    'sources': {
                        'price': {
                            'type': 'cleaned_parquet',
                            'root': str(tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1'),
                        },
                        'fundamental': {
                            'type': 'multi_parquet',
                            'root': str(fundamental_root),
                            'timestamp_col': 'date',
                            'instrument_col': 'ticker',
                        },
                    },
                    'joins': {
                        'fundamental': {
                            'method': 'asof_backward',
                        }
                    },
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
            }
        )
    )

    out = FactorEngine.run_from_config(config_path)
    result = out['result']

    assert out['factor'].name == 'close_over_pe'
    assert out['config'].data_source.type == 'composite'
    assert result.loc[(pd.Timestamp('2024-01-02'), 'AAA')] == pytest.approx(5.0)
    assert result.loc[(pd.Timestamp('2024-01-02'), 'BBB')] == pytest.approx(4.0)
    assert result.loc[(pd.Timestamp('2024-01-03'), 'AAA')] == pytest.approx(4.0)
    assert result.loc[(pd.Timestamp('2024-01-03'), 'BBB')] == pytest.approx(3.0)


def test_materialize_from_config_with_cleaned_parquet_source(tmp_path: Path):
    root = tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1' / '2024' / '01'
    root.mkdir(parents=True)

    for day, rows in {
        '2024-01-01': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-02': [('AAA', 11.0), ('BBB', 19.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'source': ['us_stocks_sip/day_aggs_v1' for _ in rows],
                'dataset_type': ['market_bar' for _ in rows],
                'frequency': ['daily' for _ in rows],
                'ticker': [ticker for ticker, _ in rows],
                'align_time': [pd.Timestamp(day, tz='UTC') for _ in rows],
                'primary_key': [f'{day}:{ticker}' for ticker, _ in rows],
                'close': [close for _, close in rows],
                'volume': [1000.0 for _ in rows],
            }
        )
        frame.to_parquet(root / f'{day}.parquet', index=False)

    lake_root = tmp_path / 'factor_lake'
    config_path = tmp_path / 'materialize_factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'cleaned_mom_2_rank',
                    'expr': 'rank(ts_mean(col("close"), 2))',
                    'freq': '1d',
                    'description': 'cleaned parquet materialization test',
                },
                'data_source': {
                    'type': 'cleaned_parquet',
                    'root': str(tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1'),
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
                'materialization': {
                    'lake_root': str(lake_root),
                    'factor_id': 'cleaned_mom_2_rank_v1',
                    'author': 'tester',
                },
            }
        )
    )

    out = FactorEngine.materialize_from_config(config_path)
    summary = out['materialization']
    result = out['result']

    parquet_path = lake_root / 'factors' / 'cleaned_mom_2_rank_v1' / 'year=2024' / 'data.parquet'
    assert out['config'].materialization is not None
    assert out['config'].materialization.lake_root == str(lake_root)
    assert summary['factor_id'] == 'cleaned_mom_2_rank_v1'
    assert summary['rows_written'] == 4
    assert summary['lake_root'] == str(lake_root)
    assert parquet_path.exists()
    assert result.loc[(pd.Timestamp('2024-01-03'), 'AAA')] == 0.5
    assert result.loc[(pd.Timestamp('2024-01-03'), 'BBB')] == 1.0


def test_run_from_config_emits_progress_logs(tmp_path: Path, caplog):
    root = tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1' / '2024' / '01'
    root.mkdir(parents=True)

    for day, rows in {
        '2024-01-01': [('AAA', 10.0), ('BBB', 20.0)],
        '2024-01-02': [('AAA', 11.0), ('BBB', 19.0)],
        '2024-01-03': [('AAA', 12.0), ('BBB', 18.0)],
    }.items():
        frame = pd.DataFrame(
            {
                'source': ['us_stocks_sip/day_aggs_v1' for _ in rows],
                'dataset_type': ['market_bar' for _ in rows],
                'frequency': ['daily' for _ in rows],
                'ticker': [ticker for ticker, _ in rows],
                'align_time': [pd.Timestamp(day, tz='UTC') for _ in rows],
                'primary_key': [f'{day}:{ticker}' for ticker, _ in rows],
                'close': [close for _, close in rows],
                'volume': [1000.0 for _ in rows],
            }
        )
        frame.to_parquet(root / f'{day}.parquet', index=False)

    config_path = tmp_path / 'logging_factor.yaml'
    config_path.write_text(
        yaml.safe_dump(
            {
                'factor': {
                    'name': 'cleaned_mom_log_rank',
                    'expr': 'rank(ts_mean(col("close"), 2))',
                },
                'data_source': {
                    'type': 'cleaned_parquet',
                    'root': str(tmp_path / 'cleaned_massive_data' / 'us_stocks_sip' / 'day_aggs_v1'),
                },
                'backend': {'type': 'pandas'},
                'engine': {'enable_cache': True},
            }
        )
    )

    with caplog.at_level('INFO', logger='factor_engine'):
        FactorEngine.run_from_config(config_path)

    messages = '\n'.join(
        record.getMessage() for record in caplog.records if record.name.startswith('factor_engine')
    )
    assert "开始执行因子 'cleaned_mom_log_rank'" in messages
    assert '读取列 close [' in messages
    assert '100.0%' in messages
