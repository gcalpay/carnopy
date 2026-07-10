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
from carnopy.preparation.baselines import build_baseline_diagnostics
from carnopy.preparation.fields import ResolvedField, ResolvedPreparation
from carnopy.preparation.grid_diagnostics import build_structured_grid_summary
from carnopy.preparation.matrix_diagnostics import build_matrix_diagnostics
from carnopy.preparation.models import (
    BaselineDiagnosticsConfig,
    MatrixDiagnosticsConfig,
    load_preparation_config,
)
from carnopy.preparation.quality import build_quality_artifacts
from carnopy.preparation.rows import SOURCE_STATE_HASH_COLUMN, PreparedRows
from carnopy.preparation.scenarios import build_scenario_outputs


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
    quality: str | None = None,
    outputs: str = "  formats: [parquet]",
) -> Path:
    categorical_block = (
        "categorical_features: []"
        if categorical.strip() == "[]"
        else f"categorical_features:\n{categorical}"
    )
    quality_block = "" if quality is None else f"quality:\n{quality}\n"
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
{quality_block}outputs:
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
    quality_report = json.loads(
        result.output_directory.joinpath("quality_report.json").read_text(encoding="utf-8")
    )
    quality_flags = pd.read_parquet(result.output_directory / "data/quality_flags.parquet")
    assert prepared["prepared_row_id"].tolist() == list(range(len(source)))
    assert provenance["prepared_row_id"].tolist() == prepared["prepared_row_id"].tolist()
    assert provenance["source_row_index"].tolist() == list(range(len(source)))
    assert source_diagnostics["prepared_row_id"].tolist() == prepared["prepared_row_id"].tolist()
    assert "source_row_hash" not in prepared.columns
    assert SOURCE_STATE_HASH_COLUMN not in prepared.columns
    assert provenance[SOURCE_STATE_HASH_COLUMN].str.fullmatch(r"[0-9a-f]{64}").all()
    assert {
        "source_mode",
        "source_fluid",
        "source_phase",
        "source_temperature_K",
        "source_pressure_Pa",
        "source_vapor_mass_fraction",
        "source_saturation_endpoint",
    }.issubset(provenance.columns)
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
    assert manifest["quality_artifacts"] == {
        "report": "quality_report.json",
        "flags": "data/quality_flags.parquet",
    }
    assert "quality_report.json" in manifest["artifact_hashes"]
    assert "data/quality_flags.parquet" in manifest["artifact_hashes"]
    assert quality_report["row_counts"] == {"eligible": len(source), "excluded": 0}
    assert quality_report["quality_flags"]["artifact"] == "data/quality_flags.parquet"
    assert set(quality_flags.columns) == {
        "prepared_row_id",
        "flag_code",
        "severity",
        "scope",
        "scenario",
        "partition",
        "field",
        "metric",
        "value",
        "message",
    }
    joined = quality_flags.dropna(subset=["prepared_row_id"]).merge(
        prepared[["prepared_row_id"]],
        on="prepared_row_id",
        how="left",
        indicator=True,
    )
    assert joined["_merge"].eq("both").all()
    assert result.scenario_report_path is None
    assert result.scenario_count == 0
    assert result.partition_count == 0
    assert _relative_files(result.output_directory) == {
        "data/diagnostics.parquet",
        "data/exclusions.parquet",
        "data/provenance.parquet",
        "data/quality_flags.parquet",
        "data/table.parquet",
        "dataset_card.md",
        "diagnostics.json",
        "manifest.json",
        "preparation.normalized.json",
        "preparation.original.yaml",
        "quality_report.json",
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
        "quality_artifacts",
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


def test_preparation_quality_duplicate_detection_is_advisory() -> None:
    frame = pd.DataFrame(
        [
            {
                "prepared_row_id": 0,
                "fluid": "Propane",
                "backend_model": "heos",
                "phase": "gas",
                "temperature": 300.0,
                "pressure": 100000.0,
                "mass_density": 1.0,
            },
            {
                "prepared_row_id": 1,
                "fluid": "Propane",
                "backend_model": "heos",
                "phase": "gas",
                "temperature": 300.0,
                "pressure": 100000.0,
                "mass_density": 2.0,
            },
        ]
    )
    resolved = ResolvedPreparation(
        numeric_features=(
            ResolvedField("temperature", "temperature_K", "K", "numeric", "coordinate"),
            ResolvedField("pressure", "pressure_Pa", "Pa", "numeric", "coordinate"),
        ),
        targets=(
            ResolvedField("mass_density", "mass_density_kg_m3", "kg/m^3", "numeric", "property"),
        ),
        auxiliary=(),
        categorical_feature_fields=(),
        derived_features=(),
        semantic_mapping={},
    )
    rows = PreparedRows(
        prepared_rows=frame.to_dict("records"),
        exclusion_rows=[],
        categories={},
        status="completed",
    )

    report, flags = build_quality_artifacts(
        frame=frame,
        rows=rows,
        resolved=resolved,
        scenario_summary=None,
        partition_target_summaries=[],
    )

    assert report["duplicate_state_candidates"] == {
        "status": "completed",
        "group_columns": ["fluid", "backend_model", "phase", "temperature", "pressure"],
        "duplicate_group_count": 1,
        "duplicate_row_count": 2,
        "conflicting_target_group_count": 1,
    }
    assert report["structured_grid"]["status"] == "skipped_unsupported_shape"
    assert flags["prepared_row_id"].tolist() == [0, 1]
    assert flags["flag_code"].tolist() == [
        "duplicate_state_conflicting_targets",
        "duplicate_state_conflicting_targets",
    ]


def test_preparation_quality_reports_defined_robust_statistics() -> None:
    frame = pd.DataFrame(
        {
            "prepared_row_id": range(5),
            "fluid": ["Propane", "Propane", "n-Butane", "n-Butane", "n-Butane"],
            "backend_model": ["heos", "heos", "heos", "heos", "pr"],
            "phase": ["gas", "gas", "liquid", "liquid", "liquid"],
            "temperature": [300.0, 310.0, 320.0, 330.0, 340.0],
            "pressure": [100000.0, 200000.0, 300000.0, 400000.0, 500000.0],
            "mass_density": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    resolved = ResolvedPreparation(
        numeric_features=(
            ResolvedField("temperature", "temperature_K", "K", "numeric", "coordinate"),
            ResolvedField("pressure", "pressure_Pa", "Pa", "numeric", "coordinate"),
        ),
        targets=(
            ResolvedField("mass_density", "mass_density_kg_m3", "kg/m^3", "numeric", "property"),
        ),
        auxiliary=(),
        categorical_feature_fields=(),
        derived_features=(),
        semantic_mapping={},
    )
    rows = PreparedRows(
        prepared_rows=frame.to_dict("records"),
        exclusion_rows=[],
        categories={},
        status="completed",
    )

    report, _ = build_quality_artifacts(
        frame=frame,
        rows=rows,
        resolved=resolved,
        scenario_summary=None,
        partition_target_summaries=[],
    )

    summary = report["finite_summaries"]["mass_density"]
    assert report["quality_report_schema_version"] == 2
    assert summary == {
        "row_count": 5,
        "missing_count": 0,
        "finite_count": 5,
        "nonfinite_count": 0,
        "minimum": 1.0,
        "maximum": 5.0,
        "mean": 3.0,
        "std": pytest.approx(2.0**0.5),
        "std_ddof": 0,
        "median": 3.0,
        "first_quartile": 2.0,
        "third_quartile": 4.0,
        "interquartile_range": 2.0,
        "median_absolute_deviation": 1.0,
        "quantiles": {
            "0.01": pytest.approx(1.04),
            "0.05": pytest.approx(1.2),
            "0.25": 2.0,
            "0.5": 3.0,
            "0.75": 4.0,
            "0.95": pytest.approx(4.8),
            "0.99": pytest.approx(4.96),
        },
        "skewness": pytest.approx(0.0, abs=1e-15),
        "excess_kurtosis": pytest.approx(-1.2),
    }
    fluid_groups = report["numeric_summaries_by_group"]["fluid"]
    assert [group["value"] for group in fluid_groups] == ["Propane", "n-Butane"]
    assert [group["row_count"] for group in fluid_groups] == [2, 3]
    assert fluid_groups[1]["fields"]["mass_density"]["median"] == 4.0
    assert report["target_summaries_by_partition"][0]["targets"]["mass_density"] == summary
    assert "Hyndman-Fan type 7" in report["estimator_definitions"]["quartiles_and_quantiles"]


def test_matrix_diagnostics_report_rank_conditioning_and_correlations() -> None:
    frame = pd.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            "x_copy": [2.0, 4.0, 6.0, 8.0, 10.0],
            "constant": [7.0] * 5,
            "almost_constant": [
                1.0,
                1.0 + 1e-14,
                1.0 + 4e-14,
                1.0 + 9e-14,
                1.0 + 16e-14,
            ],
            "target": [1.0, 4.0, 9.0, 16.0, 25.0],
        }
    )

    result = build_matrix_diagnostics(
        frame,
        feature_columns=["x", "x_copy", "constant", "almost_constant"],
        target_columns=["target"],
        config=MatrixDiagnosticsConfig(),
        scenario="baseline",
        fit_partition="train",
    )

    assert result["status"] == "completed"
    assert result["fit_partition"] == "train"
    assert result["constant_feature_columns"] == ["constant"]
    assert result["near_constant_feature_columns"][0]["field"] == "almost_constant"
    assert result["numerical_rank"] < len(result["variable_feature_columns"])
    assert result["condition_number"] is None
    assert result["condition_number_is_infinite"] is True
    assert result["highly_correlated_feature_pairs"][0] == {
        "left": "x",
        "right": "x_copy",
        "correlation": pytest.approx(1.0),
    }
    assert result["feature_target_correlations"][0]["target"] == "target"
    assert 0.0 < result["effective_rank_fraction"] <= 1.0
    assert result["rank_tolerance"] > 0.0


def test_optional_baseline_diagnostics_fit_train_and_evaluate_test() -> None:
    pytest.importorskip("sklearn")
    train = pd.DataFrame(
        {
            "x": np.arange(1.0, 21.0),
            "target": 3.0 * np.arange(1.0, 21.0) + 2.0,
        }
    )
    test = pd.DataFrame(
        {
            "x": np.arange(21.0, 26.0),
            "target": 3.0 * np.arange(21.0, 26.0) + 2.0,
        }
    )

    result = build_baseline_diagnostics(
        {"train": train, "test": test},
        feature_columns=["x"],
        target_columns=["target"],
        config=BaselineDiagnosticsConfig(models=("dummy_mean", "ridge"), ridge_alpha=1e-6),
        scenario="linear_holdout",
    )

    assert result["status"] == "completed"
    assert result["train_row_count"] == 20
    assert result["evaluation_row_counts"] == {"test": 5}
    by_model = {item["model"]: item for item in result["models"]}
    assert by_model["ridge"]["metrics"]["test"]["root_mean_squared_error"] < 1.0
    assert (
        by_model["dummy_mean"]["metrics"]["test"]["root_mean_squared_error"]
        > by_model["ridge"]["metrics"]["test"]["root_mean_squared_error"]
    )


def test_prepare_embeds_optional_baseline_metrics_without_model_artifacts(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    run = generate_dataset(
        _grid_property_config(
            tmp_path / "grid.yaml",
            pressures="[100000.0, 150000.0, 200000.0, 250000.0, 300000.0, 350000.0]",
        ),
        output_root=tmp_path / "runs",
    )
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: baseline_holdout
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
""",
        categorical="[]",
        derived="[]",
        quality="""  baseline_diagnostics:
    models: [dummy_mean, ridge]
    random_seed: 42
    ridge_alpha: 1.0
    histogram_max_iterations: 20""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    report = json.loads(
        result.output_directory.joinpath("quality_report.json").read_text(encoding="utf-8")
    )
    baseline = report["baseline_diagnostics"]
    assert baseline["status"] == "completed"
    assert baseline["fits"][0]["scenario"] == "baseline_holdout"
    assert {item["model"] for item in baseline["fits"][0]["models"]} == {
        "dummy_mean",
        "ridge",
    }
    assert not list(result.output_directory.rglob("*.pkl"))
    assert not list(result.output_directory.rglob("*.joblib"))


def test_property_grid_diagnostics_report_missing_repeated_and_phase_edges() -> None:
    frame = pd.DataFrame(
        {
            "source_mode": ["property_table"] * 4,
            "source_run_id": ["run-1"] * 4,
            "source_fluid": ["Propane"] * 4,
            "backend_model": ["heos"] * 4,
            "source_phase": ["gas", "gas", "liquid", "liquid"],
            "source_temperature_K": [300.0, 300.0, 310.0, 300.0],
            "source_pressure_Pa": [100000.0, 200000.0, 100000.0, 100000.0],
        }
    )

    result = build_structured_grid_summary(frame)

    group = result["groups"][0]
    assert result["status"] == "completed"
    assert group["expected_cells"] == 4
    assert group["expected_cell_basis"] == (
        "Cartesian product of observed eligible coordinate levels"
    )
    assert group["observed_cells"] == 3
    assert group["missing_cells"] == 1
    assert group["repeated_cell_count"] == 1
    assert group["repeated_row_count"] == 1
    assert group["coordinate_spacing"]["source_temperature_K"]["minimum_spacing"] == 10.0
    assert group["phase_boundaries"]["multi_phase_cell_count"] == 1
    assert group["disconnected_ranges"]["status"] == "not_inferred_without_sampler_contract"


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
    assert (result.output_directory / "quality_report.json").is_file()
    assert (result.output_directory / "data" / "quality_flags.parquet").is_file()
    report = json.loads(
        result.output_directory.joinpath("quality_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "no_eligible_rows"
    assert report["structured_grid"]["status"] == "skipped_unsupported_shape"
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


def test_shuffle_keeps_duplicate_thermodynamic_states_in_one_partition(tmp_path: Path) -> None:
    config = load_preparation_config(
        _prep_config_with_scenarios(
            tmp_path / "preparation.yaml",
            """scenarios:
  - name: grouped_shuffle
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
""",
            categorical="[]",
            derived="[]",
        )
    ).model.scenarios
    frame = pd.DataFrame(
        {
            "prepared_row_id": range(6),
            "source_row_hash": [f"row-{index}" for index in range(6)],
            SOURCE_STATE_HASH_COLUMN: ["duplicate", "duplicate", "a", "b", "c", "d"],
            "pressure": [1.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )

    output = build_scenario_outputs(config, frame, source_kind="dataset_run")[0]

    duplicate_partitions = [
        partition
        for partition, partition_frame in output.partitions.items()
        if set(partition_frame["prepared_row_id"]) & {0, 1}
    ]
    assert len(duplicate_partitions) == 1
    assert set(output.partitions[duplicate_partitions[0]]["prepared_row_id"]) >= {0, 1}
    assert output.metadata["state_leakage"] == {
        "identity_column": SOURCE_STATE_HASH_COLUMN,
        "duplicate_state_group_count": 1,
        "cross_partition_group_count": 0,
    }


def test_stratified_hash_balances_declared_strata_without_state_leakage(
    tmp_path: Path,
) -> None:
    config = load_preparation_config(
        _prep_config_with_scenarios(
            tmp_path / "preparation.yaml",
            """scenarios:
  - name: balanced_strata
    kind: stratified_hash
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    strata:
      categorical: [phase]
      numeric_bins:
        temperature: [305.0]
""",
            categorical="[]",
            derived="[]",
        )
    ).model.scenarios
    frame = pd.DataFrame(
        {
            "prepared_row_id": range(8),
            SOURCE_STATE_HASH_COLUMN: [f"state-{index}" for index in range(8)],
            "phase": ["gas", "gas", "gas", "gas", "liquid", "liquid", "liquid", "liquid"],
            "temperature": [300.0, 300.0, 310.0, 310.0] * 2,
        }
    )

    output = build_scenario_outputs(config, frame, source_kind="dataset_run")[0]

    for partition in ("train", "test"):
        counts = output.partitions[partition].groupby(["phase", "temperature"]).size()
        assert counts.tolist() == [1, 1, 1, 1]
    stratification = output.metadata["stratification"]
    assert stratification["stratum_count"] == 4
    assert all(
        stratum["partition_counts"] == {"train": 1, "test": 1}
        for stratum in stratification["strata"]
    )
    assert output.metadata["state_leakage"]["cross_partition_group_count"] == 0


def test_stratified_hash_rejects_empty_declared_numeric_bins(tmp_path: Path) -> None:
    config = load_preparation_config(
        _prep_config_with_scenarios(
            tmp_path / "preparation.yaml",
            """scenarios:
  - name: empty_bins
    kind: stratified_hash
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    strata:
      numeric_bins:
        temperature: [290.0, 350.0]
""",
            categorical="[]",
            derived="[]",
        )
    ).model.scenarios
    frame = pd.DataFrame(
        {
            "prepared_row_id": range(4),
            SOURCE_STATE_HASH_COLUMN: [f"state-{index}" for index in range(4)],
            "temperature": [300.0, 310.0, 320.0, 330.0],
        }
    )

    with pytest.raises(ConfigError, match="empty declared bins: 0, 2"):
        build_scenario_outputs(config, frame, source_kind="dataset_run")


def test_explicit_scenario_rejects_cross_partition_state_leakage(tmp_path: Path) -> None:
    config = load_preparation_config(
        _prep_config_with_scenarios(
            tmp_path / "preparation.yaml",
            """scenarios:
  - name: leaking_holdout
    kind: range_holdout
    field: pressure
    holdouts:
      test: {min: 1.0, max: 1.0}
    remainder: train
""",
            categorical="[]",
            derived="[]",
        )
    ).model.scenarios
    frame = pd.DataFrame(
        {
            "prepared_row_id": [0, 1, 2],
            SOURCE_STATE_HASH_COLUMN: ["same-state", "same-state", "other-state"],
            "pressure": [1.0, 2.0, 3.0],
        }
    )

    with pytest.raises(ConfigError, match="duplicate thermodynamic-state groups across"):
        build_scenario_outputs(config, frame, source_kind="dataset_run")


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


def test_prepare_robust_transformation_uses_train_median_and_iqr(tmp_path: Path) -> None:
    dataset = _grid_property_config(
        tmp_path / "grid.yaml",
        pressures="[100000.0, 150000.0, 200000.0, 250000.0, 300000.0, 350000.0]",
    )
    run = generate_dataset(dataset, output_root=tmp_path / "runs")
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: robust_baseline
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    transformations:
      - field: pressure
        methods: [robust]
""",
        categorical="[]",
        derived="[]",
        quality="""  matrix_diagnostics:
    correlation_threshold: 0.99
    near_constant_relative_spread: 1.0e-12""",
    )

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    train = pd.read_parquet(
        result.output_directory / "data/scenarios/robust_baseline/train.parquet"
    )
    scenario = json.loads(
        result.output_directory.joinpath("data/scenarios/robust_baseline/scenario.json").read_text(
            encoding="utf-8"
        )
    )
    quality_report = json.loads(
        result.output_directory.joinpath("quality_report.json").read_text(encoding="utf-8")
    )
    step = scenario["transformations"][0]["steps"][0]
    assert train["pressure__robust"].median() == pytest.approx(0.0)
    assert step["method"] == "robust"
    assert step["median"] == pytest.approx(train["pressure"].median())
    assert step["interquartile_range"] == pytest.approx(
        train["pressure"].quantile(0.75) - train["pressure"].quantile(0.25)
    )
    assert step["inverse"] == "value = transformed * interquartile_range + median"
    matrix_fit = quality_report["matrix_diagnostics"]["fits"][0]
    assert quality_report["matrix_diagnostics"]["status"] == "completed"
    assert matrix_fit["scenario"] == "robust_baseline"
    assert matrix_fit["fit_partition"] == "train"
    assert "pressure__robust" in matrix_fit["feature_columns"]


def test_prepare_robust_transformation_rejects_zero_train_iqr(tmp_path: Path) -> None:
    run = generate_dataset(
        _grid_property_config(tmp_path / "grid.yaml"),
        output_root=tmp_path / "runs",
    )
    config = _prep_config_with_scenarios(
        tmp_path / "preparation.yaml",
        """scenarios:
  - name: invalid_robust
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
    transformations:
      - field: temperature
        methods: [robust]
""",
        categorical="[]",
        derived="[]",
    )

    with pytest.raises(ConfigError, match="robust transformation has zero train IQR"):
        prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")


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
        numeric="[temperature, pressure]",
        categorical="[]",
        derived="[]",
        targets="[mass_density]",
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


def test_prepare_records_reference_state_context_for_reference_dependent_fields(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _grid_property_config(
            tmp_path / "dataset.yaml",
            fluids="[Propane, Isopentane]",
        ),
        output_root=tmp_path / "runs",
    )
    config = _prep_config(tmp_path / "preparation.yaml")

    result = prepare_dataset(run.output_directory, config=config, output_root=tmp_path / "prepared")

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    reference_state = manifest["reference_state"]
    assert reference_state["selected_reference_dependent_fields"] == ["specific_enthalpy"]
    assert reference_state["compatible_context"] == {
        "reference_state_policy": "coolprop_DEF",
        "backend": "coolprop",
        "backend_model": "heos",
    }
    targets = {
        target
        for context in reference_state["contexts"]
        for target in context["reference_state_targets"]
    }
    assert "HEOS::n-Propane" in targets
    assert len(targets) == 2
    assert all(target.startswith("HEOS::") for target in targets)
    assert "Reference-dependent fields: specific_enthalpy" in result.dataset_card_path.read_text(
        encoding="utf-8"
    )


def test_prepare_rejects_reference_dependent_fields_across_sweep_models(
    tmp_path: Path,
) -> None:
    sweep = generate_model_sweep(
        _sweep_config(tmp_path / "sweep.yaml"),
        output_root=tmp_path / "sweeps",
    )
    config = _prep_config(tmp_path / "preparation.yaml")

    with pytest.raises(ConfigError, match="one compatible reference-state context"):
        prepare_dataset(sweep.output_directory, config=config, output_root=tmp_path / "prepared")


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
