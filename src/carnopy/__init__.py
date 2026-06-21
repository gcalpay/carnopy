from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from carnopy._version import __version__

if TYPE_CHECKING:
    from carnopy.api import generate_dataset, load_config, validate_config
    from carnopy.config.models import CarnopyConfig, NormalizedConfig
    from carnopy.results import RunResult, ValidationResult

__all__ = [
    "CarnopyConfig",
    "NormalizedConfig",
    "RunResult",
    "ValidationResult",
    "__version__",
    "generate_dataset",
    "load_config",
    "validate_config",
]

_LAZY_EXPORTS = {
    "CarnopyConfig": ("carnopy.config.models", "CarnopyConfig"),
    "NormalizedConfig": ("carnopy.config.models", "NormalizedConfig"),
    "RunResult": ("carnopy.results", "RunResult"),
    "ValidationResult": ("carnopy.results", "ValidationResult"),
    "generate_dataset": ("carnopy.api", "generate_dataset"),
    "load_config": ("carnopy.api", "load_config"),
    "validate_config": ("carnopy.api", "validate_config"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
