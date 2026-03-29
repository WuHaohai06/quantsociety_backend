from .debug_backend import DebugBackend
from .pandas_backend import PandasBackend
from .polars_backend import PolarsBackend


def build_backend(backend_type: str):
    normalized = backend_type.strip().lower()

    if normalized == "debug":
        return DebugBackend()
    if normalized == "pandas":
        return PandasBackend()
    if normalized == "polars":
        return PolarsBackend()

    raise ValueError(f"Unsupported backend type: {backend_type}")
