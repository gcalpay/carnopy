from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from carnopy.app.scene_contracts import SceneContractError
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.worker import main
from carnopy.visualization.models import VisualizationError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dataset_frame(*, model: str = "heos", run_id: str = "run-heos") -> pd.DataFrame:
    temperatures = [320.0, 320.0, 300.0, 300.0]
    pressures = [100_000.0, 250_000.0, 100_000.0, 250_000.0]
    return pd.DataFrame(
        {
            "run_id": [run_id] * 4,
            "case_id": [0, 1, 2, 3],
            "mode": ["property_table"] * 4,
            "fluid": ["Propane"] * 4,
            "backend": ["coolprop"] * 4,
            "backend_model": [model] * 4,
            "backend_version": ["test"] * 4,
            "phase": ["gas", "gas", "liquid", "liquid"],
            "backend_phase": ["gas", "gas", "liquid", "liquid"],
            "temperature_K": temperatures,
            "pressure_Pa": pressures,
            "specific_enthalpy_J_kg": [420_000.0, 430_000.0, 240_000.0, 250_000.0],
            "valid": [True, True, True, False],
            "failure_layer": [None, None, None, "property"],
            "failure_code": [None, None, None, "backend_error"],
            "failure_message": [None, None, None, "test failure"],
            "failure_property": [None, None, None, "specific_enthalpy"],
            "backend_error_type": [None, None, None, "ValueError"],
            "backend_error_message": [None, None, None, "test failure"],
        }
    )


def _write_dataset_run(
    root: Path,
    *,
    model: str = "heos",
    run_id: str | None = None,
    frame: pd.DataFrame | None = None,
) -> Path:
    root.mkdir(parents=True)
    selected_run_id = run_id or f"run-{model}"
    selected_frame = _dataset_frame(model=model, run_id=selected_run_id) if frame is None else frame
    dataset = root / "dataset.parquet"
    selected_frame.to_parquet(dataset, index=False)
    _write_json(root / "report.json", {"report_schema_version": 1, "run_id": selected_run_id})
    metadata = {
        "metadata_schema_version": 1,
        "dataset_schema_version": 2,
        "run_id": selected_run_id,
        "run_status": "incomplete" if not selected_frame["valid"].all() else "completed",
        "mode": "property_table",
        "backend": "coolprop",
        "backend_model": model,
        "row_count": len(selected_frame),
        "valid_row_count": int(selected_frame["valid"].sum()),
        "invalid_row_count": int((~selected_frame["valid"]).sum()),
        "canonical_properties": ["specific_enthalpy"],
        "canonical_units": {
            "temperature_K": "K",
            "pressure_Pa": "Pa",
            "specific_enthalpy_J_kg": "J/kg",
        },
        "sampling": {
            "original": {},
            "materialized_si": {
                "temperature": [320.0, 300.0],
                "pressure": [100_000.0, 250_000.0],
            },
        },
        "artifact_hashes": {
            "dataset.parquet": _sha(dataset),
            "report.json": _sha(root / "report.json"),
        },
    }
    _write_json(root / "metadata.json", metadata)
    return root


def _write_sweep(root: Path) -> Path:
    root.mkdir()
    _write_json(root / "sweep.normalized.json", {})
    _write_json(root / "report.json", {"sweep_report_schema_version": 1})
    child = _write_dataset_run(root / "models" / "heos" / "child", model="heos")
    comparison = root / "comparison"
    comparison.mkdir()
    values = comparison / "values.parquet"
    deltas = comparison / "deltas.parquet"
    pd.DataFrame({"case_id": [0], "value": [1.0]}).to_parquet(values, index=False)
    pd.DataFrame({"case_id": [0], "delta": [0.0]}).to_parquet(deltas, index=False)
    metadata = {
        "sweep_metadata_schema_version": 1,
        "sweep_id": "sweep-id",
        "sweep_run_id": "sweep-run",
        "sweep_status": "completed",
        "mode": "property_table",
        "backend": "coolprop",
        "models": ["heos"],
        "reference_model": "heos",
        "child_runs": [
            {
                "backend_model": "heos",
                "run_id": "run-heos",
                "output_directory": str(child),
            }
        ],
        "artifact_hashes": {
            "comparison/values.parquet": _sha(values),
            "comparison/deltas.parquet": _sha(deltas),
            "sweep.normalized.json": _sha(root / "sweep.normalized.json"),
            "report.json": _sha(root / "report.json"),
        },
    }
    _write_json(root / "metadata.json", metadata)
    return root


