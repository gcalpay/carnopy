from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, get_args

from carnopy.visualization.fields import FIELD_REGISTRY
from carnopy.visualization.requests import PlotFormat, PlotScale

if TYPE_CHECKING:
    from carnopy.visualization.inspect import PlotInspection

MAX_SELECTABLE_LEVELS = 500

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


def build_plot_context(inspection: PlotInspection) -> dict[str, Any]:
    kinds = [kind.replace("-", "_") for kind in inspection.plot_kinds]
    available = _available_fields(inspection)
    coordinates = {
        str(item["field"]): _numeric_level_context(item) for item in inspection.coordinates
    }
    grid: dict[str, dict[str, object]] = {field: {} for field in coordinates}
    return {
        "mode": inspection.mode,
        "fluids": list(inspection.fluids),
        "properties": list(inspection.properties),
        "grid": grid,
        "reference_state": inspection.reference_state,
        "visualization": {
            "plot_kinds": kinds,
            "formats": list(get_args(PlotFormat)),
            "scales": list(get_args(PlotScale)),
            "kind_contracts": PLOT_KIND_CONTRACTS,
            "fields": [
                asdict(definition)
                for name, definition in FIELD_REGISTRY.items()
                if name in available
            ],
            "display_units": {
                field: list(units) for field, units in inspection.display_units.items()
            },
            "categorical_values": {
                field: list(values) for field, values in inspection.categorical_values.items()
            },
            "series_fields": {
                kind.replace("-", "_"): list(fields)
                for kind, fields in inspection.series_fields.items()
            },
            "numeric_levels": coordinates,
        },
    }


def _available_fields(inspection: PlotInspection) -> set[str]:
    columns = {str(item["name"]) for item in inspection.columns}
    available = {
        name for name, definition in FIELD_REGISTRY.items() if definition.column in columns
    }
    available.update(inspection.properties)
    if "mass_density" in inspection.properties:
        available.add("specific_volume")
    return available


def _numeric_level_context(detail: dict[str, Any]) -> dict[str, Any]:
    count = int(detail["level_count"])
    si_values = [float(value) for value in detail["levels_si"]]
    display_values = [float(value) for value in detail["levels_display"]]
    unit = str(detail["display_unit"] or "")
    choices = []
    if count <= MAX_SELECTABLE_LEVELS:
        choices = [
            {
                "label": _level_label(display, unit),
                "value": si,
            }
            for si, display in zip(si_values, display_values, strict=True)
        ]
    return {
        "count": count,
        "si_unit": detail["si_unit"],
        "display_unit": detail["display_unit"],
        "minimum_display": min(display_values) if display_values else None,
        "maximum_display": max(display_values) if display_values else None,
        "choices": choices,
    }


def _level_label(value: float, unit: str) -> str:
    rendered = format(value, ".15g")
    return f"{rendered} {unit}" if unit and unit != "1" else rendered
