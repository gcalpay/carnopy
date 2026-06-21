from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from carnopy.backends.base import PropertyBackend
    from carnopy.backends.coolprop import CoolPropBackend

__all__ = ["CoolPropBackend", "PropertyBackend"]

_LAZY_EXPORTS = {
    "CoolPropBackend": ("carnopy.backends.coolprop", "CoolPropBackend"),
    "PropertyBackend": ("carnopy.backends.base", "PropertyBackend"),
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
