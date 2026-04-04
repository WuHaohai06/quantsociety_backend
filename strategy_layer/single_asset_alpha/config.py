from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import yaml

MarketDataMode = Literal["data_root", "source_path", "mock", "aggregate_bars_daily_summary"]
FactorSourceMode = Literal["none", "factor_lake", "source_path", "legacy_factor_root"]
SignalType = Literal["dual_ma", "macd", "rsi", "factor_threshold", "combined"]
PositionMapperType = Literal["threshold", "atr_volatility"]
FactorLakeAlignMethod = Literal["outer", "inner", "asof_backward", "forward_fill"]
OutputFormat = Literal["parquet", "csv"]

DEFAULT_SIGNAL_NAMES: dict[str, str] = {
    "dual_ma": "DualMA",
    "macd": "MACD",
    "rsi": "RSI",
    "factor_threshold": "FactorThreshold",
    "combined": "CombinedSignal",
}

DEFAULT_SIGNAL_PARAMS: dict[str, dict[str, Any]] = {
    "dual_ma": {"fast_window": 5, "slow_window": 20, "ma_type": "sma"},
    "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
    "rsi": {"rsi_period": 14, "overbought": 70.0, "oversold": 30.0},
    "factor_threshold": {
        "factor_names": None,
        "factor_weights": {},
        "normalize": True,
        "zscore_window": 60,
    },
    "combined": {"combine_method": "weighted_avg"},
}

DEFAULT_MAPPER_NAMES: dict[str, str] = {
    "threshold": "ThresholdMapper",
    "atr_volatility": "ATRVolatilityMapper",
}

DEFAULT_MAPPER_PARAMS: dict[str, dict[str, Any]] = {
    "threshold": {
        "long_entry_threshold": 0.5,
        "long_exit_threshold": 0.0,
        "short_entry_threshold": -0.5,
        "short_exit_threshold": 0.0,
        "allow_short": False,
        "position_size": 1.0,
        "shift_bars": 1,
    },
    "atr_volatility": {
        "atr_period": 14,
        "base_long_threshold": 0.5,
        "base_short_threshold": -0.5,
        "exit_buffer_ratio": 0.4,
        "volatility_scale_factor": 1.0,
        "target_volatility": 0.15,
        "allow_short": False,
        "max_position": 1.0,
        "min_position": 0.1,
        "annualize_factor": 252,
        "shift_bars": 1,
    },
}

DEFAULT_AGGREGATE_COLUMNS: dict[str, str] = {
    "open": "o",
    "high": "h",
    "low": "l",
    "close": "c",
    "volume": "v",
}


@dataclass(frozen=True)
class MetaConfig:
    strategy_id: str
    version: str = "v1"
    description: str | None = None


@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str


@dataclass(frozen=True)
class MarketDataConfig:
    mode: MarketDataMode
    data_root: str | None = None
    source_path: str | None = None
    freq: str = "1d"
    start_date: str | None = None
    end_date: str | None = None
    cache_root: str | None = None
    mock_periods: int = 500
    mock_start_date: str = "2023-01-01"
    mock_seed: int = 42
    aggregate_bars_root: str | None = None
    aggregate_dataset: str = "daily_market_summary"
    aggregate_symbol_column: str = "ticker"
    aggregate_timestamp_column: str = "align_time"
    aggregate_columns: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_AGGREGATE_COLUMNS)
    )


@dataclass(frozen=True)
class FactorRefConfig:
    factor_id: str
    alias: str | None = None

    @property
    def name(self) -> str:
        return self.alias or self.factor_id


@dataclass(frozen=True)
class FactorSourceConfig:
    mode: FactorSourceMode = "none"
    factor_lake_root: str | None = None
    source_path: str | None = None
    factor_root: str | None = None
    factor_lake_align_method: FactorLakeAlignMethod = "outer"
    factor_refs: tuple[FactorRefConfig, ...] = ()


@dataclass(frozen=True)
class SignalConfig:
    type: SignalType
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    weights: tuple[float, ...] | None = None
    signals: tuple["SignalConfig", ...] = ()


