from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from carnopy.domain.properties import PROPERTY_REGISTRY

FieldKind = Literal["numeric", "categorical"]


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    column: str
    kind: FieldKind
    label: str
    symbol: str | None
    unit: str | None
    axis_allowed: bool
    group_allowed: bool
    filter_allowed: bool
    required_property: str | None = None
    derivation: Literal["reciprocal"] | None = None

    @property
    def display_label(self) -> str:
        symbol = f", {self.symbol}" if self.symbol is not None else ""
        unit = f" [{format_unit(self.unit)}]" if self.unit is not None else ""
        return f"{self.label}{symbol}{unit}"


UNIT_LABELS: Final[dict[str, str]] = {
    "1": r"$-$",
    "K": r"$\mathrm{K}$",
    "Pa": r"$\mathrm{Pa}$",
    "J/kg": r"$\mathrm{J\,kg^{-1}}$",
    "J/(kg*K)": r"$\mathrm{J\,kg^{-1}\,K^{-1}}$",
    "kg/m^3": r"$\mathrm{kg\,m^{-3}}$",
    "Pa*s": r"$\mathrm{Pa\,s}$",
    "m^2/s": r"$\mathrm{m^{2}\,s^{-1}}$",
    "W/(m*K)": r"$\mathrm{W\,m^{-1}\,K^{-1}}$",
    "m/s": r"$\mathrm{m\,s^{-1}}$",
    "kg/mol": r"$\mathrm{kg\,mol^{-1}}$",
    "N/m": r"$\mathrm{N\,m^{-1}}$",
    "m^3/kg": r"$\mathrm{m^{3}\,kg^{-1}}$",
}

PROPERTY_SYMBOLS: Final[dict[str, str]] = {
    "specific_enthalpy": r"$h$",
    "specific_entropy": r"$s$",
    "specific_internal_energy": r"$u$",
    "mass_density": r"$\rho$",
    "isobaric_specific_heat_capacity": r"$c_p$",
    "isochoric_specific_heat_capacity": r"$c_v$",
    "dynamic_viscosity": r"$\mu$",
    "kinematic_viscosity": r"$\nu$",
    "thermal_conductivity": r"$k$",
    "prandtl_number": r"$\mathrm{Pr}$",
    "speed_of_sound": r"$a$",
    "molar_mass": r"$M$",
    "critical_temperature": r"$T_\mathrm{crit}$",
    "critical_pressure": r"$p_\mathrm{crit}$",
    "triple_point_temperature": r"$T_\mathrm{triple}$",
    "surface_tension": r"$\sigma$",
}


def _property_field(name: str) -> FieldDefinition:
    definition = PROPERTY_REGISTRY[name]
    return FieldDefinition(
        name=name,
        column=definition.column,
        kind="numeric",
        label=name.replace("_", " ").capitalize(),
        symbol=PROPERTY_SYMBOLS.get(name),
        unit=definition.unit,
        axis_allowed=True,
        group_allowed=False,
        filter_allowed=False,
        required_property=name,
    )


FIELD_REGISTRY: Final[dict[str, FieldDefinition]] = {
    "temperature": FieldDefinition(
        name="temperature",
        column="temperature_K",
        kind="numeric",
        label="Temperature",
        symbol=r"$T$",
        unit="K",
        axis_allowed=True,
        group_allowed=True,
        filter_allowed=True,
    ),
    "pressure": FieldDefinition(
        name="pressure",
        column="pressure_Pa",
        kind="numeric",
        label="Pressure",
        symbol=r"$p$",
        unit="Pa",
        axis_allowed=True,
        group_allowed=True,
        filter_allowed=True,
    ),
    "vapor_mass_fraction": FieldDefinition(
        name="vapor_mass_fraction",
        column="vapor_mass_fraction",
        kind="numeric",
        label="Vapor mass fraction",
        symbol=r"$q$",
        unit="1",
        axis_allowed=True,
        group_allowed=True,
        filter_allowed=True,
    ),
    "specific_volume": FieldDefinition(
        name="specific_volume",
        column="_specific_volume_m3_kg",
        kind="numeric",
        label="Specific volume",
        symbol=r"$v$",
        unit="m^3/kg",
        axis_allowed=True,
        group_allowed=False,
        filter_allowed=False,
        required_property="mass_density",
        derivation="reciprocal",
    ),
    "phase": FieldDefinition(
        name="phase",
        column="phase",
        kind="categorical",
        label="Phase",
        symbol=None,
        unit=None,
        axis_allowed=False,
        group_allowed=True,
        filter_allowed=True,
    ),
    "saturation_endpoint": FieldDefinition(
        name="saturation_endpoint",
        column="saturation_endpoint",
        kind="categorical",
        label="Saturation endpoint",
        symbol=None,
        unit=None,
        axis_allowed=False,
        group_allowed=True,
        filter_allowed=True,
    ),
    "fluid": FieldDefinition(
        name="fluid",
        column="fluid",
        kind="categorical",
        label="Fluid",
        symbol=None,
        unit=None,
        axis_allowed=False,
        group_allowed=False,
        filter_allowed=False,
    ),
    **{name: _property_field(name) for name in PROPERTY_REGISTRY},
}


def get_field(name: str) -> FieldDefinition:
    try:
        return FIELD_REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(FIELD_REGISTRY))
        raise ValueError(
            f"unknown visualization field {name!r}; available fields: {available}"
        ) from exc


def format_unit(unit: str | None) -> str:
    if unit is None:
        return ""
    try:
        return UNIT_LABELS[unit]
    except KeyError as exc:
        raise ValueError(f"visualization unit {unit!r} has no scientific display mapping") from exc
