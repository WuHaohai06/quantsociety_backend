from __future__ import annotations

from pathlib import Path
import sys


DEMO_DIR = Path(__file__).resolve().parent
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from run_single_asset_pipeline_demo import load_demo_artifacts, run_demo


def test_single_asset_pipeline_demo_smoke() -> None:
    summary = run_demo(force=True)
    artifacts = load_demo_artifacts(summary)

    assert summary["paths"]["demo_root"].endswith("workspace_data/demos/single_asset_pipeline_demo")
    assert len(summary["factor_engine"]) == 3
    assert summary["alpha"]["target_position_rows"] > 0

    target_position_path = Path(summary["alpha"]["target_position_path"])
    returns_path = Path(summary["backtest"]["outputs"]["returns"])
    metrics_path = Path(summary["backtest"]["outputs"]["metrics"])

    assert target_position_path.exists()
    assert returns_path.exists()
    assert metrics_path.exists()
    assert summary["backtest"]["summary"]["final_equity"] > summary["backtest"]["summary"]["initial_cash"]
    assert not artifacts["factor_frame"].empty
    assert not artifacts["target_position"].empty
    assert not artifacts["returns"].empty