from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

try:
    import cvxpy as cp
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some environments
    cp = None

import numpy as np
import pandas as pd

from .config import OptimizerConfig

SUPPORTED_OPTIMIZER_NAMES = {"barra", "barra_mean_variance_ls"}
DEFAULT_IC = 0.05
DEFAULT_RISK_AVERSION = 2.0
DEFAULT_NAME_CAP = 0.05
DEFAULT_WINSOR_Q = 0.01
DEFAULT_ZSCORE_EPS = 1e-12
DEFAULT_SOLVER = "SCS"
DEFAULT_SOLVER_MAX_ITERS = 10_000
DEFAULT_SOLVER_EPS = 1e-5


def _param_dict(config: OptimizerConfig) -> dict[str, Any]:
    return dict(config.params or {})


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    return float(value)


def _as_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _resolve_path(value: Any) -> Path | None:
    if value in {None, ""}:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else path.resolve()


def _load_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pd.read_parquet(path)


def _pick_column(columns: list[str], candidates: tuple[str, ...], *, field_name: str) -> str:
    lower_map = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    raise ValueError(f"Unable to find {field_name} column. Tried: {candidates}")


def _normalize_symbol_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def _normalize_day_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def _prepare_signal_frame(signal_frame: pd.DataFrame, *, alpha_col: str) -> pd.DataFrame:
    if signal_frame.empty:
        return signal_frame.copy()

    frame = signal_frame.copy()
    timestamp_col = _pick_column(list(frame.columns), ("timestamp", "trade_date", "date"), field_name="signal timestamp")
    symbol_col = _pick_column(list(frame.columns), ("symbol", "asset", "ticker"), field_name="signal symbol")
    score_candidates = (alpha_col, "score", "composite_score", "expected_ret")
    score_col = None
    for candidate in score_candidates:
        if candidate in frame.columns:
            score_col = candidate
            break
    if score_col is None:
        raise ValueError(f"signal_frame 缺少可用的 alpha 列，候选为: {score_candidates}")

    frame["_trade_date"] = _normalize_day_series(frame[timestamp_col])
    frame["_symbol"] = _normalize_symbol_series(frame[symbol_col])
    frame["_alpha_raw"] = pd.to_numeric(frame[score_col], errors="coerce")
    frame = frame.dropna(subset=["_trade_date", "_symbol", "_alpha_raw"]).copy()
    frame = frame.sort_values(["_trade_date", "_symbol"]).reset_index(drop=True)
    return frame


def _prepare_holdings_frame(holdings_df: pd.DataFrame) -> pd.DataFrame:
    if holdings_df.empty:
        return holdings_df.copy()

    frame = holdings_df.copy()
    trade_date_col = _pick_column(list(frame.columns), ("trade_date", "timestamp", "date"), field_name="holdings trade date")
    symbol_col = _pick_column(list(frame.columns), ("symbol", "asset", "ticker"), field_name="holdings symbol")
    weight_col = _pick_column(list(frame.columns), ("weight",), field_name="holdings weight")

    frame["_trade_date"] = _normalize_day_series(frame[trade_date_col])
    frame["_symbol"] = _normalize_symbol_series(frame[symbol_col])
    frame["_weight_raw"] = pd.to_numeric(frame[weight_col], errors="coerce")
    if "side" in frame.columns:
        side = frame["side"].astype("string").str.strip().str.upper()
    else:
        side = pd.Series(pd.NA, index=frame.index, dtype="string")
    frame["_side"] = side
    frame = frame.dropna(subset=["_trade_date", "_symbol", "_weight_raw"]).copy()
    frame = frame.sort_values(["_trade_date", "_symbol"]).reset_index(drop=True)
    return frame


def _winsorize_and_zscore(values: pd.Series, *, q: float, eps: float) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric.dropna()
    if numeric.empty:
        return pd.Series(dtype="float64")

    lower = numeric.quantile(q)
    upper = numeric.quantile(1.0 - q)
    clipped = values.astype(float).clip(lower=lower, upper=upper)
    mean = float(clipped.mean())
    std = float(clipped.std(ddof=0))
    if not np.isfinite(std) or std <= eps:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return (clipped - mean) / std