@dataclass(frozen=True)
class PositionMapperConfig:
    type: PositionMapperType
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunConfig:
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True)
class OutputConfig:
    output_dir: str = "outputs"
    output_format: OutputFormat = "parquet"
    save_full_timeseries: bool = True
    save_debounced: bool = True


@dataclass(frozen=True)
class SingleAssetAlphaConfig:
    meta: MetaConfig
    instrument: InstrumentConfig
    market_data: MarketDataConfig
    factor_source: FactorSourceConfig
    signal: SignalConfig
    position_mapper: PositionMapperConfig
    run: RunConfig = field(default_factory=RunConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def _as_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是 object")
    return dict(value)


def _as_list(value: Any, *, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须是数组")
    return list(value)


def _normalize_scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _require_non_empty_text(value: Any, *, field_name: str) -> str:
    text = _normalize_scalar_text(value)
    if text is None or not text.strip():
        raise ValueError(f"{field_name} 不能为空")
    return text.strip()


def _normalize_params(defaults: dict[str, Any], payload: Any, *, field_name: str) -> dict[str, Any]:
    params = _as_mapping(payload, field_name=field_name)
    normalized = dict(defaults)
    normalized.update(params)
    return normalized


def _resolve_path_text(
    value: Any,
    *,
    field_name: str,
    base_dir: Path,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{field_name} 必须是路径字符串")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} 不能为空字符串")
    expanded = Path(os.path.expandvars(os.path.expanduser(text)))
    if not expanded.is_absolute():
        expanded = (base_dir / expanded).resolve()
    return str(expanded)


def _parse_factor_ref(raw: Any, *, field_name: str) -> FactorRefConfig:
    if isinstance(raw, str):
        factor_id = raw.strip()
        if not factor_id:
            raise ValueError(f"{field_name}.factor_id 不能为空")
        return FactorRefConfig(factor_id=factor_id)
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} 的每一项必须是字符串或 object")
    factor_id = _require_non_empty_text(raw.get("factor_id"), field_name=f"{field_name}.factor_id")
    alias = raw.get("alias")
    if alias is not None:
        alias = _require_non_empty_text(alias, field_name=f"{field_name}.alias")
    return FactorRefConfig(factor_id=factor_id, alias=alias)


def _iter_signal_tree(signal: SignalConfig):
    yield signal
    for child in signal.signals:
        yield from _iter_signal_tree(child)


def _signal_uses_factor_data(signal: SignalConfig) -> bool:
    return any(node.type == "factor_threshold" for node in _iter_signal_tree(signal))


def _parse_signal(raw: Any, *, field_name: str) -> SignalConfig:
    payload = _as_mapping(raw, field_name=field_name)
    signal_type = _require_non_empty_text(payload.get("type"), field_name=f"{field_name}.type")
    if signal_type not in DEFAULT_SIGNAL_NAMES:
        raise ValueError(f"{field_name}.type 不支持: {signal_type}")

    name = _normalize_scalar_text(payload.get("name")) or DEFAULT_SIGNAL_NAMES[signal_type]
    params = _normalize_params(
        DEFAULT_SIGNAL_PARAMS[signal_type],
        payload.get("params"),
        field_name=f"{field_name}.params",
    )

    weights: tuple[float, ...] | None = None
    child_signals: tuple[SignalConfig, ...] = ()
    if signal_type == "combined":
        raw_weights = payload.get("weights")
        if raw_weights is not None:
            if not isinstance(raw_weights, list):
                raise ValueError(f"{field_name}.weights 必须是数组")
            weights = tuple(float(item) for item in raw_weights)
        raw_children = _as_list(payload.get("signals"), field_name=f"{field_name}.signals")
        if not raw_children:
            raise ValueError(f"{field_name}.signals 不能为空")
        child_signals = tuple(
            _parse_signal(child, field_name=f"{field_name}.signals[{index}]")
            for index, child in enumerate(raw_children)
        )
    return SignalConfig(
        type=signal_type,  # type: ignore[arg-type]
        name=name,
        params=params,
        weights=weights,
        signals=child_signals,
    )


def _parse_position_mapper(raw: Any, *, field_name: str) -> PositionMapperConfig:
    payload = _as_mapping(raw, field_name=field_name)
    mapper_type = _require_non_empty_text(payload.get("type"), field_name=f"{field_name}.type")
    if mapper_type not in DEFAULT_MAPPER_NAMES:
        raise ValueError(f"{field_name}.type 不支持: {mapper_type}")
    name = _normalize_scalar_text(payload.get("name")) or DEFAULT_MAPPER_NAMES[mapper_type]
    params = _normalize_params(
        DEFAULT_MAPPER_PARAMS[mapper_type],
        payload.get("params"),
        field_name=f"{field_name}.params",
    )
    return PositionMapperConfig(type=mapper_type, name=name, params=params)  # type: ignore[arg-type]


def _validate_market_data_config(config: MarketDataConfig) -> None:
    if config.mode not in {"data_root", "source_path", "mock", "aggregate_bars_daily_summary"}:
        raise ValueError(f"market_data.mode 不支持: {config.mode}")
    if config.freq not in {"1d", "1min"}:
        raise ValueError("market_data.freq 只能是 1d 或 1min")
    if config.mode == "data_root":
        if not config.data_root:
            raise ValueError("market_data.mode=data_root 时 data_root 不能为空")
        path = Path(config.data_root)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"market_data.data_root 不存在或不是目录: {config.data_root}")
    if config.mode == "source_path":
        if not config.source_path:
            raise ValueError("market_data.mode=source_path 时 source_path 不能为空")
        path = Path(config.source_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"market_data.source_path 不存在或不是文件: {config.source_path}")
    if config.mode == "aggregate_bars_daily_summary":
        if config.freq != "1d":
            raise ValueError("aggregate_bars_daily_summary 目前只支持 1d")
        if not config.aggregate_bars_root:
            raise ValueError("market_data.mode=aggregate_bars_daily_summary 时 aggregate_bars_root 不能为空")
        root = Path(config.aggregate_bars_root)
        if not root.exists() or not root.is_dir():
            raise ValueError(
                f"market_data.aggregate_bars_root 不存在或不是目录: {config.aggregate_bars_root}"
            )
        dataset = str(config.aggregate_dataset).strip()
        if not dataset:
            raise ValueError("market_data.aggregate_dataset 不能为空")
        dataset_dir = root / dataset
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            raise ValueError(
                f"aggregate dataset 目录不存在或不是目录: {dataset_dir}"
            )
        if not str(config.aggregate_symbol_column).strip():
            raise ValueError("market_data.aggregate_symbol_column 不能为空")
        if not str(config.aggregate_timestamp_column).strip():
            raise ValueError("market_data.aggregate_timestamp_column 不能为空")
        required_columns = {"open", "high", "low", "close", "volume"}
        missing = required_columns - set(config.aggregate_columns)
        if missing:
            raise ValueError(
                f"market_data.aggregate_columns 缺少必要映射: {sorted(missing)}"
            )
        for field_name in required_columns:
            if not str(config.aggregate_columns[field_name]).strip():
                raise ValueError(f"market_data.aggregate_columns.{field_name} 不能为空")
    if config.cache_root is not None:
        cache_root = Path(config.cache_root)
        if cache_root.exists() and not cache_root.is_dir():
            raise ValueError(f"market_data.cache_root 必须是目录路径: {config.cache_root}")
    if config.mode == "mock" and config.mock_periods <= 0:
        raise ValueError("market_data.mock_periods 必须大于 0")
    if config.start_date and config.end_date and pd.Timestamp(config.start_date) > pd.Timestamp(config.end_date):
        raise ValueError("market_data.start_date 不能晚于 market_data.end_date")


