# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyPresentation:
    label: str
    symbol: str
    unit: str


PROPERTY_PRESENTATION: dict[str, PropertyPresentation] = {
    "specific_enthalpy": PropertyPresentation("Specific enthalpy", "h", "J·kg⁻¹"),
    "specific_entropy": PropertyPresentation("Specific entropy", "s", "J·kg⁻¹·K⁻¹"),
    "specific_internal_energy": PropertyPresentation("Specific internal energy", "u", "J·kg⁻¹"),
    "mass_density": PropertyPresentation("Mass density", "ρ", "kg·m⁻³"),
    "isobaric_specific_heat_capacity": PropertyPresentation(
        "Isobaric specific heat capacity", "cₚ", "J·kg⁻¹·K⁻¹"
    ),
    "isochoric_specific_heat_capacity": PropertyPresentation(
        "Isochoric specific heat capacity", "cᵥ", "J·kg⁻¹·K⁻¹"
    ),
    "dynamic_viscosity": PropertyPresentation("Dynamic viscosity", "μ", "Pa·s"),
    "kinematic_viscosity": PropertyPresentation("Kinematic viscosity", "ν", "m²·s⁻¹"),
    "thermal_conductivity": PropertyPresentation("Thermal conductivity", "k", "W·m⁻¹·K⁻¹"),
    "prandtl_number": PropertyPresentation("Prandtl number", "Pr", "1"),
    "speed_of_sound": PropertyPresentation("Speed of sound", "a", "m·s⁻¹"),
    "molar_mass": PropertyPresentation("Molar mass", "M", "kg·mol⁻¹"),
    "critical_temperature": PropertyPresentation("Critical temperature", "T<sub>c</sub>", "K"),
    "critical_pressure": PropertyPresentation("Critical pressure", "p<sub>c</sub>", "Pa"),
    "triple_point_temperature": PropertyPresentation(
        "Triple-point temperature", "T<sub>tr</sub>", "K"
    ),
    "surface_tension": PropertyPresentation("Surface tension", "σ", "N·m⁻¹"),
}


def property_presentation(name: str) -> PropertyPresentation:
    """Return private display metadata without changing scientific registry tokens."""

    return PROPERTY_PRESENTATION.get(
        name,
        PropertyPresentation(name.replace("_", " ").capitalize(), name, ""),
    )