def _write_preparation(root: Path) -> Path:
    root.mkdir()
    data = root / "data"
    scenario_root = data / "scenarios" / "baseline"
    scenario_root.mkdir(parents=True)
    _write_json(root / "preparation.normalized.json", {"schema_version": 1})
    main = pd.DataFrame(
        {
            "prepared_row_id": [0, 1, 2],
            "temperature": [300.0, 310.0, 320.0],
            "specific_volume": [0.5, 0.4, 0.3],
            "specific_enthalpy": [200_000.0, 250_000.0, 300_000.0],
        }
    )
    provenance = pd.DataFrame(
        {
            "prepared_row_id": [0, 1, 2],
            "source_kind": ["dataset_run"] * 3,
            "source_run_id": ["source-run"] * 3,
            "source_artifact": ["dataset.parquet"] * 3,
            "source_row_index": [0, 1, 2],
            "source_row_hash": ["a" * 64, "b" * 64, "c" * 64],
            "source_state_hash": ["d" * 64, "e" * 64, "f" * 64],
            "source_mode": ["property_table"] * 3,
            "source_fluid": ["Propane"] * 3,
            "source_phase": ["gas", "gas", "liquid"],
            "source_temperature_K": [300.0, 310.0, 320.0],
            "source_pressure_Pa": [100_000.0, 200_000.0, 300_000.0],
            "source_vapor_mass_fraction": [None, None, None],
            "source_saturation_endpoint": [None, None, None],
            "backend_model": ["heos"] * 3,
            "state_key": [None, None, None],
            "state_key_version": [None, None, None],
            "sweep_id": [None, None, None],
            "sweep_run_id": [None, None, None],
        }
    )
    diagnostics = pd.DataFrame(
        {
            "prepared_row_id": [0, 1, 2],
            "source_valid": [True, True, False],
            "source_failure_layer": [None, None, "property"],
            "source_failure_code": [None, None, "backend_error"],
            "source_failure_message": [None, None, "retained diagnostic"],
            "source_failure_property": [None, None, "other"],
            "source_backend_error_type": [None, None, "ValueError"],
            "source_backend_error_message": [None, None, "retained diagnostic"],
        }
    )
    exclusions = pd.DataFrame(
        columns=[
            "source_artifact",
            "source_row_index",
            "primary_reason",
            "reason_codes",
            "missing_or_invalid_fields",
        ]
    )
    paths = {
        "data/table.parquet": main,
        "data/provenance.parquet": provenance,
        "data/diagnostics.parquet": diagnostics,
        "data/exclusions.parquet": exclusions,
    }
    for relative, frame in paths.items():
        frame.to_parquet(root / relative, index=False)
    train = main.iloc[[0, 1]].copy()
    train["temperature__standardize"] = [-1.0, 1.0]
    train_path = scenario_root / "train.parquet"
    train.to_parquet(train_path, index=False)
    scenario = {
        "name": "baseline",
        "kind": "shuffle",
        "partition_counts": {"train": 2},
        "transformations": [
            {
                "field": "temperature",
                "methods": ["standardize"],
                "output_column": "temperature__standardize",
                "fit_partition": "train",
                "steps": [],
            }
        ],
        "state_leakage": {
            "identity_column": "source_state_hash",
            "duplicate_state_group_count": 0,
            "cross_partition_group_count": 0,
        },
        "partition_artifact_hashes": {"data/scenarios/baseline/train.parquet": _sha(train_path)},
    }
    scenario_path = scenario_root / "scenario.json"
    _write_json(scenario_path, scenario)
    partition_relative = "data/scenarios/baseline/train.parquet"
    scenario_relative = "data/scenarios/baseline/scenario.json"
    summary = {
        "name": "baseline",
        "kind": "shuffle",
        "partition_counts": {"train": 2},
        "transformations": scenario["transformations"],
        "partition_artifacts": [partition_relative],
        "partition_artifact_hashes": {partition_relative: _sha(train_path)},
        "array_exports": {},
        "scenario_artifact": scenario_relative,
        "artifact_hashes": {
            partition_relative: _sha(train_path),
            scenario_relative: _sha(scenario_path),
        },
    }
    scenario_report = {
        "scenario_report_schema_version": 1,
        "scenario_count": 1,
        "partition_count": 1,
        "scenarios": [summary],
    }
    _write_json(root / "scenario_report.json", scenario_report)
    diagnostics_summary = {
        "status": "completed",
        "source_kind": "dataset_run",
        "source_row_count": 3,
        "excluded_row_count": 0,
    }
    _write_json(root / "diagnostics.json", diagnostics_summary)
    artifact_hashes = {relative: _sha(root / relative) for relative in paths}
    artifact_hashes.update(
        {
            partition_relative: _sha(train_path),
            scenario_relative: _sha(scenario_path),
            "scenario_report.json": _sha(root / "scenario_report.json"),
            "diagnostics.json": _sha(root / "diagnostics.json"),
            "preparation.normalized.json": _sha(root / "preparation.normalized.json"),
        }
    )
    manifest = {
        "preparation_schema_version": 1,
        "status": "completed",
        "eligible_row_count": 3,
        "excluded_row_count": 0,
        "semantic_field_mapping": {
            "temperature": {
                "column": "temperature",
                "unit": "K",
                "kind": "numeric",
                "source": "coordinate",
            },
            "specific_volume": {
                "column": "specific_volume",
                "unit": "m^3/kg",
                "kind": "numeric",
                "source": "derived",
            },
            "specific_enthalpy": {
                "column": "specific_enthalpy",
                "unit": "J/kg",
                "kind": "numeric",
                "source": "property",
            },
        },
        "features": {
            "numeric": ["temperature"],
            "derived": ["specific_volume"],
            "categorical": [],
        },
        "targets": ["specific_enthalpy"],
        "auxiliary": [],
        "categorical_vocabularies": {},
        "data_artifacts": {
            "table": "data/table.parquet",
            "provenance": "data/provenance.parquet",
            "diagnostics": "data/diagnostics.parquet",
            "exclusions": "data/exclusions.parquet",
        },
        "column_roles": {
            "table": list(main.columns),
            "provenance": list(provenance.columns),
            "diagnostics": list(diagnostics.columns),
        },
        "artifact_hashes": artifact_hashes,
        "scenarios": {
            "scenario_count": 1,
            "partition_count": 1,
            "status": "completed",
            "report": "scenario_report.json",
            "scenarios": [summary],
        },
    }
    _write_json(root / "manifest.json", manifest)
    return root