def _estimate_sigma_mkt(specific_var: pd.Series) -> float:
    cleaned = pd.to_numeric(specific_var, errors="coerce").dropna().clip(lower=0.0)
    if cleaned.empty:
        return 0.0
    n_assets = int(cleaned.shape[0])
    if n_assets <= 0:
        return 0.0
    return float(np.sqrt(float(cleaned.sum())) / n_assets)


def _load_barra_inputs(params: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    barra_dir = _resolve_path(params.get("barra_dir"))
    factor_covariance_path = _resolve_path(params.get("factor_covariance_path"))
    specific_risk_path = _resolve_path(params.get("specific_risk_path"))
    factor_exposure_path = _resolve_path(params.get("factor_exposure_path"))

    if barra_dir is not None:
        if factor_covariance_path is None:
            factor_covariance_path = barra_dir / "factor_covariance.parquet"
        if specific_risk_path is None:
            specific_risk_path = barra_dir / "specific_risk.parquet"
        if factor_exposure_path is None:
            factor_exposure_path = barra_dir / "cleaned_factors.parquet"

    missing = [
        name
        for name, path in (
            ("factor_covariance_path", factor_covariance_path),
            ("specific_risk_path", specific_risk_path),
            ("factor_exposure_path", factor_exposure_path),
        )
        if path is None
    ]
    if missing:
        raise ValueError(
            "optimizer.params 需要提供 Barra 风险输入路径："
            "barra_dir 或 factor_covariance_path/specific_risk_path/factor_exposure_path"
        )

    return (
        _load_parquet(factor_covariance_path),
        _load_parquet(specific_risk_path),
        _load_parquet(factor_exposure_path),
    )


def _load_specific_risk_cross_section(specific_risk: pd.DataFrame, trade_date: pd.Timestamp) -> pd.DataFrame:
    frame = specific_risk.copy()
    asset_col = _pick_column(list(frame.columns), ("asset", "symbol", "ticker"), field_name="specific risk asset")
    value_col = _pick_column(
        list(frame.columns),
        ("specific_var_annual", "specific_var_daily", "specific_var", "specific_risk"),
        field_name="specific risk variance",
    )

    date_candidates = ("date", "timestamp", "trade_date", "datetime")
    date_col = next((candidate for candidate in date_candidates if candidate in frame.columns), None)
    if date_col is not None:
        frame["_trade_date"] = _normalize_day_series(frame[date_col])
        frame = frame.loc[frame["_trade_date"] == trade_date].copy()

    frame["_asset"] = _normalize_symbol_series(frame[asset_col])
    frame["_specific_var"] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=["_asset", "_specific_var"]).copy()
    if frame.empty:
        return frame.loc[:, ["_asset", "_specific_var"]]

    median_value = float(frame["_specific_var"].median())
    frame["_specific_var"] = frame["_specific_var"].fillna(median_value).fillna(0.0).clip(lower=0.0)
    return frame.loc[:, ["_asset", "_specific_var"]].drop_duplicates(subset=["_asset"], keep="last")


def _load_factor_exposure_cross_section(
    factor_exposures: pd.DataFrame,
    trade_date: pd.Timestamp,
    factor_columns: list[str],
) -> pd.DataFrame:
    frame = factor_exposures.copy()
    asset_col = _pick_column(list(frame.columns), ("asset", "symbol", "ticker"), field_name="factor exposure asset")
    date_col = _pick_column(list(frame.columns), ("date", "timestamp", "trade_date", "datetime"), field_name="factor exposure date")

    frame["_trade_date"] = _normalize_day_series(frame[date_col])
    frame = frame.loc[frame["_trade_date"] == trade_date].copy()
    if frame.empty:
        return frame

    frame["_asset"] = _normalize_symbol_series(frame[asset_col])
    missing_factors = [factor for factor in factor_columns if factor not in frame.columns]
    if missing_factors:
        raise ValueError(f"factor_exposure 缺少风险矩阵要求的列: {missing_factors}")

    frame = frame.loc[:, ["_asset", *factor_columns]].copy()
    for factor in factor_columns:
        frame[factor] = pd.to_numeric(frame[factor], errors="coerce")
    frame = frame.dropna(subset=["_asset"]).drop_duplicates(subset=["_asset"], keep="last")
    return frame


