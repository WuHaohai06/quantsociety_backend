"""pytest 收集本目录用例时注入路径：否则 `single_asset_backtest` 与 `runtime` 在裸环境下 import 失败。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BL = Path(__file__).resolve().parent.parent  # .../backtest_layer
_PROJ = _BL.parent  # monorepo 根（quantsociety_backend_project）
_FE = _PROJ / "factor_layer" / "factor_engine"  # PerfConfig、与回测共用

for _p in (_PROJ, _BL, _FE):
    _s = str(_p.resolve())
    if _s not in sys.path:
        sys.path.insert(0, _s)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: end-to-end integration tests")
