from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from uuid import uuid4

import pytest

import carnopy.preparation.source as preparation_source
from carnopy.api import generate_dataset, prepare_dataset
from carnopy.app.source_inspection import (
    inspect_for_app,
    revalidate_preparation_inspection,
)
from carnopy.app.workflow_planning import plan_preparation, plan_sweep
from carnopy.config.io import load_sweep_config_bytes, load_sweep_config_file
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.preparation.computation import fit_preparation_baselines
from carnopy.preparation.layout import (
    cleanup_preparation_layout,
    create_preparation_layout,
    finalize_preparation_layout,
)
from carnopy.preparation.models import (
    load_preparation_config,
    load_preparation_config_bytes,
)
from carnopy.preparation.source import load_preparation_source


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


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


def _preparation_config(path: Path, *, baselines: bool = False) -> Path:
    scenario = (
        ""
        if not baselines
        else """
scenarios:
  - name: baseline_holdout
    kind: shuffle
    seed: 42
    partitions:
      train: 0.5
      test: 0.5
quality:
  matrix_diagnostics: {}
  baseline_diagnostics:
    models: [dummy_mean, ridge]
    random_seed: 42
    ridge_alpha: 1.0
    histogram_max_iterations: 20
"""
    )
    return _write(
        path,
        f"""schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features: []
targets: [specific_enthalpy]
auxiliary: [fluid, backend_model, phase, run_id, case_id]
outputs:
  formats: [parquet]
{scenario}""",
    )


def test_exact_byte_workflow_loaders_preserve_identity(tmp_path: Path) -> None:
    sweep_path = _sweep_config(tmp_path / "sweep.yaml")
    sweep_bytes = sweep_path.read_bytes() + b"# exact trailing comment\n"
    loaded_sweep = load_sweep_config_bytes(sweep_bytes, source_name="exact-sweep.yaml")
    assert loaded_sweep.raw_bytes == sweep_bytes
    assert loaded_sweep.path == Path("exact-sweep.yaml")

    preparation_path = _preparation_config(tmp_path / "preparation.yaml")
    preparation_bytes = preparation_path.read_bytes() + b"# exact trailing comment\n"
    loaded_preparation = load_preparation_config_bytes(
        preparation_bytes,
        source_name="exact-preparation.yaml",
    )
    assert loaded_preparation.raw_bytes == preparation_bytes
    assert loaded_preparation.path == Path("exact-preparation.yaml")


def test_sweep_plan_is_deterministic_nonwriting_and_binds_runtime(tmp_path: Path) -> None:
    config = _sweep_config(tmp_path / "sweep.yaml")
    loaded = load_sweep_config_file(config)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    first = plan_sweep(loaded)
    second = plan_sweep(loaded)

    assert first == second
    assert first["plan_id"] == second["plan_id"]
    assert first["projected_rows_by_model"] == {"heos": 1, "pr": 1}
    assert first["projected_rows_total"] == 2
    runtime = first["fingerprint"]["runtime"]
    assert set(runtime) == {"coolprop", "numpy", "pandas", "pyarrow"}
    assert all(runtime[name] for name in runtime)
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before

    changed = load_sweep_config_bytes(
        loaded.raw_bytes + b"# identity change\n",
        source_name=str(config),
    )
    assert plan_sweep(changed)["plan_id"] != first["plan_id"]


