from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from carnopy.visualization.models import (
        Advisory,
        PlotResult,
        PlotSource,
        VisualizationDependencyError,
        VisualizationError,
    )
    from carnopy.visualization.plots import plot_dataset

__all__ = [
    "Advisory",
    "PlotResult",
    "PlotSource",
    "VisualizationDependencyError",
    "VisualizationError",
    "plot_dataset",
]

_LAZY_EXPORTS = {
    "Advisory": ("carnopy.visualization.models", "Advisory"),
    "PlotResult": ("carnopy.visualization.models", "PlotResult"),
    "PlotSource": ("carnopy.visualization.models", "PlotSource"),
    "VisualizationDependencyError": (
        "carnopy.visualization.models",
        "VisualizationDependencyError",
    ),
    "VisualizationError": ("carnopy.visualization.models", "VisualizationError"),
    "plot_dataset": ("carnopy.visualization.plots", "plot_dataset"),
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
