from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

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


def _merge_asof_by_asset(base: pd.DataFrame, other: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    if base.empty:
        return base.copy()
    if other.empty:
        out = base.copy()
        for column in value_columns:
            out[column] = pd.NA
        return out

    pieces: list[pd.DataFrame] = []
    for asset, base_group in base.groupby("asset", sort=False):
        base_group = base_group.sort_values("datetime")
        other_group = other.loc[other["asset"] == asset].sort_values("datetime")
        merged = pd.merge_asof(
            base_group,
            other_group[["datetime", *value_columns]],
            on="datetime",
            direction="backward",
            allow_exact_matches=True,
        )
        merged["asset"] = asset
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


class FactorLakeReader:
    """独立于 factor_engine 的 factor lake 读取器。"""

    def __init__(self, lake_root: str | Path) -> None:
        self.lake_root = Path(lake_root)

    def _factor_paths(self, factor_id: str, start: str | None, end: str | None) -> list[Path]:
        factor_dir = self.lake_root / "factors" / factor_id
        if not factor_dir.exists():
            return []
        paths = []
        for child in sorted(factor_dir.iterdir()):
            if child.is_dir() and child.name.startswith("year="):
                year = _extract_partition_year(child)
                start_year = _boundary_year(start, 0)
                end_year = _boundary_year(end, 9999)
                if year is not None and start_year <= year <= end_year:
                    parquet_path = child / "data.parquet"
                    if parquet_path.exists():
                        paths.append(parquet_path)
            elif child.is_file() and child.name == "data.parquet":
                paths.append(child)
        return sorted(paths)

    def load_factor(
        self,
        factor_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        paths = self._factor_paths(factor_id, start, end)
        if not paths:
            raise FileNotFoundError(f"No factor parquet found for {factor_id}")

        frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
        frame["asset"] = frame["asset"].astype("string").str.strip()
        frame = frame[frame["datetime"].notna() & frame["asset"].notna()].copy()
        if start:
            frame = frame[frame["datetime"] >= pd.Timestamp(start)]
        if end:
            frame = frame[frame["datetime"] <= pd.Timestamp(end)]
        return frame[["datetime", "asset", "value"]].sort_values(
            ["asset", "datetime"]
        ).reset_index(drop=True)

    def load_factors(
        self,
        factors: list[FactorSpec],
        *,
        start: str | None = None,
        end: str | None = None,
        align_method: str = "outer",
        anchor_factor: str | None = None,
    ) -> pd.DataFrame:
        if not factors:
            raise ValueError("factors 不能为空")

        factor_by_name = {factor.name: factor for factor in factors}
        anchor_name = anchor_factor or factors[0].name
        if anchor_name not in factor_by_name:
            raise ValueError(f"anchor_factor '{anchor_name}' 不在 factors 中")

        anchor_spec = factor_by_name[anchor_name]
        base = self.load_factor(anchor_spec.factor_id, start=start, end=end).rename(
            columns={"value": anchor_spec.name}
        )

        if align_method == "asof_backward":
            for factor in factors:
                if factor.name == anchor_spec.name:
                    continue
                other = self.load_factor(factor.factor_id, start=start, end=end).rename(
                    columns={"value": factor.name}
                )
                aligned = _merge_asof_by_asset(base[["datetime", "asset"]], other, [factor.name])
                base = base.merge(aligned, on=["datetime", "asset"], how="left")
            return base.sort_values(["asset", "datetime"]).reset_index(drop=True)

        merged = base
        for factor in factors:
            if factor.name == anchor_spec.name:
                continue
            other = self.load_factor(factor.factor_id, start=start, end=end).rename(
                columns={"value": factor.name}
            )
            merged = merged.merge(other, on=["datetime", "asset"], how="outer")

        merged = merged.sort_values(["asset", "datetime"]).reset_index(drop=True)
        if align_method == "forward_fill":
            factor_columns = [factor.name for factor in factors]
            for column in factor_columns:
                if column in merged.columns:
                    merged[column] = merged.groupby("asset")[column].ffill()
        return merged


class AuxiliaryParquetLoader:
    """独立辅助数据读取器，用于控制变量、股票池、标签等。"""

    def load(self, spec: AuxiliarySourceConfig, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        root = Path(spec.path)
        paths = _collect_parquet_paths(root, start=start, end=end, recursive=spec.recursive)
        if not paths:
            raise FileNotFoundError(f"No parquet files found for auxiliary source '{spec.name}'")

        frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        frame["datetime"] = pd.to_datetime(frame[spec.timestamp_col], errors="coerce")
        frame["asset"] = frame[spec.asset_col].astype("string").str.strip()
        selected_columns = {alias: source for alias, source in spec.columns.items()}
        normalized = pd.DataFrame(
            {
                "datetime": frame["datetime"],
                "asset": frame["asset"],
            }
        )
        for alias, source in selected_columns.items():
            normalized[alias] = frame[source]
        normalized = normalized[
            normalized["datetime"].notna() & normalized["asset"].notna()
        ].copy()
        if start:
            normalized = normalized[normalized["datetime"] >= pd.Timestamp(start)]
        if end:
            normalized = normalized[normalized["datetime"] <= pd.Timestamp(end)]
        normalized = normalized.sort_values(["asset", "datetime"]).reset_index(drop=True)
        return normalized


def align_auxiliary_to_panel(
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    *,
    method: str,
) -> pd.DataFrame:
    panel_keys = panel[["datetime", "asset"]].drop_duplicates().sort_values(
        ["asset", "datetime"]
    )
    value_columns = [column for column in auxiliary.columns if column not in {"datetime", "asset"}]
    if method == "exact":
        aligned = panel_keys.merge(auxiliary, on=["datetime", "asset"], how="left")
    elif method == "forward_fill":
        aligned = panel_keys.merge(auxiliary, on=["datetime", "asset"], how="left")
        aligned = aligned.sort_values(["asset", "datetime"]).reset_index(drop=True)
        for column in value_columns:
            aligned[column] = aligned.groupby("asset")[column].ffill()
    elif method == "asof_backward":
        aligned = _merge_asof_by_asset(panel_keys, auxiliary, value_columns)
    else:
        raise ValueError(f"Unsupported auxiliary align method: {method}")
    return panel.merge(aligned, on=["datetime", "asset"], how="left")