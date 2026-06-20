from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final


@dataclass(frozen=True)
class UnitDefinition:
    dimension: str
    si_unit: str
    scale: float = 1.0
    offset: float = 0.0

    def to_si(self, value: float) -> float:
        result = value * self.scale + self.offset
        if not isfinite(result):
            raise ValueError("unit conversion produced a non-finite value")
        return 0.0 if result == 0.0 else result


UNITS: Final[dict[str, UnitDefinition]] = {
    "K": UnitDefinition("temperature", "K"),
    "degC": UnitDefinition("temperature", "K", offset=273.15),
    "Pa": UnitDefinition("pressure", "Pa"),
    "kPa": UnitDefinition("pressure", "Pa", scale=1_000.0),
    "MPa": UnitDefinition("pressure", "Pa", scale=1_000_000.0),
    "bar": UnitDefinition("pressure", "Pa", scale=100_000.0),
    "1": UnitDefinition("dimensionless", "1"),
}

AXIS_DIMENSIONS: Final[dict[str, str]] = {
    "temperature": "temperature",
    "pressure": "pressure",
    "vapor_mass_fraction": "dimensionless",
}

AXIS_SI_UNITS: Final[dict[str, str]] = {
    "temperature": "K",
    "pressure": "Pa",
    "vapor_mass_fraction": "1",
}


def validate_axis_unit(axis: str, unit: str) -> UnitDefinition:
    try:
        definition = UNITS[unit]
    except KeyError as exc:
        raise ValueError(f"unsupported unit {unit!r}") from exc
    expected = AXIS_DIMENSIONS.get(axis)
    if expected is None:
        raise ValueError(f"unsupported grid axis {axis!r}")
    if definition.dimension != expected:
        raise ValueError(f"unit {unit!r} is incompatible with {axis!r}; expected {expected}")
    return definition


def convert_axis_values_to_si(axis: str, unit: str, values: list[float]) -> list[float]:
    definition = validate_axis_unit(axis, unit)
    converted = [definition.to_si(value) for value in values]
    if axis == "temperature" and any(value <= 0.0 for value in converted):
        raise ValueError("temperature values must be above absolute zero")
    if axis == "pressure" and any(value <= 0.0 for value in converted):
        raise ValueError("pressure values must be greater than zero")
    if axis == "vapor_mass_fraction" and any(value < 0.0 or value > 1.0 for value in converted):
        raise ValueError("vapor_mass_fraction values must be between 0 and 1")
    if len(set(converted)) != len(converted):
        raise ValueError(f"{axis} contains duplicate values after SI conversion")
    return converted
