from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ConstructionConfig, HoldingsGenConfig, SignalInputConfig, load_config
from .optimizer import apply_optimizer
from .risk_control import apply_risk_control


def _is_csv_path(path: Path) -> bool:
    return path.suffix.lower() == ".csv"


def _is_parquet_path(path: Path) -> bool:
    return path.suffix.lower() in {".parquet", ".pq"}


def _infer_format(path: Path) -> str:
    if _is_csv_path(path):
        return "csv"
    if _is_parquet_path(path):
        return "parquet"
    raise ValueError(f"无法根据后缀识别文件格式: {path}")


def _collect_input_paths(config: SignalInputConfig) -> list[Path]:
    root = Path(config.path)
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise ValueError(f"输入路径不存在: {config.path}")

    iterator = root.rglob(config.glob) if config.recursive else root.glob(config.glob)
    paths = sorted(path for path in iterator if path.is_file())
    if not paths:
        raise ValueError(f"输入目录下没有匹配文件: {config.path} glob={config.glob}")
    return paths


def _load_single_frame(path: Path, *, file_format: str) -> pd.DataFrame:
    if file_format == "csv":
        return pd.read_csv(path)
    if file_format == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"不支持的文件格式: {file_format}")


def load_signal_input(config: SignalInputConfig) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in _collect_input_paths(config):
        file_format = config.format if config.format != "infer" else _infer_format(path)
        frames.append(_load_single_frame(path, file_format=file_format))

    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0].copy()
    if config.rename:
        out = out.rename(columns=config.rename)
    return out


def _coerce_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.isin({"1", "true", "t", "yes", "y"})


def _standardize_signal_frame(
    signal_frame: pd.DataFrame,
    *,
    input_config: SignalInputConfig,
    construction: ConstructionConfig,
) -> pd.DataFrame:
    rename_map = {
        input_config.timestamp_col: "timestamp",
        input_config.symbol_col: "symbol",
    }
    if input_config.score_col is not None and input_config.score_col in signal_frame.columns:
        rename_map[input_config.score_col] = "score"
    if input_config.selected_flag_col is not None and input_config.selected_flag_col in signal_frame.columns:
        rename_map[input_config.selected_flag_col] = "selected_flag"
    if input_config.side_col is not None and input_config.side_col in signal_frame.columns:
        rename_map[input_config.side_col] = "side"

    frame = signal_frame.rename(columns=rename_map).copy()
    required = {"timestamp", "symbol"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"signal 缺少必要列: {missing}")

    if "selected_flag" not in frame.columns:
        if construction.selection_mode == "selected_flag":
            raise ValueError("construction.selection_mode=selected_flag 时，signal 必须包含 selected_flag 列")
        frame["selected_flag"] = True
    if "side" not in frame.columns:
        frame["side"] = construction.default_side
    if "score" not in frame.columns:
        frame["score"] = 1.0

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["symbol"] = frame["symbol"].astype(str)
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame["selected_flag"] = _coerce_bool_series(frame["selected_flag"])
    frame["side"] = frame["side"].fillna(construction.default_side).astype(str).str.upper()

    frame = frame.dropna(subset=["timestamp", "symbol"])
    if construction.weighting_method == "score_proportional":
        frame = frame.dropna(subset=["score"])

    if input_config.start is not None:
        frame = frame[frame["timestamp"] >= pd.Timestamp(input_config.start)]
    if input_config.end is not None:
        frame = frame[frame["timestamp"] <= pd.Timestamp(input_config.end)]

    frame = frame.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    return frame


def _select_signal_rows(signal_frame: pd.DataFrame, construction: ConstructionConfig) -> pd.DataFrame:
    if construction.selection_mode == "selected_flag":
        selected = signal_frame.loc[signal_frame["selected_flag"]].copy()
    else:
        selected = signal_frame.copy()
    selected = selected[selected["side"].ne("NONE")].copy()
    return selected.reset_index(drop=True)


