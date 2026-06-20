from __future__ import annotations

from pathlib import Path

from carnopy.backends import CoolPropBackend
from carnopy.config import load_config_file, normalize_config
from carnopy.generation import generate_property_table


def test_property_table_rows_are_deterministic(property_config_path: Path) -> None:
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(property_config_path).model, backend)
    rows = generate_property_table(config, backend, "run")
    assert [row["case_id"] for row in rows] == [0, 1]
    assert all(row["run_id"] == "run" for row in rows)
    assert all(row["phase"] for row in rows)
    assert all(row["valid"] for row in rows)


def test_strict_invalid_row_retains_successful_properties(tmp_path: Path) -> None:
    path = tmp_path / "surface.yaml"
    path.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300], unit: K}
  pressure: {kind: explicit, values: [1], unit: bar}
properties: [mass_density, surface_tension]
""",
        encoding="utf-8",
    )
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(path).model, backend)
    row = generate_property_table(config, backend, "run")[0]
    assert row["valid"] is False
    assert row["mass_density_kg_m3"] is not None
    assert row["surface_tension_N_m"] is None
    assert row["failure_property"] == "surface_tension"
