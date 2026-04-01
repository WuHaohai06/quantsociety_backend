import os
import json
from datetime import datetime

import numpy as np
import pandas as pd
class StrategyRegistryEvaluator:
    """
    只读取回测产物，对策略做注册评估。

    默认读取：
        - metrics.csv
        - summary.csv
        - metadata.json

    输出：
        - registry_evaluation.csv
        - registry_evaluation.json
    """

    def __init__(
        self,
        min_trade_days=120,
        min_annual_return=0.05,
        min_sharpe=0.8,
        min_calmar=0.5,
        max_drawdown_limit=-0.20,
        max_annual_volatility=0.40,
        min_monthly_win_rate=0.45,
        max_turnover_mean=1.0,
        min_effective_data_ratio=0.95,
        max_top5_day_pnl_contribution=0.50,
    ):
        self.min_trade_days = min_trade_days
        self.min_annual_return = min_annual_return
        self.min_sharpe = min_sharpe
        self.min_calmar = min_calmar
        self.max_drawdown_limit = max_drawdown_limit
        self.max_annual_volatility = max_annual_volatility
        self.min_monthly_win_rate = min_monthly_win_rate
        self.max_turnover_mean = max_turnover_mean
        self.min_effective_data_ratio = min_effective_data_ratio
        self.max_top5_day_pnl_contribution = max_top5_day_pnl_contribution

    # =========================
    # 对外主入口
    # =========================
    def evaluate(self, artifact_dir: str):
        metrics_path = os.path.join(artifact_dir, "metrics.csv")
        summary_path = os.path.join(artifact_dir, "summary.csv")
        metadata_path = os.path.join(artifact_dir, "metadata.json")

        if not os.path.exists(metrics_path):
            raise FileNotFoundError(f"未找到 metrics.csv: {metrics_path}")
        if not os.path.exists(summary_path):
            raise FileNotFoundError(f"未找到 summary.csv: {summary_path}")
        if not os.path.exists(metadata_path):
            raise FileNotFoundError(f"未找到 metadata.json: {metadata_path}")

        metrics_df = pd.read_csv(metrics_path)
        summary_df = pd.read_csv(summary_path)
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        metric_map = self._metrics_to_dict(metrics_df)
        summary_map = summary_df.iloc[0].to_dict() if len(summary_df) > 0 else {}

        evaluation_df = self._build_evaluation(metric_map, summary_map, metadata)
        evaluation_json = self._build_evaluation_json(evaluation_df, summary_map, metadata)

        csv_path = os.path.join(artifact_dir, "registry_evaluation.csv")
        json_path = os.path.join(artifact_dir, "registry_evaluation.json")

        evaluation_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(evaluation_json, f, ensure_ascii=False, indent=2)

        return {
            "registry_evaluation_path": csv_path,
            "registry_evaluation_json_path": json_path,
            "registry_evaluation_df": evaluation_df,
            "registry_evaluation_json": evaluation_json,
        }

    # =========================
    # 评估逻辑
    # =========================
    def _build_evaluation(self, metric_map, summary_map, metadata):
        rows = []

        def add_rule(rule_name, actual, threshold, operator, passed, note=""):
            rows.append(
                {
                    "rule_name": rule_name,
                    "actual_value": actual,
                    "threshold": threshold,
                    "operator": operator,
                    "passed": bool(passed),
                    "note": note,
                }
            )

        trade_days = metric_map.get("trade_days", np.nan)
        annual_return = metric_map.get("annual_return", np.nan)
        sharpe = metric_map.get("sharpe", np.nan)
        calmar = metric_map.get("calmar", np.nan)
        max_drawdown = metric_map.get("max_drawdown", np.nan)
        annual_volatility = metric_map.get("annual_volatility", np.nan)
        monthly_win_rate = metric_map.get("monthly_win_rate", np.nan)
        avg_turnover = metric_map.get("avg_turnover", np.nan)
        effective_data_ratio = metric_map.get("effective_asset_return_ratio", np.nan)
        top5_day_pnl_contribution = metric_map.get("top5_day_pnl_contribution", np.nan)

        add_rule(
            "min_trade_days",
            trade_days,
            self.min_trade_days,
            ">=",
            pd.notna(trade_days) and trade_days >= self.min_trade_days,
        )
        add_rule(
            "min_annual_return",
            annual_return,
            self.min_annual_return,
            ">=",
            pd.notna(annual_return) and annual_return >= self.min_annual_return,
        )
        add_rule(
            "min_sharpe",
            sharpe,
            self.min_sharpe,
            ">=",
            pd.notna(sharpe) and sharpe >= self.min_sharpe,
        )
        add_rule(
            "min_calmar",
            calmar,
            self.min_calmar,
            ">=",
            pd.notna(calmar) and calmar >= self.min_calmar,
        )
        add_rule(
            "max_drawdown_limit",
            max_drawdown,
            self.max_drawdown_limit,
            ">=",
            pd.notna(max_drawdown) and max_drawdown >= self.max_drawdown_limit,
        )
        add_rule(
            "max_annual_volatility",
            annual_volatility,
            self.max_annual_volatility,
            "<=",
            pd.notna(annual_volatility) and annual_volatility <= self.max_annual_volatility,
        )
        add_rule(
            "min_monthly_win_rate",
            monthly_win_rate,
            self.min_monthly_win_rate,
            ">=",
            pd.notna(monthly_win_rate) and monthly_win_rate >= self.min_monthly_win_rate,
        )
        add_rule(
            "max_turnover_mean",
            avg_turnover,
            self.max_turnover_mean,
            "<=",
            pd.notna(avg_turnover) and avg_turnover <= self.max_turnover_mean,
        )
        add_rule(
            "min_effective_data_ratio",
            effective_data_ratio,
            self.min_effective_data_ratio,
            ">=",
            pd.notna(effective_data_ratio) and effective_data_ratio >= self.min_effective_data_ratio,
        )
        add_rule(
            "max_top5_day_pnl_contribution",
            top5_day_pnl_contribution,
            self.max_top5_day_pnl_contribution,
            "<=",
            pd.notna(top5_day_pnl_contribution) and top5_day_pnl_contribution <= self.max_top5_day_pnl_contribution,
        )

        evaluation_df = pd.DataFrame(rows)

        total_rules = len(evaluation_df)
        passed_rules = int(evaluation_df["passed"].sum())
        pass_rate = passed_rules / total_rules if total_rules > 0 else np.nan
        grade = self._grade(pass_rate, metric_map)

        final_row = pd.DataFrame(
            [
                {
                    "rule_name": "__FINAL__",
                    "actual_value": passed_rules,
                    "threshold": total_rules,
                    "operator": "passed/total",
                    "passed": grade in ["A", "B"],
                    "note": f"grade={grade}; pass_rate={pass_rate:.2%}" if pd.notna(pass_rate) else f"grade={grade}",
                }
            ]
        )

        evaluation_df = pd.concat([evaluation_df, final_row], ignore_index=True)
        return evaluation_df

    def _build_evaluation_json(self, evaluation_df, summary_map, metadata):
        rule_df = evaluation_df[evaluation_df["rule_name"] != "__FINAL__"].copy()
        final_row = evaluation_df[evaluation_df["rule_name"] == "__FINAL__"].iloc[0].to_dict()

        passed_rules = int(rule_df["passed"].sum())
        total_rules = len(rule_df)
        pass_rate = passed_rules / total_rules if total_rules > 0 else np.nan
        grade = self._extract_grade(final_row.get("note", ""))

        return {
            "strategy_name": summary_map.get("strategy_name", metadata.get("strategy_name")),
            "evaluation_time": datetime.now().isoformat(),
            "passed_rules": passed_rules,
            "total_rules": total_rules,
            "pass_rate": pass_rate,
            "grade": grade,
            "approved": final_row.get("passed", False),
            "rules": rule_df.to_dict(orient="records"),
            "final_decision": final_row,
            "summary_snapshot": summary_map,
            "metadata_snapshot": metadata,
        }

    # =========================
    # 工具函数
    # =========================
    def _metrics_to_dict(self, metrics_df):
        out = {}
        for _, row in metrics_df.iterrows():
            out[row["metric"]] = row["value"]
        return out

    def _grade(self, pass_rate, metric_map):
        sharpe = metric_map.get("sharpe", np.nan)
        annual_return = metric_map.get("annual_return", np.nan)
        max_drawdown = metric_map.get("max_drawdown", np.nan)

        if pd.isna(pass_rate):
            return "D"

        if (
            pass_rate >= 0.90
            and pd.notna(sharpe) and sharpe >= 1.5
            and pd.notna(annual_return) and annual_return >= 0.15
            and pd.notna(max_drawdown) and max_drawdown >= -0.15
        ):
            return "A"

        if pass_rate >= 0.80:
            return "B"

        if pass_rate >= 0.60:
            return "C"

        return "D"

    def _extract_grade(self, note: str):
        if not isinstance(note, str):
            return None
        if "grade=" not in note:
            return None
        try:
            return note.split("grade=")[1].split(";")[0].strip()
        except Exception:
            return None

if __name__ == "__main__":
    evaluator = StrategyRegistryEvaluator()

    result = evaluator.evaluate(r"./backtest_artifacts/my_strategy_run")

    print("评估CSV路径:", result["registry_evaluation_path"])
    print("评估JSON路径:", result["registry_evaluation_json_path"])
    print(result["registry_evaluation_df"])
    print(result["registry_evaluation_json"])