def test_dataset_profile_preserves_exact_topology_and_deterministic_defaults(
    tmp_path: Path,
) -> None:
    run = _write_dataset_run(tmp_path / "run")
    inspected = inspect_for_app(run)
    assert [binding.selected_table_id for binding in inspected.scene_bindings] == ["dataset"]

    first = profile_scene(inspected.scene_bindings[0])
    second = profile_scene(inspected.scene_bindings[0])

    assert first == second
    assert first.binding == inspected.scene_bindings[0]
    assert first.topology.status == "exact"
    assert [axis.field_id for axis in first.topology.axes] == ["temperature", "pressure"]
    assert first.topology.axes[0].levels == (320.0, 300.0)
    assert first.topology.axes[1].levels == (100_000.0, 250_000.0)
    assert first.defaults.model_dump() == {
        "x_field": "temperature",
        "y_field": "pressure",
        "z_field": "specific_enthalpy",
        "scalar_field": "temperature",
    }
    fields = {field.field_id: field for field in first.fields}
    assert fields["specific_enthalpy"].classification == "emitted_property"
    assert fields["specific_enthalpy"].source_valid_count == 3
    assert fields["specific_enthalpy"].finite_count == 3
    assert fields["phase"].distinct_values == ("gas", "liquid")


def test_current_dataset_csv_artifact_profiles_without_numeric_coercion(tmp_path: Path) -> None:
    run = _write_dataset_run(tmp_path / "run")
    parquet = run / "dataset.parquet"
    csv = run / "dataset.csv"
    pd.read_parquet(parquet).to_csv(csv, index=False)
    parquet.unlink()
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifact_hashes"].pop("dataset.parquet")
    metadata["artifact_hashes"]["dataset.csv"] = _sha(csv)
    _write_json(metadata_path, metadata)

    inspected = inspect_for_app(run)
    profile = profile_scene(inspected.scene_bindings[0])

    assert profile.binding.selected_table().source_format == "csv"
    assert profile.topology.axes[0].levels == (320.0, 300.0)
    assert {field.field_id for field in profile.fields} >= {
        "temperature",
        "pressure",
        "specific_enthalpy",
    }