def _validate_factor_source_config(config: FactorSourceConfig) -> None:
    if config.mode not in {"none", "factor_lake", "source_path", "legacy_factor_root"}:
        raise ValueError(f"factor_source.mode 不支持: {config.mode}")
    if config.factor_lake_align_method not in {"outer", "inner", "asof_backward", "forward_fill"}:
        raise ValueError("factor_source.factor_lake_align_method 不支持")
    if config.mode == "factor_lake":
        if not config.factor_lake_root:
            raise ValueError("factor_source.mode=factor_lake 时 factor_lake_root 不能为空")
        path = Path(config.factor_lake_root)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"factor_source.factor_lake_root 不存在或不是目录: {config.factor_lake_root}")
    if config.mode == "source_path":
        if not config.source_path:
            raise ValueError("factor_source.mode=source_path 时 source_path 不能为空")
        path = Path(config.source_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"factor_source.source_path 不存在或不是文件: {config.source_path}")
    if config.mode == "legacy_factor_root":
        if not config.factor_root:
            raise ValueError("factor_source.mode=legacy_factor_root 时 factor_root 不能为空")
        path = Path(config.factor_root)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"factor_source.factor_root 不存在或不是目录: {config.factor_root}")

    factor_ref_names = [ref.name for ref in config.factor_refs]
    if len(set(factor_ref_names)) != len(factor_ref_names):
        raise ValueError("factor_source.factor_refs 中存在重复 alias/factor_id 输出名")


