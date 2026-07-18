from __future__ import annotations

DATASET_MODEL = "dataset.model"
DATASET_MODE = "dataset.mode"
DATASET_FLUIDS = "dataset.fluids"
DATASET_PROPERTIES = "dataset.properties"
DATASET_OUTPUT_FORMATS = "dataset.outputs.dataset_formats"


def dataset_grid_field(axis: str, field: str) -> str:
    """Return one stable private field identifier for a sampler control."""

    return f"dataset.grid.{axis}.{field}"
