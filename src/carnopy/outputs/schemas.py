from __future__ import annotations

from carnopy.config.models import NormalizedConfig
from carnopy.domain.properties import PROPERTY_REGISTRY

REQUIRED_ROW_COLUMNS = [
    "run_id",
    "case_id",
    "mode",
    "fluid",
    "backend",
    "backend_version",
    "phase",
    "backend_phase",
]

FAILURE_COLUMNS = [
    "valid",
    "failure_layer",
    "failure_code",
    "failure_message",
    "failure_property",
    "backend_error_type",
    "backend_error_message",
]


def dataset_columns(config: NormalizedConfig) -> list[str]:
    coordinates = {
        "property_table": ["temperature_K", "pressure_Pa"],
        "saturation_table": [
            "temperature_K",
            "pressure_Pa",
            "vapor_mass_fraction",
            "saturation_endpoint",
        ],
        "vapor_mass_fraction_table": [
            "temperature_K",
            "pressure_Pa",
            "vapor_mass_fraction",
        ],
    }[config.mode]
    properties = [PROPERTY_REGISTRY[name].column for name in config.properties]
    return [*REQUIRED_ROW_COLUMNS, *coordinates, *properties, *FAILURE_COLUMNS]


def dataset_unit_map(config: NormalizedConfig) -> dict[str, str]:
    units = {
        "temperature_K": "K",
        "pressure_Pa": "Pa",
        "vapor_mass_fraction": "1",
    }
    units.update(
        {PROPERTY_REGISTRY[name].column: PROPERTY_REGISTRY[name].unit for name in config.properties}
    )
    return {column: unit for column, unit in units.items() if column in dataset_columns(config)}
