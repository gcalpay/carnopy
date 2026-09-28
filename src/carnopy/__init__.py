from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from carnopy._version import __version__

if TYPE_CHECKING:
    from carnopy.api import (
        generate_dataset,
        generate_model_sweep,
        import_source,
        load_config,
        prepare_dataset,
        preview_source_import,
        validate_config,
    )
    from carnopy.config.models import BackendConfig, CarnopyConfig, CoolPropModel, NormalizedConfig
    from carnopy.config.outputs import OutputConfig
    from carnopy.config.visualization import VisualizationConfig, VisualizationPlotConfig
    from carnopy.results import (
        PreparationResult,
        RunResult,
        SweepResult,
        ValidationResult,
        VisualizationSummary,
    )
    from carnopy.sources.config import ImportConfig, ImportSelection
    from carnopy.sources.errors import SourceImportError
    from carnopy.sources.preview import ImportPreview
    from carnopy.sources.results import ImportResult

__all__ = [
    "BackendConfig",
    "CarnopyConfig",
    "CoolPropModel",
    "ImportConfig",
    "ImportPreview",
    "ImportResult",
    "ImportSelection",
    "NormalizedConfig",
    "OutputConfig",
    "PreparationResult",
    "RunResult",
    "SourceImportError",
    "SweepResult",
    "ValidationResult",
    "VisualizationConfig",
    "VisualizationPlotConfig",
    "VisualizationSummary",
    "__version__",
    "generate_dataset",
    "generate_model_sweep",
    "import_source",
    "load_config",
    "prepare_dataset",
    "preview_source_import",
    "validate_config",
]

_LAZY_EXPORTS = {
    "BackendConfig": ("carnopy.config.models", "BackendConfig"),
    "CarnopyConfig": ("carnopy.config.models", "CarnopyConfig"),
    "CoolPropModel": ("carnopy.config.models", "CoolPropModel"),
    "ImportConfig": ("carnopy.sources.config", "ImportConfig"),
    "ImportSelection": ("carnopy.sources.config", "ImportSelection"),
    "ImportPreview": ("carnopy.sources.preview", "ImportPreview"),
    "ImportResult": ("carnopy.sources.results", "ImportResult"),
    "SourceImportError": ("carnopy.sources.errors", "SourceImportError"),
    "NormalizedConfig": ("carnopy.config.models", "NormalizedConfig"),
    "OutputConfig": ("carnopy.config.outputs", "OutputConfig"),
    "PreparationResult": ("carnopy.results", "PreparationResult"),
    "RunResult": ("carnopy.results", "RunResult"),
    "SweepResult": ("carnopy.results", "SweepResult"),
    "ValidationResult": ("carnopy.results", "ValidationResult"),
    "VisualizationConfig": ("carnopy.config.visualization", "VisualizationConfig"),
    "VisualizationPlotConfig": (
        "carnopy.config.visualization",
        "VisualizationPlotConfig",
    ),
    "VisualizationSummary": ("carnopy.results", "VisualizationSummary"),
    "generate_dataset": ("carnopy.api", "generate_dataset"),
    "generate_model_sweep": ("carnopy.api", "generate_model_sweep"),
    "import_source": ("carnopy.api", "import_source"),
    "load_config": ("carnopy.api", "load_config"),
    "prepare_dataset": ("carnopy.api", "prepare_dataset"),
    "preview_source_import": ("carnopy.api", "preview_source_import"),
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
