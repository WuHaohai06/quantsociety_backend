import os

from .debug_backend import DebugBackend
from .pandas_backend import PandasBackend
from .polars_backend import PolarsBackend


def build_backend(backend_type: str):
    """构建后端。``pandas_modin`` 会在首次使用 pandas API 前设置 ``FACTOR_ENGINE_USE_MODIN=1``。"""
    normalized = backend_type.strip().lower()

    if normalized == "debug":
        return DebugBackend()
    if normalized == "pandas":
        return PandasBackend()
    if normalized == "pandas_modin":
        os.environ.setdefault("FACTOR_ENGINE_USE_MODIN", "1")
        return PandasBackend()
    if normalized == "polars":
        return PolarsBackend()
    if normalized == "polars_lazy":
        return PolarsBackend(use_lazy=True)

    raise ValueError(f"Unsupported backend type: {backend_type}")
