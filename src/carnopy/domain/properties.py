from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final, Literal

PropertyClass = Literal["backend_provided", "derived", "fluid_constant", "mode_limited"]


@dataclass(frozen=True)
class PropertyDefinition:
    name: str
    column: str
    unit: str
    classification: PropertyClass
    backend_key: str | None
    reference_dependent: bool = False
    dependencies: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return asdict(self)


PROPERTY_REGISTRY: Final[dict[str, PropertyDefinition]] = {
    item.name: item
    for item in (
        PropertyDefinition(
            "specific_enthalpy",
            "specific_enthalpy_J_kg",
            "J/kg",
            "backend_provided",
            "HMASS",
            reference_dependent=True,
        ),
        PropertyDefinition(
            "specific_entropy",
            "specific_entropy_J_kgK",
            "J/(kg*K)",
            "backend_provided",
            "SMASS",
            reference_dependent=True,
        ),
        PropertyDefinition(
            "specific_internal_energy",
            "specific_internal_energy_J_kg",
            "J/kg",
            "backend_provided",
            "UMASS",
            reference_dependent=True,
        ),
        PropertyDefinition(
            "mass_density",
            "mass_density_kg_m3",
            "kg/m^3",
            "backend_provided",
            "DMASS",
        ),
        PropertyDefinition(
            "isobaric_specific_heat_capacity",
            "isobaric_specific_heat_capacity_J_kgK",
            "J/(kg*K)",
            "backend_provided",
            "CPMASS",
        ),
        PropertyDefinition(
            "isochoric_specific_heat_capacity",
            "isochoric_specific_heat_capacity_J_kgK",
            "J/(kg*K)",
            "backend_provided",
            "CVMASS",
        ),
        PropertyDefinition(
            "dynamic_viscosity",
            "dynamic_viscosity_Pa_s",
            "Pa*s",
            "backend_provided",
            "VISCOSITY",
        ),
        PropertyDefinition(
            "kinematic_viscosity",
            "kinematic_viscosity_m2_s",
            "m^2/s",
            "derived",
            None,
            dependencies=("dynamic_viscosity", "mass_density"),
        ),
        PropertyDefinition(
            "thermal_conductivity",
            "thermal_conductivity_W_mK",
            "W/(m*K)",
            "backend_provided",
            "CONDUCTIVITY",
        ),
        PropertyDefinition(
            "prandtl_number",
            "prandtl_number",
            "1",
            "backend_provided",
            "PRANDTL",
        ),
        PropertyDefinition(
            "speed_of_sound",
            "speed_of_sound_m_s",
            "m/s",
            "backend_provided",
            "SPEED_OF_SOUND",
        ),
        PropertyDefinition(
            "molar_mass",
            "molar_mass_kg_mol",
            "kg/mol",
            "fluid_constant",
            "MOLARMASS",
        ),
        PropertyDefinition(
            "critical_temperature",
            "critical_temperature_K",
            "K",
            "fluid_constant",
            "TCRIT",
        ),
        PropertyDefinition(
            "critical_pressure",
            "critical_pressure_Pa",
            "Pa",
            "fluid_constant",
            "PCRIT",
        ),
        PropertyDefinition(
            "triple_point_temperature",
            "triple_point_temperature_K",
            "K",
            "fluid_constant",
            "TTRIPLE",
        ),
        PropertyDefinition(
            "surface_tension",
            "surface_tension_N_m",
            "N/m",
            "mode_limited",
            "SURFACE_TENSION",
        ),
    )
}

REFERENCE_DEPENDENT_PROPERTIES: Final[list[str]] = [
    name for name, item in PROPERTY_REGISTRY.items() if item.reference_dependent
]


def property_unit_columns(properties: list[str]) -> dict[str, str]:
    return {PROPERTY_REGISTRY[name].column: PROPERTY_REGISTRY[name].unit for name in properties}
