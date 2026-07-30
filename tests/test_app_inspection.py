from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from carnopy.app.source_inspection import inspect_for_app, resolve_table
from carnopy.inspection import inspect_source
from carnopy.visualization.models import VisualizationError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    assert resolved.path == dataset

    dataset.write_bytes(dataset.read_bytes() + b"changed")
    with pytest.raises(VisualizationError, match="changed"):
        resolve_table(dataset, "dataset", inspected.revision)


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


def test_preparation_descriptors_cover_main_and_scenario_tables(tmp_path: Path) -> None:
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
        "scenario.shuffle.train",
        "scenario.shuffle.test",
    ]
    assert inspected.arrays == ({"path": "data/arrays/features.float32.npy", "format": "npy"},)


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
