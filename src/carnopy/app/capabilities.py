from __future__ import annotations

from dataclasses import asdict
from typing import get_args

from carnopy.backends.coolprop import CoolPropBackend
from carnopy.backends.coolprop_models import supported_properties
from carnopy.config.models import CoolPropModel
from carnopy.config.outputs import DATASET_FORMAT_ORDER
from carnopy.domain.properties import PROPERTY_REGISTRY, REFERENCE_DEPENDENT_PROPERTIES
from carnopy.domain.units import AXIS_DIMENSIONS, UNITS
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    StepspaceSampler,
)
from carnopy.visualization.fields import FIELD_REGISTRY
from carnopy.visualization.requests import PlotFormat, PlotKindV2, PlotScale
from carnopy.visualization.units import DISPLAY_UNITS_BY_FIELD

MODE_NAMES = ("property_table", "saturation_table", "vapor_mass_fraction_table")
MODEL_NAMES: tuple[CoolPropModel, ...] = ("heos", "pr", "srk")
SAMPLER_MODELS = (
    ExplicitSampler,
    LinspaceSampler,
    StepspaceSampler,
    GeomspaceSampler,
    LogspaceSampler,
)
PLOT_KIND_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "property_curves": {
        "required": ["property"],
        "applicable": [
            "property",
            "x",
            "filters",
            "series",
            "display_units",
            "fluids",
            "value_scale",
            "format",
        ],
    },
    "property_heatmap": {
        "required": ["property"],
        "applicable": [
            "property",
            "filters",
            "display_units",
            "fluids",
            "color_scale",
            "format",
        ],
    },
    "xy": {
        "required": ["x", "y"],
        "applicable": [
            "x",
            "y",
            "group_by",
            "filters",
            "series",
            "display_units",
            "fluids",
            "x_scale",
            "y_scale",
            "format",
        ],
    },
    "pv": {
        "required": [],
        "applicable": [
            "filters",
            "series",
            "display_units",
            "fluids",
            "x_scale",
            "y_scale",
            "format",
        ],
    },
    "ts": {
        "required": [],
        "applicable": [
            "filters",
            "series",
            "display_units",
            "fluids",
            "x_scale",
            "y_scale",
            "format",
        ],
    },
}


def describe_capabilities(model: CoolPropModel) -> dict[str, object]:
    backend = CoolPropBackend(model=model)
    supported_by_model = {
        candidate: set(supported_properties(candidate)) for candidate in MODEL_NAMES
    }
    property_catalog = []
    for name, definition in PROPERTY_REGISTRY.items():
        metadata = definition.metadata()
        metadata["supported_models"] = [
            candidate for candidate in MODEL_NAMES if name in supported_by_model[candidate]
        ]
        metadata["supported"] = name in supported_by_model[model]
        property_catalog.append(metadata)

    return {
        "backend": backend.name,
        "backend_version": backend.version,
        "model": backend.model,
        "models": list(MODEL_NAMES),
        "modes": list(MODE_NAMES),
        "samplers": [
            {
                "kind": get_args(sampler.model_fields["kind"].annotation)[0],
                "fields": [name for name in sampler.model_fields if name not in {"kind", "unit"}],
            }
            for sampler in SAMPLER_MODELS
        ],
        "units_by_axis": {
            axis: [unit for unit, definition in UNITS.items() if definition.dimension == dimension]
            for axis, dimension in AXIS_DIMENSIONS.items()
        },
        "dataset_formats": list(DATASET_FORMAT_ORDER),
        "fluids": [
            {"name": fluid, "aliases": list(backend.aliases_for(fluid))}
            for fluid in backend.list_fluids()
        ],
        "properties": [PROPERTY_REGISTRY[name].metadata() for name in supported_properties(model)],
        "property_catalog": property_catalog,
        "reference_dependent_fields": list(REFERENCE_DEPENDENT_PROPERTIES),
        "visualization": {
            "plot_kinds": list(get_args(PlotKindV2)),
            "formats": list(get_args(PlotFormat)),
            "scales": list(get_args(PlotScale)),
            "kind_contracts": PLOT_KIND_CONTRACTS,
            "fields": [asdict(definition) for definition in FIELD_REGISTRY.values()],
            "display_units": {
                field: list(units) for field, units in DISPLAY_UNITS_BY_FIELD.items()
            },
        },
    }