def test_standalone_tables_and_sweep_comparisons_are_not_scene_sources(tmp_path: Path) -> None:
    standalone = tmp_path / "standalone.parquet"
    _dataset_frame().to_parquet(standalone, index=False)

    standalone_inspection = inspect_for_app(standalone)

    assert standalone_inspection.scene_bindings == ()
    standalone_reasons = standalone_inspection.scene_ineligible_reasons
    assert standalone_reasons is not None
    assert "standalone" in standalone_reasons["dataset"]

    sweep = _write_sweep(tmp_path / "sweep")
    sweep_inspection = inspect_for_app(sweep)

    assert [binding.selected_table_id for binding in sweep_inspection.scene_bindings] == [
        "model.heos.dataset"
    ]
    sweep_reasons = sweep_inspection.scene_ineligible_reasons
    assert sweep_reasons is not None
    assert set(sweep_reasons) == {
        "comparison.values",
        "comparison.deltas",
    }
    assert profile_scene(sweep_inspection.scene_bindings[0]).binding.source_kind == "model_sweep"


def test_prepared_main_and_scenario_profiles_validate_joins_and_transforms(
    tmp_path: Path,
) -> None:
    prepared = _write_preparation(tmp_path / "prepared")
    inspected = inspect_for_app(prepared)
    bindings = {binding.selected_table_id: binding for binding in inspected.scene_bindings}

    main = profile_scene(bindings["table"])
    scenario = profile_scene(bindings["scenario.baseline.train"])

    assert main.topology.status == "unavailable"
    assert main.topology.reason_code == "source_sampling_levels_not_recorded"
    main_fields = {field.field_id: field for field in main.fields}
    assert main_fields["specific_volume"].classification == "derived_feature"
    assert main_fields["source.temperature"].classification == "source_coordinate"
    assert main_fields["source.temperature"].origin == "provenance"
    assert main_fields["temperature"].source_valid_count == 2
    scenario_fields = {field.field_id: field for field in scenario.fields}
    transformed = scenario_fields["temperature__standardize"]
    assert transformed.classification == "recorded_transform"
    assert transformed.unit_status == "transformed"
    assert scenario_fields["scenario"].distinct_values == ("baseline",)
    assert scenario_fields["partition"].distinct_values == ("train",)


def test_profile_rejects_changed_revision_and_corrupt_recorded_hash(tmp_path: Path) -> None:
    run = _write_dataset_run(tmp_path / "run")
    binding = inspect_for_app(run).scene_bindings[0]
    dataset = run / "dataset.parquet"
    frame = pd.read_parquet(dataset)
    frame.loc[0, "specific_enthalpy_J_kg"] = 999_999.0
    frame.to_parquet(dataset, index=False)

    with pytest.raises(SceneContractError) as changed:
        profile_scene(binding)
    assert changed.value.code == "scene_source_changed"

    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifact_hashes"]["dataset.parquet"] = "0" * 64
    _write_json(metadata_path, metadata)
    with pytest.raises(VisualizationError, match="hash mismatch"):
        inspect_for_app(run)


def test_profile_rejects_duplicate_prepared_join_identity(tmp_path: Path) -> None:
    prepared = _write_preparation(tmp_path / "prepared")
    provenance_path = prepared / "data" / "provenance.parquet"
    provenance = pd.read_parquet(provenance_path)
    provenance.loc[1, "prepared_row_id"] = 0
    provenance.to_parquet(provenance_path, index=False)
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"]["data/provenance.parquet"] = _sha(provenance_path)
    _write_json(manifest_path, manifest)
    binding = next(
        binding
        for binding in inspect_for_app(prepared).scene_bindings
        if binding.selected_table_id == "table"
    )

    with pytest.raises(SceneContractError, match="repeats a prepared_row_id"):
        profile_scene(binding)


def test_profile_rejects_missing_prepared_diagnostics_join(tmp_path: Path) -> None:
    prepared = _write_preparation(tmp_path / "prepared")
    diagnostics_path = prepared / "data" / "diagnostics.parquet"
    diagnostics = pd.read_parquet(diagnostics_path).iloc[:2]
    diagnostics.to_parquet(diagnostics_path, index=False)
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"]["data/diagnostics.parquet"] = _sha(diagnostics_path)
    _write_json(manifest_path, manifest)
    binding = next(
        binding
        for binding in inspect_for_app(prepared).scene_bindings
        if binding.selected_table_id == "table"
    )

    with pytest.raises(SceneContractError, match="do not join one-to-one"):
        profile_scene(binding)


