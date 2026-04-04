from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from strategy_layer.data.contracts import (
    CANONICAL_KEY_COLUMNS,
    CANONICAL_SYMBOL_COLUMN,
    CANONICAL_TIMESTAMP_COLUMN,
    FACTOR_VALUE_COLUMN,
    AlignMethod,
    FactorRef,
    validate_canonical_panel,
    validate_factor_long,
)


def _extract_partition_year(path: Path) -> int | None:
    for part in reversed(path.parts):
        if part.startswith("year="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return None
    stem = path.stem
    if len(stem) >= 4 and stem[:4].isdigit():
        return int(stem[:4])
    return None


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


def _normalize_symbols(symbols: Iterable[str] | None) -> tuple[str, ...] | None:
    if symbols is None:
        return None
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        text = str(symbol).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _collect_factor_paths(
    factor_root: Path,
    *,
    start: object | None,
    end: object | None,
) -> list[Path]:
    if not factor_root.exists():
        return []

    start_year = _boundary_year(start, 0)
    end_year = _boundary_year(end, 9999)
    paths: list[Path] = []
    for child in sorted(factor_root.iterdir()):
        if child.is_dir() and child.name.startswith("year="):
            year = _extract_partition_year(child)
            if year is None or not (start_year <= year <= end_year):
                continue
            parquet_path = child / "data.parquet"
            if parquet_path.exists():
                paths.append(parquet_path)
        elif child.is_file() and child.name == "data.parquet":
            paths.append(child)
    return sorted(paths)


def _read_factor_partition(path: Path, *, symbols: tuple[str, ...] | None) -> pd.DataFrame:
    columns = ["datetime", "asset", "value"]
    frame: pd.DataFrame
    if symbols:
        try:
            frame = pd.read_parquet(
                path,
                columns=columns,
                filters=[("asset", "in", list(symbols))],
            )
        except Exception:
            frame = pd.read_parquet(path, columns=columns)
    else:
        frame = pd.read_parquet(path, columns=columns)

    if symbols:
        symbol_set = set(symbols)
        frame = frame.loc[
            frame["asset"].astype("string").str.strip().isin(symbol_set)
        ].copy()
    return frame


def _merge_asof_by_symbol(base: pd.DataFrame, other: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    if base.empty:
        return base.copy()
    if other.empty:
        out = base.copy()
        for column in value_columns:
            out[column] = pd.NA
        return out

    pieces: list[pd.DataFrame] = []
    for symbol, base_group in base.groupby(CANONICAL_SYMBOL_COLUMN, sort=False):
        base_group = base_group.sort_values(CANONICAL_TIMESTAMP_COLUMN)
        other_group = other.loc[
            other[CANONICAL_SYMBOL_COLUMN] == symbol
        ].sort_values(CANONICAL_TIMESTAMP_COLUMN)
        merged = pd.merge_asof(
            base_group,
            other_group[[CANONICAL_TIMESTAMP_COLUMN, *value_columns]],
            on=CANONICAL_TIMESTAMP_COLUMN,
            direction="backward",
            allow_exact_matches=True,
        )
        merged[CANONICAL_SYMBOL_COLUMN] = symbol
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def load_factor_long(
    lake_root: str | Path,
    factor_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    factor_root = Path(lake_root) / "factors" / factor_id
    if not factor_root.exists():
        raise FileNotFoundError(f"No factor parquet found for {factor_id}")

    normalized_symbols = _normalize_symbols(symbols)
    paths = _collect_factor_paths(factor_root, start=start, end=end)
    if not paths:
        raise FileNotFoundError(f"No factor parquet found for {factor_id}")

    frame = pd.concat(
        [_read_factor_partition(path, symbols=normalized_symbols) for path in paths],
        ignore_index=True,
    )
    frame = frame.rename(
        columns={
            "datetime": CANONICAL_TIMESTAMP_COLUMN,
            "asset": CANONICAL_SYMBOL_COLUMN,
        }
    )
    frame = validate_factor_long(frame)

    if start is not None:
        frame = frame.loc[
            frame[CANONICAL_TIMESTAMP_COLUMN] >= pd.Timestamp(start)
        ].copy()
    if end is not None:
        frame = frame.loc[
            frame[CANONICAL_TIMESTAMP_COLUMN] <= pd.Timestamp(end)
        ].copy()
    if normalized_symbols:
        frame = frame.loc[
            frame[CANONICAL_SYMBOL_COLUMN].isin(normalized_symbols)
        ].copy()

    return frame.reset_index(drop=True)


def build_factor_panel(
    lake_root: str | Path,
    factors: Sequence[FactorRef],
    *,
    start: str | None = None,
    end: str | None = None,
    symbols: Iterable[str] | None = None,
    align_method: AlignMethod = "outer",
    anchor_factor: str | None = None,
) -> pd.DataFrame:
    if not factors:
        raise ValueError("factors 不能为空")

    factor_by_name = {factor.name: factor for factor in factors}
    if len(factor_by_name) != len(factors):
        raise ValueError("factors 中存在重复列名")

    if align_method not in {"outer", "inner", "asof_backward", "forward_fill"}:
        raise ValueError(f"Unsupported align_method: {align_method}")

    normalized_symbols = _normalize_symbols(symbols)

    if align_method == "asof_backward":
        anchor_name = anchor_factor or factors[0].name
        if anchor_name not in factor_by_name:
            raise ValueError(f"anchor_factor '{anchor_name}' 不在 factors 中")

        anchor_ref = factor_by_name[anchor_name]
        panel = load_factor_long(
            lake_root,
            anchor_ref.factor_id,
            start=start,
            end=end,
            symbols=normalized_symbols,
        ).rename(columns={FACTOR_VALUE_COLUMN: anchor_ref.name})

        for factor in factors:
            if factor.name == anchor_ref.name:
                continue
            other = load_factor_long(
                lake_root,
                factor.factor_id,
                start=start,
                end=end,
                symbols=normalized_symbols,
            ).rename(columns={FACTOR_VALUE_COLUMN: factor.name})
            aligned = _merge_asof_by_symbol(
                panel[list(CANONICAL_KEY_COLUMNS)],
                other,
                [factor.name],
            )
            panel = panel.merge(aligned, on=list(CANONICAL_KEY_COLUMNS), how="left")
        return validate_canonical_panel(panel)

    merged = load_factor_long(
        lake_root,
        factors[0].factor_id,
        start=start,
        end=end,
        symbols=normalized_symbols,
    ).rename(columns={FACTOR_VALUE_COLUMN: factors[0].name})

    merge_how = "outer" if align_method in {"outer", "forward_fill"} else "inner"
    for factor in factors[1:]:
        other = load_factor_long(
            lake_root,
            factor.factor_id,
            start=start,
            end=end,
            symbols=normalized_symbols,
        ).rename(columns={FACTOR_VALUE_COLUMN: factor.name})
        merged = merged.merge(other, on=list(CANONICAL_KEY_COLUMNS), how=merge_how)

    merged = validate_canonical_panel(merged)
    if align_method == "forward_fill":
        factor_columns = [factor.name for factor in factors]
        merged = merged.sort_values([CANONICAL_SYMBOL_COLUMN, CANONICAL_TIMESTAMP_COLUMN]).reset_index(drop=True)
        for column in factor_columns:
            merged[column] = merged.groupby(CANONICAL_SYMBOL_COLUMN)[column].ffill()
        merged = validate_canonical_panel(merged)
    return merged


def project_single_asset(panel: pd.DataFrame, symbol: str) -> pd.DataFrame:
    normalized_panel = validate_canonical_panel(panel)
    target_symbol = str(symbol).strip()
    single_asset = normalized_panel.loc[
        normalized_panel[CANONICAL_SYMBOL_COLUMN] == target_symbol
    ].copy()
    factor_columns = [
        column
        for column in normalized_panel.columns
        if column not in CANONICAL_KEY_COLUMNS
    ]
    if single_asset.empty:
        empty = pd.DataFrame(columns=factor_columns)
        empty.index = pd.DatetimeIndex([], name=CANONICAL_TIMESTAMP_COLUMN)
        return empty

    if single_asset[CANONICAL_TIMESTAMP_COLUMN].duplicated().any():
        raise ValueError(f"单标的视图存在重复 timestamp: symbol={target_symbol}")

    single_asset = single_asset.sort_values(CANONICAL_TIMESTAMP_COLUMN).set_index(CANONICAL_TIMESTAMP_COLUMN)
    single_asset.index.name = CANONICAL_TIMESTAMP_COLUMN
    return single_asset[factor_columns]