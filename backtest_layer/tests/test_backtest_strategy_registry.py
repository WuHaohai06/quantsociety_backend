from __future__ import annotations

import pytest

from single_asset_backtest.strategy_library import build_strategy_registry
from single_asset_backtest.strategy_registry import StrategyRegistry, StrategySpec


class _DummyStrategyA:
    pass


class _DummyStrategyB:
    pass


def test_strategy_registry_register_get_and_latest():
    registry = StrategyRegistry()
    registry.register(StrategySpec(name="alpha", version="1.0", strategy_cls=_DummyStrategyA, default_params={"x": 1}))
    registry.register(StrategySpec(name="alpha", version="1.2", strategy_cls=_DummyStrategyB, default_params={"x": 2}))

    latest = registry.get("alpha")
    assert latest.version == "1.2"
    assert latest.strategy_cls is _DummyStrategyB

    v1 = registry.get("alpha", "1.0")
    assert v1.strategy_cls is _DummyStrategyA


def test_strategy_registry_rejects_duplicate_registration():
    registry = StrategyRegistry()
    registry.register(StrategySpec(name="alpha", version="1.0", strategy_cls=_DummyStrategyA, default_params={}))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(StrategySpec(name="alpha", version="1.0", strategy_cls=_DummyStrategyB, default_params={}))


def test_strategy_registry_rejects_unknown_name_or_version():
    registry = StrategyRegistry()
    registry.register(StrategySpec(name="alpha", version="1.0", strategy_cls=_DummyStrategyA, default_params={}))

    with pytest.raises(ValueError, match="Unknown strategy"):
        registry.get("beta")

    with pytest.raises(ValueError, match="Unknown strategy version"):
        registry.get("alpha", "2.0")


def test_build_strategy_registry_includes_dual_ma():
    bt = pytest.importorskip("backtrader")
    registry = build_strategy_registry(bt)

    dual_ma = registry.get("dual_ma")
    assert dual_ma.version == "1.0"
    assert dual_ma.default_params["short_window"] == 5
    assert dual_ma.default_params["long_window"] == 20
    assert dual_ma.default_params["position_size"] == pytest.approx(1.0)
