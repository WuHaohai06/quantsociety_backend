from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    """因子引擎数据源契约。

    `load_column()` 必须返回一个按 `(timestamp, instrument)` MultiIndex 排序的列数据。
    当前 PandasBackend 只依赖这一层抽象，因此单数据源接入可以保持很薄。
    """

    @abstractmethod
    def load_column(self, name: str) -> Any:
        raise NotImplementedError
