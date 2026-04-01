from __future__ import annotations

from typing import Any


class CacheManager:
    """最小可用缓存管理器，供执行后端复用子树结果。"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()
