from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.api import generate_dataset
from carnopy.app.protocol import PROTOCOL_VERSION, WorkerRequest
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.worker import main
from carnopy.app.workflow_planning import plan_sweep
from carnopy.app.workflow_worker import execute_workflow_request
from carnopy.app.workspace import initialize_workspace
from carnopy.config.io import load_sweep_config_file
from carnopy.domain.failures import OutputError
from carnopy.sweeps.comparison import write_comparison_artifacts
from carnopy.sweeps.layout import (
    SweepLayout,
    cleanup_sweep_layout,
    create_sweep_layout,
    finalize_sweep_layout,
)
from carnopy.sweeps.pipeline import _child_execution, run_model_sweep


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


def _preparation_config(path: Path) -> Path:
    return _write(
        path,
        """schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features: []
targets: [specific_enthalpy]
auxiliary: [fluid, backend_model, phase, run_id, case_id]
outputs:
  formats: [parquet]
""",
    )


def _request(request_type: str, payload: dict[str, object]) -> tuple[str, str]:
    request_id = str(uuid4())
    return request_id, json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "type": request_type,
            "payload": payload,
        }
    )


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_child_finalization_does_not_protect_the_outer_sweep() -> None:
    cancelled = False
    phases: list[tuple[str, bool]] = []
    parent = ExecutionControl(
        cancellation_requested=lambda: cancelled,
        on_phase=lambda name, cancellable: phases.append((name, cancellable)),
        on_progress=lambda _completed, _total: None,
    )
    child = _child_execution(
        parent,
        model="heos",
        completed_before_model=0,
        projected_total=1,
    )
    assert child is not None

    child.protected_phase("finalization")
    cancelled = True

    assert phases == [("model:heos:finalization", False)]
    with pytest.raises(ExecutionCancelled):
        parent.raise_if_cancelled()


