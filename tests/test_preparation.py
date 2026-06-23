from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset, generate_model_sweep, prepare_dataset
from carnopy.domain.failures import ConfigError
from carnopy.preparation.models import load_preparation_config


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _prep_config(
    path: Path,
    *,
    numeric: str = "[temperature, pressure, mass_density]",
    derived: str = "[specific_volume]",
    categorical: str = """  - field: phase
    encoding: one_hot
    categories: observed""",
    targets: str = "[specific_enthalpy]",
    auxiliary: str = "[fluid, backend_model, phase, run_id, case_id]",
    allow_partial: str = "false",
) -> Path:
    categorical_block = (
        "categorical_features: []"
        if categorical.strip() == "[]"
        else f"categorical_features:\n{categorical}"
    )
    return _write(
        path,
        f"""schema_version: 1
document_type: preparation
source_policy:
  allow_partial_sweep: {allow_partial}
features:
  numeric: {numeric}
  derived: {derived}
{categorical_block}
targets: {targets}
auxiliary: {auxiliary}
outputs:
  formats: [parquet]
""",
    )


def _property_config(path: Path, *, properties: str) -> Path:
    return _write(
        path,
        f"""schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {{kind: explicit, values: [300.0], unit: K}}
  pressure: {{kind: explicit, values: [100000.0, 200000.0], unit: Pa}}
properties: {properties}
outputs:
  dataset_formats: [parquet]
""",
    )


def _sweep_config(path: Path) -> Path:
    return _write(
        path,
        """schema_version: 2
document_type: model_sweep
backend:
  name: coolprop
  models: [heos, pr]
  reference_model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300.0], unit: K}
  pressure: {kind: explicit, values: [100000.0], unit: Pa}
properties: [mass_density, specific_enthalpy]
outputs:
  dataset_formats: [parquet]
""",
    )


def test_preparation_schema_v1_is_independent_from_dataset_schema_v1(tmp_path: Path) -> None:
    config = _prep_config(tmp_path / "preparation.yaml")
    assert load_preparation_config(config).model.schema_version == 1

    dataset_v1 = _write(
        tmp_path / "dataset-v1.yaml",
        """schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid: {}
properties: [mass_density]
""",
    )
    with pytest.raises(ConfigError, match="schema version 1 is no longer supported"):
        generate_dataset(dataset_v1, output_root=tmp_path / "runs")


def test_prepare_dataset_run_writes_manifest_and_preserves_order(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = _prep_config(tmp_path / "preparation.yaml")

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.status == "completed"
    assert result.unsplit_path is not None
    prepared = pd.read_parquet(result.unsplit_path)
    source = pd.read_parquet(run.output_directory / "dataset.parquet")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert prepared["source_row_index"].tolist() == list(range(len(source)))
    assert prepared["mass_density"].tolist() == source["mass_density_kg_m3"].tolist()
    assert prepared["specific_enthalpy"].tolist() == source["specific_enthalpy_J_kg"].tolist()
    assert prepared["specific_volume"].tolist() == pytest.approx(
        (1.0 / source["mass_density_kg_m3"]).tolist()
    )
    assert "phase__" in " ".join(prepared.columns)
    assert manifest["semantic_field_mapping"]["mass_density"]["column"] == "mass_density_kg_m3"
    assert manifest["semantic_field_mapping"]["temperature"]["unit"] == "K"
    assert manifest["eligible_row_count"] == len(source)
    assert pd.read_parquet(result.exclusions_path).empty


def test_prepare_includes_invalid_rows_when_requested_values_exist(tmp_path: Path) -> None:
    dataset = _property_config(tmp_path / "invalid.yaml", properties="[surface_tension]")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature]",
        derived="[]",
        categorical="[]",
        targets="[pressure]",
        auxiliary="[valid, failure_code]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.status == "completed"
    assert result.unsplit_path is not None
    prepared = pd.read_parquet(result.unsplit_path)
    assert prepared["source_valid"].eq(False).all()
    assert prepared["temperature"].notna().all()
    assert prepared["pressure"].notna().all()


def test_prepare_no_eligible_rows_is_explicit(tmp_path: Path) -> None:
    dataset = _property_config(tmp_path / "invalid.yaml", properties="[surface_tension]")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature]",
        derived="[]",
        categorical="[]",
        targets="[surface_tension]",
        auxiliary="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.status == "no_eligible_rows"
    assert result.unsplit_path is None
    assert not (result.output_directory / "data" / "unsplit.parquet").exists()
    exclusions = pd.read_parquet(result.exclusions_path)
    assert len(exclusions) == 2
    assert set(exclusions["primary_reason"]) == {"missing_required_field"}


def test_prepare_derived_features_use_source_columns_and_metadata_constants(tmp_path: Path) -> None:
    dataset = _property_config(
        tmp_path / "constants.yaml",
        properties=(
            "[mass_density, specific_enthalpy, critical_temperature, critical_pressure, molar_mass]"
        ),
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature, pressure]",
        derived="[reduced_temperature, reduced_pressure, compressibility_factor]",
        categorical="[]",
        targets="[mass_density]",
        auxiliary="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.unsplit_path is not None
    prepared = pd.read_parquet(result.unsplit_path)
    source = pd.read_parquet(run.output_directory / "dataset.parquet")
    assert prepared["reduced_temperature"].tolist() == pytest.approx(
        (source["temperature_K"] / source["critical_temperature_K"]).tolist()
    )
    assert prepared["reduced_pressure"].tolist() == pytest.approx(
        (source["pressure_Pa"] / source["critical_pressure_Pa"]).tolist()
    )
    expected_z = (
        source["pressure_Pa"]
        * source["molar_mass_kg_mol"]
        / (source["mass_density_kg_m3"] * 8.31446261815324 * source["temperature_K"])
    )
    assert prepared["compressibility_factor"].tolist() == pytest.approx(expected_z.tolist())


