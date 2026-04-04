from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


CANONICAL_TIMESTAMP_COLUMN = "timestamp"
CANONICAL_SYMBOL_COLUMN = "symbol"
FACTOR_VALUE_COLUMN = "value"
CANONICAL_KEY_COLUMNS = (
    CANONICAL_TIMESTAMP_COLUMN,
    CANONICAL_SYMBOL_COLUMN,
)
RESERVED_CANONICAL_COLUMNS = set(CANONICAL_KEY_COLUMNS)

AlignMethod = Literal["outer", "inner", "asof_backward", "forward_fill"]


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    normalized = pd.to_datetime(series, utc=True, errors="coerce")
    if isinstance(normalized.dtype, pd.DatetimeTZDtype):
        normalized = normalized.dt.tz_convert(None)
    return normalized


@dataclass(frozen=True)
class FactorRef:
    factor_id: str
    column_name: str | None = None

    def __post_init__(self) -> None:
        if not str(self.factor_id).strip():
            raise ValueError("factor_id 不能为空")
        if self.name in RESERVED_CANONICAL_COLUMNS:
            raise ValueError(f"因子列名 '{self.name}' 与保留列冲突")

    @property
    def name(self) -> str:
        return self.column_name or self.factor_id


def validate_factor_long(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        CANONICAL_TIMESTAMP_COLUMN,
        CANONICAL_SYMBOL_COLUMN,
        FACTOR_VALUE_COLUMN,
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"factor long 缺少必要列: {sorted(missing)}")

    out = frame.loc[:, [*CANONICAL_KEY_COLUMNS, FACTOR_VALUE_COLUMN]].copy()
    out[CANONICAL_TIMESTAMP_COLUMN] = _normalize_timestamp(out[CANONICAL_TIMESTAMP_COLUMN])
    out[CANONICAL_SYMBOL_COLUMN] = out[CANONICAL_SYMBOL_COLUMN].astype("string").str.strip()
    out[FACTOR_VALUE_COLUMN] = pd.to_numeric(out[FACTOR_VALUE_COLUMN], errors="coerce")
    out = out.dropna(subset=[*CANONICAL_KEY_COLUMNS, FACTOR_VALUE_COLUMN]).copy()

    if out.duplicated(list(CANONICAL_KEY_COLUMNS)).any():
        duplicated = out.loc[out.duplicated(list(CANONICAL_KEY_COLUMNS), keep=False)].head(1)
        raise ValueError(
            "factor long 存在重复主键: "
            f"{duplicated[list(CANONICAL_KEY_COLUMNS)].to_dict(orient='records')[0]}"
        )

    out[FACTOR_VALUE_COLUMN] = out[FACTOR_VALUE_COLUMN].astype("float32")
    out = out.sort_values(list(CANONICAL_KEY_COLUMNS)).reset_index(drop=True)
    return out


def validate_canonical_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = set(CANONICAL_KEY_COLUMNS)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"canonical panel 缺少必要列: {sorted(missing)}")

    factor_columns = [
        column
        for column in frame.columns
        if column not in RESERVED_CANONICAL_COLUMNS
    ]
    if not factor_columns:
        raise ValueError("canonical panel 至少需要一列因子")

    out = frame.loc[:, [*CANONICAL_KEY_COLUMNS, *factor_columns]].copy()
    out[CANONICAL_TIMESTAMP_COLUMN] = _normalize_timestamp(out[CANONICAL_TIMESTAMP_COLUMN])
    out[CANONICAL_SYMBOL_COLUMN] = out[CANONICAL_SYMBOL_COLUMN].astype("string").str.strip()
    out = out.dropna(subset=list(CANONICAL_KEY_COLUMNS)).copy()

    if out.duplicated(list(CANONICAL_KEY_COLUMNS)).any():
        duplicated = out.loc[out.duplicated(list(CANONICAL_KEY_COLUMNS), keep=False)].head(1)
        raise ValueError(
            "canonical panel 存在重复主键: "
            f"{duplicated[list(CANONICAL_KEY_COLUMNS)].to_dict(orient='records')[0]}"
        )

    for column in factor_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    out = out.sort_values(list(CANONICAL_KEY_COLUMNS)).reset_index(drop=True)
    return out