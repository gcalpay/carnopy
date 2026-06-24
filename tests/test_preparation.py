from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from carnopy.api import generate_dataset, generate_model_sweep, prepare_dataset
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.preparation.models import load_preparation_config


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _relative_files(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    }


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
    outputs: str = "  formats: [parquet]",
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
{outputs}
""",
    )


def _prep_config_with_scenarios(path: Path, scenarios: str, **kwargs: str) -> Path:
    base = _prep_config(path, **kwargs).read_text(encoding="utf-8")
    return _write(path, base + "\n" + scenarios)


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


def _grid_property_config(
    path: Path,
    *,
    fluids: str = "[Propane]",
    temperatures: str = "[300.0]",
    pressures: str = "[100000.0, 200000.0, 300000.0, 400000.0]",
    properties: str = "[mass_density, specific_enthalpy]",
) -> Path:
    return _write(
        path,
        f"""schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: {fluids}
grid:
  temperature: {{kind: explicit, values: {temperatures}, unit: K}}
  pressure: {{kind: explicit, values: {pressures}, unit: Pa}}
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
    assert result.table_path is not None
    prepared = pd.read_parquet(result.table_path)
    provenance = pd.read_parquet(result.provenance_path)
    source_diagnostics = pd.read_parquet(result.source_diagnostics_path)
    source = pd.read_parquet(run.output_directory / "dataset.parquet")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert prepared["prepared_row_id"].tolist() == list(range(len(source)))
    assert provenance["prepared_row_id"].tolist() == prepared["prepared_row_id"].tolist()
    assert provenance["source_row_index"].tolist() == list(range(len(source)))
    assert source_diagnostics["prepared_row_id"].tolist() == prepared["prepared_row_id"].tolist()
    assert "source_row_hash" not in prepared.columns
    assert "source_failure_code" not in prepared.columns
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
    assert result.scenario_report_path is None
    assert result.scenario_count == 0
    assert result.partition_count == 0
    assert _relative_files(result.output_directory) == {
        "data/diagnostics.parquet",
        "data/exclusions.parquet",
        "data/provenance.parquet",
        "data/table.parquet",
        "dataset_card.md",
        "diagnostics.json",
        "manifest.json",
        "preparation.normalized.json",
        "preparation.original.yaml",
    }
    assert {
        "preparation_schema_version",
        "preparation_request_id",
        "preparation_context_id",
        "preparation_run_id",
        "status",
        "source",
        "source_artifacts",
        "semantic_field_mapping",
        "features",
        "targets",
        "auxiliary",
        "eligible_row_count",
        "excluded_row_count",
        "data_artifacts",
        "column_roles",
        "artifact_hashes",
    }.issubset(manifest)
    diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
    assert {
        "status",
        "source_kind",
        "source_row_count",
        "excluded_row_count",
        "exclusion_counts_by_reason",
    }.issubset(diagnostics)
    assert result.dataset_card_path.read_text(encoding="utf-8").startswith(
        "# Carnopy prepared dataset\n"
    )


