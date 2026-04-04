from __future__ import annotations

"""回测运行器：单标的（Backtrader + 策略库）与多标的（向量化执行层 + 成本 + 组合收益）。

重要顺序（多标的）：``asset_return`` → ``_apply_multi_asset_execution_and_cost`` 得 ``executed_weights`` →
``shift(portfolio_weight_lag_bars)`` → 毛收益 − 成本 = 净收益 → 复利权益。指纹使用执行后权重列统计。
"""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from runtime.perf_config import PerfConfig
from single_asset_backtest.config import BacktestConfig
from single_asset_backtest.contracts import (
    align_target_position_to_index,
    align_target_weights_to_index,
    validate_target_position,
    validate_target_weights,
)
from single_asset_backtest.io import load_ohlcv_from_config
from single_asset_backtest.metrics import annualization_factor
from single_asset_backtest.report import build_backtest_report
from single_asset_backtest.strategy_library import build_strategy_registry

# ---------------------------------------------------------------------------
# 可复现指纹：对 OHLCV/权重做统计摘要后哈希，非文件字节级 hash
# ---------------------------------------------------------------------------
_NUMBA_AVAILABLE: bool | None = None
_MULTI_ASSET_NUMBA_KERNEL = None


def _safe_series_stats(series: pd.Series) -> dict:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return {
        "sum": float(s.sum()),
        "mean": float(s.mean()) if len(s) else 0.0,
        "std": float(s.std(ddof=0)) if len(s) else 0.0,
        "first": float(s.iloc[0]) if len(s) else 0.0,
        "last": float(s.iloc[-1]) if len(s) else 0.0,
    }


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _single_asset_fingerprint(feed_frame: pd.DataFrame, target_series: pd.Series) -> str:
    """单标的：OHLCV 各列 + 目标序列统计量 → JSON → SHA256。"""
    payload = {
        "mode": "single",
        "bars": int(len(feed_frame)),
        "start": str(feed_frame.index.min()) if len(feed_frame) else None,
        "end": str(feed_frame.index.max()) if len(feed_frame) else None,
        "columns": list(feed_frame.columns),
        "ohlcv_stats": {col: _safe_series_stats(feed_frame[col]) for col in feed_frame.columns},
        "target_stats": _safe_series_stats(target_series),
    }
    return _hash_payload(payload)


def _multi_asset_fingerprint(feeds: dict[str, pd.DataFrame], weight_matrix: pd.DataFrame) -> str:
    """多标的：各标的 close 统计 + 权重矩阵各列统计（调用处传入 ``executed_weights``）。"""
    ordered_symbols = sorted(feeds.keys())
    payload = {
        "mode": "multi",
        "symbols": ordered_symbols,
        "bars": int(len(weight_matrix.index)),
        "start": str(weight_matrix.index.min()) if len(weight_matrix.index) else None,
        "end": str(weight_matrix.index.max()) if len(weight_matrix.index) else None,
        "close_stats": {
            symbol: _safe_series_stats(feeds[symbol]["close"])
            for symbol in ordered_symbols
        },
        "weight_stats": {
            symbol: _safe_series_stats(weight_matrix[symbol])
            for symbol in weight_matrix.columns
        },
    }
    return _hash_payload(payload)


def _dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {
        "python": platform.python_version(),
        "pandas": None,
        "numpy": None,
        "backtrader": None,
    }
    for pkg in ("pandas", "numpy", "backtrader"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    return versions


def _git_sha() -> str | None:
    """向上查找含 ``.git`` 的目录作为仓库根（适配 monorepo 与本包嵌套路径）。"""
    here = Path(__file__).resolve().parent
    repo_root = None
    for p in [here, *here.parents]:
        if (p / ".git").is_dir():
            repo_root = p
            break
    if repo_root is None:
        return None
    cmd = ["git", "-C", str(repo_root), "rev-parse", "HEAD"]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True)
        sha = out.stdout.strip()
        return sha or None
    except Exception:
        return None


def _build_reproducibility_metadata(*, mode: str, data_fingerprint: str | None) -> dict:
    return {
        "mode": mode,
        "run_id": uuid.uuid4().hex,
        "data_fingerprint": data_fingerprint,
        "dependency_versions": _dependency_versions(),
        "git_sha": _git_sha(),
    }


