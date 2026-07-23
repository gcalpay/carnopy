from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.config_controller import DatasetConfigController
from carnopy.app.config_document import ConfigDocumentError, SavedConfigSnapshot
from carnopy.app.execution_controller import DatasetExecutionController
from carnopy.app.jobs import JobStore
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import DesktopRequestCoordinator
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
        self.started: list[tuple[UUID, RequestType, dict[str, object]]] = []
        self.cancelled: list[UUID] = []
        self.force_stopped: list[UUID] = []
        self.raise_on_start = False

    def start_request(
        self,
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        if self.raise_on_start:
            raise RuntimeError("simulated worker-start failure")
        self.is_busy = True
        self.request_id = request_id
        self.request_type = request_type
        self.started.append((request_id, request_type, dict(payload or {})))

    def send_cancel(self, request_id: UUID) -> bool:
        if not self.is_busy or request_id != self.request_id:
            return False
        self.cancelled.append(request_id)
        return True

    def force_stop(self, request_id: UUID) -> bool:
        if not self.is_busy or request_id != self.request_id:
            return False
        self.force_stopped.append(request_id)
        return True

    def shutdown(self) -> None:
        assert not self.is_busy

    def emit_event(self, event_type: EventType, payload: dict[str, object]) -> None:
        assert self.request_id is not None
        self.event_received.emit(
            WorkerEvent(
                request_id=self.request_id,
                type=event_type,
                payload=payload,
            )
        )

    def finish(
        self,
        *,
        terminal_type: EventType = "result",
        payload: dict[str, object] | None = None,
        force_stopped: bool = False,
    ) -> None:
        assert self.request_id is not None
        assert self.request_type is not None
        terminal = WorkerEvent(
            request_id=self.request_id,
            type=terminal_type,
            payload=dict(payload or {}),
        )
        outcome = TransportOutcome(
            request_id=self.request_id,
            request_type=self.request_type,
            terminal_event=terminal,
            client_failure=None,
            stderr="",
            exit_code=0 if not force_stopped else 9,
            exit_status="normal" if not force_stopped else "crash",
            force_stopped=force_stopped,
        )
        self.is_busy = False
        self.request_id = None
        self.request_type = None
        self.transport_finished.emit(outcome)


class StubConfigController(QObject):
    state_changed = Signal()

    def __init__(self, snapshot: SavedConfigSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.snapshot_issue: str | None = None
        self.dirty = False
        self.document = SimpleNamespace(
            source_path=snapshot.path,
            source_sha256=snapshot.sha256,
            workspace_owned=True,
        )

    def execution_snapshot(self) -> SavedConfigSnapshot:
        if self.snapshot_issue is not None:
            raise ConfigDocumentError(self.snapshot_issue)
        return self.snapshot

    def get_dirty(self) -> bool:
        return self.dirty


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def controller_for(
    tmp_path: Path,
) -> tuple[
    DatasetExecutionController,
    StubConfigController,
    DesktopRequestCoordinator,
    StubTransport,
    Workspace,
]:
    workspace = initialize_workspace(tmp_path / "workspace")
    config_path = workspace.configs / "dataset.yaml"
    content = b"schema_version: 2\n"
    config_path.write_bytes(content)
    snapshot = SavedConfigSnapshot(
        config_path.resolve(),
        content,
        hashlib.sha256(content).hexdigest(),
    )
    config = StubConfigController(snapshot)
    transport = StubTransport()
    coordinator = DesktopRequestCoordinator(cast(WorkerClient, transport))
    controller = DatasetExecutionController(
        coordinator,
        cast(DatasetConfigController, config),
    )
    controller.set_workspace(workspace)
    return controller, config, coordinator, transport, workspace


def test_generation_reserves_persists_then_starts_with_the_same_request_id(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, _config, coordinator, transport, workspace = controller_for(tmp_path)
    store = cast(JobStore, controller._activity_store)
    original_start = store.start
    order: list[str] = []

    def record_start(**kwargs: object) -> dict[str, object]:
        order.append("persist")
        assert not coordinator.is_busy
        assert transport.started == []
        return original_start(**kwargs)

    monkeypatch.setattr(store, "start", record_start)
    original_transport_start = transport.start_request

    def start_transport(
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        order.append("worker")
        record_path = store.directory / f"{request_id}.json"
        assert record_path.is_file()
        original_transport_start(request_id, request_type, payload)

    monkeypatch.setattr(transport, "start_request", start_transport)

    assert controller.generate()

    assert order == ["persist", "worker"]
    assert controller.get_state() == "starting"
    assert controller.get_activity_record_available()
    assert controller.get_activity_persistence_issue() == ""
    [(request_id, request_type, payload)] = transport.started
    assert request_type == "generate_dataset"
    assert payload == {
        "config_path": str(controller.snapshot.path),
        "expected_config_sha256": controller.snapshot.sha256,
        "output_root": str(workspace.outputs),
        "figures_root": str(workspace.figures),
    }
    [loaded] = store.load()
    assert loaded.data is not None
    assert loaded.data["request_id"] == str(request_id)
    assert loaded.data["status"] == "running"


def test_live_progress_is_immediate_but_activity_writes_are_coalesced(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, _config, _coordinator, transport, _workspace = controller_for(tmp_path)
    assert controller.generate()
    store = cast(JobStore, controller._activity_store)
    writes: list[tuple[str, dict[str, object]]] = []
    original_update = store.update_event

    def update(
        record: dict[str, object],
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        writes.append((event_type, dict(payload)))
        original_update(cast(dict[str, object], record), event_type, payload)

    monkeypatch.setattr(store, "update_event", update)
    transport.emit_event("phase", {"name": "generation", "cancellable": True})
    transport.emit_event("progress", {"completed": 1, "total": 10})
    transport.emit_event("progress", {"completed": 7, "total": 10})

    assert controller.get_completed_rows() == 7
    assert controller.get_total_rows() == 10
    assert controller._progress_write_timer.interval() == 250
    assert writes == [("phase", {"name": "generation", "cancellable": True})]

    controller._flush_progress_record()

    assert writes[-1] == ("progress", {"completed": 7, "total": 10})
    [loaded] = store.load()
    assert loaded.data is not None
    assert loaded.data["progress"] == {"completed": 7, "total": 10}


def test_success_preserves_saved_baseline_identity_across_unsaved_edits(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, config, _coordinator, transport, workspace = controller_for(tmp_path)
    assert controller.generate()
    run = workspace.outputs / "run"
    transport.finish(
        payload={
            "run_id": "run-id",
            "run_status": "completed",
            "row_count": 10,
            "valid_row_count": 9,
            "invalid_row_count": 1,
            "output_directory": str(run),
            "spec_id": "spec",
            "generation_context_id": "context",
            "output_request_id": "output",
            "visualization": {"status": "completed"},
        }
    )

    assert controller.get_state() == "succeeded"
    assert controller.get_result_matches_current_saved_baseline()
    assert controller.get_result_relation_issue() == ""
    assert controller.get_result_output_directory() == str(run)
    assert controller.get_result_row_count() == 10
    [loaded] = cast(JobStore, controller._activity_store).load()
    assert loaded.data is not None
    assert loaded.data["status"] == "completed"
    assert loaded.data["summary"]["run_id"] == "run-id"

    config.dirty = True
    config.snapshot_issue = "save the current configuration changes before execution"
    config.state_changed.emit()

    assert not controller.get_snapshot_available()
    assert controller.get_current_draft_dirty()
    assert controller.get_result_matches_current_saved_baseline()
    assert controller.get_result_relation_issue() == (
        "Generated from the current saved configuration; unsaved draft changes now exist."
    )

    config.snapshot.path.write_bytes(b"externally changed\n")

    assert not controller.get_result_matches_current_saved_baseline()
    assert "outside Carnopy" in controller.get_result_relation_issue()


def test_initial_record_failure_starts_no_worker_and_releases_reservation(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, _config, coordinator, transport, _workspace = controller_for(tmp_path)
    store = cast(JobStore, controller._activity_store)
    monkeypatch.setattr(
        store,
        "start",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    assert not controller.generate()

    assert transport.started == []
    assert not coordinator.is_busy
    assert controller.get_state() == "failed"
    assert controller.get_failure_code() == "activity_persistence_failed"
    assert not controller.get_activity_record_available()
    assert "disk unavailable" in controller.get_activity_persistence_issue()
    reservation = coordinator.reserve_request("execution", "validate_config")
    coordinator.abandon_reserved_request(reservation)


def test_worker_start_failure_is_written_to_the_reserved_record(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, _config, coordinator, transport, _workspace = controller_for(tmp_path)
    transport.raise_on_start = True

    assert not controller.validate()

    assert not coordinator.is_busy
    assert controller.get_state() == "failed"
    assert controller.get_failure_code() == "worker_start_failed"
    assert controller.get_activity_record_available()
    [loaded] = cast(JobStore, controller._activity_store).load()
    assert loaded.data is not None
    assert loaded.data["status"] == "failed"
    assert loaded.data["summary"]["code"] == "worker_start_failed"
    reservation = coordinator.reserve_request("execution", "validate_config")
    coordinator.abandon_reserved_request(reservation)


def test_terminal_persistence_failure_does_not_change_worker_success(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, _config, _coordinator, transport, _workspace = controller_for(tmp_path)
    assert controller.validate()
    store = cast(JobStore, controller._activity_store)
    monkeypatch.setattr(
        store,
        "write",
        lambda _record: (_ for _ in ()).throw(OSError("terminal disk failure")),
    )

    transport.finish(
        payload={"mode": "property_table", "projected_rows": 4, "backend_model": "heos"}
    )

    assert controller.get_state() == "succeeded"
    assert controller.get_result_projected_rows() == 4
    assert "after one retry" in controller.get_activity_persistence_issue()


def test_invalid_config_is_distinct_from_operational_failure(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    controller, _config, _coordinator, transport, _workspace = controller_for(tmp_path)
    assert controller.validate()

    transport.finish(
        terminal_type="error",
        payload={
            "category": "config",
            "code": "invalid_config",
            "message": "configuration is invalid",
        },
    )

    assert controller.get_state() == "invalid"
    assert controller.get_failure_category() == "config"
    assert controller.get_failure_code() == "invalid_config"