def test_prepare_writes_numpy_and_safetensors_exports(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    from safetensors.numpy import load_file

    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        outputs="""  parquet: true
  arrays:
    formats: [npz, safetensors, npy]
    dtype: float32
    include_auxiliary: false""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.table_path is not None
    table = pd.read_parquet(result.table_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    arrays = manifest["array_exports"]
    assert arrays["enabled"] is True
    assert arrays["formats"] == ["npy", "npz", "safetensors"]
    assert arrays["dtype"] == "float32"
    assert arrays["feature_columns"][:4] == [
        "temperature",
        "pressure",
        "mass_density",
        "specific_volume",
    ]
    assert any(column.startswith("phase__") for column in arrays["feature_columns"])
    assert arrays["target_columns"] == ["specific_enthalpy"]
    assert arrays["source_table"] == "table.parquet"
    assert set(arrays["float_conversion"]["features"]) == set(arrays["feature_columns"])

    directory = result.output_directory / "data" / "arrays"
    features_npy = np.load(directory / "features.float32.npy", allow_pickle=False)
    targets_npy = np.load(directory / "targets.float32.npy", allow_pickle=False)
    expected_features = table.loc[:, arrays["feature_columns"]].to_numpy(dtype=np.float32)
    expected_targets = table.loc[:, arrays["target_columns"]].to_numpy(dtype=np.float32)
    np.testing.assert_array_equal(features_npy, expected_features)
    np.testing.assert_array_equal(targets_npy, expected_targets)

    with np.load(directory / "dataset.float32.npz", allow_pickle=False) as archive:
        assert sorted(archive.files) == ["features", "targets"]
        np.testing.assert_array_equal(archive["features"], expected_features)
        np.testing.assert_array_equal(archive["targets"], expected_targets)

    tensors = load_file(directory / "dataset.float32.safetensors")
    assert sorted(tensors) == ["features", "targets"]
    np.testing.assert_array_equal(tensors["features"], expected_features)
    np.testing.assert_array_equal(tensors["targets"], expected_targets)
    assert not (directory / "dataset.float32.pt").exists()
    assert not (directory / "dataset.float32.pth").exists()


def test_prepare_float64_array_exports_match_table_exactly(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        outputs="""  parquet: true
  arrays:
    formats: [npy]
    dtype: float64
    include_auxiliary: false""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.table_path is not None
    table = pd.read_parquet(result.table_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    arrays = manifest["array_exports"]
    expected = table.loc[:, arrays["feature_columns"]].to_numpy(dtype=np.float64)
    actual = np.load(
        result.output_directory / "data" / "arrays" / "features.float64.npy",
        allow_pickle=False,
    )
    np.testing.assert_array_equal(actual, expected, strict=True)
    for summary in arrays["float_conversion"]["features"].values():
        assert summary == {
            "max_abs_error": 0.0,
            "max_rel_error": 0.0,
            "mean_abs_error": 0.0,
        }


def test_prepare_array_auxiliary_requires_safe_columns(
    tmp_path: Path, property_config_path: Path
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    unsafe = _prep_config(
        tmp_path / "unsafe.yaml",
        outputs="""  parquet: true
  arrays:
    formats: [npy]
    dtype: float32
    include_auxiliary: true""",
    )

    with pytest.raises(OutputError, match="unsupported: run_id"):
        prepare_dataset(run.output_directory, config=unsafe, output_root=tmp_path / "prepared")

    safe = _prep_config(
        tmp_path / "safe.yaml",
        auxiliary="[fluid, backend_model, phase, case_id]",
        outputs="""  parquet: true
  arrays:
    formats: [npz]
    dtype: float32
    include_auxiliary: true""",
    )

    result = prepare_dataset(run.output_directory, config=safe, output_root=tmp_path / "prepared2")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    arrays = manifest["array_exports"]
    assert arrays["auxiliary_columns"] == ["fluid", "backend_model", "phase", "case_id"]
    assert arrays["categorical_auxiliary"]["fluid"]["encoding"] == "int_code"
    assert arrays["categorical_auxiliary"]["fluid"]["dtype"] == "int32"
    with np.load(
        result.output_directory / "data" / "arrays" / "dataset.float32.npz",
        allow_pickle=False,
    ) as archive:
        assert sorted(archive.files) == [
            "auxiliary_categorical",
            "auxiliary_numeric",
            "features",
            "targets",
        ]
        assert archive["auxiliary_categorical"].dtype == np.int32
        assert archive["auxiliary_numeric"].dtype == np.float32


def test_prepare_rejects_array_formats_in_legacy_formats_field(tmp_path: Path) -> None:
    config = _prep_config(
        tmp_path / "preparation.yaml",
        outputs="  formats: [parquet, npy]",
    )

    with pytest.raises(ConfigError, match=r"array formats must be declared under outputs\.arrays"):
        load_preparation_config(config)


def test_prepare_rejects_array_outputs_without_dtype(tmp_path: Path) -> None:
    config = _prep_config(
        tmp_path / "preparation.yaml",
        outputs="""  parquet: true
  arrays:
    formats: [npy]""",
    )

    with pytest.raises(ConfigError, match="array output dtype is required"):
        load_preparation_config(config)


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
    assert result.table_path is not None
    prepared = pd.read_parquet(result.table_path)
    source_diagnostics = pd.read_parquet(result.source_diagnostics_path)
    assert source_diagnostics["source_valid"].eq(False).all()
    assert prepared["temperature"].notna().all()
    assert prepared["pressure"].notna().all()
    assert prepared["valid"].eq(False).all()


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
    assert result.table_path is None
    assert not (result.output_directory / "data" / "table.parquet").exists()
    assert result.provenance_path.is_file()
    assert result.source_diagnostics_path.is_file()
    exclusions = pd.read_parquet(result.exclusions_path)
    assert len(exclusions) == 2
    assert set(exclusions["primary_reason"]) == {"missing_required_field"}


def test_prepare_no_eligible_rows_skips_array_exports(tmp_path: Path) -> None:
    dataset = _property_config(tmp_path / "invalid.yaml", properties="[surface_tension]")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config(
        tmp_path / "preparation.yaml",
        numeric="[temperature]",
        derived="[]",
        categorical="[]",
        targets="[surface_tension]",
        auxiliary="[]",
        outputs="""  parquet: true
  arrays:
    formats: [npy, npz]
    dtype: float32
    include_auxiliary: false""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.status == "no_eligible_rows"
    assert manifest["array_exports"] == {"enabled": False, "exports": []}
    assert not (result.output_directory / "data" / "arrays").exists()


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

    assert result.table_path is not None
    prepared = pd.read_parquet(result.table_path)
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
    assert result.table_path is not None
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


def test_prepare_rejects_invalid_scenario_names_and_partitions(tmp_path: Path) -> None:
    invalid_name = _prep_config_with_scenarios(
        tmp_path / "invalid-name.yaml",
        """scenarios:
  - name: "not safe"
    kind: unsplit
""",
    )
    with pytest.raises(ConfigError, match="safe slugs"):
        load_preparation_config(invalid_name)

    invalid_shuffle = _prep_config_with_scenarios(
        tmp_path / "invalid-shuffle.yaml",
        """scenarios:
  - name: bad_shuffle
    kind: shuffle
    partitions:
      train: 0.8
      all: 0.2
""",
    )
    with pytest.raises(ConfigError, match="all partition"):
        load_preparation_config(invalid_shuffle)

    invalid_remainder = _prep_config_with_scenarios(
        tmp_path / "invalid-remainder.yaml",
        """scenarios:
  - name: bad_holdout
    kind: leave_fluid_out
    holdouts:
      train: [Propane]
    remainder: train
""",
    )
    with pytest.raises(ConfigError, match="remainder as a holdout"):
        load_preparation_config(invalid_remainder)


def test_prepare_rejects_empty_declared_holdout_partitions(tmp_path: Path) -> None:
    dataset = _grid_property_config(tmp_path / "dataset.yaml")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: missing_fluid_holdout
    kind: leave_fluid_out
    holdouts:
      test: [Isopentane]
    remainder: train
""",
        categorical="[]",
        derived="[]",
    )

    with pytest.raises(ConfigError, match="empty partitions: test"):
        prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")


def test_prepare_shuffle_scenario_is_deterministic_and_seeded(tmp_path: Path) -> None:
    dataset = _grid_property_config(
        tmp_path / "grid.yaml",
        pressures="[100000.0, 150000.0, 200000.0, 250000.0, 300000.0, 350000.0]",
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    scenarios = """scenarios:
  - name: shuffle_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
"""
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        scenarios,
        categorical="[]",
        derived="[]",
    )

    first = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "first")
    second = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "second")

    first_train = pd.read_parquet(
        first.output_directory / "data/scenarios/shuffle_baseline/train.parquet"
    )
    second_train = pd.read_parquet(
        second.output_directory / "data/scenarios/shuffle_baseline/train.parquet"
    )
    assert first_train["prepared_row_id"].tolist() == second_train["prepared_row_id"].tolist()
    assert "source_row_hash" not in first_train.columns
    assert first.scenario_count == 1
    assert first.partition_count == 2
    assert first.scenario_report_path is not None
    assert first.scenario_report_path.is_file()

    changed_seed = _prep_config_with_scenarios(
        tmp_path / "changed-seed.yaml",
        scenarios.replace("42", "7"),
        categorical="[]",
        derived="[]",
    )
    changed = prepare_dataset(
        run.output_directory,
        config=changed_seed,
        output_root=tmp_path / "changed",
    )
    changed_train = pd.read_parquet(
        changed.output_directory / "data/scenarios/shuffle_baseline/train.parquet"
    )
    assert first_train["prepared_row_id"].tolist() != changed_train["prepared_row_id"].tolist()


def test_prepare_scenario_transformations_use_train_statistics(tmp_path: Path) -> None:
    dataset = _grid_property_config(
        tmp_path / "grid.yaml",
        pressures="[100000.0, 150000.0, 200000.0, 250000.0, 300000.0, 350000.0]",
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: shuffle_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    transformations:
      - field: pressure
        methods: [log10, standard]
""",
        categorical="[]",
        derived="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    train = pd.read_parquet(
        result.output_directory / "data/scenarios/shuffle_baseline/train.parquet"
    )
    test = pd.read_parquet(result.output_directory / "data/scenarios/shuffle_baseline/test.parquet")
    scenario = json.loads(
        result.output_directory.joinpath("data/scenarios/shuffle_baseline/scenario.json").read_text(
            encoding="utf-8"
        )
    )
    output_column = "pressure__log10__standard"
    assert output_column in train.columns
    assert output_column in test.columns
    assert "pressure" in train.columns
    assert train[output_column].mean() == pytest.approx(0.0)
    assert scenario["transformations"][0]["fit_partition"] == "train"
    assert scenario["transformations"][0]["steps"][1]["method"] == "standard"


def test_prepare_scenario_partitions_write_array_exports(tmp_path: Path) -> None:
    run = generate_dataset(
        _grid_property_config(tmp_path / "grid.yaml"),
        output_root=tmp_path / "runs",
    )
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: shuffle_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    transformations:
      - field: pressure
        methods: [log10]
""",
        outputs="""  parquet: true
  arrays:
    formats: [npz]
    dtype: float32
    include_auxiliary: false""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.scenario_report_path is not None
    report = json.loads(result.scenario_report_path.read_text(encoding="utf-8"))
    scenario = report["scenarios"][0]
    train_arrays = scenario["array_exports"]["train"]
    assert train_arrays["enabled"] is True
    assert "pressure__log10" in train_arrays["feature_columns"]
    train_archive = (
        result.output_directory / "data/scenarios/shuffle_baseline/arrays/train.dataset.float32.npz"
    )
    with np.load(train_archive, allow_pickle=False) as archive:
        assert sorted(archive.files) == ["features", "targets"]
        assert archive["features"].dtype == np.float32


def test_prepare_holdout_scenarios_select_expected_rows(tmp_path: Path) -> None:
    dataset = _grid_property_config(
        tmp_path / "multi.yaml",
        fluids="[Propane, Isopentane]",
        pressures="[100000.0, 200000.0]",
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: leave_fluid_out
    kind: leave_fluid_out
    holdouts:
      test: [Isopentane]
    remainder: train
  - name: pressure_range
    kind: range_holdout
    field: pressure
    holdouts:
      validation: {min: 100000.0, max: 100000.0}
    remainder: train
  - name: pressure_temperature_block
    kind: coordinate_block
    holdouts:
      test:
        pressure: {min: 200000.0, max: 200000.0}
        temperature: {min: 300.0, max: 300.0}
    remainder: train
""",
        categorical="[]",
        derived="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    fluid_test = pd.read_parquet(
        result.output_directory / "data/scenarios/leave_fluid_out/test.parquet"
    )
    assert set(fluid_test["fluid"]) == {"Isopentane"}
    pressure_validation = pd.read_parquet(
        result.output_directory / "data/scenarios/pressure_range/validation.parquet"
    )
    assert set(pressure_validation["pressure"]) == {100000.0}
    block_test = pd.read_parquet(
        result.output_directory / "data/scenarios/pressure_temperature_block/test.parquet"
    )
    assert set(block_test["pressure"]) == {200000.0}
    assert set(block_test["temperature"]) == {300.0}


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

    assert result.table_path is not None
    prepared = pd.read_parquet(result.table_path)
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


def test_prepare_model_holdout_requires_sweep_source(tmp_path: Path) -> None:
    dataset = _grid_property_config(tmp_path / "dataset.yaml")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: holdout_model
    kind: model_holdout
    holdouts:
      test: [pr]
    remainder: train
""",
        categorical="[]",
        derived="[]",
        auxiliary="[fluid, backend_model]",
    )

    with pytest.raises(ConfigError, match="model-sweep source"):
        prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    sweep = generate_model_sweep(
        _sweep_config(tmp_path / "sweep.yaml"),
        output_root=tmp_path / "sweeps",
    )
    result = prepare_dataset(
        sweep.output_directory,
        config=config,
        output_root=tmp_path / "sweep-prep",
    )
    model_test = pd.read_parquet(
        result.output_directory / "data/scenarios/holdout_model/test.parquet"
    )
    assert set(model_test["backend_model"]) == {"pr"}


def test_prepare_no_eligible_rows_skips_scenario_artifacts(tmp_path: Path) -> None:
    dataset = _property_config(tmp_path / "invalid.yaml", properties="[surface_tension]")
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: no_rows
    kind: unsplit
""",
        numeric="[temperature]",
        derived="[]",
        categorical="[]",
        targets="[surface_tension]",
        auxiliary="[]",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    assert result.status == "no_eligible_rows"
    assert result.scenario_report_path is None
    assert not (result.output_directory / "scenario_report.json").exists()
    assert not (result.output_directory / "data/scenarios").exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenarios"]["status"] == "skipped_no_eligible_rows"


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
