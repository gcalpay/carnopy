from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset, validate_config
from carnopy.backends import CoolPropBackend
from carnopy.domain.failures import ConfigError


def _write_config(
    path: Path,
    *,
    model: str,
    mode: str,
    grid: str,
    properties: str = "mass_density, specific_enthalpy",
) -> Path:
    path.write_text(
        f"""
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: {model}
mode: {mode}
fluids: [Propane]
grid:
{grid}
properties: [{properties}]
outputs:
  dataset_formats: [parquet]
""",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("model", ["heos", "pr", "srk"])
@pytest.mark.parametrize(
    ("mode", "grid", "expected_rows"),
    [
        (
            "property_table",
            "  temperature: {kind: explicit, values: [300], unit: K}\n"
            "  pressure: {kind: explicit, values: [1], unit: bar}",
            1,
        ),
        (
            "saturation_table",
            "  pressure: {kind: explicit, values: [2], unit: bar}",
            2,
        ),
        (
            "vapor_mass_fraction_table",
            "  pressure: {kind: explicit, values: [2], unit: bar}\n"
            '  vapor_mass_fraction: {kind: explicit, values: [0, 0.5, 1], unit: "1"}',
            3,
        ),
    ],
)
def test_all_models_generate_all_dataset_modes(
    tmp_path: Path,
    model: str,
    mode: str,
    grid: str,
    expected_rows: int,
) -> None:
    config = _write_config(
        tmp_path / f"{model}-{mode}.yaml",
        model=model,
        mode=mode,
        grid=grid,
    )
    run = generate_dataset(config, output_root=tmp_path / "runs")
    frame = pd.read_parquet(run.output_directory / "dataset.parquet")
    metadata = json.loads((run.output_directory / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads((run.output_directory / "report.json").read_text(encoding="utf-8"))

    assert len(frame) == expected_rows
    assert frame["valid"].all()
    assert frame["backend_model"].unique().tolist() == [model]
    assert run.backend == metadata["backend"] == report["backend"] == "coolprop"
    assert run.backend_model == metadata["backend_model"] == report["backend_model"] == model
    assert run.backend_version == metadata["backend_version"] == report["backend_version"]
    assert metadata["reference_state_backend_model"] == model
    assert metadata["reference_state_targets"] == [f"{model.upper()}::n-Propane"]
    normalized = json.loads(
        (run.output_directory / "config.normalized.json").read_text(encoding="utf-8")
    )
    assert normalized["schema_version"] == 2
    assert normalized["document_type"] == "dataset"
    assert normalized["backend"] == {"name": "coolprop", "model": model}
    unsupported = metadata["backend_model_capabilities"]["unsupported_properties"]
    if model == "heos":
        assert unsupported == []
    else:
        assert "dynamic_viscosity" in unsupported
        assert "kinematic_viscosity" in unsupported


@pytest.mark.parametrize("model", ["pr", "srk"])
@pytest.mark.parametrize(
    "property_name",
    [
        "dynamic_viscosity",
        "kinematic_viscosity",
        "thermal_conductivity",
        "prandtl_number",
        "surface_tension",
        "triple_point_temperature",
    ],
)
def test_cubic_models_reject_globally_unsupported_properties(
    tmp_path: Path,
    model: str,
    property_name: str,
) -> None:
    config = _write_config(
        tmp_path / f"{model}-{property_name}.yaml",
        model=model,
        mode="property_table",
        grid=(
            "  temperature: {kind: explicit, values: [300], unit: K}\n"
            "  pressure: {kind: explicit, values: [1], unit: bar}"
        ),
        properties=property_name,
    )
    with pytest.raises(
        ConfigError,
        match=rf"CoolProp model {model} does not support properties: {property_name}",
    ):
        validate_config(config)


@pytest.mark.parametrize("model", ["heos", "pr", "srk"])
def test_backend_qualifies_calls_and_reference_targets(model: str) -> None:
    backend = CoolPropBackend(model=model)  # type: ignore[arg-type]
    assert backend.reference_state_target("n-Propane") == f"{model.upper()}::n-Propane"
    density = backend.property("DMASS", "n-Propane", "T", 300.0, "P", 100_000.0)
    assert density.valid
    assert density.value is not None
    assert density.value > 0


def test_cubic_model_rejects_fluid_missing_from_cubics_library(tmp_path: Path) -> None:
    config = _write_config(
        tmp_path / "air-pr.yaml",
        model="pr",
        mode="property_table",
        grid=(
            "  temperature: {kind: explicit, values: [300], unit: K}\n"
            "  pressure: {kind: explicit, values: [1], unit: bar}"
        ),
    )
    config.write_text(
        config.read_text(encoding="utf-8").replace("fluids: [Propane]", "fluids: [Air]"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="model pr does not support pure fluid"):
        validate_config(config)


def test_model_selection_changes_scientific_identity(tmp_path: Path) -> None:
    grid = (
        "  temperature: {kind: explicit, values: [300], unit: K}\n"
        "  pressure: {kind: explicit, values: [1], unit: bar}"
    )
    heos = _write_config(
        tmp_path / "heos.yaml",
        model="heos",
        mode="property_table",
        grid=grid,
    )
    pr = _write_config(
        tmp_path / "pr.yaml",
        model="pr",
        mode="property_table",
        grid=grid,
    )
    heos_run = generate_dataset(heos, output_root=tmp_path / "heos-runs")
    pr_run = generate_dataset(pr, output_root=tmp_path / "pr-runs")

    assert heos_run.spec_id != pr_run.spec_id
    assert heos_run.generation_context_id != pr_run.generation_context_id
    assert (
        heos_run.output_directory.joinpath("config.normalized.json").read_bytes()
        != pr_run.output_directory.joinpath("config.normalized.json").read_bytes()
    )
