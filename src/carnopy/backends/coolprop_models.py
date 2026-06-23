from __future__ import annotations

from typing import Final

from carnopy.config.models import CoolPropModel
from carnopy.domain.properties import PROPERTY_REGISTRY

MODEL_PREFIXES: Final[dict[CoolPropModel, str]] = {
    "heos": "HEOS",
    "pr": "PR",
    "srk": "SRK",
}

MODEL_DIRECT_UNSUPPORTED_PROPERTIES: Final[dict[CoolPropModel, frozenset[str]]] = {
    "heos": frozenset(),
    "pr": frozenset(
        {
            "dynamic_viscosity",
            "thermal_conductivity",
            "prandtl_number",
            "surface_tension",
            "triple_point_temperature",
        }
    ),
    "srk": frozenset(
        {
            "dynamic_viscosity",
            "thermal_conductivity",
            "prandtl_number",
            "surface_tension",
            "triple_point_temperature",
        }
    ),
}


def unsupported_properties(
    model: CoolPropModel,
    properties: list[str] | None = None,
) -> tuple[str, ...]:
    candidates = properties if properties is not None else list(PROPERTY_REGISTRY)
    direct = MODEL_DIRECT_UNSUPPORTED_PROPERTIES[model]

    def unsupported(name: str) -> bool:
        definition = PROPERTY_REGISTRY[name]
        return name in direct or any(
            unsupported(dependency) for dependency in definition.dependencies
        )

    return tuple(sorted(name for name in candidates if unsupported(name)))


def supported_properties(model: CoolPropModel) -> tuple[str, ...]:
    unsupported = set(unsupported_properties(model))
    return tuple(sorted(PROPERTY_REGISTRY.keys() - unsupported))
