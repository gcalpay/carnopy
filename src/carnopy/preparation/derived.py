from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True)
class DerivedFeatureDefinition:
    name: str
    formula: str
    dependencies: tuple[str, ...]
    unit: str
    reference_state_safe: bool
    array_export_allowed: bool

    def metadata(self) -> dict[str, object]:
        return asdict(self)


DERIVED_FEATURE_REGISTRY: Final[dict[str, DerivedFeatureDefinition]] = {
    item.name: item
    for item in (
        DerivedFeatureDefinition(
            name="specific_volume",
            formula="1 / mass_density",
            dependencies=("mass_density",),
            unit="m^3/kg",
            reference_state_safe=True,
            array_export_allowed=True,
        ),
        DerivedFeatureDefinition(
            name="reduced_temperature",
            formula="temperature / critical_temperature",
            dependencies=("temperature", "critical_temperature"),
            unit="1",
            reference_state_safe=True,
            array_export_allowed=True,
        ),
        DerivedFeatureDefinition(
            name="reduced_pressure",
            formula="pressure / critical_pressure",
            dependencies=("pressure", "critical_pressure"),
            unit="1",
            reference_state_safe=True,
            array_export_allowed=True,
        ),
        DerivedFeatureDefinition(
            name="compressibility_factor",
            formula="pressure * molar_mass / (mass_density * R * temperature)",
            dependencies=("pressure", "molar_mass", "mass_density", "temperature"),
            unit="1",
            reference_state_safe=True,
            array_export_allowed=True,
        ),
    )
}


def derived_definition(name: str) -> DerivedFeatureDefinition:
    return DERIVED_FEATURE_REGISTRY[name]