@pytest.mark.parametrize(
    ("failure", "expected_type"),
    [
        (ExecutionCancelled("cancelled sentinel"), ExecutionCancelled),
        (RuntimeError("unexpected sentinel"), RuntimeError),
    ],
)
def test_sweep_cancellation_and_unexpected_failures_clean_without_finalizing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_type: type[Exception],
) -> None:
    loaded = load_sweep_config_file(_sweep_config(tmp_path / "sweep.yaml"))
    output_root = tmp_path / "outputs"

    def fail_generation(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr("carnopy.sweeps.pipeline.run_generation", fail_generation)

    with pytest.raises(expected_type, match="sentinel"):
        run_model_sweep(loaded, output_root)

    assert list(output_root.iterdir()) == []


def test_comparison_artifact_writes_preserve_cancellation_between_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.sweeps.comparison as comparison

    cancelled = False
    writes: list[Path] = []

    class FakeFrame:
        def to_parquet(self, path: Path, *, index: bool) -> None:
            nonlocal cancelled
            assert index is False
            path.write_bytes(b"parquet")
            writes.append(path)
            cancelled = True

    monkeypatch.setattr(comparison, "_values_frame", lambda **_kwargs: FakeFrame())
    monkeypatch.setattr(
        comparison,
        "_deltas_frame",
        lambda *_args, **_kwargs: FakeFrame(),
    )

    def checkpoint() -> None:
        if cancelled:
            raise ExecutionCancelled("cancel between comparison artifacts")

    directory = tmp_path / "comparison"
    with pytest.raises(ExecutionCancelled, match="between comparison artifacts"):
        write_comparison_artifacts(
            sweep_id="sweep-test",
            reference_model="heos",
            child_run_paths={},
            child_results={},
            properties=[],
            comparison_directory=directory,
            checkpoint=checkpoint,
        )
    assert writes == [directory / "values.parquet"]
    assert not (directory / "deltas.parquet").exists()


def test_sweep_reporting_checks_cancellation_between_artifact_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.sweeps.pipeline as sweep_pipeline

    loaded = load_sweep_config_file(_sweep_config(tmp_path / "sweep.yaml"))
    output_root = tmp_path / "outputs"
    cancelled = False
    real_write_json = sweep_pipeline.write_json

    def write_then_cancel(path: Path, value: dict[str, Any]) -> None:
        nonlocal cancelled
        real_write_json(path, value)
        if path.name == "report.json":
            cancelled = True

    monkeypatch.setattr(sweep_pipeline, "write_json", write_then_cancel)
    control = ExecutionControl(
        cancellation_requested=lambda: cancelled,
        on_phase=lambda _name, _cancellable: None,
        on_progress=lambda _completed, _total: None,
    )

    with pytest.raises(ExecutionCancelled):
        run_model_sweep(loaded, output_root, execution=control)
    assert output_root.is_dir()
    assert list(output_root.iterdir()) == []


def test_protocol_accepts_all_stage4_request_names() -> None:
    request_types = (
        "load_sweep_config",
        "validate_sweep_config",
        "plan_sweep",
        "execute_sweep",
        "load_preparation_config",
        "validate_preparation_config",
        "plan_preparation",
        "execute_preparation",
    )
    for request_type in request_types:
        request = WorkerRequest.model_validate(
            {
                "protocol_version": 1,
                "request_id": str(uuid4()),
                "type": request_type,
                "payload": {},
            }
        )
        assert request.type == request_type


def test_worker_sweep_plan_execute_emits_only_outer_protected_finalization(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _sweep_config(workspace.configs / "sweep.yaml")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    common = {
        "config_path": str(config),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
    }
    _, plan_line = _request("plan_sweep", common)
    plan_stdout = io.StringIO()
    assert main(io.StringIO(plan_line + "\n"), plan_stdout, io.StringIO()) == 0
    plan_events = _events(plan_stdout)
    plan = plan_events[-1]["payload"]
    assert isinstance(plan, dict)
    assert list(workspace.outputs.iterdir()) == []

    _, execute_line = _request(
        "execute_sweep",
        {
            **common,
            "expected_plan_id": plan["plan_id"],
            "output_root": str(workspace.outputs),
        },
    )
    execute_stdout = io.StringIO()
    assert main(io.StringIO(execute_line + "\n"), execute_stdout, io.StringIO()) == 0
    execute_events = _events(execute_stdout)
    protected = [
        event
        for event in execute_events
        if event["type"] == "phase"
        and isinstance(event["payload"], dict)
        and event["payload"].get("termination_protected") is True
    ]
    assert len(protected) == 1
    assert protected[0]["payload"]["name"] == "finalization"
    result = execute_events[-1]
    assert result["type"] == "result"
    assert result["payload"]["sweep_status"] == "completed"


def test_worker_preparation_plan_execute_covers_the_complete_request_lifecycle(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    source = generate_dataset(
        property_config_path,
        output_root=workspace.outputs,
    ).output_directory
    inspection = inspect_for_app(source)
    descriptor = inspection.preparation_source_descriptor
    assert descriptor is not None
    config = _preparation_config(workspace.configs / "preparation.yaml")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    common = {
        "config_path": str(config),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
        "source_path": str(source),
        "inspection_revision": inspection.revision,
        "inspection_descriptor": descriptor,
    }
    _, plan_line = _request("plan_preparation", common)
    plan_stdout = io.StringIO()

    assert main(io.StringIO(plan_line + "\n"), plan_stdout, io.StringIO()) == 0
    plan_events = _events(plan_stdout)
    plan = plan_events[-1]["payload"]
    assert isinstance(plan, dict)
    assert plan_events[-1]["type"] == "result"
    assert plan["workflow_kind"] == "preparation"

    _, execute_line = _request(
        "execute_preparation",
        {
            **common,
            "expected_plan_id": plan["plan_id"],
            "output_root": str(workspace.outputs),
        },
    )
    execute_stdout = io.StringIO()

    assert main(io.StringIO(execute_line + "\n"), execute_stdout, io.StringIO()) == 0
    execute_events = _events(execute_stdout)
    protected = [
        event
        for event in execute_events
        if event["type"] == "phase"
        and isinstance(event["payload"], dict)
        and event["payload"].get("termination_protected") is True
    ]
    assert len(protected) == 1
    assert protected[0]["payload"]["name"] == "finalization"
    result = execute_events[-1]
    assert result["type"] == "result"
    assert result["payload"]["status"] in {"completed", "completed_with_exclusions"}


def test_execute_sweep_reuses_the_verified_normalized_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _sweep_config(workspace.configs / "sweep.yaml")
    loaded = load_sweep_config_file(config)
    plan = plan_sweep(loaded)

    def unexpected_second_normalization(*_args: object, **_kwargs: object) -> object:
        pytest.fail("execution normalized the sweep a second time")

    monkeypatch.setattr(
        "carnopy.sweeps.pipeline.normalize_sweep_config",
        unexpected_second_normalization,
    )

    result = execute_workflow_request(
        "execute_sweep",
        {
            "config_path": str(config),
            "expected_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
            "configs_root": str(workspace.configs),
            "expected_plan_id": plan["plan_id"],
            "output_root": str(workspace.outputs),
        },
        emit=lambda _event_type, _payload: None,
        cancellation_requested=lambda: False,
    )

    assert result["sweep_status"] == "completed"


def test_sweep_layout_rejects_replaced_staging_directory(tmp_path: Path) -> None:
    layout = create_sweep_layout(
        output_root=tmp_path / "sweeps",
        sweep_run_id=str(uuid4()),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    original = layout.staging_directory.with_name(f"{layout.staging_directory.name}.original")
    layout.staging_directory.rename(original)
    layout.staging_directory.mkdir()

    with pytest.raises(OutputError, match="replaced sweep staging"):
        finalize_sweep_layout(layout)
    with pytest.raises(OutputError, match="replaced sweep staging"):
        cleanup_sweep_layout(layout)


def test_sweep_finalization_atomically_rejects_a_competing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import carnopy.sweeps.layout as sweep_layout

    layout = create_sweep_layout(
        output_root=tmp_path / "sweeps",
        sweep_run_id=str(uuid4()),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    original_verify = sweep_layout._verify_sweep_staging

    def verify_then_compete(value: SweepLayout) -> None:
        original_verify(value)
        layout.final_directory.mkdir()

    monkeypatch.setattr(sweep_layout, "_verify_sweep_staging", verify_then_compete)

    with pytest.raises(OutputError, match="could not finalize sweep"):
        finalize_sweep_layout(layout)
    assert layout.staging_directory.is_dir()
    assert layout.final_directory.is_dir()
