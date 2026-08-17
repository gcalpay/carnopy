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

PREPARATION_SOURCE_POLICY = "preparation.source_policy.allow_partial_sweep"
PREPARATION_FEATURES = "preparation.features"
PREPARATION_NUMERIC_FEATURES = "preparation.features.numeric"
PREPARATION_DERIVED_FEATURES = "preparation.features.derived"
PREPARATION_CATEGORICAL_FEATURES = "preparation.categorical_features"
PREPARATION_TARGETS = "preparation.targets"
PREPARATION_AUXILIARY = "preparation.auxiliary"
PREPARATION_OUTPUTS = "preparation.outputs"
PREPARATION_MATRIX_DIAGNOSTICS = "preparation.quality.matrix_diagnostics"
PREPARATION_BASELINE_DIAGNOSTICS = "preparation.quality.baseline_diagnostics"
PREPARATION_SCENARIO_ACTIVE = "preparation.scenario.active"


def preparation_scenario_field(field: str) -> str:
    """Return one stable private field identifier for the temporary scenario editor."""

    return f"{PREPARATION_SCENARIO_ACTIVE}.{field}"


def dataset_grid_field(axis: str, field: str) -> str:
    """Return one stable private field identifier for a sampler control."""

    return f"dataset.grid.{axis}.{field}"


def plot_field(field: str) -> str:
    """Return one stable private field identifier for a plot control."""

    return f"plot.{field}"
