from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.app.protocol import PROTOCOL_VERSION, WorkerRequest
from carnopy.app.worker import main
from carnopy.app.workflow_planning import plan_sweep
from carnopy.app.workflow_worker import execute_workflow_request
from carnopy.app.workspace import initialize_workspace
from carnopy.config.io import load_sweep_config_file
from carnopy.domain.failures import OutputError
from carnopy.sweeps.layout import (
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