def _build_timing_audit_metadata(*, mode: str, config: BacktestConfig) -> dict:
    """写入 summary 的时序语义：信号/决策时刻标注、有效滞后 bar 数、收益归因字符串。"""
    if mode == "single":
        lag_bars = max(0, int(config.target_lag_bars))
    else:
        lag_bars = max(1, int(config.portfolio_weight_lag_bars))

    return {
        "signal_timestamp": "bar_close_t",
        "decision_timestamp": "bar_close_t",
        "execution_effective_lag_bars": lag_bars,
        "return_attribution": f"weights(t-{lag_bars}) * returns(t)",
    }


def _is_numba_available() -> bool:
    global _NUMBA_AVAILABLE
    if _NUMBA_AVAILABLE is None:
        try:
            import numba  # noqa: F401

            _NUMBA_AVAILABLE = True
        except Exception:
            _NUMBA_AVAILABLE = False
    return bool(_NUMBA_AVAILABLE)


def _resolve_portfolio_execution_engine(config: BacktestConfig) -> tuple[str, str]:
    """解析多标的执行内核：YAML 写 ``python`` 时由环境变量 ``FACTOR_BACKTEST_EXECUTION_ENGINE`` 覆盖请求。"""
    requested = str(config.portfolio_execution_engine).lower()
    if requested == "python":
        requested = str(PerfConfig.from_env().backtest_execution_engine).lower()

    if requested not in {"python", "numpy", "numba", "auto"}:
        requested = "python"

    if requested in {"python", "numpy"}:
        resolved = requested
    elif requested == "numba":
        resolved = "numba" if _is_numba_available() else "numpy"
    else:  # auto
        resolved = "numba" if _is_numba_available() else "numpy"

    return requested, resolved


def _apply_multi_asset_execution_and_cost_python(
    *,
    target_weights: pd.DataFrame,
    close_matrix: pd.DataFrame,
    volume_matrix: pd.DataFrame,
    config: BacktestConfig,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """逐 bar pandas 实现：调仓阈值、ADV 裁剪、换手与每 bar 成本收益率（与 numpy/numba 语义对齐）。"""
    executed_weights = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)
    turnover = pd.Series(0.0, index=target_weights.index, dtype=float)
    cost_return = pd.Series(0.0, index=target_weights.index, dtype=float)
    participation = pd.Series(0.0, index=target_weights.index, dtype=float)

    initial_cash = float(config.initial_cash)
    min_trade_weight = max(0.0, float(config.portfolio_min_trade_weight))
    adv_cap = config.portfolio_adv_participation_cap
    cost_model = str(config.portfolio_cost_model)
    commission_rate = float(config.portfolio_commission_bps) / 10_000.0
    spread_rate = float(config.portfolio_spread_bps) / 10_000.0
    impact_coeff = max(0.0, float(config.portfolio_impact_coeff))

    if cost_model not in {"simple_bps", "linear_impact", "square_impact"}:
        raise ValueError(f"Unknown portfolio_cost_model: {cost_model}")

    prev_weight = pd.Series(0.0, index=target_weights.columns, dtype=float)
    for ts in target_weights.index:
        desired = target_weights.loc[ts].astype(float)
        delta = (desired - prev_weight).astype(float)

        if min_trade_weight > 0.0:
            delta = delta.where(delta.abs() >= min_trade_weight, 0.0)

        # 参与率上限：用 price*volume 推算本 bar 可交易名义，再换算成权重变化上限
        cap_weight = pd.Series(float("inf"), index=target_weights.columns, dtype=float)
        if adv_cap is not None:
            adv_cap_value = float(adv_cap)
            if adv_cap_value <= 0:
                raise ValueError("portfolio_adv_participation_cap must be > 0 when provided")
            adv_notional = (close_matrix.loc[ts] * volume_matrix.loc[ts]).astype(float).clip(lower=0.0)
            cap_weight = (adv_notional * adv_cap_value / max(initial_cash, 1e-12)).astype(float)
            cap_weight = cap_weight.fillna(0.0)
            bounded_delta = delta.copy()
            for symbol in bounded_delta.index:
                cap = float(cap_weight.loc[symbol])
                if cap <= 0.0:
                    bounded_delta.loc[symbol] = 0.0
                else:
                    bounded_delta.loc[symbol] = float(min(max(bounded_delta.loc[symbol], -cap), cap))
            delta = bounded_delta

        new_weight = (prev_weight + delta).astype(float)
        executed_weights.loc[ts] = new_weight

        # 换手：全标的权重变化绝对值之和（可选 ×0.5 表示单边口径）
        bar_turnover = float(delta.abs().sum())
        if config.portfolio_half_turnover:
            bar_turnover *= 0.5
        turnover.loc[ts] = bar_turnover

        base_cost = bar_turnover * (commission_rate + spread_rate)

        if adv_cap is None:
            part_by_symbol = pd.Series(0.0, index=target_weights.columns, dtype=float)
        else:
            part_by_symbol = pd.Series(0.0, index=target_weights.columns, dtype=float)
            for symbol in part_by_symbol.index:
                cap = float(cap_weight.loc[symbol])
                if cap > 0:
                    part_by_symbol.loc[symbol] = float(abs(delta.loc[symbol]) / cap)

        participation.loc[ts] = float(part_by_symbol.max()) if len(part_by_symbol) else 0.0

        if cost_model == "simple_bps":
            impact_cost = 0.0
        elif cost_model == "linear_impact":
            impact_cost = float((delta.abs() * part_by_symbol).sum()) * impact_coeff
        else:  # square_impact
            impact_cost = float((delta.abs() * (part_by_symbol**2)).sum()) * impact_coeff

        cost_return.loc[ts] = float(base_cost + impact_cost)
        prev_weight = new_weight

    return executed_weights.astype(float), turnover.astype(float), cost_return.astype(float), participation.astype(float)


