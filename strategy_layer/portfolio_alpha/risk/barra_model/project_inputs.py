from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from strategy_layer.data import FactorRef, build_factor_panel

DEFAULT_MARKET_DATASET = "daily_market_summary"
DEFAULT_FLOATS_DATASET = "stocks_floats"
DEFAULT_FLOAT_COLUMNS = ("stock_float", "free_float", "outstanding_shares")


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _normalize_asset(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.upper()
    return normalized.where(normalized.notna() & (normalized != ""), pd.NA)


def _boundary_year(value: object | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(pd.Timestamp(value).year)
    except Exception:
        text = str(value)
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
        return default


def _resolve_root(root: str | Path, dataset: str | None = None) -> Path:
    base = Path(root)
    if dataset is not None and (base / dataset).exists():
        return base / dataset
    return base


def _collect_parquet_paths(root: Path, *, start: str | None = None, end: str | None = None) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []

    start_year = _boundary_year(start, 0)
    end_year = _boundary_year(end, 9999)
    paths: list[Path] = []
    for path in root.rglob("*.parquet"):
        if not path.is_file():
            continue
        year = None
        for part in reversed(path.parts):
            if part.startswith("year="):
                try:
                    year = int(part.split("=", 1)[1])
                except ValueError:
                    year = None
                break
        if year is None:
            stem = path.stem
            if len(stem) >= 4 and stem[:4].isdigit():
                year = int(stem[:4])
        if year is None or start_year <= year <= end_year:
            paths.append(path)
    return sorted(paths)


def _load_parquet_frame(root: str | Path, *, dataset: str | None = None, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    source_root = _resolve_root(root, dataset)
    paths = _collect_parquet_paths(source_root, start=start, end=end)
    if not paths:
        raise FileNotFoundError(f"No parquet files found under {source_root}")
    return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)


def _normalize_factor_refs(factor_refs: Sequence[FactorRef | str]) -> list[FactorRef]:
    refs: list[FactorRef] = []
    for item in factor_refs:
        if isinstance(item, FactorRef):
            refs.append(item)
            continue

        text = str(item).strip()
        if not text:
            continue
        if ":" in text:
            factor_id, alias = text.split(":", 1)
            factor_id = factor_id.strip()
            alias = alias.strip()
            refs.append(FactorRef(factor_id=factor_id, column_name=alias or None))
        else:
            refs.append(FactorRef(factor_id=text, column_name=text))
    if not refs:
        raise ValueError("factor_refs 不能为空")
    return refs


def build_project_factor_frame(
    *,
    factor_lake_root: str | Path,
    factor_refs: Sequence[FactorRef | str],
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
    align_method: str = "outer",
    anchor_factor: str | None = None,
) -> pd.DataFrame:
    refs = _normalize_factor_refs(factor_refs)
    panel = build_factor_panel(
        factor_lake_root,
        refs,
        start=start,
        end=end,
        symbols=symbols,
        align_method=align_method,
        anchor_factor=anchor_factor,
    ).rename(columns={"timestamp": "datetime", "symbol": "asset"})

    factor_columns = [ref.name for ref in refs]
    frame = panel.loc[:, ["datetime", "asset", *factor_columns]].copy()
    frame["datetime"] = _normalize_timestamp(frame["datetime"])
    frame["asset"] = _normalize_asset(frame["asset"])
    frame = frame.dropna(subset=["datetime", "asset"]).copy()
    frame = frame.sort_values(["datetime", "asset"], kind="stable", ignore_index=True)
    return frame


def load_project_market_frame(
    *,
    aggregate_bars_root: str | Path,
    dataset: str = DEFAULT_MARKET_DATASET,
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
    timestamp_column: str = "align_time",
    symbol_column: str = "ticker",
    close_column: str = "c",
) -> pd.DataFrame:
    frame = _load_parquet_frame(aggregate_bars_root, dataset=dataset, start=start, end=end)
    if timestamp_column not in frame.columns:
        raise KeyError(f"Market table missing required column: {timestamp_column}")
    if symbol_column not in frame.columns:
        raise KeyError(f"Market table missing required column: {symbol_column}")

    close_source = close_column if close_column in frame.columns else "close" if "close" in frame.columns else None
    if close_source is None:
        raise KeyError(f"Market table missing required close column: {close_column}")

    normalized = pd.DataFrame(
        {
            "align_time": _normalize_timestamp(frame[timestamp_column]),
            "ticker": _normalize_asset(frame[symbol_column]),
            "c": pd.to_numeric(frame[close_source], errors="coerce").astype("float32"),
        }
    )
    normalized = normalized.dropna(subset=["align_time", "ticker", "c"]).copy()
    if symbols is not None:
        symbol_set = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        normalized = normalized.loc[normalized["ticker"].isin(symbol_set)].copy()
    normalized = normalized.sort_values(["ticker", "align_time"], kind="stable", ignore_index=True)
    normalized = normalized.drop_duplicates(subset=["ticker", "align_time"], keep="last", ignore_index=True)
    return normalized


def load_project_floats_frame(
    *,
    stocks_floats_root: str | Path,
    dataset: str = DEFAULT_FLOATS_DATASET,
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
    timestamp_column: str = "effective_date",
    symbol_column: str = "ticker",
    float_column: str | None = None,
) -> pd.DataFrame:
    frame = _load_parquet_frame(stocks_floats_root, dataset=dataset, start=start, end=end)
    if timestamp_column not in frame.columns:
        raise KeyError(f"Stocks floats table missing required column: {timestamp_column}")
    if symbol_column not in frame.columns:
        raise KeyError(f"Stocks floats table missing required column: {symbol_column}")

    if float_column is not None:
        candidates = [float_column]
    else:
        candidates = list(DEFAULT_FLOAT_COLUMNS)
    chosen_column = next((column for column in candidates if column in frame.columns), None)
    if chosen_column is None:
        raise KeyError(
            "Stocks floats table missing quantity column. Expected one of: " + ", ".join(candidates)
        )

    normalized = pd.DataFrame(
        {
            "datetime": _normalize_timestamp(frame[timestamp_column]),
            "asset": _normalize_asset(frame[symbol_column]),
            "stock_float": pd.to_numeric(frame[chosen_column], errors="coerce").astype("float32"),
        }
    )
    normalized = normalized.dropna(subset=["datetime", "asset", "stock_float"]).copy()
    if symbols is not None:
        symbol_set = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        normalized = normalized.loc[normalized["asset"].isin(symbol_set)].copy()
    normalized = normalized.sort_values(["asset", "datetime"], kind="stable", ignore_index=True)
    normalized = normalized.drop_duplicates(subset=["asset", "datetime"], keep="last", ignore_index=True)
    return normalized


def build_market_cap_frame(
    market_frame: pd.DataFrame,
    floats_frame: pd.DataFrame,
) -> pd.DataFrame:
    required_market = {"align_time", "ticker", "c"}
    required_floats = {"datetime", "asset", "stock_float"}
    missing_market = sorted(required_market - set(market_frame.columns))
    missing_floats = sorted(required_floats - set(floats_frame.columns))
    if missing_market:
        raise KeyError(f"Market frame missing required columns: {missing_market}")
    if missing_floats:
        raise KeyError(f"Floats frame missing required columns: {missing_floats}")

    market = market_frame.copy()
    market["align_time"] = _normalize_timestamp(market["align_time"])
    market["ticker"] = _normalize_asset(market["ticker"])
    market["date"] = market["align_time"].dt.normalize()
    market["c"] = pd.to_numeric(market["c"], errors="coerce").astype("float32")
    market = market.dropna(subset=["date", "ticker", "c"]).copy()
    market = market.sort_values(["ticker", "date"], kind="stable", ignore_index=True)
    market = market.drop_duplicates(subset=["ticker", "date"], keep="last", ignore_index=True)

    floats = floats_frame.copy()
    floats["datetime"] = _normalize_timestamp(floats["datetime"])
    floats["asset"] = _normalize_asset(floats["asset"])
    floats["date"] = floats["datetime"].dt.normalize()
    floats["stock_float"] = pd.to_numeric(floats["stock_float"], errors="coerce").astype("float32")
    floats = floats.dropna(subset=["date", "asset", "stock_float"]).copy()
    floats = floats.sort_values(["asset", "date"], kind="stable", ignore_index=True)
    floats = floats.drop_duplicates(subset=["asset", "date"], keep="last", ignore_index=True)

    merged_parts: list[pd.DataFrame] = []
    for ticker, market_group in market.groupby("ticker", sort=False):
        float_group = floats.loc[floats["asset"] == ticker, ["date", "stock_float"]].sort_values("date")
        merged = pd.merge_asof(
            market_group.sort_values("date"),
            float_group,
            on="date",
            direction="backward",
            allow_exact_matches=True,
        )
        merged["asset"] = ticker
        merged_parts.append(merged)

    if not merged_parts:
        return pd.DataFrame(columns=["datetime", "asset", "market_cap"])

    merged_frame = pd.concat(merged_parts, ignore_index=True)
    merged_frame["market_cap"] = (merged_frame["stock_float"] * merged_frame["c"]).astype("float32")
    merged_frame = merged_frame.loc[:, ["date", "asset", "market_cap"]].copy()
    merged_frame["datetime"] = pd.to_datetime(merged_frame["date"], errors="coerce")
    merged_frame = merged_frame.dropna(subset=["datetime", "asset"]).copy()
    merged_frame = merged_frame.loc[:, ["datetime", "asset", "market_cap"]]
    merged_frame = merged_frame.sort_values(["datetime", "asset"], kind="stable", ignore_index=True)
    return merged_frame


def build_project_barra_inputs(
    *,
    factor_lake_root: str | Path,
    factor_refs: Sequence[FactorRef | str],
    aggregate_bars_root: str | Path,
    stocks_floats_root: str | Path,
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
    factor_align_method: str = "outer",
    factor_anchor: str | None = None,
    market_dataset: str = DEFAULT_MARKET_DATASET,
    floats_dataset: str = DEFAULT_FLOATS_DATASET,
    market_timestamp_column: str = "align_time",
    market_symbol_column: str = "ticker",
    market_close_column: str = "c",
    floats_timestamp_column: str = "effective_date",
    floats_symbol_column: str = "ticker",
    floats_column: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factors = build_project_factor_frame(
        factor_lake_root=factor_lake_root,
        factor_refs=factor_refs,
        start=start,
        end=end,
        symbols=symbols,
        align_method=factor_align_method,
        anchor_factor=factor_anchor,
    )
    market = load_project_market_frame(
        aggregate_bars_root=aggregate_bars_root,
        dataset=market_dataset,
        start=start,
        end=end,
        symbols=symbols,
        timestamp_column=market_timestamp_column,
        symbol_column=market_symbol_column,
        close_column=market_close_column,
    )
    floats = load_project_floats_frame(
        stocks_floats_root=stocks_floats_root,
        dataset=floats_dataset,
        start=start,
        end=end,
        symbols=symbols,
        timestamp_column=floats_timestamp_column,
        symbol_column=floats_symbol_column,
        float_column=floats_column,
    )
    market_cap = build_market_cap_frame(market, floats)
    return factors, market, market_cap