def _validate_signal_config(signal: SignalConfig, factor_source: FactorSourceConfig) -> None:
    if signal.type == "dual_ma":
        if int(signal.params["fast_window"]) <= 0 or int(signal.params["slow_window"]) <= 0:
            raise ValueError("dual_ma 的 fast_window/slow_window 必须为正整数")
        if int(signal.params["slow_window"]) <= int(signal.params["fast_window"]):
            raise ValueError("dual_ma.slow_window 必须大于 fast_window")
        if signal.params["ma_type"] not in {"sma", "ema"}:
            raise ValueError("dual_ma.ma_type 只能是 sma 或 ema")

    if signal.type == "macd":
        if int(signal.params["fast_period"]) <= 0 or int(signal.params["slow_period"]) <= 0:
            raise ValueError("macd 的 fast_period/slow_period 必须为正整数")
        if int(signal.params["slow_period"]) <= int(signal.params["fast_period"]):
            raise ValueError("macd.slow_period 必须大于 fast_period")
        if int(signal.params["signal_period"]) <= 0:
            raise ValueError("macd.signal_period 必须为正整数")

    if signal.type == "rsi":
        if int(signal.params["rsi_period"]) <= 0:
            raise ValueError("rsi.rsi_period 必须为正整数")
        overbought = float(signal.params["overbought"])
        oversold = float(signal.params["oversold"])
        if oversold >= overbought:
            raise ValueError("rsi.oversold 必须小于 overbought")

    if signal.type == "factor_threshold":
        factor_names = signal.params.get("factor_names")
        if factor_names is not None:
            if not isinstance(factor_names, list) or not all(isinstance(name, str) and name.strip() for name in factor_names):
                raise ValueError("factor_threshold.factor_names 必须是非空字符串数组")
        factor_weights = signal.params.get("factor_weights") or {}
        if not isinstance(factor_weights, dict):
            raise ValueError("factor_threshold.factor_weights 必须是 object")
        if factor_weights:
            scale = sum(abs(float(value)) for value in factor_weights.values())
            if scale <= 1e-12:
                raise ValueError("factor_threshold.factor_weights 的绝对值和必须大于 0")
        if int(signal.params["zscore_window"]) <= 0:
            raise ValueError("factor_threshold.zscore_window 必须为正整数")

    if signal.type == "combined":
        if not signal.signals:
            raise ValueError("combined.signals 不能为空")
        if signal.weights is not None:
            if len(signal.weights) != len(signal.signals):
                raise ValueError("combined.weights 长度必须与 signals 一致")
            if sum(abs(weight) for weight in signal.weights) <= 1e-12:
                raise ValueError("combined.weights 绝对值和必须大于 0")
        if signal.params.get("combine_method") not in {"weighted_avg", "rank_avg"}:
            raise ValueError("combined.combine_method 只能是 weighted_avg 或 rank_avg")
        for child in signal.signals:
            _validate_signal_config(child, factor_source)

    if _signal_uses_factor_data(signal):
        if factor_source.mode == "none":
            raise ValueError("signal 使用 factor_threshold 时，factor_source.mode 不能为 none")
        if factor_source.mode == "factor_lake":
            factor_ref_names = {ref.name for ref in factor_source.factor_refs}
            aliased_refs = any(ref.alias is not None for ref in factor_source.factor_refs)
            for node in _iter_signal_tree(signal):
                if node.type != "factor_threshold":
                    continue
                factor_names = node.params.get("factor_names")
                if not factor_ref_names and not factor_names:
                    raise ValueError(
                        "factor_lake 模式下，若未配置 factor_refs，则 factor_threshold.factor_names 不能为空"
                    )
                if aliased_refs and factor_names:
                    missing = sorted(set(factor_names) - factor_ref_names)
                    if missing:
                        raise ValueError(
                            "factor_threshold.factor_names 必须引用 factor_refs 中配置的 alias/name: "
                            f"{missing}"
                        )