def _allocate_side_weights(
    frame: pd.DataFrame,
    *,
    budget: float,
    sign: float,
    construction: ConstructionConfig,
) -> pd.DataFrame:
    if frame.empty or budget <= 0:
        return frame.iloc[0:0].copy()

    out = frame.copy()
    if construction.weighting_method == "equal":
        out["weight"] = sign * (budget / len(out))
        return out

    base = out["score"].abs().clip(lower=construction.score_abs_floor)
    total = float(base.sum())
    if total <= 0:
        out["weight"] = sign * (budget / len(out))
        return out
    out["weight"] = sign * base / total * budget
    return out


def _normalize_total_abs_weight(holdings_df: pd.DataFrame, target_abs_weight: float | None) -> pd.DataFrame:
    if holdings_df.empty or target_abs_weight is None:
        return holdings_df

    out = holdings_df.copy()
    gross = out.groupby("trade_date")["weight"].transform(lambda s: float(s.abs().sum()))
    scale = pd.Series(1.0, index=out.index, dtype=float)
    positive_mask = gross > 0
    scale.loc[positive_mask] = target_abs_weight / gross.loc[positive_mask]
    out["weight"] = out["weight"] * scale
    return out.reset_index(drop=True)


def generate_holdings_from_signal(
    signal_frame: pd.DataFrame,
    construction: ConstructionConfig,
) -> dict[str, pd.DataFrame]:
    selected_signal = _select_signal_rows(signal_frame, construction)

    records: list[pd.DataFrame] = []
    for timestamp, group in selected_signal.groupby("timestamp", sort=False):
        long_rows = _allocate_side_weights(
            group[group["side"] == "LONG"],
            budget=construction.long_budget,
            sign=1.0,
            construction=construction,
        )
        short_rows = _allocate_side_weights(
            group[group["side"] == "SHORT"],
            budget=construction.short_budget,
            sign=-1.0,
            construction=construction,
        )
        if long_rows.empty and short_rows.empty:
            continue
        day_rows = pd.concat([long_rows, short_rows], ignore_index=True)
        day_rows["trade_date"] = pd.Timestamp(timestamp)
        records.append(day_rows)

    if not records:
        raw_holdings = pd.DataFrame(columns=["trade_date", "symbol", "weight", "score", "side", "selected_flag"])
    else:
        raw_holdings = pd.concat(records, ignore_index=True)
        raw_holdings = raw_holdings[["trade_date", "symbol", "weight", "score", "side", "selected_flag"]]
        raw_holdings = raw_holdings.sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    final_holdings = _normalize_total_abs_weight(raw_holdings[["trade_date", "symbol", "weight"]].copy(), construction.normalize_total_abs_weight)
    final_holdings = final_holdings.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    return {
        "selected_signal": selected_signal,
        "raw_holdings": raw_holdings,
        "holdings": final_holdings,
    }