def _solve_problem(problem: cp.Problem, *, solver: str, max_iters: int, eps: float) -> None:
    solver_name = solver.strip().upper()
    solver_candidates: list[Any] = []
    if hasattr(cp, solver_name):
        solver_candidates.append(getattr(cp, solver_name))
    else:
        raise ValueError(f"不支持的求解器: {solver}")

    last_error: Exception | None = None
    for candidate in solver_candidates:
        try:
            solver_options: dict[str, Any]
            if candidate == cp.OSQP:
                solver_options = {"max_iter": max_iters, "eps_abs": eps, "eps_rel": eps}
            elif candidate == cp.SCS:
                solver_options = {"max_iters": max_iters, "eps": eps}
            elif candidate == cp.ECOS:
                solver_options = {"max_iters": max_iters, "abstol": eps, "reltol": eps}
            else:
                solver_options = {"max_iters": max_iters, "eps": eps}
            problem.solve(solver=candidate, verbose=False, **solver_options)
            if problem.status in {"optimal", "optimal_inaccurate"}:
                return
        except Exception as exc:  # pragma: no cover - solver backends can vary by environment
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise ValueError(f"Optimization failed with status: {problem.status}")


def _optimize_one_day(
    day_holdings: pd.DataFrame,
    day_signal: pd.DataFrame,
    factor_covariance: pd.DataFrame,
    specific_risk: pd.DataFrame,
    factor_exposures: pd.DataFrame,
    *,
    params: dict[str, Any],
) -> pd.DataFrame:
    if day_holdings.empty:
        return day_holdings.copy()

    trade_date = day_holdings["_trade_date"].iloc[0]
    alpha_col = str(params.get("alpha_col") or params.get("score_col") or "score")
    ic = _as_float(params.get("ic"), default=DEFAULT_IC) or DEFAULT_IC
    risk_aversion = _as_float(params.get("risk_aversion"), default=DEFAULT_RISK_AVERSION) or DEFAULT_RISK_AVERSION
    name_cap = _as_float(params.get("name_cap"), default=DEFAULT_NAME_CAP) or DEFAULT_NAME_CAP
    winsor_q = _as_float(params.get("winsor_q"), default=DEFAULT_WINSOR_Q) or DEFAULT_WINSOR_Q
    zscore_eps = _as_float(params.get("zscore_eps"), default=DEFAULT_ZSCORE_EPS) or DEFAULT_ZSCORE_EPS
    sigma_mkt_param = _as_float(params.get("sigma_mkt"), default=None)
    long_budget_override = _as_float(params.get("long_budget"), default=None)
    short_budget_override = _as_float(params.get("short_budget"), default=None)
    strict = _as_bool(params.get("strict"), default=False)
    fallback_to_input_on_fail = _as_bool(params.get("fallback_to_input_on_fail"), default=True)
    solver = str(params.get("solver") or DEFAULT_SOLVER)
    solver_max_iters = _as_int(params.get("solver_max_iters"), default=DEFAULT_SOLVER_MAX_ITERS)
    solver_eps = _as_float(params.get("solver_eps"), default=DEFAULT_SOLVER_EPS) or DEFAULT_SOLVER_EPS

    if not (0.0 < winsor_q < 0.5):
        raise ValueError("winsor_q 必须位于 (0, 0.5)")
    if name_cap <= 0:
        raise ValueError("name_cap 必须大于 0")
    if risk_aversion < 0:
        raise ValueError("risk_aversion 不能为负数")
    if ic < 0:
        raise ValueError("ic 不能为负数")

    signal_day = day_signal.loc[day_signal["_trade_date"] == trade_date].copy()
    if signal_day.empty:
        raise ValueError(f"{trade_date.date()} 没有对应的 signal 数据")

    merged = day_holdings.merge(
        signal_day.loc[:, ["_trade_date", "_symbol", "_alpha_raw"]],
        on=["_trade_date", "_symbol"],
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(day_holdings):
        raise ValueError(f"{trade_date.date()} 的 holdings 与 signal 无法一一对齐")

    factor_cols = [column for column in factor_covariance.index.tolist() if column in factor_covariance.columns]
    if not factor_cols:
        raise ValueError("factor_covariance 必须是方阵且包含 factor 名称")
    covariance = factor_covariance.reindex(index=factor_cols, columns=factor_cols).apply(pd.to_numeric, errors="coerce")
    if covariance.isna().any().any():
        raise ValueError("factor_covariance 存在无法对齐的 factor 列")

    exposure_day = _load_factor_exposure_cross_section(factor_exposures, trade_date, factor_cols)
    if exposure_day.empty:
        raise ValueError(f"{trade_date.date()} 没有对应的 factor exposure")

    specific_day = _load_specific_risk_cross_section(specific_risk, trade_date)
    if specific_day.empty:
        raise ValueError(f"{trade_date.date()} 没有对应的 specific risk")

    merged = merged.merge(exposure_day, left_on="_symbol", right_on="_asset", how="inner", validate="one_to_one")
    if len(merged) != len(day_holdings):
        raise ValueError(f"{trade_date.date()} 的 holdings 无法与 factor exposure 一一对齐")

    merged = merged.merge(specific_day, left_on="_symbol", right_on="_asset", how="left", validate="one_to_one")
    if merged["_specific_var"].isna().any():
        fill_value = float(merged["_specific_var"].median())
        merged["_specific_var"] = merged["_specific_var"].fillna(fill_value)
    merged["_specific_var"] = merged["_specific_var"].fillna(0.0).clip(lower=0.0)

    alpha_series = _winsorize_and_zscore(merged["_alpha_raw"], q=winsor_q, eps=zscore_eps)
    if alpha_series.empty:
        raise ValueError(f"{trade_date.date()} 的 alpha 无法标准化")
    merged["_alpha_z"] = alpha_series.reindex(merged.index).fillna(0.0)

    sigma_mkt = sigma_mkt_param if sigma_mkt_param is not None else _estimate_sigma_mkt(merged["_specific_var"])
    if not np.isfinite(sigma_mkt):
        raise ValueError(f"{trade_date.date()} 的 sigma_mkt 无效")
    mu = merged["_alpha_z"].to_numpy(dtype=np.float64) * float(sigma_mkt) * ic

    asset_count = len(merged)
    long_mask = merged["_side"].fillna("LONG").eq("LONG").to_numpy(dtype=np.float64)
    short_mask = merged["_side"].fillna("LONG").eq("SHORT").to_numpy(dtype=np.float64)
    if not long_mask.any() and not short_mask.any():
        raise ValueError(f"{trade_date.date()} 没有可优化的 long/short 资产")

    inferred_long_budget = float(day_holdings.loc[day_holdings["_weight_raw"] > 0, "_weight_raw"].sum())
    inferred_short_budget = float(-day_holdings.loc[day_holdings["_weight_raw"] < 0, "_weight_raw"].sum())
    long_budget = inferred_long_budget if long_budget_override is None else float(long_budget_override)
    short_budget = inferred_short_budget if short_budget_override is None else float(short_budget_override)

    if long_budget < 0 or short_budget < 0:
        raise ValueError("long_budget/short_budget 不能为负数")
    if long_mask.sum() > 0 and long_mask.sum() * name_cap + 1e-12 < long_budget:
        raise ValueError(f"{trade_date.date()} long_budget 无法被当前资产数量和 name_cap 覆盖")
    if short_mask.sum() > 0 and short_mask.sum() * name_cap + 1e-12 < short_budget:
        raise ValueError(f"{trade_date.date()} short_budget 无法被当前资产数量和 name_cap 覆盖")
    if long_budget == 0 and short_budget == 0:
        out = day_holdings.copy()
        out["weight"] = 0.0
        return out

    signs = np.where(merged["_side"].fillna("LONG").eq("SHORT"), -1.0, 1.0).astype(np.float64)
    x = cp.Variable(asset_count, nonneg=True)
    signed_weights = cp.multiply(signs, x)

    factor_matrix = merged.loc[:, factor_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    factor_cov = covariance.to_numpy(dtype=np.float64)
    specific_var = merged["_specific_var"].to_numpy(dtype=np.float64)

    factor_risk = cp.quad_form(factor_matrix.T @ signed_weights, cp.psd_wrap(factor_cov))
    specific_risk_term = cp.sum(cp.multiply(cp.square(signed_weights), specific_var))
    total_variance = factor_risk + specific_risk_term
    utility = mu @ signed_weights - 0.5 * risk_aversion * total_variance

    constraints: list[Any] = [
        x <= name_cap,
        cp.sum(cp.multiply(long_mask, x)) == long_budget,
        cp.sum(cp.multiply(short_mask, x)) == short_budget,
    ]

    problem = cp.Problem(cp.Maximize(utility), constraints)
    _solve_problem(problem, solver=solver, max_iters=solver_max_iters, eps=solver_eps)

    if problem.status not in {"optimal", "optimal_inaccurate"} or x.value is None:
        raise ValueError(f"{trade_date.date()} optimization failed with status: {problem.status}")

    optimized = day_holdings.copy()
    optimized_weights = np.asarray(signs * np.asarray(x.value, dtype=np.float64), dtype=np.float64)
    optimized["weight"] = optimized_weights
    return optimized


def apply_optimizer(
    holdings_df: pd.DataFrame,
    *,
    signal_frame: pd.DataFrame,
    config: OptimizerConfig,
) -> pd.DataFrame:
    if holdings_df.empty or not config.enabled or config.name == "noop":
        return holdings_df

    optimizer_name = str(config.name).strip().lower()
    if optimizer_name not in SUPPORTED_OPTIMIZER_NAMES:
        raise ValueError(
            f"Optimizer '{config.name}' 尚未实现；当前支持: {sorted(SUPPORTED_OPTIMIZER_NAMES)}"
        )

    params = _param_dict(config)
    fallback_to_input_on_fail = _as_bool(params.get("fallback_to_input_on_fail"), default=True)
    strict = _as_bool(params.get("strict"), default=False)

    prepared_holdings = _prepare_holdings_frame(holdings_df)
    prepared_signal = _prepare_signal_frame(signal_frame, alpha_col=str(params.get("alpha_col") or params.get("score_col") or "score"))
    factor_covariance, specific_risk, factor_exposures = _load_barra_inputs(params)

    outputs: list[pd.DataFrame] = []
    for trade_date, day_holdings in prepared_holdings.groupby("_trade_date", sort=True):
        try:
            day_signal = prepared_signal.loc[prepared_signal["_trade_date"] == trade_date].copy()
            optimized_day = _optimize_one_day(
                day_holdings,
                day_signal,
                factor_covariance,
                specific_risk,
                factor_exposures,
                params=params,
            )
            outputs.append(optimized_day)
        except Exception as exc:
            message = f"holdings_gen optimizer 在 {trade_date.date()} 失败: {exc}"
            if strict or not fallback_to_input_on_fail:
                raise type(exc)(message) from exc
            warnings.warn(message, RuntimeWarning)
            outputs.append(day_holdings.drop(columns=["_trade_date", "_symbol", "_weight_raw", "_side"], errors="ignore").copy())

    result = pd.concat(outputs, ignore_index=True) if outputs else prepared_holdings.copy()
    if "weight" not in result.columns:
        result["weight"] = pd.to_numeric(result.get("_weight_raw"), errors="coerce")
    result = result.sort_values([col for col in ("_trade_date", "_symbol") if col in result.columns]).reset_index(drop=True)

    drop_columns = [column for column in result.columns if column.startswith("_")]
    result = result.drop(columns=drop_columns, errors="ignore")
    return result
