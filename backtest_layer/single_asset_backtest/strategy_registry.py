from __future__ import annotations

"""策略注册表：按 ``name@version`` 管理 Backtrader 策略类与默认参数，供 ``run_single_asset_backtest`` 解析。"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategySpec:
    """一项策略：展示名、版本、已绑定 ``bt`` 的策略类、合并默认参数。"""

    name: str
    version: str
    strategy_cls: type
    default_params: dict = field(default_factory=dict)


class StrategyRegistry:
    """内存注册表 ``{name: {version: StrategySpec}}``；未指定 version 时取 ``latest``。"""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, StrategySpec]] = {}

    def register(self, spec: StrategySpec) -> None:
        """注册策略；同一 ``name@version`` 重复注册会报错。"""
        versions = self._items.setdefault(spec.name, {})
        if spec.version in versions:
            raise ValueError(f"Strategy already registered: {spec.name}@{spec.version}")
        versions[spec.version] = spec

    def list(self, name: str | None = None) -> list[StrategySpec]:
        if name is not None:
            return [self._items[name][v] for v in sorted(self._items.get(name, {}), key=_version_key)]

        out: list[StrategySpec] = []
        for strategy_name in sorted(self._items):
            out.extend(self.list(strategy_name))
        return out

    def latest(self, name: str) -> StrategySpec:
        versions = self._items.get(name)
        if not versions:
            raise ValueError(f"Unknown strategy: {name}")
        latest_version = max(versions, key=_version_key)
        return versions[latest_version]

    def get(self, name: str, version: str | None = None) -> StrategySpec:
        """按名与版本取策略；``version is None`` 时解析为最新版本。"""
        if version is None:
            return self.latest(name)

        versions = self._items.get(name)
        if not versions or version not in versions:
            raise ValueError(f"Unknown strategy version: {name}@{version}")
        return versions[version]


def _version_key(version: str) -> tuple:
    """版本号排序键：按 ``1.10`` > ``1.2`` 数值序比较（分段数字与非数字）。"""
    out: list[int | str] = []
    for token in version.split("."):
        if token.isdigit():
            out.append(int(token))
        else:
            out.append(token)
    return tuple(out)
