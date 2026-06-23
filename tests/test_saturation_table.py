from __future__ import annotations

from pathlib import Path

from carnopy.backends import CoolPropBackend
from carnopy.config import load_config_file, normalize_config
from carnopy.generation import generate_saturation_table


def test_temperature_saturation_emits_two_endpoints(
    saturation_config_path: Path,
) -> None:
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(saturation_config_path).model, backend)
    rows = generate_saturation_table(config, backend, "run")
    assert [row["saturation_endpoint"] for row in rows] == [
        "saturated_liquid",
        "saturated_vapor",
    ]
    assert rows[0]["pressure_Pa"] == rows[1]["pressure_Pa"]
    assert all(row["valid"] for row in rows)


def test_pressure_saturation_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "pressure.yaml"
    path.write_text(
        """
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: saturation_table
fluids: [Propane]
grid:
  pressure: {kind: explicit, values: [2], unit: bar}
properties: [specific_enthalpy]
""",
        encoding="utf-8",
    )
    backend = CoolPropBackend()
    config = normalize_config(load_config_file(path).model, backend)
    rows = generate_saturation_table(config, backend, "run")
    assert len(rows) == 2
    assert rows[0]["temperature_K"] == rows[1]["temperature_K"]
