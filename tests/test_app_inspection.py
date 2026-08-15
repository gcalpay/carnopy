from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from carnopy.app.source_inspection import inspect_for_app, resolve_table
from carnopy.app.table_preview import preview_table
from carnopy.inspection import inspect_source
from carnopy.visualization.models import VisualizationError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_preparation_dataset_run(
    root: Path,
    *,
    model: str = "heos",
    run_status: str = "completed",
) -> Path:
    root.mkdir(parents=True)
    dataset = root / "dataset.parquet"
    pd.DataFrame(
        {
            "run_id": [f"run-{model}", f"run-{model}"],
            "case_id": [0, 1],
            "mode": ["property_table", "property_table"],
            "fluid": ["Propane", "n-Butane"],
            "backend": ["coolprop", "coolprop"],
            "backend_model": [model, model],
            "backend_version": ["test", "test"],
            "phase": ["gas", "liquid"],
            "valid": [True, True],
            "temperature_K": [300.0, 310.0],
            "pressure_Pa": [100000.0, 200000.0],
            "mass_density_kg_m3": [1.8, 570.0],
            "specific_enthalpy_J_kg": [420000.0, 240000.0],
            "critical_temperature_K": [369.89, 425.12],
            "critical_pressure_Pa": [4251200.0, 3796000.0],
            "molar_mass_kg_mol": [0.04409562, 0.0581222],
        }
    ).to_parquet(dataset, index=False)
    metadata = {
        "run_id": f"run-{model}",
        "run_status": run_status,
        "backend": "coolprop",
        "backend_model": model,
        "reference_state_policy": "coolprop_DEF",
        "reference_state_backend_model": model,
        "reference_state_targets": [f"{model}::Propane", f"{model}::n-Butane"],
        "canonical_units": {
            "temperature_K": "K",
            "pressure_Pa": "Pa",
            "mass_density_kg_m3": "kg/m^3",
            "specific_enthalpy_J_kg": "J/kg",
            "critical_temperature_K": "K",
            "critical_pressure_Pa": "Pa",
            "molar_mass_kg_mol": "kg/mol",
        },
        "artifact_hashes": {"dataset.parquet": _sha(dataset)},
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return root


def _write_preparation_sweep(
    root: Path,
    *,
    included_models: tuple[str, ...],
    status: str,
) -> Path:
    root.mkdir()
    (root / "sweep.normalized.json").write_text("{}\n", encoding="utf-8")
    (root / "report.json").write_text("{}\n", encoding="utf-8")
    child_runs: list[dict[str, str]] = []
    for model in included_models:
        child = _write_preparation_dataset_run(
            root / "models" / model / f"run-{model}",
            model=model,
        )
        child_runs.append(
            {
                "backend_model": model,
                "output_directory": str(child),
                "run_id": f"run-{model}",
            }
        )
    metadata = {
        "sweep_id": "sweep-id",
        "sweep_run_id": "sweep-run-id",
        "sweep_status": status,
        "backend": "coolprop",
        "mode": "property_table",
        "models": ["heos", "pr"],
        "reference_model": "heos",
        "child_runs": child_runs,
        "artifact_hashes": {},
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return root


def test_dataset_app_inspection_returns_stable_descriptor_and_revision(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.parquet"
    pd.DataFrame(
        {
            "run_id": ["run"],
            "case_id": [0],
            "mode": ["property_table"],
            "fluid": ["Propane"],
            "backend": ["coolprop"],
            "backend_version": ["test"],
            "phase": ["gas"],
            "valid": [True],
            "temperature_K": [300.0],
            "pressure_Pa": [100000.0],
        }
    ).to_parquet(dataset, index=False)

    inspected = inspect_for_app(dataset)
    resolved = resolve_table(dataset, "dataset", inspected.revision)

    assert inspected.source_kind == "dataset"
    assert [item.table_id for item in inspected.tables] == ["dataset"]
    assert inspected.preparation_profile is None
    assert resolved.path == dataset

    dataset.write_bytes(dataset.read_bytes() + b"changed")
    with pytest.raises(VisualizationError, match="changed"):
        resolve_table(dataset, "dataset", inspected.revision)


def test_dataset_run_projects_authoritative_preparation_profile(tmp_path: Path) -> None:
    run = _write_preparation_dataset_run(tmp_path / "dataset-run")

    inspected = inspect_for_app(run)

    profile = inspected.preparation_profile
    assert inspected.preparation_eligible
    assert inspected.preparation_source_descriptor is not None
    assert profile is not None
    assert inspected.public_payload()["preparation_profile"] == profile
    assert profile["profile_schema_version"] == 1
    assert profile["source_path"] == str(run)
    assert profile["source_kind"] == "dataset_run"
    assert profile["inspection_revision"] == inspected.revision
    assert profile["source_identity"]["run_id"] == "run-heos"
    assert profile["completion"] == {
        "status": "completed",
        "partial": False,
        "included_child_models": [],
        "missing_child_models": [],
    }
    assert profile["available_models"] == ["heos"]
    assert profile["declared_models"] == []
    assert profile["reference_model"] == "heos"
    numeric_names = [item["name"] for item in profile["numeric_candidates"]]
    assert numeric_names == [
        "temperature",
        "pressure",
        "specific_enthalpy",
        "mass_density",
        "molar_mass",
        "critical_temperature",
        "critical_pressure",
    ]
    assert profile["target_candidates"] == profile["numeric_candidates"]
    assert [item["name"] for item in profile["categorical_candidates"]] == [
        "phase",
        "fluid",
    ]
    assert profile["observed_category_values"] == {
        "phase": ["gas", "liquid"],
        "fluid": ["Propane", "n-Butane"],
        "backend_model": ["heos"],
    }
    assert all(item["status"] == "ready" for item in profile["derived_features"])
    assert profile["model_holdout"] == {
        "available": False,
        "reason": "Model holdout scenarios require a model-sweep source.",
    }
    assert profile["reference_context"]["compatible"] is True
    assert profile["reference_context"]["compatible_context"] == {
        "reference_state_policy": "coolprop_DEF",
        "backend": "coolprop",
        "backend_model": "heos",
    }


def test_preparation_profile_reports_partial_and_unavailable_derived_features(
    tmp_path: Path,
) -> None:
    run = _write_preparation_dataset_run(tmp_path / "dataset-run")
    dataset = run / "dataset.parquet"
    frame = pd.read_parquet(dataset)
    frame.loc[0, "mass_density_kg_m3"] = None
    frame = frame.drop(columns="critical_pressure_Pa")
    frame.to_parquet(dataset, index=False)
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifact_hashes"]["dataset.parquet"] = _sha(dataset)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    profile = inspect_for_app(run).preparation_profile

    assert profile is not None
    derived = {item["name"]: item for item in profile["derived_features"]}
    assert derived["specific_volume"]["status"] == "partial"
    assert derived["specific_volume"]["ready_row_count"] == 1
    assert derived["specific_volume"]["missing_dependencies"] == ["mass_density"]
    assert "missing_derived_dependency" in derived["specific_volume"]["reason_codes"]
    assert derived["reduced_pressure"]["status"] == "unavailable"
    assert derived["reduced_pressure"]["missing_dependencies"] == ["critical_pressure"]
    assert derived["reduced_pressure"]["reason"]


def test_sweep_preparation_profile_reports_partial_and_reference_context(
    tmp_path: Path,
) -> None:
    partial = _write_preparation_sweep(
        tmp_path / "partial-sweep",
        included_models=("heos",),
        status="incomplete",
    )

    partial_inspection = inspect_for_app(partial)

    partial_profile = partial_inspection.preparation_profile
    assert partial_inspection.preparation_eligible
    assert partial_profile is not None
    assert partial_profile["source_kind"] == "model_sweep"
    assert partial_profile["completion"] == {
        "status": "incomplete",
        "partial": True,
        "included_child_models": ["heos"],
        "missing_child_models": ["pr"],
    }
    assert partial_profile["available_models"] == ["heos"]
    assert partial_profile["declared_models"] == ["heos", "pr"]
    assert partial_profile["reference_model"] == "heos"
    assert partial_profile["model_holdout"] == {
        "available": False,
        "reason": ("Model holdout scenarios require at least two available sweep child models."),
    }
    assert partial_profile["reference_context"]["compatible"] is True

    complete = _write_preparation_sweep(
        tmp_path / "complete-sweep",
        included_models=("heos", "pr"),
        status="completed",
    )

    complete_profile = inspect_for_app(complete).preparation_profile

    assert complete_profile is not None
    assert complete_profile["completion"]["partial"] is False
    assert complete_profile["available_models"] == ["heos", "pr"]
    assert complete_profile["model_holdout"] == {"available": True, "reason": ""}
    assert complete_profile["reference_context"]["compatible"] is False
    assert complete_profile["reference_context"]["reason_code"] == "incompatible_reference_context"


def test_dataset_run_without_generator_metadata_remains_inspectable(tmp_path: Path) -> None:
    run = tmp_path / "legacy-run"
    run.mkdir()
    dataset = run / "dataset.parquet"
    pd.DataFrame(
        {
            "run_id": ["legacy"],
            "case_id": [0],
            "mode": ["property_table"],
            "fluid": ["Propane"],
            "backend": ["coolprop"],
            "backend_version": ["8.0.0"],
            "phase": ["gas"],
            "valid": [True],
            "temperature_K": [300.0],
            "pressure_Pa": [100000.0],
        }
    ).to_parquet(dataset, index=False)
    (run / "metadata.json").write_text(
        json.dumps(
            {
                "metadata_schema_version": 1,
                "carnopy_version": "0.1.0a3",
                "canonical_units": {"temperature_K": "K", "pressure_Pa": "Pa"},
                "artifact_hashes": {"dataset.parquet": _sha(dataset)},
            }
        ),
        encoding="utf-8",
    )

    inspected = inspect_for_app(run)
    resolved = resolve_table(run, "dataset", inspected.revision)

    assert inspected.source_kind == "dataset"
    assert resolved.path == dataset
    assert resolved.units == {"temperature_K": "K", "pressure_Pa": "Pa"}


def _write_malicious_preparation(
    root: Path,
    *,
    table_value: str,
    expected_hash: str | None = None,
) -> None:
    root.mkdir()
    (root / "preparation.normalized.json").write_text("{}\n", encoding="utf-8")
    (root / "diagnostics.json").write_text("{}\n", encoding="utf-8")
    data = root / "data"
    data.mkdir()
    for name in ("provenance.parquet", "diagnostics.parquet", "exclusions.parquet"):
        (data / name).write_bytes(b"placeholder")
    artifacts = {
        "table": table_value,
        "provenance": "data/provenance.parquet",
        "diagnostics": "data/diagnostics.parquet",
        "exclusions": "data/exclusions.parquet",
    }
    hashes = {} if expected_hash is None else {table_value: expected_hash}
    (root / "manifest.json").write_text(
        json.dumps({"data_artifacts": artifacts, "artifact_hashes": hashes}),
        encoding="utf-8",
    )


def test_shared_preparation_inspection_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "preparation"
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"outside")
    _write_malicious_preparation(root, table_value="../outside.parquet")

    with pytest.raises(VisualizationError, match="relative to the bundle"):
        inspect_source(root)


def test_shared_preparation_inspection_rejects_symlink_components(tmp_path: Path) -> None:
    root = tmp_path / "preparation"
    _write_malicious_preparation(root, table_value="data/link/table.parquet")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "table.parquet").write_bytes(b"outside")
    (root / "data" / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(VisualizationError, match="symbolic link"):
        inspect_source(root)


def test_shared_preparation_inspection_rejects_recorded_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "preparation"
    _write_malicious_preparation(
        root,
        table_value="data/table.parquet",
        expected_hash=hashlib.sha256(b"expected").hexdigest(),
    )
    (root / "data" / "table.parquet").write_bytes(b"actual")

    with pytest.raises(VisualizationError, match="hash mismatch"):
        inspect_source(root)


def test_preparation_descriptors_cover_quality_flags_and_scenario_tables(tmp_path: Path) -> None:
    root = tmp_path / "preparation"
    data = root / "data"
    scenario = data / "scenarios" / "shuffle"
    scenario.mkdir(parents=True)
    (root / "preparation.normalized.json").write_text("{}\n", encoding="utf-8")
    (root / "diagnostics.json").write_text(json.dumps({"source_row_count": 2}), encoding="utf-8")
    paths = {
        "data/table.parquet": pd.DataFrame({"prepared_row_id": [0, 1], "x": [1.0, 2.0]}),
        "data/provenance.parquet": pd.DataFrame({"prepared_row_id": [0, 1]}),
        "data/diagnostics.parquet": pd.DataFrame({"prepared_row_id": [0, 1]}),
        "data/exclusions.parquet": pd.DataFrame({"primary_reason": []}),
        "data/quality_flags.parquet": pd.DataFrame(
            {
                "prepared_row_id": [0, 1, 1],
                "flag_code": ["candidate_a", "candidate_b", "candidate_c"],
                "severity": ["advisory", "warning", "advisory"],
            }
        ),
        "data/scenarios/shuffle/train.parquet": pd.DataFrame({"prepared_row_id": [0], "x": [1.0]}),
        "data/scenarios/shuffle/test.parquet": pd.DataFrame({"prepared_row_id": [1], "x": [2.0]}),
    }
    for relative, frame in paths.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(destination, index=False)
    hashes = {relative: _sha(root / relative) for relative in paths}
    manifest = {
        "status": "completed",
        "eligible_row_count": 2,
        "excluded_row_count": 0,
        "data_artifacts": {
            "table": "data/table.parquet",
            "provenance": "data/provenance.parquet",
            "diagnostics": "data/diagnostics.parquet",
            "exclusions": "data/exclusions.parquet",
        },
        "artifact_hashes": hashes,
        "quality_artifacts": {"flags": "data/quality_flags.parquet"},
        "array_exports": {
            "enabled": True,
            "exports": [{"path": "data/arrays/features.float32.npy", "format": "npy"}],
        },
        "scenarios": {
            "scenario_count": 1,
            "partition_count": 2,
            "scenarios": [
                {
                    "name": "shuffle",
                    "partition_counts": {"train": 1, "test": 1},
                    "partition_artifacts": [
                        "data/scenarios/shuffle/train.parquet",
                        "data/scenarios/shuffle/test.parquet",
                    ],
                    "partition_artifact_hashes": {
                        key: hashes[key]
                        for key in (
                            "data/scenarios/shuffle/train.parquet",
                            "data/scenarios/shuffle/test.parquet",
                        )
                    },
                }
            ],
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    inspected = inspect_for_app(root)

    assert [table.table_id for table in inspected.tables] == [
        "table",
        "provenance",
        "diagnostics",
        "exclusions",
        "quality_flags",
        "scenario.shuffle.train",
        "scenario.shuffle.test",
    ]
    assert inspected.arrays == ({"path": "data/arrays/features.float32.npy", "format": "npy"},)

    quality_flags = resolve_table(root, "quality_flags", inspected.revision)
    assert quality_flags.path == data / "quality_flags.parquet"
    assert quality_flags.sha256 == hashes["data/quality_flags.parquet"]
    preview = preview_table(quality_flags, offset=1, limit=1)
    assert preview["table_id"] == "quality_flags"
    assert preview["total_row_count"] == 3
    assert preview["block_offset"] == 1
    assert preview["block_count"] == 1
    assert preview["rows"] == [[1, "candidate_b", "warning"]]
    with pytest.raises(ValueError, match="between 1 and 500"):
        preview_table(quality_flags, offset=0, limit=501)

    quality_flags.path.write_bytes(b"tampered")
    refreshed = inspect_for_app(root)
    assert refreshed.revision != inspected.revision
    assert "quality_flags" not in {table.table_id for table in refreshed.tables}
    assert refreshed.summary["quality"]["summary"]["status"] == "corrupt_or_missing"
    assert any("hash mismatch" in issue for issue in refreshed.summary["quality"]["errors"])
    with pytest.raises(VisualizationError, match="changed"):
        resolve_table(root, "quality_flags", inspected.revision)


def test_sweep_descriptors_cover_comparisons_and_child_datasets(tmp_path: Path) -> None:
    root = tmp_path / "sweep"
    comparison = root / "comparison"
    child = root / "models" / "heos" / "child"
    comparison.mkdir(parents=True)
    child.mkdir(parents=True)
    (root / "sweep.normalized.json").write_text("{}\n", encoding="utf-8")
    values = comparison / "values.parquet"
    deltas = comparison / "deltas.parquet"
    dataset = child / "dataset.parquet"
    pd.DataFrame(
        {
            "backend_model": ["heos"],
            "property": ["mass_density"],
            "value": [1.0],
        }
    ).to_parquet(values, index=False)
    pd.DataFrame(
        {
            "backend_model": ["pr"],
            "property": ["mass_density"],
            "signed_relative_difference": [0.01],
            "unavailable_reason": [None],
        }
    ).to_parquet(deltas, index=False)
    pd.DataFrame({"case_id": [0]}).to_parquet(dataset, index=False)
    child_metadata = {
        "artifact_hashes": {"dataset.parquet": _sha(dataset)},
        "canonical_units": {"case_id": "1"},
    }
    (child / "metadata.json").write_text(json.dumps(child_metadata), encoding="utf-8")
    metadata = {
        "sweep_status": "completed",
        "models": ["heos"],
        "reference_model": "heos",
        "child_runs": [{"backend_model": "heos", "output_directory": str(child), "run_id": "run"}],
        "artifact_hashes": {
            "comparison/values.parquet": _sha(values),
            "comparison/deltas.parquet": _sha(deltas),
        },
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "report.json").write_text("{}\n", encoding="utf-8")

    inspected = inspect_for_app(root)

    assert [table.table_id for table in inspected.tables] == [
        "comparison.values",
        "comparison.deltas",
        "model.heos.dataset",
    ]
