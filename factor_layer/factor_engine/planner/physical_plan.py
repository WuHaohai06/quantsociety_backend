from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhysicalPlan:
    op: str
    attrs: dict[str, Any] = field(default_factory=dict)
