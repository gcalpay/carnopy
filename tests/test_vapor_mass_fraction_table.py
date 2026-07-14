from __future__ import annotations

from pathlib import Path

import CoolProp.CoolProp as CP
import pytest

from carnopy.backends import CoolPropBackend
from carnopy.config import load_config_file, normalize_config
from carnopy.generation import generate_vapor_mass_fraction_table


def test_vapor_fraction_phases(vapor_config_path: Path) -> None:
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(vapor_config_path).model, backend)
    rows = generate_vapor_mass_fraction_table(config, backend, "run")
    assert [row["phase"] for row in rows] == [
        "saturated_liquid",
        "two_phase",
        "saturated_vapor",
    ]
    assert all(row["valid"] for row in rows)


def test_pressure_driven_vapor_fraction_table(tmp_path: Path) -> None:
    path = tmp_path / "pressure.yaml"
    path.write_text(
        """
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: vapor_mass_fraction_table
fluids: [Propane]
grid:
  pressure: {kind: explicit, values: [2], unit: bar}
  vapor_mass_fraction: {kind: explicit, values: [0.5], unit: "1"}
properties: [mass_density]
""",
        encoding="utf-8",
    )
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(path).model, backend)
    row = generate_vapor_mass_fraction_table(config, backend, "run")[0]
    assert row["temperature_K"] is not None
    assert row["valid"] is True


@pytest.mark.parametrize("model", ["heos", "pr", "srk"])
def test_invalid_vapor_fraction_state_retains_backend_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    path = tmp_path / f"invalid-pressure-{model}.yaml"
    path.write_text(
        f"""
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: {model}
mode: vapor_mass_fraction_table
fluids: [Propane]
grid:
  pressure: {{kind: explicit, values: [2], unit: bar}}
  vapor_mass_fraction: {{kind: explicit, values: [0.5], unit: "1"}}
properties: [mass_density]
""",
        encoding="utf-8",
    )
    original_propssi = CP.PropsSI

    def fail_saturation_coordinate(
        output: str,
        input1: str,
        value1: float,
        input2: str,
        value2: float,
        fluid: str,
    ) -> float:
        if output == "T" and input2 == "Q":
            raise ValueError("portable saturation-coordinate failure")
        return float(original_propssi(output, input1, value1, input2, value2, fluid))

    monkeypatch.setattr(CP, "PropsSI", fail_saturation_coordinate)
    backend = CoolPropBackend(model=model)  # type: ignore[arg-type]
    config = normalize_config(load_config_file(path).model, backend)
    row = generate_vapor_mass_fraction_table(config, backend, "run")[0]

    assert row["valid"] is False
    assert row["failure_layer"] == "domain"
    assert row["failure_code"] == "outside_saturation_domain"
    assert row["backend_error_type"] == "ValueError"
    assert row["backend_error_message"]
