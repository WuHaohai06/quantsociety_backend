from __future__ import annotations

from pathlib import Path
import sys


DEMO_DIR = Path(__file__).resolve().parent
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from run_all_pipeline_demo import load_demo_artifacts, run_demo


def test_all_pipeline_demo_smoke() -> None:
    summary = run_demo(force=True)
    artifacts = load_demo_artifacts(summary)

    assert summary["paths"]["demo_root"].endswith("workspace_data/demos/all_pipeline_demo")
    assert len(summary["factor_engine"]) == 2
    assert len(summary["factor_evaluations"]) == 2
    assert all(item["approved"] for item in summary["factor_admissions"])

    signal_path = Path(summary["composite"]["outputs"]["signal"])
    holdings_path = Path(summary["holdings"]["outputs"]["holdings"])
    returns_path = Path(summary["backtest"]["returns_path"])

    assert signal_path.exists()
    assert holdings_path.exists()
    assert returns_path.exists()
    assert summary["backtest"]["summary"]["total_return"] > 0.0
    assert not artifacts["evaluation_summary"].empty
    assert not artifacts["signal"].empty
    assert not artifacts["holdings"].empty
    assert not artifacts["returns"].empty