from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FactorDefinitionConfig:
    name: str
    expr: str
    freq: str = "1d"
    universe: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class DataSourceConfig:
    type: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BackendConfig:
    type: str = "pandas"


@dataclass(frozen=True)
class EngineConfig:
    enable_cache: bool = True


@dataclass(frozen=True)
class FactorEngineConfig:
    factor: FactorDefinitionConfig
    data_source: DataSourceConfig
    backend: BackendConfig = field(default_factory=BackendConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)


def load_config(path: str | Path) -> FactorEngineConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text()) or {}

    factor_payload = payload.get("factor", {})
    data_source_payload = payload.get("data_source", {})
    backend_payload = payload.get("backend", {})
    engine_payload = payload.get("engine", {})

    if "name" not in factor_payload or "expr" not in factor_payload:
        raise ValueError("Config must include factor.name and factor.expr")

    if "type" not in data_source_payload:
        raise ValueError("Config must include data_source.type")

    factor_config = FactorDefinitionConfig(
        name=factor_payload["name"],
        expr=factor_payload["expr"],
        freq=factor_payload.get("freq", "1d"),
        universe=factor_payload.get("universe"),
        description=factor_payload.get("description"),
    )
    data_source_config = DataSourceConfig(
        type=data_source_payload["type"],
        options={key: value for key, value in data_source_payload.items() if key != "type"},
    )
    backend_config = BackendConfig(type=backend_payload.get("type", "pandas"))
    engine_config = EngineConfig(enable_cache=engine_payload.get("enable_cache", True))

    return FactorEngineConfig(
        factor=factor_config,
        data_source=data_source_config,
        backend=backend_config,
        engine=engine_config,
    )

