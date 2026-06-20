from __future__ import annotations

import pytest

from carnopy.domain.units import convert_axis_values_to_si, validate_axis_unit


def test_engineering_units_convert_to_si() -> None:
    assert convert_axis_values_to_si("temperature", "degC", [0.0]) == [273.15]
    assert convert_axis_values_to_si("pressure", "bar", [1.0]) == [100_000.0]


def test_invalid_unit_and_physical_values_fail() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        validate_axis_unit("temperature", "bar")
    with pytest.raises(ValueError, match="absolute zero"):
        convert_axis_values_to_si("temperature", "K", [0.0])
    with pytest.raises(ValueError, match="between 0 and 1"):
        convert_axis_values_to_si("vapor_mass_fraction", "1", [1.1])
