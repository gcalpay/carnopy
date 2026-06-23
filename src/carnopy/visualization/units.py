from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final

from carnopy.visualization.fields import get_field


@dataclass(frozen=True)
class DisplayUnitDefinition:
    field_unit: str
    scale: float = 1.0
    offset: float = 0.0

    def to_si(self, value: float) -> float:
        result = value * self.scale + self.offset
        if not isfinite(result):
            raise ValueError("display-unit conversion produced a non-finite value")
        return 0.0 if result == 0.0 else result

    def from_si(self, value: float) -> float:
        result = (value - self.offset) / self.scale
        if not isfinite(result):
            raise ValueError("display-unit conversion produced a non-finite value")
        return 0.0 if result == 0.0 else result


DISPLAY_UNITS: Final[dict[str, DisplayUnitDefinition]] = {
    "K": DisplayUnitDefinition("K"),
    "degC": DisplayUnitDefinition("K", offset=273.15),
    "Pa": DisplayUnitDefinition("Pa"),
    "kPa": DisplayUnitDefinition("Pa", scale=1_000.0),
    "MPa": DisplayUnitDefinition("Pa", scale=1_000_000.0),
    "bar": DisplayUnitDefinition("Pa", scale=100_000.0),
    "J/kg": DisplayUnitDefinition("J/kg"),
    "kJ/kg": DisplayUnitDefinition("J/kg", scale=1_000.0),
    "J/(kg*K)": DisplayUnitDefinition("J/(kg*K)"),
    "kJ/(kg*K)": DisplayUnitDefinition("J/(kg*K)", scale=1_000.0),
}

DISPLAY_UNIT_ALIASES: Final[dict[str, str]] = {
    "°C": "degC",
    "J/(kg·K)": "J/(kg*K)",
    "kJ/(kg·K)": "kJ/(kg*K)",
}

PLAIN_UNIT_LABELS: Final[dict[str, str]] = {
    "degC": "°C",
    "J/(kg*K)": "J/(kg·K)",
    "kJ/(kg*K)": "kJ/(kg·K)",
}

DISPLAY_UNITS_BY_FIELD: Final[dict[str, tuple[str, ...]]] = {
    "temperature": ("K", "degC"),
    "pressure": ("Pa", "kPa", "MPa", "bar"),
    "specific_enthalpy": ("J/kg", "kJ/kg"),
    "specific_internal_energy": ("J/kg", "kJ/kg"),
    "specific_entropy": ("J/(kg*K)", "kJ/(kg*K)"),
    "isobaric_specific_heat_capacity": ("J/(kg*K)", "kJ/(kg*K)"),
    "isochoric_specific_heat_capacity": ("J/(kg*K)", "kJ/(kg*K)"),
}


def canonical_display_unit(unit: str) -> str:
    cleaned = unit.strip()
    return DISPLAY_UNIT_ALIASES.get(cleaned, cleaned)


def plain_unit_label(unit: str | None) -> str:
    if unit is None:
        return ""
    return PLAIN_UNIT_LABELS.get(unit, unit)


def supported_display_units(field: str) -> tuple[str, ...]:
    get_field(field)
    return DISPLAY_UNITS_BY_FIELD.get(field, ())


def validate_display_unit(field: str, unit: str) -> str:
    canonical = canonical_display_unit(unit)
    allowed = supported_display_units(field)
    if canonical not in allowed:
        rendered = ", ".join(allowed) if allowed else "none"
        raise ValueError(
            f"display unit {unit!r} is not supported for {field!r}; available units: {rendered}"
        )
    definition = get_field(field)
    converter = DISPLAY_UNITS[canonical]
    if definition.unit != converter.field_unit:
        raise ValueError(f"display unit {canonical!r} is incompatible with field {field!r}")
    return canonical


def to_si(field: str, value: float, unit: str) -> float:
    canonical = validate_display_unit(field, unit)
    return DISPLAY_UNITS[canonical].to_si(value)


def from_si(field: str, value: float, unit: str) -> float:
    canonical = validate_display_unit(field, unit)
    return DISPLAY_UNITS[canonical].from_si(value)
