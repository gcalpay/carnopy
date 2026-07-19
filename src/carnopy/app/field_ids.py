from __future__ import annotations

DATASET_MODEL = "dataset.model"
DATASET_MODE = "dataset.mode"
DATASET_FLUIDS = "dataset.fluids"
DATASET_PROPERTIES = "dataset.properties"
DATASET_OUTPUT_FORMATS = "dataset.outputs.dataset_formats"

VISUALIZATION_ENABLED = "visualization.enabled"
VISUALIZATION_FORMAT = "visualization.format"
VISUALIZATION_FLUIDS = "visualization.fluids"
VISUALIZATION_FILTERS = "visualization.filters"
VISUALIZATION_DISPLAY_UNITS = "visualization.display_units"
VISUALIZATION_PLOTS = "visualization.plots"

PLOT_NAME = "plot.name"
PLOT_KIND = "plot.kind"
PLOT_FLUIDS = "plot.fluids"
PLOT_FILTERS = "plot.filters"
PLOT_SERIES = "plot.series"
PLOT_DISPLAY_UNITS = "plot.display_units"


def dataset_grid_field(axis: str, field: str) -> str:
    """Return one stable private field identifier for a sampler control."""

    return f"dataset.grid.{axis}.{field}"


def plot_field(field: str) -> str:
    """Return one stable private field identifier for a plot control."""

    return f"plot.{field}"
