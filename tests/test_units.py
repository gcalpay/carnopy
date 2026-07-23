from __future__ import annotations

import pytest

from carnopy.domain.numbers import (
    binary64_from_decimal,
    decimal_from_binary64,
    stable_binary64,
    stable_number_text,
)
from carnopy.domain.units import convert_axis_values_to_si, validate_axis_unit


def test_engineering_units_convert_to_si() -> None:
    assert convert_axis_values_to_si("temperature", "degC", [0.0]) == [273.15]
    assert convert_axis_values_to_si("pressure", "hPa", [1_013.25]) == [101_325.0]
    assert convert_axis_values_to_si("pressure", "bar", [1.0]) == [100_000.0]
    assert convert_axis_values_to_si("pressure", "atm", [1.0]) == [101_325.0]


def test_invalid_unit_and_physical_values_fail() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        validate_axis_unit("temperature", "bar")
    with pytest.raises(ValueError, match="absolute zero"):
        convert_axis_values_to_si("temperature", "K", [0.0])
    with pytest.raises(ValueError, match="between 0 and 1"):
        convert_axis_values_to_si("vapor_mass_fraction", "1", [1.1])


def test_canonical_binary64_boundary_uses_stabilized_decimal_text() -> None:
    assert stable_number_text(-0.0) == "0"
    assert stable_binary64(-0.0) == 0.0
    assert str(decimal_from_binary64(0.1)) == "0.1"
    assert stable_number_text(binary64_from_decimal(decimal_from_binary64(1.234567890123456))) == (
        "1.23456789012346"
    )


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_canonical_binary64_boundary_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        stable_binary64(value)
