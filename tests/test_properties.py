from __future__ import annotations

from carnopy.backends import CoolPropBackend
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.generation.common import evaluate_properties


def test_registry_classifies_reference_and_derived_properties() -> None:
    assert PROPERTY_REGISTRY["specific_enthalpy"].reference_dependent
    assert PROPERTY_REGISTRY["kinematic_viscosity"].classification == "derived"
    assert PROPERTY_REGISTRY["kinematic_viscosity"].dependencies == (
        "dynamic_viscosity",
        "mass_density",
    )


def test_derived_dependencies_are_hidden_when_not_requested() -> None:
    row: dict[str, object] = {}
    failures = evaluate_properties(
        row,
        backend=CoolPropBackend(),
        mode="property_table",
        fluid="n-Propane",
        input1="T",
        value1=300.0,
        input2="P",
        value2=100_000.0,
        properties=["kinematic_viscosity"],
    )
    assert not failures
    assert "kinematic_viscosity_m2_s" in row
    assert "dynamic_viscosity_Pa_s" not in row
    assert "mass_density_kg_m3" not in row
