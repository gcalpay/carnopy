from __future__ import annotations

from pathlib import Path

import CoolProp.CoolProp as CP
import pandas as pd
import pytest

from carnopy.api import generate_dataset

TEMPERATURE_ABS_TOL = 1e-8
PRESSURE_ABS_TOL = 1e-3
DENSITY_REL_TOL = 1e-11
DENSITY_ABS_TOL = 1e-9
ENTHALPY_REL_TOL = 1e-11
ENTHALPY_ABS_TOL = 1e-6


def _generate_parquet(
    tmp_path: Path,
    *,
    name: str,
    config_text: str,
) -> pd.DataFrame:
    config_path = tmp_path / f"{name}.yaml"
    config_path.write_text(config_text, encoding="utf-8")
    result = generate_dataset(
        config_path,
        output_root=tmp_path / f"{name}-runs",
    )
    return pd.read_parquet(result.output_directory / "dataset.parquet")


def _reset_reference_state(fluid: str) -> None:
    CP.set_reference_state(fluid, "DEF")


def test_property_table_matches_direct_coolprop(tmp_path: Path) -> None:
    fluid = "Water"
    temperature = 300.0
    pressure = 100_000.0
    _reset_reference_state(fluid)

    frame = _generate_parquet(
        tmp_path,
        name="water-property",
        config_text=f"""
schema_version: 1
backend: coolprop
mode: property_table
fluids: [{fluid}]
grid:
  temperature: {{kind: explicit, values: [{temperature}], unit: K}}
  pressure: {{kind: explicit, values: [{pressure}], unit: Pa}}
properties: [mass_density, specific_enthalpy]
""",
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert bool(row["valid"])
    assert row["fluid"] == fluid
    assert row["phase"] == "liquid"
    assert row["backend_phase"] == CP.PhaseSI(
        "T",
        temperature,
        "P",
        pressure,
        fluid,
    )
    assert row["temperature_K"] == pytest.approx(
        temperature,
        abs=TEMPERATURE_ABS_TOL,
    )
    assert row["pressure_Pa"] == pytest.approx(
        pressure,
        abs=PRESSURE_ABS_TOL,
    )
    assert row["mass_density_kg_m3"] == pytest.approx(
        CP.PropsSI("DMASS", "T", temperature, "P", pressure, fluid),
        rel=DENSITY_REL_TOL,
        abs=DENSITY_ABS_TOL,
    )
    assert row["specific_enthalpy_J_kg"] == pytest.approx(
        CP.PropsSI("HMASS", "T", temperature, "P", pressure, fluid),
        rel=ENTHALPY_REL_TOL,
        abs=ENTHALPY_ABS_TOL,
    )


def test_saturation_table_matches_direct_coolprop(tmp_path: Path) -> None:
    fluid = "Cyclopentane"
    pressure = 101_325.0
    _reset_reference_state(fluid)

    frame = _generate_parquet(
        tmp_path,
        name="cyclopentane-saturation",
        config_text=f"""
schema_version: 1
backend: coolprop
mode: saturation_table
fluids: [{fluid}]
grid:
  pressure: {{kind: explicit, values: [{pressure}], unit: Pa}}
properties: [mass_density, specific_enthalpy]
""",
    )

    assert frame["valid"].astype(bool).all()
    assert frame["phase"].tolist() == ["saturated_liquid", "saturated_vapor"]
    assert frame["saturation_endpoint"].tolist() == [
        "saturated_liquid",
        "saturated_vapor",
    ]
    for fraction, (_, row) in zip((0.0, 1.0), frame.iterrows(), strict=True):
        assert row["backend_phase"] == CP.PhaseSI(
            "P",
            pressure,
            "Q",
            fraction,
            fluid,
        )
        assert row["pressure_Pa"] == pytest.approx(
            pressure,
            abs=PRESSURE_ABS_TOL,
        )
        assert row["temperature_K"] == pytest.approx(
            CP.PropsSI("T", "P", pressure, "Q", fraction, fluid),
            abs=TEMPERATURE_ABS_TOL,
        )
        assert row["mass_density_kg_m3"] == pytest.approx(
            CP.PropsSI("DMASS", "P", pressure, "Q", fraction, fluid),
            rel=DENSITY_REL_TOL,
            abs=DENSITY_ABS_TOL,
        )
        assert row["specific_enthalpy_J_kg"] == pytest.approx(
            CP.PropsSI("HMASS", "P", pressure, "Q", fraction, fluid),
            rel=ENTHALPY_REL_TOL,
            abs=ENTHALPY_ABS_TOL,
        )


def test_vapor_mass_fraction_table_matches_coolprop_and_mixture_invariants(
    tmp_path: Path,
) -> None:
    fluid = "Isopentane"
    pressure = 200_000.0
    fractions = (0.0, 0.01, 0.5, 0.99, 1.0)
    _reset_reference_state(fluid)

    frame = _generate_parquet(
        tmp_path,
        name="isopentane-vapor-fraction",
        config_text=f"""
schema_version: 1
backend: coolprop
mode: vapor_mass_fraction_table
fluids: [{fluid}]
grid:
  pressure: {{kind: explicit, values: [{pressure}], unit: Pa}}
  vapor_mass_fraction:
    kind: explicit
    values: [{", ".join(str(value) for value in fractions)}]
    unit: "1"
properties: [mass_density, specific_enthalpy]
""",
    )

    assert frame["valid"].astype(bool).all()
    assert frame["vapor_mass_fraction"].tolist() == list(fractions)
    assert frame["phase"].tolist() == [
        "saturated_liquid",
        "two_phase",
        "two_phase",
        "two_phase",
        "saturated_vapor",
    ]
    for fraction, (_, row) in zip(fractions, frame.iterrows(), strict=True):
        assert row["backend_phase"] == CP.PhaseSI(
            "P",
            pressure,
            "Q",
            fraction,
            fluid,
        )
        assert row["pressure_Pa"] == pytest.approx(
            pressure,
            abs=PRESSURE_ABS_TOL,
        )
        assert row["temperature_K"] == pytest.approx(
            CP.PropsSI("T", "P", pressure, "Q", fraction, fluid),
            abs=TEMPERATURE_ABS_TOL,
        )
        assert row["mass_density_kg_m3"] == pytest.approx(
            CP.PropsSI("DMASS", "P", pressure, "Q", fraction, fluid),
            rel=DENSITY_REL_TOL,
            abs=DENSITY_ABS_TOL,
        )
        assert row["specific_enthalpy_J_kg"] == pytest.approx(
            CP.PropsSI("HMASS", "P", pressure, "Q", fraction, fluid),
            rel=ENTHALPY_REL_TOL,
            abs=ENTHALPY_ABS_TOL,
        )

    indexed = frame.set_index("vapor_mass_fraction")
    liquid = indexed.loc[0.0]
    vapor = indexed.loc[1.0]
    for fraction in (0.01, 0.5, 0.99):
        row = indexed.loc[fraction]
        expected_enthalpy = (1.0 - fraction) * float(
            liquid["specific_enthalpy_J_kg"]
        ) + fraction * float(vapor["specific_enthalpy_J_kg"])
        assert row["specific_enthalpy_J_kg"] == pytest.approx(
            expected_enthalpy,
            rel=ENTHALPY_REL_TOL,
            abs=ENTHALPY_ABS_TOL,
        )
        expected_specific_volume = (1.0 - fraction) / float(
            liquid["mass_density_kg_m3"]
        ) + fraction / float(vapor["mass_density_kg_m3"])
        actual_specific_volume = 1.0 / float(row["mass_density_kg_m3"])
        assert actual_specific_volume == pytest.approx(
            expected_specific_volume,
            rel=DENSITY_REL_TOL,
            abs=1e-12,
        )


@pytest.mark.parametrize(
    ("fluid", "expected_temperature", "uncertainty", "source"),
    [
        (
            "Propane",
            231.1,
            0.2,
            "https://webbook.nist.gov/cgi/cbook.cgi?ID=C74986&Mask=4",
        ),
        (
            "Cyclopentane",
            322.4,
            0.3,
            "https://webbook.nist.gov/cgi/cbook.cgi?ID=C287923&Mask=4",
        ),
    ],
)
def test_normal_boiling_point_is_within_nist_interval(
    tmp_path: Path,
    fluid: str,
    expected_temperature: float,
    uncertainty: float,
    source: str,
) -> None:
    pressure = 101_325.0
    frame = _generate_parquet(
        tmp_path,
        name=f"{fluid.casefold()}-normal-boiling",
        config_text=f"""
schema_version: 1
backend: coolprop
mode: saturation_table
fluids: [{fluid}]
grid:
  pressure: {{kind: explicit, values: [{pressure}], unit: Pa}}
properties: [mass_density]
""",
    )

    assert frame["valid"].astype(bool).all()
    assert len(frame) == 2
    liquid_temperature, vapor_temperature = frame["temperature_K"].tolist()
    assert liquid_temperature == pytest.approx(
        vapor_temperature,
        abs=TEMPERATURE_ABS_TOL,
    )
    lower = expected_temperature - uncertainty
    upper = expected_temperature + uncertainty
    assert lower <= liquid_temperature <= upper, (
        f"{fluid} normal boiling point {liquid_temperature} K is outside "
        f"the NIST interval [{lower}, {upper}] K from {source}"
    )