def _write_frame(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_csv_path(path):
        frame.to_csv(path, index=False)
    elif _is_parquet_path(path):
        frame.to_parquet(path, index=False)
    else:
        raise ValueError(f"输出文件格式仅支持 csv/parquet: {path}")
    return str(path)


def _build_summary(holdings_df: pd.DataFrame) -> dict[str, Any]:
    if holdings_df.empty:
        return {
            "trade_days": 0,
            "holdings_rows": 0,
            "unique_symbols": 0,
            "gross_exposure_mean": 0.0,
            "gross_exposure_max": 0.0,
            "net_exposure_mean": 0.0,
            "net_exposure_max": 0.0,
        }

    daily = holdings_df.groupby("trade_date")["weight"]
    gross = daily.apply(lambda s: float(s.abs().sum()))
    net = daily.sum().abs()
    counts = holdings_df.groupby("trade_date")["symbol"].nunique()
    return {
        "trade_days": int(gross.shape[0]),
        "holdings_rows": int(len(holdings_df)),
        "unique_symbols": int(holdings_df["symbol"].nunique()),
        "positions_per_day_mean": float(counts.mean()),
        "positions_per_day_max": int(counts.max()),
        "gross_exposure_mean": float(gross.mean()),
        "gross_exposure_max": float(gross.max()),
        "net_exposure_mean": float(net.mean()),
        "net_exposure_max": float(net.max()),
        "trade_date_min": str(holdings_df["trade_date"].min()),
        "trade_date_max": str(holdings_df["trade_date"].max()),
    }


def _write_outputs(
    config: HoldingsGenConfig,
    *,
    config_path: Path | None,
    selected_signal: pd.DataFrame,
    raw_holdings: pd.DataFrame,
    final_holdings: pd.DataFrame,
) -> tuple[dict[str, str], dict[str, Any]]:
    assert config.output is not None
    root = Path(config.output.root)
    root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    outputs["holdings"] = _write_frame(root / "holdings" / config.output.holdings_filename, final_holdings)
    if config.output.write_selected_signal:
        outputs["selected_signal"] = _write_frame(
            root / "debug" / config.output.selected_signal_filename,
            selected_signal,
        )
    if config.output.write_raw_holdings:
        outputs["raw_holdings"] = _write_frame(
            root / "debug" / config.output.raw_holdings_filename,
            raw_holdings,
        )

    summary = _build_summary(final_holdings)
    summary_path = root / config.output.summary_filename
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    outputs["summary"] = str(summary_path)

    manifest = {
        "portfolio_id": config.meta.portfolio_id,
        "version": config.meta.version,
        "description": config.meta.description,
        "input_signal_path": config.inputs.signal.path if config.inputs is not None else None,
        "construction": {
            "selection_mode": config.construction.selection_mode,
            "weighting_method": config.construction.weighting_method,
            "long_budget": config.construction.long_budget,
            "short_budget": config.construction.short_budget,
            "normalize_total_abs_weight": config.construction.normalize_total_abs_weight,
        },
        "optimizer": {
            "enabled": config.optimizer.enabled,
            "name": config.optimizer.name,
        },
        "risk_control": {
            "enabled": config.risk_control.enabled,
            "name": config.risk_control.name,
        },
        "summary": summary,
        "output_files": outputs,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    outputs["manifest"] = str(manifest_path)

    if config_path is not None:
        snapshot_path = root / "config_snapshot.yaml"
        snapshot_path.write_text(config_path.read_text())
        outputs["config_snapshot"] = str(snapshot_path)

    return outputs, summary


def run_pipeline(config: HoldingsGenConfig, *, config_path: str | Path | None = None) -> dict[str, Any]:
    if config.inputs is None:
        raise ValueError("inputs 不能为空")

    loaded_signal = load_signal_input(config.inputs.signal)
    signal_frame = _standardize_signal_frame(
        loaded_signal,
        input_config=config.inputs.signal,
        construction=config.construction,
    )
    generated = generate_holdings_from_signal(signal_frame, config.construction)

    optimized_holdings = apply_optimizer(
        generated["raw_holdings"],
        signal_frame=generated["selected_signal"],
        config=config.optimizer,
    )
    risk_adjusted_holdings = apply_risk_control(
        optimized_holdings,
        signal_frame=generated["selected_signal"],
        config=config.risk_control,
    )
    final_holdings = _normalize_total_abs_weight(
        risk_adjusted_holdings[["trade_date", "symbol", "weight"]].copy(),
        config.construction.normalize_total_abs_weight,
    )

    outputs, summary = _write_outputs(
        config,
        config_path=Path(config_path) if config_path is not None else None,
        selected_signal=generated["selected_signal"],
        raw_holdings=generated["raw_holdings"],
        final_holdings=final_holdings,
    )
    return {
        "signal": signal_frame,
        "selected_signal": generated["selected_signal"],
        "raw_holdings": generated["raw_holdings"],
        "optimized_holdings": optimized_holdings,
        "holdings": final_holdings,
        "summary": summary,
        "outputs": outputs,
    }


def run_from_config(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    return run_pipeline(config, config_path=config_path)