def test_prepare_excludes_rows_when_derived_constants_are_unavailable(tmp_path: Path) -> None:
    dataset = _property_config(
        tmp_path / "no-constants.yaml",
        properties="[mass_density, specific_enthalpy]",
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature]",
        derived="[reduced_temperature]",
        categorical="[]",
        targets="[mass_density]",
        auxiliary="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.status == "no_eligible_rows"
    exclusions = pd.read_parquet(result.exclusions_path)
    assert set(exclusions["primary_reason"]) == {"missing_derived_dependency"}
    assert all(
        "critical_temperature" in fields for fields in exclusions["missing_or_invalid_fields"]
    )


def test_prepare_rejects_role_conflicts_and_unknown_fields(tmp_path: Path) -> None:
    conflict = _prep_config(
        tmp_path / "conflict.yaml",
        numeric="[temperature]",
        derived="[]",
        targets="[temperature]",
    )
    with pytest.raises(ConfigError, match="both features and targets"):
        load_preparation_config(conflict)

    dataset = _property_config(tmp_path / "dataset.yaml", properties="[mass_density]")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    unknown = _prep_config(
        tmp_path / "unknown.yaml",
        numeric="[not_a_field]",
        derived="[]",
        categorical="[]",
        targets="[mass_density]",
    )
    with pytest.raises(ConfigError, match="unknown or unavailable numeric"):
        prepare_dataset(run.output_directory, config=unknown, output_root=tmp_path / "prepared")


def test_prepare_one_hot_categories_are_deterministic_and_explicit_unknowns_fail(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        categorical="""  - field: phase
    encoding: one_hot
    categories: [liquid]""",
    )

    with pytest.raises(ConfigError, match="omit observed values"):
        prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    observed = _prep_config(tmp_path / "observed.yaml")
    result = prepare_dataset(
        run.output_directory,
        config=observed,
        output_root=tmp_path / "prepared2",
    )
    assert result.unsplit_path is not None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    phase_vocab = manifest["categorical_vocabularies"]["phase"]
    assert phase_vocab["categories"] == sorted(phase_vocab["categories"], key=str)
    assert all(column.startswith("phase__") for column in phase_vocab["columns"])


def test_prepare_request_identity_is_output_independent_and_context_tracks_source(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    first = generate_dataset(property_config_path, output_root=tmp_path / "runs1")
    second = generate_dataset(property_config_path, output_root=tmp_path / "runs2")
    config = _prep_config(tmp_path / "preparation.yaml")

    prepared_first = prepare_dataset(
        first.output_directory,
        config=config,
        output_root=tmp_path / "p1",
    )
    prepared_second = prepare_dataset(
        second.output_directory,
        config=config,
        output_root=tmp_path / "p2",
    )

    assert prepared_first.preparation_request_id == prepared_second.preparation_request_id
    assert prepared_first.preparation_context_id != prepared_second.preparation_context_id


def test_prepare_sweep_source_order_and_partial_policy(tmp_path: Path) -> None:
    sweep = generate_model_sweep(
        _sweep_config(tmp_path / "sweep.yaml"),
        output_root=tmp_path / "sweeps",
    )
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature, pressure]",
        derived="[]",
        categorical="[]",
        targets="[mass_density]",
        auxiliary="[backend_model, state_key]",
    )

    result = prepare_dataset(
        sweep.output_directory,
        config=config,
        output_root=tmp_path / "prepared",
    )

    assert result.unsplit_path is not None
    prepared = pd.read_parquet(result.unsplit_path)
    assert prepared["backend_model"].tolist() == ["heos", "pr"]
    assert prepared["state_key"].notna().all()

    metadata_path = sweep.output_directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sweep_status"] = "incomplete"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ConfigError, match="source is incomplete"):
        prepare_dataset(sweep.output_directory, config=config, output_root=tmp_path / "reject")

    allow = _prep_config(
        tmp_path / "allow-partial.yaml",
        numeric="[temperature, pressure]",
        derived="[]",
        categorical="[]",
        targets="[mass_density]",
        auxiliary="[backend_model, state_key]",
        allow_partial="true",
    )
    partial = prepare_dataset(
        sweep.output_directory,
        config=allow,
        output_root=tmp_path / "partial",
    )
    manifest = json.loads(partial.manifest_path.read_text(encoding="utf-8"))
    assert manifest["partial_sweep_source"] is True


def test_preparation_execution_does_not_import_coolprop(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = _prep_config(tmp_path / "preparation.yaml")
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    script = f"""
import sys
from carnopy.preparation.pipeline import prepare_dataset

prepare_dataset(
    {str(run.output_directory)!r},
    {str(config)!r},
    output_root={str(tmp_path / "prepared")!r},
)
if "CoolProp" in sys.modules:
    raise SystemExit("CoolProp imported during preparation")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
