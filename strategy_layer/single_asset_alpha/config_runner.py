from __future__ import annotations

from pathlib import Path
from typing import Any

from strategy_layer.data import FactorRef
from strategy_layer.single_asset_alpha.config import (
    FactorRefConfig,
    SignalConfig,
    SingleAssetAlphaConfig,
    load_config,
)
from strategy_layer.single_asset_alpha.data_loader.fetcher import DataFetcher
from strategy_layer.single_asset_alpha.pipeline import StrategyPipeline
from strategy_layer.single_asset_alpha.strategies.position_mappers.atr_volatility_mapper import ATRVolatilityMapper
from strategy_layer.single_asset_alpha.strategies.position_mappers.simple_mapper import ThresholdPositionMapper
from strategy_layer.single_asset_alpha.strategies.signals.dual_ma_signal import DualMASignal
from strategy_layer.single_asset_alpha.strategies.signals.factor_threshold_signal import FactorThresholdSignal
from strategy_layer.single_asset_alpha.strategies.signals.macd_signal import MACDSignal
from strategy_layer.single_asset_alpha.strategies.signals.rsi_signal import RSISignal
from strategy_layer.single_asset_alpha.strategies.signals.signal_combiner import SignalCombiner


def _build_factor_refs(factor_refs: tuple[FactorRefConfig, ...]) -> list[FactorRef]:
    return [FactorRef(factor_id=ref.factor_id, column_name=ref.name) for ref in factor_refs]


def build_data_fetcher(config: SingleAssetAlphaConfig) -> DataFetcher:
    kwargs: dict[str, Any] = {}
    if config.market_data.mode == "data_root":
        kwargs["data_root"] = config.market_data.data_root
    elif config.market_data.mode == "aggregate_bars_daily_summary":
        kwargs["aggregate_bars_root"] = config.market_data.aggregate_bars_root
        kwargs["aggregate_dataset"] = config.market_data.aggregate_dataset
        kwargs["aggregate_symbol_column"] = config.market_data.aggregate_symbol_column
        kwargs["aggregate_timestamp_column"] = config.market_data.aggregate_timestamp_column
        kwargs["aggregate_columns"] = dict(config.market_data.aggregate_columns)
    if config.market_data.cache_root is not None:
        kwargs["market_data_cache_root"] = config.market_data.cache_root
    if config.factor_source.mode == "factor_lake":
        kwargs["factor_lake_root"] = config.factor_source.factor_lake_root
        kwargs["factor_refs"] = _build_factor_refs(config.factor_source.factor_refs)
        kwargs["factor_lake_align_method"] = config.factor_source.factor_lake_align_method
    elif config.factor_source.mode == "legacy_factor_root":
        kwargs["factor_root"] = config.factor_source.factor_root
    return DataFetcher(**kwargs)


def build_signal_generator(config: SignalConfig):
    params = dict(config.params)
    if config.type == "dual_ma":
        return DualMASignal(params=params, name=config.name)
    if config.type == "macd":
        return MACDSignal(params=params, name=config.name)
    if config.type == "rsi":
        return RSISignal(params=params, name=config.name)
    if config.type == "factor_threshold":
        return FactorThresholdSignal(params=params, name=config.name)
    if config.type == "combined":
        return SignalCombiner(
            signal_generators=[build_signal_generator(child) for child in config.signals],
            weights=list(config.weights) if config.weights is not None else None,
            params=params,
            name=config.name,
        )
    raise ValueError(f"Unsupported signal type: {config.type}")


def build_position_mapper(config):
    params = dict(config.params)
    if config.type == "threshold":
        return ThresholdPositionMapper(params=params, name=config.name)
    if config.type == "atr_volatility":
        return ATRVolatilityMapper(params=params, name=config.name)
    raise ValueError(f"Unsupported position mapper type: {config.type}")


def build_pipeline(
    config: SingleAssetAlphaConfig,
    *,
    data_fetcher: DataFetcher | None = None,
) -> StrategyPipeline:
    return StrategyPipeline(
        symbol=config.instrument.symbol,
        signal_generator=build_signal_generator(config.signal),
        position_mapper=build_position_mapper(config.position_mapper),
        data_fetcher=data_fetcher or build_data_fetcher(config),
        output_dir=config.output.output_dir,
    )


def _resolve_run_window(config: SingleAssetAlphaConfig) -> tuple[str | None, str | None]:
    start_date = config.run.start_date or config.market_data.start_date
    end_date = config.run.end_date or config.market_data.end_date
    return start_date, end_date


def _load_market_data(
    config: SingleAssetAlphaConfig,
    fetcher: DataFetcher,
    *,
    start_date: str | None,
    end_date: str | None,
):
    if config.market_data.mode == "mock":
        market_data = DataFetcher.generate_sample_data(
            symbol=config.instrument.symbol,
            periods=config.market_data.mock_periods,
            start_date=config.market_data.mock_start_date,
            seed=config.market_data.mock_seed,
        )
        if start_date:
            market_data = market_data.loc[start_date:]
        if end_date:
            market_data = market_data.loc[:end_date]
        return market_data
    if config.market_data.mode == "source_path":
        return fetcher.load_market_data(
            symbol=config.instrument.symbol,
            start_date=start_date,
            end_date=end_date,
            freq=config.market_data.freq,
            source_path=config.market_data.source_path,
        )
    return fetcher.load_market_data(
        symbol=config.instrument.symbol,
        start_date=start_date,
        end_date=end_date,
        freq=config.market_data.freq,
    )


def _load_factor_data(
    config: SingleAssetAlphaConfig,
    fetcher: DataFetcher,
    *,
    start_date: str | None,
    end_date: str | None,
):
    if config.factor_source.mode == "none":
        return None
    if config.factor_source.mode == "source_path":
        return fetcher.load_factor_data(
            symbol=config.instrument.symbol,
            start_date=start_date,
            end_date=end_date,
            source_path=config.factor_source.source_path,
        )
    return fetcher.load_factor_data(
        symbol=config.instrument.symbol,
        start_date=start_date,
        end_date=end_date,
    )


def _write_config_snapshot(config_path: str | Path, output_dir: str | Path) -> str:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_root / "config_snapshot.yaml"
    snapshot_path.write_text(Path(config_path).read_text())
    return str(snapshot_path)


def run_with_config(
    config: SingleAssetAlphaConfig,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    fetcher = build_data_fetcher(config)
    pipeline = build_pipeline(config, data_fetcher=fetcher)
    start_date, end_date = _resolve_run_window(config)

    market_data = _load_market_data(
        config,
        fetcher,
        start_date=start_date,
        end_date=end_date,
    )
    factor_data = _load_factor_data(
        config,
        fetcher,
        start_date=start_date,
        end_date=end_date,
    )

    target_position = pipeline.run(
        market_data=market_data,
        factor_data=factor_data,
        start_date=start_date,
        end_date=end_date,
        save_full_timeseries=config.output.save_full_timeseries,
        save_debounced=config.output.save_debounced,
        output_format=config.output.output_format,
    )

    config_snapshot = None
    if config_path is not None:
        config_snapshot = _write_config_snapshot(config_path, config.output.output_dir)

    return {
        "config": config,
        "market_data": market_data,
        "factor_data": factor_data,
        "target_position": target_position,
        "output_dir": config.output.output_dir,
        "config_snapshot": config_snapshot,
    }


def run_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    return run_with_config(config, config_path=config_path)
