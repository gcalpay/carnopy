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
    [record] = coordinator_for_job_records(workspace)
    assert record["owner"] == "sweep"
    assert record["operation"] == "execute_sweep"
    assert record["plan_identity"] == {
        "plan_id": "b" * 64,
        "plan_schema_version": None,
        "fingerprint": None,
    }
    coordinator.shutdown()


def test_failed_workflow_load_invalidates_previous_plan(
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
    assert controller.current_plan is None
    assert controller.loaded_config is None
    assert controller.config_path is None
    assert controller.config_sha256 == ""
    assert controller.validation is None
    assert not controller.can_plan
    assert not controller.can_execute
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