def test_preparation_plan_is_revision_bound_nonwriting_and_never_fits(
    tmp_path: Path,
    property_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("sklearn")
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    assert inspection.preparation_eligible
    assert inspection.preparation_source_descriptor is not None
    loaded = load_preparation_config(
        _preparation_config(tmp_path / "preparation.yaml", baselines=True)
    )

    fit_calls: list[str] = []

    def fail_if_fitted(self: object, *_args: object, **_kwargs: object) -> object:
        fit_calls.append(type(self).__name__)
        raise RuntimeError("fit sentinel")

    monkeypatch.setattr("sklearn.dummy.DummyRegressor.fit", fail_if_fitted)
    monkeypatch.setattr("sklearn.linear_model.Ridge.fit", fail_if_fitted)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    plan, computation = plan_preparation(
        loaded,
        str(run.output_directory),
        inspection_revision=inspection.revision,
        inspection_descriptor=inspection.preparation_source_descriptor,
    )

    assert fit_calls == []
    assert plan["source_revision"]["inspection_revision"] == inspection.revision
    assert plan["selected_backend_models"] == ["heos"]
    assert plan["eligible_row_count"] > 0
    assert plan["baseline_feasibility"][0]["status"] == "ready"
    assert plan["matrix_diagnostics"]
    assert plan["scenarios"][0]["state_leakage"]["cross_partition_group_count"] == 0
    runtime = plan["fingerprint"]["runtime"]
    assert set(runtime) == {"numpy", "pandas", "pyarrow", "scikit-learn"}
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before

    fitted = fit_preparation_baselines(computation)
    assert fitted is not None
    assert fit_calls


def test_inspection_explicitly_rejects_standalone_and_prepared_sources(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    standalone = tmp_path / "standalone.parquet"
    standalone.write_bytes((run.output_directory / "dataset.parquet").read_bytes())
    standalone_inspection = inspect_for_app(standalone)
    assert not standalone_inspection.preparation_eligible
    assert "standalone" in standalone_inspection.preparation_ineligible_reason

    prepared = prepare_dataset(
        run.output_directory,
        config=_preparation_config(tmp_path / "preparation.yaml"),
        output_root=tmp_path / "prepared",
    )
    prepared_inspection = inspect_for_app(prepared.output_directory)
    assert not prepared_inspection.preparation_eligible
    assert "prepared bundles" in prepared_inspection.preparation_ineligible_reason


def test_stable_source_read_rejects_same_digest_replacement_after_inspection(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    dataset_descriptor = next(item for item in descriptor["tables"] if item["id"] == "dataset")
    dataset = Path(dataset_descriptor["path"])
    replacement = dataset.with_name("replacement.parquet")
    replacement.write_bytes(dataset.read_bytes())
    os.replace(replacement, dataset)

    with pytest.raises(ConfigError, match="identity changed after inspection"):
        load_preparation_source(
            run.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
        )


@pytest.mark.parametrize("mutation", ["in_place", "truncate"])
def test_stable_source_read_rejects_changed_bytes_after_inspection(
    tmp_path: Path,
    property_config_path: Path,
    mutation: str,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    dataset_descriptor = next(item for item in descriptor["tables"] if item["id"] == "dataset")
    dataset = Path(dataset_descriptor["path"])
    original = dataset.read_bytes()
    if mutation == "truncate":
        dataset.write_bytes(original[: len(original) // 2])
    else:
        with dataset.open("r+b") as stream:
            stream.seek(len(original) // 2)
            current = stream.read(1)
            stream.seek(len(original) // 2)
            stream.write(bytes([current[0] ^ 1]))

    with pytest.raises(ConfigError, match=r"hash mismatch|changed after inspection"):
        load_preparation_source(
            run.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
        )


@pytest.mark.parametrize("mutation", ["in_place", "replacement"])
def test_stable_source_read_rejects_changes_during_table_parsing(
    tmp_path: Path,
    property_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    original_reader = preparation_source._read_dataset_stream

    def read_then_change(path: Path, stream: IO[bytes]) -> object:
        frame = original_reader(path, stream)
        original = path.read_bytes()
        if mutation == "replacement":
            replacement = path.with_name("during-parse.parquet")
            replacement.write_bytes(original)
            os.replace(replacement, path)
        else:
            with path.open("r+b") as writer:
                writer.seek(len(original) // 2)
                current = writer.read(1)
                writer.seek(len(original) // 2)
                writer.write(bytes([current[0] ^ 1]))
        return frame

    monkeypatch.setattr(preparation_source, "_read_dataset_stream", read_then_change)

    with pytest.raises(ConfigError, match=r"changed while loading|changed after loading"):
        load_preparation_source(
            run.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
        )


def test_preparation_layout_rejects_replaced_staging_directory(tmp_path: Path) -> None:
    layout = create_preparation_layout(
        tmp_path / "prepared",
        preparation_run_id=str(uuid4()),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    original = layout.staging_directory.with_name(f"{layout.staging_directory.name}.original")
    layout.staging_directory.rename(original)
    layout.staging_directory.mkdir()

    with pytest.raises(OutputError, match="replaced preparation staging"):
        finalize_preparation_layout(layout)
    with pytest.raises(OutputError, match="replaced preparation staging"):
        cleanup_preparation_layout(layout)


def test_inspection_revalidation_hashes_revision_without_reloading_tables(
    tmp_path: Path,
    property_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None

    monkeypatch.setattr(
        "carnopy.app.source_inspection.load_preparation_source",
        lambda *_args, **_kwargs: pytest.fail("revalidation reparsed source tables"),
    )
    revalidate_preparation_inspection(
        run.output_directory,
        inspection_revision=inspection.revision,
        inspection_descriptor=descriptor,
    )
