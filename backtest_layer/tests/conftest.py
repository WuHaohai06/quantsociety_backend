"""Ensure `single_asset_backtest` and `runtime` resolve when running pytest from repo root."""

from __future__ import annotations

import sys
from pathlib import Path

_BL = Path(__file__).resolve().parent.parent
_PROJ = _BL.parent
_FE = _PROJ / "factor_layer" / "factor_engine"

for _p in (_BL, _FE):
    _s = str(_p.resolve())
    if _s not in sys.path:
        sys.path.insert(0, _s)
