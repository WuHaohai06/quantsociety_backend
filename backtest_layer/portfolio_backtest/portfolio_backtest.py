import os
import json
from datetime import datetime

import numpy as np
import pandas as pd

from workspace_paths import default_portfolio_backtest_root


class PortfolioBacktestArtifactBuilder:
    """
    宽表 / 向量化版本

    输入仍支持长表： !!!!!!!!!!!!!!!!!!!!!!!!!
        holdings_df:
            - trade_date
            - symbol
            - weight

        kline_df:
            - trade_date
            - symbol
            - close

    内部统一转成宽表：
        weight_wide: index=date, columns=symbol
        price_wide:  index=date, columns=symbol
        asset_return_wide: next_close / close - 1

    核心组合收益计算：
        signal_weight_t 先整体下移一行，作为 t+1 生效的 execution_weight
        portfolio_return_t = sum_i(execution_weight_{t,i} * asset_return_{t,i})

    输出：
        - returns.csv
        - metrics.csv
        - summary.csv
        - metadata.json
    """

    def __init__(
        self,
        annualization=252,
        return_window=1,
        fee_rate=0.0003,
        slippage_rate=0.0002,
        date_col="trade_date",
        symbol_col="symbol",
        weight_col="weight",
        price_col="close",
        tradable_df=None,
        tradable_date_col="trade_date",
        tradable_symbol_col="symbol",
        tradable_flag_col="is_tradable",
        output_root=None,
        strategy_name="default_strategy",
        benchmark_df=None,
        benchmark_date_col="trade_date",
        benchmark_return_col="benchmark_return",
    ):
        """初始化回测器的全局参数、列名映射和可选附加数据。"""
        self.annualization = annualization
        self.return_window = return_window
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate

        self.date_col = date_col
        self.symbol_col = symbol_col
        self.weight_col = weight_col
        self.price_col = price_col

        self.tradable_df = tradable_df
        self.tradable_date_col = tradable_date_col
        self.tradable_symbol_col = tradable_symbol_col
        self.tradable_flag_col = tradable_flag_col

        self.output_root = output_root or str(default_portfolio_backtest_root())
        self.strategy_name = strategy_name

        self.benchmark_df = benchmark_df
        self.benchmark_date_col = benchmark_date_col
        self.benchmark_return_col = benchmark_return_col

    # =========================================================
    # 对外主入口
    # =========================================================
    def build(self, holdings_df: pd.DataFrame, kline_df: pd.DataFrame, run_name=None):
        """执行完整回测流程，并把结果表与元数据写入输出目录。"""
        # 第一步：清洗输入长表，统一日期/字段类型，并去掉关键字段缺失的数据。
        holdings_df = self._prepare_holdings_long(holdings_df.copy())
        kline_df = self._prepare_kline_long(kline_df.copy())

        # 第二步：把长表转换成宽表，方便后面做矩阵化对齐和向量化计算。
        weight_wide = self._build_weight_wide(holdings_df)

        # 第三步：将 t 日信号整体下移到 t+1 生效，避免未来函数。
        weight_wide = self._shift_weight_wide_for_execution(weight_wide)
        price_wide = self._build_price_wide(kline_df)
        tradable_wide = self._build_tradable_wide(price_wide)

        # 第四步：把权重、价格、可交易状态对齐到统一的日期和股票维度。
        aligned = self._build_aligned_panels(weight_wide, price_wide, tradable_wide)

        # 第五步：过滤不可交易或无法计算收益的单元格，得到最终可用于收益计算的面板。
        aligned = self._apply_tradable_filter(aligned)

        # 第六步：基于对齐后的宽表计算逐日收益、换手、覆盖率和净值曲线。
        returns_df = self._build_returns(aligned)

        # 第七步：如果提供了基准，则补充基准收益、超额收益和对应净值。
        returns_df = self._attach_benchmark_if_needed(returns_df)

        # 第八步：补充回撤、胜负日标记等更便于分析的衍生列。
        returns_df = self._enrich_returns(returns_df)

        # 第九步：从日收益序列和宽表面板中汇总风险收益指标与摘要信息。
        metrics_df = self._build_metrics(returns_df, aligned)
        summary_df = self._build_summary(metrics_df)
        metadata = self._build_metadata(
            holdings_df=holdings_df,
            kline_df=kline_df,
            aligned=aligned,
            returns_df=returns_df,
            metrics_df=metrics_df,
            run_name=run_name,
        )

        # 第十步：创建输出目录，并把明细表、汇总表和元数据落盘。
        out_dir = self._make_output_dir(run_name)
        os.makedirs(out_dir, exist_ok=True)

        returns_path = os.path.join(out_dir, "returns.csv")
        metrics_path = os.path.join(out_dir, "metrics.csv")
        summary_path = os.path.join(out_dir, "summary.csv")
        metadata_path = os.path.join(out_dir, "metadata.json")

        returns_df.to_csv(returns_path, index=False, encoding="utf-8-sig")
        metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
        summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return {
            "output_dir": out_dir,
            "returns_path": returns_path,
            "metrics_path": metrics_path,
            "summary_path": summary_path,
            "metadata_path": metadata_path,
            "returns_df": returns_df,
            "metrics_df": metrics_df,
            "summary_df": summary_df,
            "metadata": metadata,
        }

    # =========================================================
    # 数据准备：长表
    # =========================================================
    def _prepare_holdings_long(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗持仓长表，确保日期、标的和权重字段可用于后续透视。"""
        required = [self.date_col, self.symbol_col, self.weight_col]
        self._check_required_columns(df, required, "holdings_df")

        df[self.date_col] = pd.to_datetime(df[self.date_col])
        df[self.symbol_col] = df[self.symbol_col].astype(str)
        df[self.weight_col] = pd.to_numeric(df[self.weight_col], errors="coerce")

        df = df.dropna(subset=[self.date_col, self.symbol_col, self.weight_col])
        df = df.sort_values([self.date_col, self.symbol_col]).reset_index(drop=True)

        return df

    def _prepare_kline_long(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗行情长表，确保价格字段为数值并按标的日期排序。"""
        required = [self.date_col, self.symbol_col, self.price_col]
        self._check_required_columns(df, required, "kline_df")

        df[self.date_col] = pd.to_datetime(df[self.date_col])
        df[self.symbol_col] = df[self.symbol_col].astype(str)
        df[self.price_col] = pd.to_numeric(df[self.price_col], errors="coerce")

        df = df.dropna(subset=[self.date_col, self.symbol_col, self.price_col])
        df = df.sort_values([self.symbol_col, self.date_col]).reset_index(drop=True)

        return df

    def _prepare_tradable_long(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗可交易标记长表，统一成日期-标的-布尔值结构。"""
        required = [self.tradable_date_col, self.tradable_symbol_col, self.tradable_flag_col]
        self._check_required_columns(df, required, "tradable_df")

        df[self.tradable_date_col] = pd.to_datetime(df[self.tradable_date_col])
        df[self.tradable_symbol_col] = df[self.tradable_symbol_col].astype(str)
        df[self.tradable_flag_col] = df[self.tradable_flag_col].fillna(False).astype(bool)

        df = df.dropna(subset=[self.tradable_date_col, self.tradable_symbol_col])
        df = df.sort_values([self.tradable_date_col, self.tradable_symbol_col]).reset_index(drop=True)

        return df

    # =========================================================
    # 宽表构建
    # =========================================================
    def _build_weight_wide(self, holdings_df: pd.DataFrame) -> pd.DataFrame:
        """把持仓长表透视成日期 x 标的的权重宽表。"""
        # 同一天同一 symbol 若重复，直接求和
        weight_wide = holdings_df.pivot_table(
            index=self.date_col,
            columns=self.symbol_col,
            values=self.weight_col,
            aggfunc="sum",
            fill_value=0.0,
        )

        weight_wide = weight_wide.sort_index()
        weight_wide.columns.name = None
        return weight_wide

    def _shift_weight_wide_for_execution(self, weight_wide: pd.DataFrame) -> pd.DataFrame:
        """将信号权重整体后移一个交易步长，使其在下一期收益上生效。"""
        # 避免未来函数：t 日生成的信号权重在 t+1 日收益上生效
        return weight_wide.shift(1, fill_value=0.0)

    def _build_price_wide(self, kline_df: pd.DataFrame) -> pd.DataFrame:
        """把行情长表透视成日期 x 标的的价格宽表。"""
        # 同一天同一 symbol 若重复，取最后一个有效值更合理；这里用 pivot_table + last
        price_wide = kline_df.pivot_table(
            index=self.date_col,
            columns=self.symbol_col,
            values=self.price_col,
            aggfunc="last",
        )

        price_wide = price_wide.sort_index()
        price_wide.columns.name = None
        return price_wide

    def _build_tradable_wide(self, price_wide: pd.DataFrame) -> pd.DataFrame:
        """生成可交易宽表，优先使用外部输入，否则退化为基于价格可得性的默认判断。"""
        if self.tradable_df is None:
            return self._build_default_tradable_wide(price_wide)

        tradable_df = self._prepare_tradable_long(self.tradable_df.copy())
        tradable_wide = tradable_df.pivot_table(
            index=self.tradable_date_col,
            columns=self.tradable_symbol_col,
            values=self.tradable_flag_col,
            aggfunc="last",
            fill_value=False,
        )

        tradable_wide = tradable_wide.sort_index().astype(bool)
        tradable_wide.columns.name = None
        return tradable_wide

    def _build_default_tradable_wide(self, price_wide: pd.DataFrame) -> pd.DataFrame:
        """在未提供可交易标记时，用未来收益是否可计算来近似定义可交易状态。"""
        asset_return_wide = self._calculate_asset_return_wide(price_wide)
        return asset_return_wide.notna()

    def _calculate_asset_return_wide(self, price_wide: pd.DataFrame) -> pd.DataFrame:
        """根据价格宽表计算逐资产未来 return_window 期收益。"""
        return price_wide.shift(-self.return_window) / price_wide - 1.0

    def _build_aligned_panels(
        self,
        weight_wide: pd.DataFrame,
        price_wide: pd.DataFrame,
        tradable_wide: pd.DataFrame,
    ) -> dict:
        """把权重、价格、可交易状态扩展并对齐到统一的日期和标的全集。"""
        asset_return_wide = self._calculate_asset_return_wide(price_wide)

        # 日期与列统一对齐
        all_dates = (
            weight_wide.index
            .union(asset_return_wide.index)
            .union(tradable_wide.index)
            .sort_values()
        )
        all_symbols = (
            weight_wide.columns
            .union(asset_return_wide.columns)
            .union(tradable_wide.columns)
        )

        weight_aligned = weight_wide.reindex(index=all_dates, columns=all_symbols, fill_value=0.0)
        price_aligned = price_wide.reindex(index=all_dates, columns=all_symbols)
        asset_return_aligned_raw = asset_return_wide.reindex(index=all_dates, columns=all_symbols)
        tradable_aligned = tradable_wide.reindex(index=all_dates, columns=all_symbols, fill_value=False).astype(bool)

        return {
            "weight_wide": weight_wide,
            "price_wide": price_wide,
            "tradable_wide": tradable_wide,
            "weight_aligned": weight_aligned,
            "price_aligned": price_aligned,
            "tradable_aligned": tradable_aligned,
            "asset_return_wide_raw": asset_return_aligned_raw,
        }

    def _apply_tradable_filter(self, aligned: dict) -> dict:
        """
        根据可交易约束和价格可得性过滤资产收益面板，并生成逐资产收益贡献。

        tradable_aligned 是基于价格数据计算的默认值，若用户提供了 tradable_df 则覆盖默认值
        price_based_tradable 是基于价格数据计算的是否有有效价格的掩码
        tradable = tradable_aligned & price_based_tradable
        实际上只有tradable是无法交易的标的 price_based_tradable是无法计算收益的标的 两者都需要过滤掉
        """
        asset_return_raw = aligned["asset_return_wide_raw"]
        tradable = aligned["tradable_aligned"]

        price_based_tradable = asset_return_raw.notna()
        effective_tradable = tradable & price_based_tradable
        asset_return_filtered_raw = asset_return_raw.where(effective_tradable)
        asset_return_filtered = asset_return_filtered_raw.fillna(0.0)
        pnl_contrib_wide = aligned["weight_aligned"].mul(asset_return_filtered)

        out = dict(aligned)
        out.update(
            {
                "price_based_tradable_mask": price_based_tradable,
                "asset_return_valid_mask": effective_tradable,
                "asset_return_wide_raw": asset_return_filtered_raw,
                "asset_return_wide": asset_return_filtered,
                "pnl_contrib_wide": pnl_contrib_wide,
            }
        )
        return out

    # =========================================================
    # 收益序列构建：向量化
    # =========================================================
    def _build_returns(self, aligned: dict) -> pd.DataFrame:
        """从对齐后的宽表面板中生成逐日收益、换手、风险暴露和净值序列。"""
        weight = aligned["weight_aligned"]
        asset_ret = aligned["asset_return_wide"]
        asset_ret_raw = aligned["asset_return_wide_raw"]
        pnl_contrib = aligned["pnl_contrib_wide"]

        # 组合毛收益
        gross_return = pnl_contrib.sum(axis=1)

        turnover = self._calculate_turnover(weight)

        holdings_stats = self._calculate_holdings_stats(weight)

        coverage_stats = self._calculate_asset_return_coverage(weight, asset_ret_raw)

        # 成本
        trading_cost = turnover.fillna(0.0) * (self.fee_rate + self.slippage_rate)
        net_return = gross_return - trading_cost

        returns_df = pd.DataFrame({
            self.date_col: weight.index,
            "gross_return": gross_return.values,
            "net_return": net_return.values,
            "trading_cost": trading_cost.values,
            "turnover": turnover.values,
            "holdings_count": holdings_stats["holdings_count"].values,
            "long_exposure": holdings_stats["long_exposure"].values,
            "short_exposure": holdings_stats["short_exposure"].values,
            "net_exposure": holdings_stats["net_exposure"].values,
            "gross_exposure": holdings_stats["gross_exposure"].values,
            "holding_cells": coverage_stats["holding_cells"].values,
            "valid_holding_cells": coverage_stats["valid_holding_cells"].values,
            "asset_return_coverage": coverage_stats["asset_return_coverage"].values,
        })

        returns_df = returns_df.sort_values(self.date_col).reset_index(drop=True)
        returns_df["nav_gross"] = (1.0 + returns_df["gross_return"]).cumprod()
        returns_df["nav_net"] = (1.0 + returns_df["net_return"]).cumprod()

        return returns_df

    def _attach_benchmark_if_needed(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        """若提供基准收益序列，则合并到回测结果并计算超额表现。"""
        if self.benchmark_df is None:
            return returns_df

        benchmark_df = self.benchmark_df.copy()
        required = [self.benchmark_date_col, self.benchmark_return_col]
        self._check_required_columns(benchmark_df, required, "benchmark_df")

        benchmark_df[self.benchmark_date_col] = pd.to_datetime(benchmark_df[self.benchmark_date_col])
        benchmark_df[self.benchmark_return_col] = pd.to_numeric(
            benchmark_df[self.benchmark_return_col], errors="coerce"
        )

        if self.benchmark_date_col != self.date_col:
            benchmark_df = benchmark_df.rename(columns={self.benchmark_date_col: self.date_col})

        benchmark_df = benchmark_df[[self.date_col, self.benchmark_return_col]].drop_duplicates(
            subset=[self.date_col], keep="last"
        )

        out = returns_df.merge(benchmark_df, on=self.date_col, how="left")
        out[self.benchmark_return_col] = out[self.benchmark_return_col].fillna(0.0)
        out["benchmark_nav"] = (1.0 + out[self.benchmark_return_col]).cumprod()
        out["excess_return"] = out["net_return"] - out[self.benchmark_return_col]
        out["excess_nav"] = (1.0 + out["excess_return"]).cumprod()
        return out

    def _enrich_returns(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        """为收益表补充回撤和胜负日等分析辅助字段。"""
        df = returns_df.copy()

        df["drawdown_net"] = df["nav_net"] / df["nav_net"].cummax() - 1.0
        df["drawdown_gross"] = df["nav_gross"] / df["nav_gross"].cummax() - 1.0

        if "benchmark_nav" in df.columns:
            df["benchmark_drawdown"] = df["benchmark_nav"] / df["benchmark_nav"].cummax() - 1.0

        df["is_win_day"] = (df["net_return"] > 0).astype(int)
        df["is_loss_day"] = (df["net_return"] < 0).astype(int)

        return df

    # =========================================================
    # 指标计算
    # =========================================================
    def _build_metrics(self, returns_df: pd.DataFrame, aligned: dict) -> pd.DataFrame:
        """基于收益曲线、换手和覆盖率等信息汇总核心绩效指标。"""
        net_ret = returns_df["net_return"]
        gross_ret = returns_df["gross_return"]
        nav_net = returns_df["nav_net"]
        nav_gross = returns_df["nav_gross"]

        trade_days = len(returns_df)
        metrics_map = {}

        total_return = nav_net.iloc[-1] - 1.0 if trade_days > 0 else np.nan
        gross_total_return = nav_gross.iloc[-1] - 1.0 if trade_days > 0 else np.nan

        annual_return = self._annualize_return(nav_net.iloc[-1], trade_days)
        gross_annual_return = self._annualize_return(nav_gross.iloc[-1], trade_days)

        annual_vol = self._annualize_vol(net_ret)
        gross_annual_vol = self._annualize_vol(gross_ret)

        sharpe = self._sharpe(net_ret)
        gross_sharpe = self._sharpe(gross_ret)
        sortino = self._sortino(net_ret)

        max_dd = self._max_drawdown(nav_net)
        gross_max_dd = self._max_drawdown(nav_gross)
        calmar = self._calmar(annual_return, max_dd)

        daily_win_rate = self._win_rate(net_ret)
        weekly_win_rate = self._period_win_rate(returns_df, freq="W", return_col="net_return")
        monthly_win_rate = self._period_win_rate(returns_df, freq="M", return_col="net_return")

        avg_daily_return = net_ret.mean()
        median_daily_return = net_ret.median()
        best_day = net_ret.max()
        worst_day = net_ret.min()

        downside_vol = self._downside_vol(net_ret)
        var_95 = net_ret.quantile(0.05) if trade_days > 0 else np.nan
        cvar_95 = net_ret[net_ret <= var_95].mean() if trade_days > 0 else np.nan

        max_dd_duration = self._max_drawdown_duration(nav_net)
        profit_loss_ratio = self._profit_loss_ratio(net_ret)

        longest_win_streak = self._longest_streak((net_ret > 0).astype(int))
        longest_loss_streak = self._longest_streak((net_ret < 0).astype(int))

        avg_turnover = returns_df["turnover"].mean()
        median_turnover = returns_df["turnover"].median()
        max_turnover = returns_df["turnover"].max()
        avg_holding_count = returns_df["holdings_count"].mean()

        avg_long_exposure = returns_df["long_exposure"].mean()
        avg_short_exposure = returns_df["short_exposure"].mean()
        avg_net_exposure = returns_df["net_exposure"].mean()
        avg_gross_exposure = returns_df["gross_exposure"].mean()

        total_cost = returns_df["trading_cost"].sum()
        cost_drag = gross_total_return - total_return if pd.notna(gross_total_return) and pd.notna(total_return) else np.nan

        top5_day_pnl_contribution = self._top_n_pnl_contribution_ratio(net_ret, n=5)

        effective_asset_return_ratio = self._global_effective_asset_return_ratio(aligned["weight_aligned"], aligned["asset_return_wide_raw"])
        avg_daily_asset_return_coverage = returns_df["asset_return_coverage"].mean()

        metrics_map.update(
            {
                "trade_days": trade_days,
                "total_return": total_return,
                "gross_total_return": gross_total_return,
                "annual_return": annual_return,
                "gross_annual_return": gross_annual_return,
                "annual_volatility": annual_vol,
                "gross_annual_volatility": gross_annual_vol,
                "sharpe": sharpe,
                "gross_sharpe": gross_sharpe,
                "sortino": sortino,
                "max_drawdown": max_dd,
                "gross_max_drawdown": gross_max_dd,
                "calmar": calmar,
                "daily_win_rate": daily_win_rate,
                "weekly_win_rate": weekly_win_rate,
                "monthly_win_rate": monthly_win_rate,
                "avg_daily_return": avg_daily_return,
                "median_daily_return": median_daily_return,
                "best_day": best_day,
                "worst_day": worst_day,
                "downside_volatility": downside_vol,
                "var_95": var_95,
                "cvar_95": cvar_95,
                "max_drawdown_duration": max_dd_duration,
                "profit_loss_ratio": profit_loss_ratio,
                "longest_win_streak": longest_win_streak,
                "longest_loss_streak": longest_loss_streak,
                "avg_turnover": avg_turnover,
                "median_turnover": median_turnover,
                "max_turnover": max_turnover,
                "avg_holding_count": avg_holding_count,
                "avg_long_exposure": avg_long_exposure,
                "avg_short_exposure": avg_short_exposure,
                "avg_net_exposure": avg_net_exposure,
                "avg_gross_exposure": avg_gross_exposure,
                "total_trading_cost": total_cost,
                "cost_drag": cost_drag,
                "top5_day_pnl_contribution": top5_day_pnl_contribution,
                "effective_asset_return_ratio": effective_asset_return_ratio,
                "avg_daily_asset_return_coverage": avg_daily_asset_return_coverage,
            }
        )

        if self.benchmark_return_col in returns_df.columns:
            benchmark_total_return = returns_df["benchmark_nav"].iloc[-1] - 1.0 if trade_days > 0 else np.nan
            excess_total_return = returns_df["excess_nav"].iloc[-1] - 1.0 if trade_days > 0 else np.nan
            excess_annual_return = self._annualize_return(returns_df["excess_nav"].iloc[-1], trade_days)
            excess_sharpe = self._sharpe(returns_df["excess_return"])
            tracking_error = self._annualize_vol(returns_df["excess_return"])
            information_ratio = (
                excess_annual_return / tracking_error
                if pd.notna(tracking_error) and abs(tracking_error) > 1e-12
                else np.nan
            )

            beta, alpha = self._alpha_beta(
                strategy_returns=returns_df["net_return"],
                benchmark_returns=returns_df[self.benchmark_return_col],
            )

            metrics_map.update(
                {
                    "benchmark_total_return": benchmark_total_return,
                    "excess_total_return": excess_total_return,
                    "excess_annual_return": excess_annual_return,
                    "tracking_error": tracking_error,
                    "information_ratio": information_ratio,
                    "excess_sharpe": excess_sharpe,
                    "beta": beta,
                    "alpha": alpha,
                }
            )

        return self._metrics_map_to_df(metrics_map)

    def _build_summary(self, metrics_df: pd.DataFrame) -> pd.DataFrame:
        """从完整指标表中挑选常用核心指标，形成单行摘要。"""
        metric_map = dict(zip(metrics_df["metric"], metrics_df["value"]))

        summary = {
            "strategy_name": self.strategy_name,
            "trade_days": metric_map.get("trade_days"),
            "total_return": metric_map.get("total_return"),
            "annual_return": metric_map.get("annual_return"),
            "annual_volatility": metric_map.get("annual_volatility"),
            "sharpe": metric_map.get("sharpe"),
            "sortino": metric_map.get("sortino"),
            "calmar": metric_map.get("calmar"),
            "max_drawdown": metric_map.get("max_drawdown"),
            "monthly_win_rate": metric_map.get("monthly_win_rate"),
            "avg_turnover": metric_map.get("avg_turnover"),
            "avg_holding_count": metric_map.get("avg_holding_count"),
            "avg_gross_exposure": metric_map.get("avg_gross_exposure"),
            "cost_drag": metric_map.get("cost_drag"),
            "top5_day_pnl_contribution": metric_map.get("top5_day_pnl_contribution"),
            "effective_asset_return_ratio": metric_map.get("effective_asset_return_ratio"),
            "avg_daily_asset_return_coverage": metric_map.get("avg_daily_asset_return_coverage"),
        }

        return pd.DataFrame([summary])

    def _build_metadata(
        self,
        holdings_df: pd.DataFrame,
        kline_df: pd.DataFrame,
        aligned: dict,
        returns_df: pd.DataFrame,
        metrics_df: pd.DataFrame,
        run_name=None,
    ) -> dict:
        """整理一次回测运行的配置、输入规模和面板统计信息。"""
        weight_wide = aligned["weight_wide"]
        price_wide = aligned["price_wide"]
        weight_aligned = aligned["weight_aligned"]
        asset_return_raw = aligned["asset_return_wide_raw"]

        metadata = {
            "strategy_name": self.strategy_name,
            "run_name": run_name,
            "generated_at": datetime.now().isoformat(),
            "annualization": self.annualization,
            "weight_execution_lag": 1,
            "return_window": self.return_window,
            "fee_rate": self.fee_rate,
            "slippage_rate": self.slippage_rate,
            "date_col": self.date_col,
            "symbol_col": self.symbol_col,
            "weight_col": self.weight_col,
            "price_col": self.price_col,
            "tradable_date_col": self.tradable_date_col,
            "tradable_symbol_col": self.tradable_symbol_col,
            "tradable_flag_col": self.tradable_flag_col,
            "benchmark_date_col": self.benchmark_date_col,
            "benchmark_return_col": self.benchmark_return_col,
            "has_benchmark": self.benchmark_df is not None,
            "has_tradable_df": self.tradable_df is not None,
            "input_summary": {
                "holdings_rows": int(len(holdings_df)),
                "kline_rows": int(len(kline_df)),
                "returns_rows": int(len(returns_df)),
                "metrics_rows": int(len(metrics_df)),
                "holdings_date_min": str(holdings_df[self.date_col].min()) if len(holdings_df) > 0 else None,
                "holdings_date_max": str(holdings_df[self.date_col].max()) if len(holdings_df) > 0 else None,
                "kline_date_min": str(kline_df[self.date_col].min()) if len(kline_df) > 0 else None,
                "kline_date_max": str(kline_df[self.date_col].max()) if len(kline_df) > 0 else None,
                "unique_symbols_in_holdings": int(holdings_df[self.symbol_col].nunique()) if len(holdings_df) > 0 else 0,
                "unique_symbols_in_kline": int(kline_df[self.symbol_col].nunique()) if len(kline_df) > 0 else 0,
            },
            "panel_summary": {
                "weight_wide_shape": [int(weight_wide.shape[0]), int(weight_wide.shape[1])],
                "price_wide_shape": [int(price_wide.shape[0]), int(price_wide.shape[1])],
                "weight_aligned_shape": [int(weight_aligned.shape[0]), int(weight_aligned.shape[1])],
                "asset_return_raw_shape": [int(asset_return_raw.shape[0]), int(asset_return_raw.shape[1])],
                "aligned_dates": int(len(weight_aligned.index)),
                "aligned_symbols": int(len(weight_aligned.columns)),
                "nonzero_weight_cells": int((weight_aligned != 0).sum().sum()),
                "valid_asset_return_cells": int(asset_return_raw.notna().sum().sum()),
                "tradable_true_cells": int(aligned["tradable_aligned"].to_numpy().sum()),
            },
        }
        return metadata

    # =========================================================
    # 工具函数
    # =========================================================
    def _make_output_dir(self, run_name=None):
        """生成本次回测结果的输出目录路径。"""
        run_name = run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.output_root, self.strategy_name, run_name)

    def _check_required_columns(self, df, cols, df_name):
        """检查输入表是否包含必需列，缺失时直接抛出异常。"""
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"{df_name} 缺少必要列: {missing}")

    def _append_metric(self, metrics, name, value):
        """把单个指标转换成基础 Python 类型后追加到指标列表中。"""
        if isinstance(value, (np.integer, np.int64, np.int32)):
            value = int(value)
        elif isinstance(value, (np.floating, np.float32, np.float64)):
            value = float(value) if pd.notna(value) else np.nan
        metrics.append({"metric": name, "value": value})

    def _metrics_map_to_df(self, metrics_map):
        """把指标字典转换成两列表形式的 DataFrame。"""
        metrics = []
        for name, value in metrics_map.items():
            self._append_metric(metrics, name, value)
        return pd.DataFrame(metrics)

    def _calculate_turnover(self, weight: pd.DataFrame) -> pd.Series:
        """根据相邻两期权重变化计算逐日换手率。"""
        turnover = weight.diff().abs().sum(axis=1)
        if len(turnover) > 0:
            turnover.iloc[0] = weight.iloc[0].abs().sum()
        return turnover

    def _calculate_holdings_stats(self, weight: pd.DataFrame) -> dict:
        """统计每日持仓个数以及多空、净、总暴露。"""
        return {
            "holdings_count": (weight != 0).sum(axis=1),
            "long_exposure": weight.clip(lower=0).sum(axis=1),
            "short_exposure": (-weight.clip(upper=0)).sum(axis=1),
            "net_exposure": weight.sum(axis=1),
            "gross_exposure": weight.abs().sum(axis=1),
        }

    def _calculate_asset_return_coverage(self, weight: pd.DataFrame, asset_ret_raw: pd.DataFrame) -> dict:
        """统计持仓单元格中有多少比例能匹配到有效资产收益。"""
        holding_mask = weight != 0
        valid_on_holding = holding_mask & asset_ret_raw.notna()

        holding_cells = holding_mask.sum(axis=1)
        valid_holding_cells = valid_on_holding.sum(axis=1)
        asset_return_coverage = pd.Series(
            np.where(holding_cells > 0, valid_holding_cells / holding_cells, np.nan),
            index=weight.index,
        )

        return {
            "holding_cells": holding_cells,
            "valid_holding_cells": valid_holding_cells,
            "asset_return_coverage": asset_return_coverage,
        }

    def _annualize_return(self, nav_end, periods):
        """把区间净值终值换算成年化收益。"""
        if periods <= 0 or pd.isna(nav_end) or nav_end <= 0:
            return np.nan
        return nav_end ** (self.annualization / periods) - 1.0

    def _annualize_vol(self, returns):
        """把日频收益波动率换算成年化波动率。"""
        returns = pd.Series(returns).dropna()
        if len(returns) <= 1:
            return np.nan
        return returns.std(ddof=1) * np.sqrt(self.annualization)

    def _sharpe(self, returns, rf=0.0):
        """计算夏普比率，rf 按年化无风险利率传入。"""
        returns = pd.Series(returns).dropna()
        if len(returns) <= 1:
            return np.nan
        excess = returns - rf / self.annualization
        vol = excess.std(ddof=1)
        if abs(vol) < 1e-12:
            return np.nan
        return excess.mean() / vol * np.sqrt(self.annualization)

    def _sortino(self, returns, rf=0.0):
        """仅用下行波动衡量风险，计算 Sortino 比率。"""
        returns = pd.Series(returns).dropna()
        if len(returns) <= 1:
            return np.nan
        excess = returns - rf / self.annualization
        downside = excess[excess < 0]
        if len(downside) <= 1:
            return np.nan
        downside_std = downside.std(ddof=1)
        if abs(downside_std) < 1e-12:
            return np.nan
        return excess.mean() / downside_std * np.sqrt(self.annualization)

    def _max_drawdown(self, nav):
        """计算净值曲线的最大回撤。"""
        nav = pd.Series(nav).dropna()
        if len(nav) == 0:
            return np.nan
        dd = nav / nav.cummax() - 1.0
        return dd.min()

    def _calmar(self, annual_return, max_drawdown):
        """计算 Calmar 比率，即年化收益除以最大回撤绝对值。"""
        if pd.isna(annual_return) or pd.isna(max_drawdown) or abs(max_drawdown) < 1e-12:
            return np.nan
        return annual_return / abs(max_drawdown)

    def _win_rate(self, returns):
        """计算收益序列中正收益样本占比。"""
        returns = pd.Series(returns).dropna()
        if len(returns) == 0:
            return np.nan
        return (returns > 0).mean()

    def _period_win_rate(self, returns_df, freq="M", return_col="net_return"):
        """把日收益按周或月聚合后，统计周期维度的胜率。"""
        if len(returns_df) == 0:
            return np.nan

        temp = returns_df[[self.date_col, return_col]].copy()
        temp[self.date_col] = pd.to_datetime(temp[self.date_col])
        temp = temp.sort_values(self.date_col)

        temp["period"] = temp[self.date_col].dt.to_period(freq)
        period_ret = temp.groupby("period")[return_col].apply(lambda x: (1.0 + x).prod() - 1.0)

        if len(period_ret) == 0:
            return np.nan
        return (period_ret > 0).mean()

    def _downside_vol(self, returns):
        """仅基于负收益样本计算年化下行波动率。"""
        returns = pd.Series(returns).dropna()
        downside = returns[returns < 0]
        if len(downside) <= 1:
            return np.nan
        return downside.std(ddof=1) * np.sqrt(self.annualization)

    def _max_drawdown_duration(self, nav):
        """计算净值曲线处于水下区间的最长持续天数。"""
        nav = pd.Series(nav).dropna()
        if len(nav) == 0:
            return 0
        dd = nav / nav.cummax() - 1.0

        is_underwater = dd < 0
        grp = (is_underwater != is_underwater.shift(fill_value=False)).cumsum()
        durations = is_underwater.groupby(grp).sum()

        if len(durations) == 0:
            return 0
        return int(durations.max())

    def _profit_loss_ratio(self, returns):
        """计算平均盈利日收益与平均亏损日收益绝对值的比值。"""
        returns = pd.Series(returns).dropna()
        pos = returns[returns > 0]
        neg = returns[returns < 0]
        if len(pos) == 0 or len(neg) == 0:
            return np.nan

        pos_mean = pos.mean()
        neg_mean_abs = abs(neg.mean())
        if neg_mean_abs < 1e-12:
            return np.nan
        return pos_mean / neg_mean_abs

    def _longest_streak(self, binary_series):
        """计算二值序列中连续为 1 的最长长度。"""
        s = pd.Series(binary_series).fillna(0).astype(int)
        grp = (s != s.shift(fill_value=0)).cumsum()
        streak_lengths = s.groupby(grp).transform("size")
        streak_lengths = streak_lengths.where(s == 1, 0)
        return int(streak_lengths.max()) if len(streak_lengths) > 0 else 0

    def _top_n_pnl_contribution_ratio(self, returns, n=5):
        """计算收益最高的前 n 天对全部正收益的贡献占比。"""
        returns = pd.Series(returns).dropna()
        pos_sum = returns[returns > 0].sum()
        if pos_sum <= 0:
            return np.nan
        top_sum = returns.nlargest(n).sum()
        return top_sum / pos_sum

    def _global_effective_asset_return_ratio(self, weight_wide: pd.DataFrame, asset_return_raw: pd.DataFrame):
        """统计全部持仓单元格中，实际能匹配到有效收益的总体比例。"""
        holding_mask = (weight_wide != 0)
        total_holding_cells = holding_mask.to_numpy().sum()
        if total_holding_cells == 0:
            return np.nan

        valid_cells = (holding_mask & asset_return_raw.notna()).to_numpy().sum()
        return valid_cells / total_holding_cells

    def _alpha_beta(self, strategy_returns, benchmark_returns):
        """通过策略收益和基准收益的线性关系估算 beta 与年化 alpha。"""
        df = pd.DataFrame({
            "strategy": pd.to_numeric(strategy_returns, errors="coerce"),
            "benchmark": pd.to_numeric(benchmark_returns, errors="coerce"),
        }).dropna()

        if len(df) <= 2:
            return np.nan, np.nan

        x = df["benchmark"].values
        y = df["strategy"].values

        var_x = np.var(x, ddof=1)
        if abs(var_x) < 1e-12:
            return np.nan, np.nan

        cov_xy = np.cov(x, y, ddof=1)[0, 1]
        beta = cov_xy / var_x
        alpha_daily = y.mean() - beta * x.mean()
        alpha_annual = alpha_daily * self.annualization

        return beta, alpha_annual



if __name__ == "__main__":
    # ===== 你的输入数据 =====
    holdings_df = pd.read_csv(r"mock_holdings.csv")  # 替换成你的持仓数据路径

    kline_df = pd.read_csv(r"mock_kline.csv")  # 替换成你的K线数据路径


    # ===== 初始化 =====
    builder = PortfolioBacktestArtifactBuilder(
        annualization=252,
        return_window=1,
        fee_rate=0.0003,
        slippage_rate=0.0002,
        date_col="trade_date",
        symbol_col="symbol",
        weight_col="weight",
        price_col="close",
        output_root=str(default_portfolio_backtest_root()),
        strategy_name="demo_strategy",
    )

    # ===== 生成产物 =====
    result = builder.build(
        holdings_df=holdings_df,
        kline_df=kline_df,
        run_name="demo_run"
    )

    # ===== 查看结果 =====
    print("输出目录:", result["output_dir"])
    print("returns.csv 路径:", result["returns_path"])
    print("metrics.csv 路径:", result["metrics_path"])
    print("summary.csv 路径:", result["summary_path"])
    print("metadata.json 路径:", result["metadata_path"])

    print("\n=== returns_df ===")
    print(result["returns_df"])

    print("\n=== metrics_df ===")
    print(result["metrics_df"])

    print("\n=== summary_df ===")
    print(result["summary_df"])

    print("\n=== metadata ===")
    print(result["metadata"])