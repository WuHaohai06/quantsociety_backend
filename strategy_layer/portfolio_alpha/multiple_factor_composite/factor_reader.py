from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from strategy_layer.data import FactorRef, build_factor_panel, load_factor_long
from strategy_layer.portfolio_alpha.multiple_factor_composite.composite_config import AuxiliarySourceConfig, FactorSpec


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


def _collect_parquet_paths(
    root: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    recursive: bool = True,
) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []

    iterator: Iterable[Path]
    iterator = root.rglob("*.parquet") if recursive else root.glob("*.parquet")
    start_year = _boundary_year(start, 0)
    end_year = _boundary_year(end, 9999)

    paths = []
    for path in iterator:
        if not path.is_file():
            continue
        year = _extract_partition_year(path)
        if year is None or start_year <= year <= end_year:
            paths.append(path)
    return sorted(paths)


def _merge_asof_by_symbol(base: pd.DataFrame, other: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    if base.empty:
        return base.copy()
    if other.empty:
        out = base.copy()
        for column in value_columns:
            out[column] = pd.NA
        return out

    pieces: list[pd.DataFrame] = []
    for symbol, base_group in base.groupby("symbol", sort=False):
        base_group = base_group.sort_values("timestamp")
        other_group = other.loc[other["symbol"] == symbol].sort_values("timestamp")
        merged = pd.merge_asof(
            base_group,
            other_group[["timestamp", *value_columns]],
            on="timestamp",
            direction="backward",
            allow_exact_matches=True,
        )
        merged["symbol"] = symbol
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


class FactorLakeReader:
    """portfolio_alpha factor lake 读取器。

    内外统一使用 strategy_layer.data 的 canonical `timestamp/symbol` 命名。
    """

    def __init__(self, lake_root: str | Path) -> None:
        self.lake_root = Path(lake_root)

    def load_factor(
        self,
        factor_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
        symbols: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        frame = load_factor_long(
            self.lake_root,
            factor_id,
            start=start,
            end=end,
            symbols=symbols,
        )
        return frame[["timestamp", "symbol", "value"]].sort_values(
            ["symbol", "timestamp"]
        ).reset_index(drop=True)

    def load_factors(
        self,
        factors: list[FactorSpec],
        *,
        start: str | None = None,
        end: str | None = None,
        align_method: str = "outer",
        anchor_factor: str | None = None,
        symbols: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        if not factors:
            raise ValueError("factors 不能为空")

        refs = [FactorRef(factor_id=factor.factor_id, column_name=factor.name) for factor in factors]
        panel = build_factor_panel(
            self.lake_root,
            refs,
            start=start,
            end=end,
            symbols=symbols,
            align_method=align_method,
            anchor_factor=anchor_factor,
        )
        return panel.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


class AuxiliaryParquetLoader:
    """独立辅助数据读取器，用于控制变量、股票池、标签等。"""

    def load(self, spec: AuxiliarySourceConfig, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        root = Path(spec.path)
        paths = _collect_parquet_paths(root, start=start, end=end, recursive=spec.recursive)
        if not paths:
            raise FileNotFoundError(f"No parquet files found for auxiliary source '{spec.name}'")

        frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        frame["timestamp"] = pd.to_datetime(frame[spec.timestamp_col], errors="coerce")
        frame["symbol"] = frame[spec.symbol_col].astype("string").str.strip()
        selected_columns = {alias: source for alias, source in spec.columns.items()}
        normalized = pd.DataFrame(
            {
                "timestamp": frame["timestamp"],
                "symbol": frame["symbol"],
            }
        )
        for alias, source in selected_columns.items():
            normalized[alias] = frame[source]
        normalized = normalized[
            normalized["timestamp"].notna() & normalized["symbol"].notna()
        ].copy()
        if start:
            normalized = normalized[normalized["timestamp"] >= pd.Timestamp(start)]
        if end:
            normalized = normalized[normalized["timestamp"] <= pd.Timestamp(end)]
        normalized = normalized.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return normalized


def align_auxiliary_to_panel(
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    *,
    method: str,
) -> pd.DataFrame:
    panel_keys = panel[["timestamp", "symbol"]].drop_duplicates().sort_values(
        ["symbol", "timestamp"]
    )
    value_columns = [column for column in auxiliary.columns if column not in {"timestamp", "symbol"}]
    if method == "exact":
        aligned = panel_keys.merge(auxiliary, on=["timestamp", "symbol"], how="left")
    elif method == "forward_fill":
        aligned = panel_keys.merge(auxiliary, on=["timestamp", "symbol"], how="left")
        aligned = aligned.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        for column in value_columns:
            aligned[column] = aligned.groupby("symbol")[column].ffill()
    elif method == "asof_backward":
        aligned = _merge_asof_by_symbol(panel_keys, auxiliary, value_columns)
    else:
        raise ValueError(f"Unsupported auxiliary align method: {method}")
    return panel.merge(aligned, on=["timestamp", "symbol"], how="left")