def _validate_position_mapper_config(config: PositionMapperConfig) -> None:
    if config.type == "threshold":
        if float(config.params["long_entry_threshold"]) <= float(config.params["long_exit_threshold"]):
            raise ValueError("threshold.long_entry_threshold 应大于 long_exit_threshold")
        if float(config.params["position_size"]) <= 0:
            raise ValueError("threshold.position_size 必须大于 0")
        if int(config.params["shift_bars"]) < 0:
            raise ValueError("threshold.shift_bars 不能小于 0")
    elif config.type == "atr_volatility":
        if int(config.params["atr_period"]) <= 0:
            raise ValueError("atr_volatility.atr_period 必须为正整数")
        if float(config.params["base_long_threshold"]) <= 0:
            raise ValueError("atr_volatility.base_long_threshold 必须大于 0")
        if float(config.params["base_short_threshold"]) >= 0:
            raise ValueError("atr_volatility.base_short_threshold 必须小于 0")
        exit_buffer = float(config.params["exit_buffer_ratio"])
        if not (0 < exit_buffer < 1):
            raise ValueError("atr_volatility.exit_buffer_ratio 必须在 (0,1) 之间")
        if float(config.params["target_volatility"]) <= 0:
            raise ValueError("atr_volatility.target_volatility 必须大于 0")
        min_position = float(config.params["min_position"])
        max_position = float(config.params["max_position"])
        if not (0 <= min_position <= max_position <= 1.0):
            raise ValueError("atr_volatility 要满足 0 <= min_position <= max_position <= 1")
        if int(config.params["shift_bars"]) < 0:
            raise ValueError("atr_volatility.shift_bars 不能小于 0")


def _validate_run_config(config: RunConfig) -> None:
    if config.start_date and config.end_date and pd.Timestamp(config.start_date) > pd.Timestamp(config.end_date):
        raise ValueError("run.start_date 不能晚于 run.end_date")


def _validate_output_config(config: OutputConfig) -> None:
    if config.output_format not in {"parquet", "csv"}:
        raise ValueError("output.output_format 只能是 parquet 或 csv")
    if not str(config.output_dir).strip():
        raise ValueError("output.output_dir 不能为空")