def _apply_multi_asset_execution_and_cost_numpy(
    *,
    target_weights: pd.DataFrame,
    close_matrix: pd.DataFrame,
    volume_matrix: pd.DataFrame,
    config: BacktestConfig,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """向量化 numpy 循环，逻辑与 ``_apply_multi_asset_execution_and_cost_python`` 等价，通常更快。"""
    cost_model = str(config.portfolio_cost_model)
    if cost_model not in {"simple_bps", "linear_impact", "square_impact"}:
        raise ValueError(f"Unknown portfolio_cost_model: {cost_model}")

    adv_cap = config.portfolio_adv_participation_cap
    if adv_cap is not None and float(adv_cap) <= 0.0:
        raise ValueError("portfolio_adv_participation_cap must be > 0 when provided")

    target_arr = target_weights.to_numpy(dtype=float)
    close_arr = close_matrix.to_numpy(dtype=float)
    volume_arr = volume_matrix.to_numpy(dtype=float)

    n_bars, n_assets = target_arr.shape
    executed_arr = np.zeros((n_bars, n_assets), dtype=float)
    turnover_arr = np.zeros(n_bars, dtype=float)
    cost_arr = np.zeros(n_bars, dtype=float)
    participation_arr = np.zeros(n_bars, dtype=float)

    prev = np.zeros(n_assets, dtype=float)
    min_trade_weight = max(0.0, float(config.portfolio_min_trade_weight))
    commission_rate = float(config.portfolio_commission_bps) / 10_000.0
    spread_rate = float(config.portfolio_spread_bps) / 10_000.0
    impact_coeff = max(0.0, float(config.portfolio_impact_coeff))
    initial_cash = max(float(config.initial_cash), 1e-12)
    half_turnover = bool(config.portfolio_half_turnover)

    for i in range(n_bars):
        desired = target_arr[i]
        delta = desired - prev

        if min_trade_weight > 0.0:
            delta = np.where(np.abs(delta) >= min_trade_weight, delta, 0.0)

        if adv_cap is None:
            cap = np.full(n_assets, np.inf, dtype=float)
            delta_eff = delta
            part_by_symbol = np.zeros(n_assets, dtype=float)
        else:
            cap = np.maximum(close_arr[i] * volume_arr[i], 0.0) * float(adv_cap) / initial_cash
            cap = np.nan_to_num(cap, nan=0.0, posinf=0.0, neginf=0.0)
            clipped = np.clip(delta, -cap, cap)
            delta_eff = np.where(cap > 0.0, clipped, 0.0)
            part_by_symbol = np.where(cap > 0.0, np.abs(delta_eff) / cap, 0.0)

        new_weight = prev + delta_eff
        executed_arr[i] = new_weight

        bar_turnover = float(np.abs(delta_eff).sum())
        if half_turnover:
            bar_turnover *= 0.5
        turnover_arr[i] = bar_turnover

        base_cost = bar_turnover * (commission_rate + spread_rate)
        if cost_model == "simple_bps":
            impact_cost = 0.0
        elif cost_model == "linear_impact":
            impact_cost = float((np.abs(delta_eff) * part_by_symbol).sum()) * impact_coeff
        else:
            impact_cost = float((np.abs(delta_eff) * (part_by_symbol**2)).sum()) * impact_coeff

        cost_arr[i] = float(base_cost + impact_cost)
        participation_arr[i] = float(part_by_symbol.max()) if n_assets > 0 else 0.0
        prev = new_weight

    return (
        pd.DataFrame(executed_arr, index=target_weights.index, columns=target_weights.columns),
        pd.Series(turnover_arr, index=target_weights.index, dtype=float),
        pd.Series(cost_arr, index=target_weights.index, dtype=float),
        pd.Series(participation_arr, index=target_weights.index, dtype=float),
    )


def _get_multi_asset_numba_kernel():
    """延迟编译并缓存 ``@njit`` 内核；无 numba 时返回 None，由上层回退 numpy。"""
    global _MULTI_ASSET_NUMBA_KERNEL

    if _MULTI_ASSET_NUMBA_KERNEL is not None:
        return _MULTI_ASSET_NUMBA_KERNEL

    try:
        from numba import njit  # type: ignore
    except Exception:
        _MULTI_ASSET_NUMBA_KERNEL = None
        return None

    @njit(cache=True)
    def _kernel(
        target_arr: np.ndarray,
        close_arr: np.ndarray,
        volume_arr: np.ndarray,
        min_trade_weight: float,
        commission_rate: float,
        spread_rate: float,
        impact_coeff: float,
        initial_cash: float,
        half_turnover: bool,
        adv_cap_value: float,
        use_adv_cap: bool,
        cost_model_code: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n_bars, n_assets = target_arr.shape
        executed_arr = np.zeros((n_bars, n_assets), dtype=np.float64)
        turnover_arr = np.zeros(n_bars, dtype=np.float64)
        cost_arr = np.zeros(n_bars, dtype=np.float64)
        participation_arr = np.zeros(n_bars, dtype=np.float64)

        prev = np.zeros(n_assets, dtype=np.float64)

        for i in range(n_bars):
            max_participation = 0.0
            bar_turnover_abs = 0.0
            impact_linear_sum = 0.0
            impact_square_sum = 0.0

            for j in range(n_assets):
                desired = target_arr[i, j]
                delta = desired - prev[j]

                if min_trade_weight > 0.0 and abs(delta) < min_trade_weight:
                    delta = 0.0

                part = 0.0
                if use_adv_cap:
                    raw_cap = close_arr[i, j] * volume_arr[i, j] * adv_cap_value / initial_cash
                    if not np.isfinite(raw_cap) or raw_cap <= 0.0:
                        cap = 0.0
                    else:
                        cap = raw_cap

                    if cap <= 0.0:
                        delta_eff = 0.0
                    else:
                        if delta > cap:
                            delta_eff = cap
                        elif delta < -cap:
                            delta_eff = -cap
                        else:
                            delta_eff = delta
                        part = abs(delta_eff) / cap
                else:
                    delta_eff = delta

                new_weight = prev[j] + delta_eff
                executed_arr[i, j] = new_weight
                prev[j] = new_weight

                abs_delta = abs(delta_eff)
                bar_turnover_abs += abs_delta

                if part > max_participation:
                    max_participation = part

                if cost_model_code == 1:
                    impact_linear_sum += abs_delta * part
                elif cost_model_code == 2:
                    impact_square_sum += abs_delta * part * part

            bar_turnover = bar_turnover_abs * 0.5 if half_turnover else bar_turnover_abs
            turnover_arr[i] = bar_turnover

            base_cost = bar_turnover * (commission_rate + spread_rate)
            if cost_model_code == 1:
                impact_cost = impact_linear_sum * impact_coeff
            elif cost_model_code == 2:
                impact_cost = impact_square_sum * impact_coeff
            else:
                impact_cost = 0.0

            cost_arr[i] = base_cost + impact_cost
            participation_arr[i] = max_participation

        return executed_arr, turnover_arr, cost_arr, participation_arr

    _MULTI_ASSET_NUMBA_KERNEL = _kernel
    return _MULTI_ASSET_NUMBA_KERNEL


def _apply_multi_asset_execution_and_cost_numba(
    *,
    target_weights: pd.DataFrame,
    close_matrix: pd.DataFrame,
    volume_matrix: pd.DataFrame,
    config: BacktestConfig,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """调用 numba 内核；不可用时降级为 ``_apply_multi_asset_execution_and_cost_numpy``。"""
    cost_model = str(config.portfolio_cost_model)
    if cost_model not in {"simple_bps", "linear_impact", "square_impact"}:
        raise ValueError(f"Unknown portfolio_cost_model: {cost_model}")

    adv_cap = config.portfolio_adv_participation_cap
    if adv_cap is not None and float(adv_cap) <= 0.0:
        raise ValueError("portfolio_adv_participation_cap must be > 0 when provided")

    kernel = _get_multi_asset_numba_kernel()
    if kernel is None:
        return _apply_multi_asset_execution_and_cost_numpy(
            target_weights=target_weights,
            close_matrix=close_matrix,
            volume_matrix=volume_matrix,
            config=config,
        )

    target_arr = target_weights.to_numpy(dtype=float)
    close_arr = close_matrix.to_numpy(dtype=float)
    volume_arr = volume_matrix.to_numpy(dtype=float)

    cost_model_code = 0
    if cost_model == "linear_impact":
        cost_model_code = 1
    elif cost_model == "square_impact":
        cost_model_code = 2

    executed_arr, turnover_arr, cost_arr, participation_arr = kernel(
        target_arr,
        close_arr,
        volume_arr,
        max(0.0, float(config.portfolio_min_trade_weight)),
        float(config.portfolio_commission_bps) / 10_000.0,
        float(config.portfolio_spread_bps) / 10_000.0,
        max(0.0, float(config.portfolio_impact_coeff)),
        max(float(config.initial_cash), 1e-12),
        bool(config.portfolio_half_turnover),
        0.0 if adv_cap is None else float(adv_cap),
        adv_cap is not None,
        cost_model_code,
    )

    return (
        pd.DataFrame(executed_arr, index=target_weights.index, columns=target_weights.columns),
        pd.Series(turnover_arr, index=target_weights.index, dtype=float),
        pd.Series(cost_arr, index=target_weights.index, dtype=float),
        pd.Series(participation_arr, index=target_weights.index, dtype=float),
    )


def _apply_multi_asset_execution_and_cost(
    *,
    target_weights: pd.DataFrame,
    close_matrix: pd.DataFrame,
    volume_matrix: pd.DataFrame,
    config: BacktestConfig,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series, dict[str, str]]:
    """根据解析后的内核选择 pandas / numpy / numba 实现，并返回 requested/resolved 供 summary。"""
    requested_engine, resolved_engine = _resolve_portfolio_execution_engine(config)

    if resolved_engine == "python":
        executed_weights, turnover, cost_return, participation = _apply_multi_asset_execution_and_cost_python(
            target_weights=target_weights,
            close_matrix=close_matrix,
            volume_matrix=volume_matrix,
            config=config,
        )
    elif resolved_engine == "numpy":
        executed_weights, turnover, cost_return, participation = _apply_multi_asset_execution_and_cost_numpy(
            target_weights=target_weights,
            close_matrix=close_matrix,
            volume_matrix=volume_matrix,
            config=config,
        )
    else:
        executed_weights, turnover, cost_return, participation = _apply_multi_asset_execution_and_cost_numba(
            target_weights=target_weights,
            close_matrix=close_matrix,
            volume_matrix=volume_matrix,
            config=config,
        )

    return executed_weights, turnover, cost_return, participation, {
        "requested": requested_engine,
        "resolved": resolved_engine,
    }


def run_single_asset_backtest(
    *,
    ohlcv: pd.DataFrame | None = None,
    target_position: pd.Series | pd.DataFrame | None = None,
    config: BacktestConfig | None = None,
    strategy_name: str = "target_position",
    strategy_version: str | None = None,
    strategy_params: dict | None = None,
    benchmark_return: pd.Series | None = None,
    avg_daily_volume: float | None = None,
) -> dict:
    """单标的回测：加载/规范化 OHLCV → 校验对齐目标仓位（含 ``target_lag_bars``）→ Cerebro 运行策略 → 报告。

    可选融券近似：在 ``borrow_rate_annual>0`` 时对权益序列做事后扣减（非逐笔融券仿真）。
    """
    try:
        import backtrader as bt
    except ImportError as exc:  # pragma: no cover
        raise ImportError("run_single_asset_backtest requires backtrader. Install with factor-engine[backtest].") from exc

    config = config or BacktestConfig()

    if config.strict_real_data and ohlcv is not None:
        raise ValueError("strict_real_data=True requires loading OHLCV from config data_root; inline ohlcv is disabled")

    if ohlcv is None:
        feed_frame = _normalize_ohlcv_frame(load_ohlcv_from_config(config), max_rows=config.max_rows)
    else:
        feed_frame = _normalize_ohlcv_frame(ohlcv, max_rows=config.max_rows)

    registry = build_strategy_registry(bt)
    spec = registry.get(strategy_name, strategy_version)
    use_target_position = spec.name == "target_position"

    if use_target_position:
        if target_position is None:
            raise ValueError("target_position is required for strategy 'target_position'")
        canonical_target = validate_target_position(
            target_position,
            strict=True,
            enforce_bounds=config.enforce_target_bounds,
        )
        aligned_target = align_target_position_to_index(canonical_target, feed_frame.index)

        # 引擎级机械滞后：在已与行情对齐的序列上再 shift，防双重滞后需与因子侧约定一致
        lag = int(config.target_lag_bars)
        if lag < 0:
            raise ValueError("target_lag_bars must be >= 0")
        if lag:
            aligned_target = aligned_target.shift(lag).fillna(0.0).astype(float)
    else:
        aligned_target = pd.Series(0.0, index=feed_frame.index, name="target_position", dtype=float)

    include_trade_ledger = bool(config.include_trade_ledger or config.metrics_profile == "industrial")

    runtime_params = dict(spec.default_params)
    runtime_params.update(strategy_params or {})
    if use_target_position:
        runtime_params["target_series"] = aligned_target
        runtime_params["target_values"] = aligned_target.to_numpy(dtype=float)
        runtime_params.setdefault("rebalance_threshold", float(config.rebalance_threshold))
        runtime_params.setdefault("allow_short", bool(config.allow_short))
        runtime_params.setdefault("short_margin_requirement", float(config.short_margin_requirement))
    runtime_params.setdefault("include_trade_ledger", include_trade_ledger)
    strategy_instance_id = uuid.uuid4().hex

    strategy_summary_params = dict(spec.default_params)
    strategy_summary_params.update(strategy_params or {})
    if use_target_position:
        strategy_summary_params.setdefault("rebalance_threshold", float(config.rebalance_threshold))
        strategy_summary_params.setdefault("allow_short", bool(config.allow_short))
        strategy_summary_params.setdefault("short_margin_requirement", float(config.short_margin_requirement))
        strategy_summary_params.setdefault("target_lag_bars", int(config.target_lag_bars))
    strategy_summary_params["include_trade_ledger"] = include_trade_ledger

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(dataname=feed_frame[["open", "high", "low", "close", "volume"]])
    cerebro.adddata(data)

    cerebro.broker.setcash(float(config.initial_cash))
    cerebro.broker.setcommission(commission=float(config.commission))
    if config.slippage_perc > 0:
        cerebro.broker.set_slippage_perc(perc=float(config.slippage_perc))

    cerebro.addstrategy(spec.strategy_cls, **runtime_params)

    strategies = cerebro.run()
    strategy = strategies[0]

    equity_curve = pd.Series(strategy.trace.equity_curve, index=pd.DatetimeIndex(strategy.trace.timestamps), name="equity")
    realized_position = pd.Series(
        strategy.trace.realized_position,
        index=pd.DatetimeIndex(strategy.trace.timestamps),
        name="realized_position",
    )
    target_used = pd.Series(strategy.trace.target_position, index=pd.DatetimeIndex(strategy.trace.timestamps), name="target_position")

    commission_paid_total = float(strategy.trace.commission_paid)
    # 融券成本：按空头暴露 × 年化借券率近似摊到每根 bar，并回推权益曲线（研究用）
    if config.borrow_rate_annual > 0 and len(equity_curve):
        ann = max(annualization_factor(equity_curve.index), 1e-12)
        short_exposure = realized_position.clip(upper=0.0).abs().astype(float)
        borrow_rate_per_bar = float(config.borrow_rate_annual) / ann
        borrow_return = short_exposure * borrow_rate_per_bar

        equity_prev = equity_curve.shift(1).fillna(float(config.initial_cash)).astype(float)
        borrow_cost = (equity_prev * borrow_return).astype(float)
        commission_paid_total += float(borrow_cost.sum())

        adjusted_period_return = equity_curve.pct_change().fillna(0.0) - borrow_return
        equity_curve = (1.0 + adjusted_period_return).cumprod() * float(config.initial_cash)

    report = build_backtest_report(
        equity_curve=equity_curve,
        realized_position=realized_position,
        target_position=target_used,
        commission_paid=commission_paid_total,
        trades=int(strategy.trace.trades),
        config=config,
        strategy_metadata={
            "strategy_name": spec.name,
            "strategy_version": spec.version,
            "strategy_params": strategy_summary_params,
            "strategy_instance_id": strategy_instance_id,
        },
        benchmark_return=benchmark_return,
        avg_daily_volume=avg_daily_volume,
        trade_ledger=strategy.trace.trade_ledger if include_trade_ledger else None,
        reproducibility_metadata={
            **_build_reproducibility_metadata(
                mode="single",
                data_fingerprint=(
                    _single_asset_fingerprint(feed_frame, aligned_target) if config.include_data_fingerprint else None
                ),
            ),
            **_build_timing_audit_metadata(mode="single", config=config),
        },
    )

    return report


def _normalize_ohlcv_frame(frame: pd.DataFrame, *, max_rows: int | None) -> pd.DataFrame:
    """统一索引为无时区 DatetimeIndex，缺 volume 补 0，可选截断最近 max_rows 根。"""
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLCV missing required columns: {sorted(missing)}")

    out = frame.copy().sort_index()
    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("ohlcv index must be DatetimeIndex")

    out.index = pd.to_datetime(out.index, utc=True, errors="raise").tz_convert(None)
    if "volume" not in out.columns:
        out["volume"] = 0.0

    if max_rows is not None and max_rows > 0:
        out = out.tail(int(max_rows))

    return out[["open", "high", "low", "close", "volume"]]


def _load_multi_asset_ohlcv(
    *,
    ohlcv_by_symbol: dict[str, pd.DataFrame] | None,
    symbols: list[str] | None,
    config: BacktestConfig,
) -> dict[str, pd.DataFrame]:
    """加载各标的 OHLCV，取时间索引交集并 reindex，保证多标的 bar 对齐。"""
    if config.strict_real_data and ohlcv_by_symbol is not None:
        raise ValueError("strict_real_data=True requires loading OHLCV from config data_root; inline ohlcv_by_symbol is disabled")

    if ohlcv_by_symbol is not None:
        feeds = {
            str(symbol): _normalize_ohlcv_frame(frame, max_rows=config.max_rows)
            for symbol, frame in ohlcv_by_symbol.items()
        }
    else:
        if not symbols:
            raise ValueError("symbols is required when ohlcv_by_symbol is not provided")
        feeds = {}
        for symbol in symbols:
            cfg = replace(config, symbol=str(symbol))
            feeds[str(symbol)] = _normalize_ohlcv_frame(load_ohlcv_from_config(cfg), max_rows=config.max_rows)

    if not feeds:
        raise ValueError("At least one symbol OHLCV feed is required")

    common_index: pd.DatetimeIndex | None = None
    for frame in feeds.values():
        common_index = frame.index if common_index is None else common_index.intersection(frame.index)

    if common_index is None or len(common_index) == 0:
        raise ValueError("No overlapping timestamps across ohlcv_by_symbol feeds")

    return {symbol: frame.reindex(common_index) for symbol, frame in feeds.items()}


def run_multi_asset_backtest(
    *,
    ohlcv_by_symbol: dict[str, pd.DataFrame] | None = None,
    target_weights: pd.Series | pd.DataFrame,
    config: BacktestConfig | None = None,
    symbols: list[str] | None = None,
) -> dict:
    """多标的组合回测：矩阵化目标权重 → 执行与成本 → 滞后权重 × 资产收益 − 成本 → 权益与报告。"""
    config = config or BacktestConfig(portfolio_mode="multi")

    feeds = _load_multi_asset_ohlcv(
        ohlcv_by_symbol=ohlcv_by_symbol,
        symbols=symbols,
        config=config,
    )

    ordered_symbols = symbols or list(feeds.keys())
    ordered_symbols = [str(s) for s in ordered_symbols]

    base_index = next(iter(feeds.values())).index
    aligned_weights = align_target_weights_to_index(
        validate_target_weights(
            target_weights,
            strict=True,
            enforce_bounds=config.enforce_target_bounds,
        ),
        base_index,
        ordered_symbols,
    )
    weight_matrix = aligned_weights.unstack("symbol").reindex(index=base_index, columns=ordered_symbols).fillna(0.0)

    close_matrix = pd.concat({symbol: frame["close"] for symbol, frame in feeds.items()}, axis=1)
    close_matrix = close_matrix.reindex(index=base_index, columns=ordered_symbols)
    volume_matrix = pd.concat({symbol: frame["volume"] for symbol, frame in feeds.items()}, axis=1)
    volume_matrix = volume_matrix.reindex(index=base_index, columns=ordered_symbols).fillna(0.0)
    if close_matrix.isna().any().any():
        raise ValueError("Missing close prices after multi-asset alignment")

    # 各标的收益率（第一根为 0）；组合会计在下一行之后才 shift，避免前视
    asset_return = close_matrix.pct_change().fillna(0.0)
    executed_weights, turnover, cost_return, participation, execution_engine_meta = _apply_multi_asset_execution_and_cost(
        target_weights=weight_matrix,
        close_matrix=close_matrix,
        volume_matrix=volume_matrix,
        config=config,
    )

    w_lag = int(config.portfolio_weight_lag_bars)
    if w_lag < 1:
        raise ValueError("portfolio_weight_lag_bars must be >= 1 to avoid lookahead in portfolio returns")
    realized_weights = executed_weights.shift(w_lag).fillna(0.0)

    gross_return = (realized_weights * asset_return).sum(axis=1)
    # cost_return 为每 bar 收益率口径；乘上一期权益得到金额成本序列（与单标的 commission 展示一致）
    net_return = gross_return - cost_return

    initial_cash = float(config.initial_cash)
    equity_curve = (1.0 + net_return).cumprod() * initial_cash
    equity_prev = equity_curve.shift(1).fillna(initial_cash)
    portfolio_cost = cost_return * equity_prev

    realized_position = realized_weights.sum(axis=1).astype(float)
    target_position = weight_matrix.sum(axis=1).astype(float)

    report = build_backtest_report(
        equity_curve=equity_curve.astype(float),
        realized_position=realized_position,
        target_position=target_position,
        commission_paid=float(portfolio_cost.sum()),
        trades=int((turnover > 1e-12).sum()),
        config=config,
        strategy_metadata={
            "strategy_name": "portfolio_target_weights",
            "strategy_version": "1.0",
            "strategy_params": {
                "portfolio_cost_model": config.portfolio_cost_model,
                "portfolio_commission_bps": float(config.portfolio_commission_bps),
                "portfolio_spread_bps": float(config.portfolio_spread_bps),
                "portfolio_impact_coeff": float(config.portfolio_impact_coeff),
                "portfolio_adv_participation_cap": (
                    None
                    if config.portfolio_adv_participation_cap is None
                    else float(config.portfolio_adv_participation_cap)
                ),
                "portfolio_min_trade_weight": float(config.portfolio_min_trade_weight),
                "portfolio_half_turnover": bool(config.portfolio_half_turnover),
                "portfolio_weight_lag_bars": int(config.portfolio_weight_lag_bars),
                "portfolio_execution_engine": str(config.portfolio_execution_engine),
                "symbols": ordered_symbols,
            },
            "strategy_instance_id": uuid.uuid4().hex,
        },
        reproducibility_metadata={
            **_build_reproducibility_metadata(
                mode="multi",
                data_fingerprint=_multi_asset_fingerprint(feeds, executed_weights),
            ),
            **_build_timing_audit_metadata(mode="multi", config=config),
            "execution_engine_requested": execution_engine_meta["requested"],
            "execution_engine_resolved": execution_engine_meta["resolved"],
        },
    )

    report["returns"]["portfolio_turnover"] = turnover.astype(float)
    report["returns"]["portfolio_cost"] = portfolio_cost.astype(float)
    report["returns"]["portfolio_participation"] = participation.astype(float)
    report["metrics"]["portfolio_turnover_total"] = float(turnover.sum())
    report["metrics"]["portfolio_cost_total"] = float(portfolio_cost.sum())
    report["metrics"]["portfolio_participation_max"] = float(participation.max()) if len(participation) else 0.0

    return report