def test_profile_rejects_overlap_between_retained_and_excluded_source_rows(
    tmp_path: Path,
) -> None:
    prepared = _write_preparation(tmp_path / "prepared")
    exclusions_path = prepared / "data" / "exclusions.parquet"
    exclusions = pd.DataFrame(
        {
            "source_artifact": ["dataset.parquet"],
            "source_row_index": [0],
            "primary_reason": ["missing_required_field"],
            "reason_codes": [["missing_required_field"]],
            "missing_or_invalid_fields": [["temperature"]],
        }
    )
    exclusions.to_parquet(exclusions_path, index=False)
    diagnostics_path = prepared / "diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["source_row_count"] = 4
    diagnostics["excluded_row_count"] = 1
    _write_json(diagnostics_path, diagnostics)
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["excluded_row_count"] = 1
    manifest["artifact_hashes"]["data/exclusions.parquet"] = _sha(exclusions_path)
    manifest["artifact_hashes"]["diagnostics.json"] = _sha(diagnostics_path)
    _write_json(manifest_path, manifest)
    binding = next(
        binding
        for binding in inspect_for_app(prepared).scene_bindings
        if binding.selected_table_id == "table"
    )

    with pytest.raises(SceneContractError, match="contradict source row identity"):
        profile_scene(binding)


def test_profile_rejects_scenario_rows_that_contradict_prepared_main(tmp_path: Path) -> None:
    prepared = _write_preparation(tmp_path / "prepared")
    partition_path = prepared / "data" / "scenarios" / "baseline" / "train.parquet"
    partition = pd.read_parquet(partition_path)
    partition.loc[0, "specific_enthalpy"] = -1.0
    partition.to_parquet(partition_path, index=False)
    partition_relative = "data/scenarios/baseline/train.parquet"
    scenario_relative = "data/scenarios/baseline/scenario.json"
    scenario_path = prepared / scenario_relative
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["partition_artifact_hashes"][partition_relative] = _sha(partition_path)
    _write_json(scenario_path, scenario)
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = manifest["scenarios"]["scenarios"][0]
    summary["partition_artifact_hashes"][partition_relative] = _sha(partition_path)
    summary["artifact_hashes"][partition_relative] = _sha(partition_path)
    summary["artifact_hashes"][scenario_relative] = _sha(scenario_path)
    manifest["artifact_hashes"][partition_relative] = _sha(partition_path)
    manifest["artifact_hashes"][scenario_relative] = _sha(scenario_path)
    scenario_report_path = prepared / "scenario_report.json"
    scenario_report = json.loads(scenario_report_path.read_text(encoding="utf-8"))
    scenario_report["scenarios"][0] = summary
    _write_json(scenario_report_path, scenario_report)
    manifest["artifact_hashes"]["scenario_report.json"] = _sha(scenario_report_path)
    _write_json(manifest_path, manifest)
    binding = next(
        binding
        for binding in inspect_for_app(prepared).scene_bindings
        if binding.selected_table_id == "scenario.baseline.train"
    )

    with pytest.raises(SceneContractError, match="contradict the main table"):
        profile_scene(binding)


def test_profile_scene_worker_returns_structured_profile_and_error(tmp_path: Path) -> None:
    run = _write_dataset_run(tmp_path / "run")
    binding = inspect_for_app(run).scene_bindings[0]
    request_id = str(uuid4())
    request = json.dumps(
        {
            "protocol_version": 1,
            "request_id": request_id,
            "type": "profile_scene",
            "payload": {"binding": binding.model_dump(mode="json")},
        }
    )
    stdout = io.StringIO()

    assert main(io.StringIO(request + "\n"), stdout, io.StringIO()) == 0

    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [event["type"] for event in events] == ["accepted", "phase", "result"]
    assert events[-1]["payload"]["scene_profile_schema_version"] == 1
    assert events[-1]["payload"]["binding"] == binding.model_dump(mode="json")

    (run / "dataset.parquet").write_bytes(b"changed")
    stdout = io.StringIO()
    assert main(io.StringIO(request + "\n"), stdout, io.StringIO()) == 1
    error = json.loads(stdout.getvalue().splitlines()[-1])
    assert error["payload"]["code"] == "scene_source_changed"