def load_config(path: str | Path) -> SingleAssetAlphaConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("配置文件顶层必须是 object")

    base_dir = config_path.resolve().parent
    meta_payload = _as_mapping(payload.get("meta"), field_name="meta")
    instrument_payload = _as_mapping(payload.get("instrument"), field_name="instrument")
    market_payload = _as_mapping(payload.get("market_data"), field_name="market_data")
    factor_payload = _as_mapping(payload.get("factor_source"), field_name="factor_source")
    run_payload = _as_mapping(payload.get("run"), field_name="run")
    output_payload = _as_mapping(payload.get("output"), field_name="output")

    meta = MetaConfig(
        strategy_id=_require_non_empty_text(meta_payload.get("strategy_id"), field_name="meta.strategy_id"),
        version=_normalize_scalar_text(meta_payload.get("version")) or "v1",
        description=_normalize_scalar_text(meta_payload.get("description")),
    )
    instrument = InstrumentConfig(
        symbol=_require_non_empty_text(instrument_payload.get("symbol"), field_name="instrument.symbol")
    )

    market_data = MarketDataConfig(
        mode=_require_non_empty_text(market_payload.get("mode"), field_name="market_data.mode"),  # type: ignore[arg-type]
        data_root=_resolve_path_text(market_payload.get("data_root"), field_name="market_data.data_root", base_dir=base_dir),
        source_path=_resolve_path_text(market_payload.get("source_path"), field_name="market_data.source_path", base_dir=base_dir),
        freq=_normalize_scalar_text(market_payload.get("freq")) or "1d",
        start_date=_normalize_scalar_text(market_payload.get("start_date")),
        end_date=_normalize_scalar_text(market_payload.get("end_date")),
        cache_root=_resolve_path_text(market_payload.get("cache_root"), field_name="market_data.cache_root", base_dir=base_dir),
        mock_periods=int(market_payload.get("mock_periods", 500)),
        mock_start_date=_normalize_scalar_text(market_payload.get("mock_start_date")) or "2023-01-01",
        mock_seed=int(market_payload.get("mock_seed", 42)),
        aggregate_bars_root=_resolve_path_text(
            market_payload.get("aggregate_bars_root"),
            field_name="market_data.aggregate_bars_root",
            base_dir=base_dir,
        ),
        aggregate_dataset=_normalize_scalar_text(market_payload.get("aggregate_dataset")) or "daily_market_summary",
        aggregate_symbol_column=_normalize_scalar_text(market_payload.get("aggregate_symbol_column")) or "ticker",
        aggregate_timestamp_column=_normalize_scalar_text(market_payload.get("aggregate_timestamp_column")) or "align_time",
        aggregate_columns={
            **DEFAULT_AGGREGATE_COLUMNS,
            **{
                str(key): str(value)
                for key, value in _as_mapping(
                    market_payload.get("aggregate_columns"),
                    field_name="market_data.aggregate_columns",
                ).items()
            },
        },
    )

    factor_source = FactorSourceConfig(
        mode=_normalize_scalar_text(factor_payload.get("mode")) or "none",  # type: ignore[arg-type]
        factor_lake_root=_resolve_path_text(
            factor_payload.get("factor_lake_root"),
            field_name="factor_source.factor_lake_root",
            base_dir=base_dir,
        ),
        source_path=_resolve_path_text(
            factor_payload.get("source_path"),
            field_name="factor_source.source_path",
            base_dir=base_dir,
        ),
        factor_root=_resolve_path_text(
            factor_payload.get("factor_root"),
            field_name="factor_source.factor_root",
            base_dir=base_dir,
        ),
        factor_lake_align_method=_normalize_scalar_text(factor_payload.get("factor_lake_align_method")) or "outer",  # type: ignore[arg-type]
        factor_refs=tuple(
            _parse_factor_ref(item, field_name=f"factor_source.factor_refs[{index}]")
            for index, item in enumerate(_as_list(factor_payload.get("factor_refs"), field_name="factor_source.factor_refs"))
        ),
    )

    signal = _parse_signal(payload.get("signal"), field_name="signal")
    position_mapper = _parse_position_mapper(payload.get("position_mapper"), field_name="position_mapper")
    run = RunConfig(
        start_date=_normalize_scalar_text(run_payload.get("start_date")),
        end_date=_normalize_scalar_text(run_payload.get("end_date")),
    )
    output = OutputConfig(
        output_dir=_resolve_path_text(output_payload.get("output_dir") or "outputs", field_name="output.output_dir", base_dir=base_dir) or str((base_dir / "outputs").resolve()),
        output_format=_normalize_scalar_text(output_payload.get("output_format")) or "parquet",  # type: ignore[arg-type]
        save_full_timeseries=bool(output_payload.get("save_full_timeseries", True)),
        save_debounced=bool(output_payload.get("save_debounced", True)),
    )

    config = SingleAssetAlphaConfig(
        meta=meta,
        instrument=instrument,
        market_data=market_data,
        factor_source=factor_source,
        signal=signal,
        position_mapper=position_mapper,
        run=run,
        output=output,
    )

    _validate_market_data_config(config.market_data)
    _validate_factor_source_config(config.factor_source)
    _validate_signal_config(config.signal, config.factor_source)
    _validate_position_mapper_config(config.position_mapper)
    _validate_run_config(config.run)
    _validate_output_config(config.output)

    return config
