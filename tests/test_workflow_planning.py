from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from uuid import uuid4

import pytest

import carnopy.preparation.source as preparation_source
from carnopy.api import generate_dataset, generate_model_sweep, prepare_dataset
from carnopy.app.source_inspection import (
    inspect_for_app,
    revalidate_preparation_inspection,
)
from carnopy.app.workflow_planning import plan_preparation, plan_sweep
from carnopy.app.workflow_worker import StalePlanError, execute_workflow_request
from carnopy.config.io import load_sweep_config_bytes, load_sweep_config_file
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.preparation.computation import fit_preparation_baselines
from carnopy.preparation.layout import (
    PreparationLayout,
    cleanup_preparation_layout,
    create_preparation_layout,
    finalize_preparation_layout,
)
from carnopy.preparation.models import (
    load_preparation_config,
    load_preparation_config_bytes,
)
from carnopy.preparation.source import load_preparation_source
from carnopy.visualization.models import VisualizationError


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


def test_sweep_runtime_change_invalidates_plan_before_output_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = tmp_path / "configs"
    config = _sweep_config(configs / "sweep.yaml")
    loaded = load_sweep_config_file(config)
    versions = {
        "CoolProp": "7.1.0",
        "numpy": "2.3.0",
        "pandas": "2.3.0",
        "pyarrow": "20.0.0",
    }
    monkeypatch.setattr(
        "carnopy.app.workflow_planning._distribution_version",
        versions.__getitem__,
    )
    accepted = plan_sweep(loaded)
    versions["pandas"] = "2.4.0"

    current = plan_sweep(loaded)

    assert current["plan_id"] != accepted["plan_id"]
    assert current["fingerprint"]["runtime"]["pandas"] == "2.4.0"
    output_root = tmp_path / "outputs"
    with pytest.raises(StalePlanError, match="workflow plan changed"):
        execute_workflow_request(
            "execute_sweep",
            {
                "config_path": str(config),
                "expected_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                "configs_root": str(configs),
                "expected_plan_id": accepted["plan_id"],
                "output_root": str(output_root),
            },
            emit=lambda _event_type, _payload: None,
            cancellation_requested=lambda: False,
        )
    assert not output_root.exists()


def test_sweep_runtime_fingerprint_includes_only_requested_optional_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain_path = _sweep_config(tmp_path / "plain.yaml")
    plotted_path = _sweep_config(tmp_path / "plotted.yaml")
    plotted_path.write_text(
        plotted_path.read_text(encoding="utf-8")
        + """comparison_plots:
  format: png
  plots:
    - name: density_comparison
      kind: property_comparison
      fluid: Propane
      property: mass_density
      x: temperature
      models: [heos, pr]
""",
        encoding="utf-8",
    )
    versions = {
        "CoolProp": "7.1.0",
        "numpy": "2.3.0",
        "pandas": "2.3.0",
        "pyarrow": "20.0.0",
        "matplotlib": "3.10.0",
    }
    monkeypatch.setattr(
        "carnopy.app.workflow_planning._distribution_version",
        versions.__getitem__,
    )

    plain_runtime = plan_sweep(load_sweep_config_file(plain_path))["fingerprint"]["runtime"]
    plotted_runtime = plan_sweep(load_sweep_config_file(plotted_path))["fingerprint"]["runtime"]

    assert "matplotlib" not in plain_runtime
    assert plotted_runtime["matplotlib"] == "3.10.0"


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


def test_preparation_inspection_binds_sweep_child_metadata(
    tmp_path: Path,
) -> None:
    sweep = generate_model_sweep(
        _sweep_config(tmp_path / "sweep.yaml"),
        output_root=tmp_path / "sweeps",
    )
    inspection = inspect_for_app(sweep.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None

    metadata_path = sweep.child_runs[0].output_directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["run_id"] = "changed-after-inspection"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(VisualizationError, match="changed after inspection"):
        revalidate_preparation_inspection(
            sweep.output_directory,
            inspection_revision=inspection.revision,
            inspection_descriptor=descriptor,
        )
    with pytest.raises(ConfigError, match="metadata identity changed"):
        load_preparation_source(
            sweep.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
        )


def test_preparation_metadata_parse_is_bound_to_the_verified_descriptor(
    tmp_path: Path,
    property_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    inspection = inspect_for_app(run.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    metadata_path = run.output_directory / "metadata.json"
    original = metadata_path.read_bytes()
    original_info = metadata_path.stat(follow_symlinks=False)
    metadata = json.loads(original)
    run_id = metadata["run_id"]
    replacement_id = ("0" if run_id[0] != "0" else "1") + run_id[1:]
    changed = original.replace(run_id.encode(), replacement_id.encode(), 1)
    assert len(changed) == len(original)
    metadata_path.write_bytes(changed)
    os.utime(
        metadata_path,
        ns=(original_info.st_atime_ns, original_info.st_mtime_ns),
    )
    real_loads = preparation_source.json.loads

    def parse_then_restore(value: object, *args: object, **kwargs: object) -> object:
        parsed = real_loads(value, *args, **kwargs)
        metadata_path.write_bytes(original)
        os.utime(
            metadata_path,
            ns=(original_info.st_atime_ns, original_info.st_mtime_ns),
        )
        return parsed

    monkeypatch.setattr(preparation_source.json, "loads", parse_then_restore)

    with pytest.raises(ConfigError, match="metadata identity changed after inspection"):
        load_preparation_source(
            run.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
        )
    assert metadata_path.read_bytes() == original


def test_sweep_source_loading_checks_cancellation_between_child_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep = generate_model_sweep(
        _sweep_config(tmp_path / "sweep.yaml"),
        output_root=tmp_path / "sweeps",
    )
    inspection = inspect_for_app(sweep.output_directory)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    original_reader = preparation_source._read_dataset_stream
    parsed_tables: list[Path] = []
    cancelled = False

    def read_then_cancel(path: Path, stream: IO[bytes]) -> object:
        nonlocal cancelled
        frame = original_reader(path, stream)
        parsed_tables.append(path)
        cancelled = True
        return frame

    def checkpoint() -> None:
        if cancelled:
            raise RuntimeError("cancel between source tables")

    monkeypatch.setattr(preparation_source, "_read_dataset_stream", read_then_cancel)

    with pytest.raises(RuntimeError, match="cancel between source tables"):
        load_preparation_source(
            sweep.output_directory,
            allow_partial_sweep=False,
            accepted_descriptor=descriptor,
            cancellation_checkpoint=checkpoint,
        )
    assert len(parsed_tables) == 1


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


def test_preparation_finalization_atomically_rejects_a_competing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.preparation.layout as preparation_layout

    layout = create_preparation_layout(
        tmp_path / "prepared",
        preparation_run_id=str(uuid4()),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    original_verify = preparation_layout._verify_preparation_staging

    def verify_then_compete(value: PreparationLayout) -> None:
        original_verify(value)
        layout.final_directory.mkdir()

    monkeypatch.setattr(
        preparation_layout,
        "_verify_preparation_staging",
        verify_then_compete,
    )

    with pytest.raises(OutputError, match="could not finalize preparation"):
        finalize_preparation_layout(layout)
    assert layout.staging_directory.is_dir()
    assert layout.final_directory.is_dir()


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
