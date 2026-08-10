from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workflow_controller import (
    PreparationWorkflowController,
    SweepWorkflowController,
)
from carnopy.app.workspace import Workspace, initialize_workspace


class StubTransport(QObject):
    event_received = Signal(object)
    transport_finished = Signal(object)
    stderr_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.request_id: UUID | None = None
        self.request_type: RequestType | None = None
        self.raise_on_start = False

    def start_request(
        self,
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        del payload
        if self.raise_on_start:
            raise RuntimeError("simulated start failure")
        if self.is_busy:
            raise RuntimeError("transport is already busy")
        self.is_busy = True
        self.request_id = request_id
        self.request_type = request_type

    def send_cancel(self, request_id: UUID) -> bool:
        return self.is_busy and request_id == self.request_id

    def force_stop(self, request_id: UUID) -> bool:
        return self.is_busy and request_id == self.request_id

    def shutdown(self) -> None:
        if self.is_busy:
            raise RuntimeError("transport is busy")

    def emit_event(self, event_type: EventType, payload: dict[str, object]) -> None:
        request_id = self.request_id
        assert request_id is not None
        self.event_received.emit(
            WorkerEvent(request_id=request_id, type=event_type, payload=payload)
        )

    def finish(
        self,
        *,
        payload: dict[str, object] | None = None,
        terminal_type: EventType = "result",
    ) -> None:
        request_id = self.request_id
        request_type = self.request_type
        assert request_id is not None
        assert request_type is not None
        terminal = WorkerEvent(
            request_id=request_id,
            type=terminal_type,
            payload=dict(payload or {}),
        )
        self.is_busy = False
        self.request_id = None
        self.request_type = None
        self.transport_finished.emit(
            TransportOutcome(
                request_id=request_id,
                request_type=request_type,
                terminal_event=terminal,
                client_failure=None,
                stderr="",
                exit_code=0,
                exit_status="normal",
                force_stopped=False,
            )
        )


@pytest.fixture(scope="module")
def application() -> Iterator[QCoreApplication]:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def coordinator_for() -> tuple[DesktopRequestCoordinator, StubTransport]:
    transport = StubTransport()
    return DesktopRequestCoordinator(cast(WorkerClient, transport)), transport


def _config(workspace: Workspace, name: str = "workflow.yaml") -> Path:
    path = workspace.configs / name
    path.write_text("schema_version: 2\n", encoding="utf-8")
    return path


def _finish_load(transport: StubTransport, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    transport.finish(
        payload={
            "config": {"schema_version": 2},
            "source_name": str(path),
            "source_sha256": digest,
        }
    )
    return digest


def _finish_plan(
    transport: StubTransport,
    *,
    digest: str,
    plan_id: str = "b" * 64,
    source_revision: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "plan_id": plan_id,
        "configuration_sha256": digest,
    }
    if source_revision is not None:
        payload["source_revision"] = source_revision
    transport.finish(payload=payload)


def _finish_execution(
    transport: StubTransport,
    output_directory: Path,
    *,
    run_id: str = "workflow-run",
) -> None:
    transport.finish(
        payload={
            "run_id": run_id,
            "output_directory": str(output_directory),
            "status": "completed",
        }
    )


def _accept_preparation_inspection(
    inspection: InspectionController,
    source: Path,
    *,
    revision: str,
) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "controls": {},
        "tables": [],
    }
    inspection._clear_inspection(source=source.resolve(), state="loading")
    inspection._accept_inspection_payload(
        {
            "source": str(source.resolve()),
            "source_kind": "dataset",
            "revision": revision,
            "summary": {},
            "tables": [],
            "arrays": [],
            "plot_context": None,
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
        }
    )
    return descriptor


def test_sweep_controller_persists_only_execution_with_plan_identity(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.state == "ready"
    assert controller.can_plan

    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.state == "planned"
    assert controller.can_execute

    output = workspace.outputs / "sweep-output"
    finalized: list[Path] = []
    controller.output_finalized.connect(finalized.append)
    assert controller.execute()
    transport.finish(
        payload={
            "sweep_run_id": "sweep-run",
            "output_directory": str(output),
            "sweep_status": "completed",
        }
    )

    assert controller.state == "succeeded"
    assert finalized == [output]
    assert controller.get_has_result()
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(output)
    [record] = coordinator_for_job_records(workspace)
    assert record["owner"] == "sweep"
    assert record["operation"] == "execute_sweep"
    assert record["plan_identity"] == {
        "plan_id": "b" * 64,
        "plan_schema_version": None,
        "fingerprint": None,
    }
    coordinator.shutdown()


def test_finalized_result_survives_later_failed_and_cancelled_attempts(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert not controller.get_has_result()
    assert controller.get_result_relation() == "unavailable"
    assert controller.get_result_output_directory() == ""
    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    first_output = workspace.outputs / "first-output"
    first_output.mkdir()
    assert controller.execute()
    _finish_execution(transport, first_output, run_id="first-run")
    first_result = controller.result
    assert controller.get_result_relation() == "current"

    assert controller.execute()
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"
    transport.finish(
        terminal_type="error",
        payload={
            "category": "execution",
            "code": "execution_failed",
            "message": "simulated later failure",
        },
    )
    assert controller.state == "failed"
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(first_output)

    assert controller.execute()
    assert controller.result == first_result
    transport.finish(
        terminal_type="cancelled",
        payload={"code": "cancelled", "message": "simulated cancellation"},
    )
    assert controller.state == "cancelled"
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"

    second_output = workspace.outputs / "second-output"
    second_output.mkdir()
    assert controller.execute()
    _finish_execution(transport, second_output, run_id="second-run")
    assert controller.result != first_result
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(second_output)
    coordinator.shutdown()


def test_sweep_result_relation_uses_saved_identity_and_clears_with_workspace(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    output = workspace.outputs / "sweep-output"
    output.mkdir()
    assert controller.execute()
    _finish_execution(transport, output)
    finalized_result = controller.result

    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    controller.state_changed.emit()
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "stale"

    config.write_bytes(original_bytes)
    assert controller.get_result_relation() == "current"

    replacement = workspace.configs / "replacement.yaml"
    replacement.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    assert controller.load_config(replacement)
    _finish_load(transport, replacement)
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "stale"

    assert controller.load_config(config)
    assert _finish_load(transport, config) == digest
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "current"

    controller.set_workspace(initialize_workspace(tmp_path / "other-workspace"))
    assert controller.result is None
    assert not controller.get_has_result()
    assert controller.get_result_relation() == "unavailable"
    assert controller.get_result_output_directory() == ""
    coordinator.shutdown()


def test_failed_workflow_load_retains_previous_plan_as_stale(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.can_execute

    assert controller.load_config(workspace.configs / "missing.yaml")
    transport.finish(
        terminal_type="error",
        payload={
            "category": "config",
            "code": "invalid_config",
            "message": "configuration is invalid",
        },
    )

    assert controller.state == "failed"
    assert controller.current_plan is not None
    assert controller.get_has_plan()
    assert controller.get_plan_id() == "b" * 64
    assert not controller.get_plan_current()
    assert controller.loaded_config is None
    assert controller.config_path is None
    assert controller.config_sha256 == ""
    assert controller.validation is None
    assert not controller.can_plan
    assert not controller.can_execute
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "plan_configuration_changed",
        "saved_configuration_required",
    ]
    coordinator.shutdown()


def test_sweep_plan_currentness_follows_exact_saved_configuration_identity(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    assert controller.get_has_plan()
    assert controller.get_plan_id() == "b" * 64
    assert controller.get_plan_current()
    assert controller.can_execute

    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    controller.state_changed.emit()
    assert not controller.get_plan_current()
    assert not controller.can_execute
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "saved_configuration_unavailable"
    ]

    config.write_bytes(original_bytes)
    assert controller.get_plan_current()
    assert controller.can_execute

    replacement = workspace.configs / "replacement.yaml"
    replacement.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    assert controller.load_config(replacement)
    replacement_digest = _finish_load(transport, replacement)
    assert replacement_digest != digest
    assert controller.get_has_plan()
    assert not controller.get_plan_current()
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "plan_configuration_changed"
    ]

    assert controller.load_config(config)
    assert _finish_load(transport, config) == digest
    assert controller.get_plan_current()
    assert controller.can_execute

    controller.set_workspace(initialize_workspace(tmp_path / "other-workspace"))
    assert not controller.get_has_plan()
    assert not controller.get_plan_current()
    coordinator.shutdown()


def test_cancelled_replan_keeps_the_last_semantically_current_plan(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.plan()
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert not controller.can_execute
    transport.finish(
        terminal_type="cancelled",
        payload={"code": "cancelled", "message": "planning cancelled"},
    )

    assert controller.state == "cancelled"
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


def test_changed_saved_bytes_prevent_a_plan_response_from_replacing_the_last_plan(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.plan()
    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    _finish_plan(transport, digest=digest, plan_id="c" * 64)

    assert controller.state == "failed"
    assert controller.failure["code"] == "stale_plan"
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_id() == "b" * 64
    assert not controller.get_plan_current()

    config.write_bytes(original_bytes)
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


@pytest.mark.parametrize("failure_code", ["stale_plan", "source_changed"])
def test_worker_semantic_failure_retains_but_rejects_the_plan(
    tmp_path: Path,
    application: QCoreApplication,
    failure_code: str,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.execute()
    transport.finish(
        terminal_type="error",
        payload={
            "category": "config",
            "code": failure_code,
            "message": "execution-time planning produced a different identity",
        },
    )

    assert controller.state == "failed"
    assert controller.current_plan == accepted_plan
    assert controller.get_has_plan()
    assert not controller.get_plan_current()
    assert not controller.can_execute
    [reason] = controller.execution_blocking_reasons.issues
    assert reason.code == "plan_rejected_by_worker"
    assert reason.origin == "plan"
    assert reason.message == "execution-time planning produced a different identity"
    coordinator.shutdown()


def test_workflow_terminal_activity_persistence_failure_is_reported(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    from carnopy.app.jobs import JobStore

    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.execute()

    store = controller._store
    assert isinstance(store, JobStore)

    def fail_persistence(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "finish", fail_persistence)
    monkeypatch.setattr(store, "write", fail_persistence)
    transport.finish(payload={"output_directory": str(workspace.outputs / "sweep")})

    assert controller.state == "succeeded"
    assert "disk unavailable" in controller.activity_persistence_issue
    coordinator.shutdown()


def test_worker_start_failure_does_not_leak_activity_record_into_next_request(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    from carnopy.app.jobs import JobStore

    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    transport.raise_on_start = True
    assert not controller.execute()
    failed_records = JobStore(workspace.private_directory).load()
    [failed] = [item.data for item in failed_records if item.data is not None]
    assert failed["operation"] == "execute_sweep"
    assert failed["phase"] == "starting"

    transport.raise_on_start = False
    assert controller.load_config(config)
    transport.emit_event("phase", {"name": "validation", "cancellable": True})
    _finish_load(transport, config)

    records = JobStore(workspace.private_directory).load()
    failed_after = next(
        item.data
        for item in records
        if item.data is not None and item.data["operation"] == "execute_sweep"
    )
    assert failed_after is not None
    assert failed_after["phase"] == "starting"
    coordinator.shutdown()


def coordinator_for_job_records(workspace: Workspace) -> list[dict[str, object]]:
    from carnopy.app.jobs import JobStore

    records = JobStore(workspace.private_directory).load()
    return [cast(dict[str, object], item.data) for item in records if item.data is not None]


def test_preparation_controller_rejects_a_plan_for_replaced_inspection(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    old_revision = "a" * 64
    old_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=old_revision,
    )
    assert controller.plan()

    new_revision = "c" * 64
    new_descriptor = _accept_preparation_inspection(
        inspection,
        replacement,
        revision=new_revision,
    )
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": old_revision,
            "inspection_descriptor": old_descriptor,
            "consumed_source": {},
        },
    )

    assert controller.state == "failed"
    assert controller.failure["code"] == "stale_plan"
    assert controller.current_plan is None
    assert controller._plan_context() == {
        "source_path": str(replacement.resolve()),
        "inspection_revision": new_revision,
        "inspection_descriptor": new_descriptor,
    }
    coordinator.shutdown()


def test_preparation_plan_currentness_uses_the_complete_inspection_context(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    accepted_plan = controller.current_plan
    assert controller.get_plan_current()
    assert controller.can_execute

    _accept_preparation_inspection(
        inspection,
        replacement,
        revision=revision,
    )
    assert controller.current_plan == accepted_plan
    assert not controller.get_plan_current()
    assert not controller.can_execute
    [reason] = controller.execution_blocking_reasons.issues
    assert reason.code == "plan_context_changed"
    assert reason.origin == "source"

    restored_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert restored_descriptor == descriptor
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


def test_preparation_result_keeps_the_source_context_used_by_execution(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    output = workspace.outputs / "preparation-output"
    output.mkdir()
    assert controller.execute()
    _accept_preparation_inspection(
        inspection,
        replacement,
        revision=revision,
    )
    _finish_execution(transport, output)

    assert controller.state == "succeeded"
    assert controller.get_has_result()
    assert controller.get_result_output_directory() == str(output)
    assert controller.get_result_relation() == "stale"

    restored_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert restored_descriptor == descriptor
    assert controller.get_result_relation() == "current"
    coordinator.shutdown()


def test_workflow_qml_projections_expose_existing_state_without_changing_eligibility(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, _transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)

    assert controller.get_workflow_kind() == "sweep"
    assert controller.get_document_kind() == "model_sweep"
    assert controller.get_workflow_state() == "unavailable"
    assert not controller.get_operation_active()
    assert not controller.get_can_plan()
    assert not controller.get_can_execute()
    assert [issue.code for issue in controller.plan_blocking_reasons.issues] == [
        "workspace_required"
    ]
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "current_plan_required",
        "workspace_required",
    ]

    controller.set_workspace(workspace)

    assert controller.get_workflow_state() == "ready"
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "saved_configuration_required"
    assert reason.origin == "local"
    assert reason.severity == "blocking"
    assert reason.document_kind == "model_sweep"
    assert reason.section == "configuration"
    assert reason.field_id == "sweep.configuration"
    coordinator.shutdown()


def test_workflow_operation_progress_and_protected_finalization_are_typed(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)
    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.get_can_plan()
    assert controller.plan_blocking_reasons.issues == ()
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.get_can_execute()
    assert controller.execution_blocking_reasons.issues == ()

    assert controller.execute()
    assert controller.get_operation_active()
    assert controller.get_workflow_operation() == "execute"
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "operation_active"
    ]
    transport.emit_event("accepted", {})
    transport.emit_event(
        "phase",
        {"name": "generation", "cancellable": True},
    )
    transport.emit_event("progress", {"completed": 7, "total": 10})

    assert controller.get_workflow_state() == "running"
    assert controller.get_workflow_phase() == "generation"
    assert controller.get_progress_available()
    assert controller.get_progress_completed() == 7
    assert controller.get_progress_total() == 10
    assert controller.get_cancellation_available()
    assert not controller.get_force_stop_available()
    assert not controller.get_protected_finalization()

    transport.emit_event(
        "phase",
        {
            "name": "finalization",
            "cancellable": False,
            "termination_protected": True,
        },
    )

    assert controller.get_protected_finalization()
    assert not controller.get_cancellation_available()
    assert not controller.get_force_stop_available()
    transport.finish(payload={"output_directory": str(workspace.outputs / "sweep")})
    assert not controller.get_operation_active()
    assert not controller.get_protected_finalization()
    coordinator.shutdown()


def test_workflow_failure_and_preparation_source_blockers_are_typed(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)
    assert controller.load_config(config)
    _finish_load(transport, config)

    assert not controller.get_can_plan()
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "preparation_source_unavailable"
    assert reason.origin == "source"
    assert reason.document_kind == "preparation"
    assert reason.section == "source"
    assert reason.field_id == "preparation.source"

    assert not controller.plan()
    assert controller.get_workflow_state() == "failed"
    assert controller.get_failure_category() == "request"
    assert controller.get_failure_code() == "plan_unavailable"
    assert "eligible preparation source" in controller.get_failure_message()
    coordinator.shutdown()
