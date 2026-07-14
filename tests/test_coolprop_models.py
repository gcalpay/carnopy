from __future__ import annotations

import json
from pathlib import Path

import CoolProp.CoolProp as CP
import pandas as pd
import pytest

from carnopy.api import generate_dataset, validate_config
from carnopy.backends import CoolPropBackend
from carnopy.domain.failures import ConfigError

DENSITY_REL_TOL = 1e-11
DENSITY_ABS_TOL = 1e-9
ENTHALPY_REL_TOL = 1e-11
ENTHALPY_ABS_TOL = 1e-6
TEMPERATURE_ABS_TOL = 1e-8
PRESSURE_ABS_TOL = 1e-3


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


def _assert_direct_coolprop_agreement(
    frame: pd.DataFrame,
    *,
    model: str,
    mode: str,
) -> None:
    qualified_fluid = f"{model.upper()}::n-Propane"
    CP.set_reference_state(qualified_fluid, "DEF")
    if mode == "property_table":
        input_pairs = [("T", 300.0, "P", 100_000.0)]
    else:
        fractions = (0.0, 1.0) if mode == "saturation_table" else (0.0, 0.5, 1.0)
        input_pairs = [("P", 200_000.0, "Q", fraction) for fraction in fractions]

    for inputs, (_, row) in zip(input_pairs, frame.iterrows(), strict=True):
        input1, value1, input2, value2 = inputs
        assert row["backend_phase"] == CP.PhaseSI(
            input1,
            value1,
            input2,
            value2,
            qualified_fluid,
        )
        assert row["temperature_K"] == pytest.approx(
            CP.PropsSI("T", input1, value1, input2, value2, qualified_fluid),
            abs=TEMPERATURE_ABS_TOL,
        )
        assert row["pressure_Pa"] == pytest.approx(
            CP.PropsSI("P", input1, value1, input2, value2, qualified_fluid),
            abs=PRESSURE_ABS_TOL,
        )
        assert row["mass_density_kg_m3"] == pytest.approx(
            CP.PropsSI("DMASS", input1, value1, input2, value2, qualified_fluid),
            rel=DENSITY_REL_TOL,
            abs=DENSITY_ABS_TOL,
        )
        assert row["specific_enthalpy_J_kg"] == pytest.approx(
            CP.PropsSI("HMASS", input1, value1, input2, value2, qualified_fluid),
            rel=ENTHALPY_REL_TOL,
            abs=ENTHALPY_ABS_TOL,
        )


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
    _assert_direct_coolprop_agreement(frame, model=model, mode=mode)
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
    target = f"{model.upper()}::n-Propane"
    assert backend.reference_state_target("n-Propane") == target
    assert CP.AbstractState(model.upper(), "n-Propane").backend_name()
    CP.set_reference_state(target, "DEF")
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
