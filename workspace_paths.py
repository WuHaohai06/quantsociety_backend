from __future__ import annotations

import os
import re
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def _sanitize_segment(value: str | None, *, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def workspace_data_root() -> Path:
    override = os.getenv("QUANTSOCIETY_WORKSPACE_DATA_ROOT")
    if override:
        return Path(os.path.expanduser(os.path.expandvars(override))).resolve()
    return (repo_root() / "workspace_data").resolve()


def default_factor_lake_root() -> Path:
    override = os.getenv("FACTOR_LAKE_ROOT")
    if override:
        return Path(os.path.expanduser(os.path.expandvars(override))).resolve()
    return workspace_data_root() / "factors" / "lake"


def default_factor_evaluation_root(*, factor_lake_root: str | Path | None = None) -> Path:
    lake_root = Path(factor_lake_root).resolve() if factor_lake_root is not None else default_factor_lake_root()
    return lake_root / "evaluations"


def default_composite_signal_root(signal_id: str | None = None, version: str | None = None) -> Path:
    name = _sanitize_segment(signal_id, fallback="composite_signal")
    suffix = _sanitize_segment(version, fallback="v1")
    return workspace_data_root() / "strategy" / "composite_signals" / f"{name}_{suffix}"


def default_holdings_root(portfolio_id: str | None = None, version: str | None = None) -> Path:
    name = _sanitize_segment(portfolio_id, fallback="generated_holdings")
    suffix = _sanitize_segment(version, fallback="v1")
    return workspace_data_root() / "strategy" / "holdings" / f"{name}_{suffix}"


def default_single_asset_alpha_output_root(strategy_id: str | None = None, version: str | None = None) -> Path:
    name = _sanitize_segment(strategy_id, fallback="single_asset_alpha")
    suffix = _sanitize_segment(version, fallback="v1")
    return workspace_data_root() / "strategy" / "single_asset_alpha" / f"{name}_{suffix}"


def default_portfolio_backtest_root() -> Path:
    return workspace_data_root() / "backtests" / "portfolio"


def default_single_asset_backtest_root() -> Path:
    return workspace_data_root() / "backtests" / "single_asset"


def default_market_cache_root() -> Path:
    return workspace_data_root() / "cache" / "market_data"


def default_demo_root(demo_name: str | None = None) -> Path:
    name = _sanitize_segment(demo_name, fallback="demo")
    return workspace_data_root() / "demos" / name