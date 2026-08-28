from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
)


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
            raise RuntimeError("simulated start failure")
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

    def emit_event(self, event_type: str, payload: dict[str, object] | None = None) -> None:
        assert self.request_id is not None
        self.event_received.emit(
            WorkerEvent(
                request_id=self.request_id,
                type=cast(EventType, event_type),
                payload=dict(payload or {}),
            )
        )

    def finish(
        self,
        *,
        terminal_type: str | None = "result",
        payload: dict[str, object] | None = None,
        client_failure: dict[str, object] | None = None,
        exit_code: int = 0,
        exit_status: str = "normal",
        force_stopped: bool = False,
    ) -> None:
        assert self.request_id is not None
        assert self.request_type is not None
        terminal = (
            None
            if terminal_type is None
            else WorkerEvent(
                request_id=self.request_id,
                type=cast(EventType, terminal_type),
                payload=dict(payload or {}),
            )
        )
        outcome = TransportOutcome(
            request_id=self.request_id,
            request_type=self.request_type,
            terminal_event=terminal,
            client_failure=client_failure,
            stderr="worker stderr\n",
            exit_code=exit_code,
            exit_status=exit_status,
            force_stopped=force_stopped,
        )
        self.is_busy = False
        self.request_id = None
        self.request_type = None
        self.transport_finished.emit(outcome)


@dataclass
class RecordingFinalizer:
    cleanup_error: str | None = None
    calls: int = 0
    successful: bool | None = None

    def finish(self, successful: bool) -> str | None:
        self.calls += 1
        self.successful = successful
        return self.cleanup_error


class CompletionReceiver(QObject):
    def __init__(self, calls: list[RequestOutcome]) -> None:
        super().__init__()
        self.calls = calls

    def receive(self, outcome: RequestOutcome) -> None:
        self.calls.append(outcome)


@pytest.fixture(scope="module")
def application() -> Iterator[QCoreApplication]:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app


def coordinator_for(transport: StubTransport) -> DesktopRequestCoordinator:
    return DesktopRequestCoordinator(cast(WorkerClient, transport))


def test_coordinator_routes_events_only_to_the_owner_and_preserves_envelope(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    session = coordinator.start_request(
        "configuration",
        "describe_capabilities",
        {"model": "heos"},
    )
    events: list[WorkerEvent] = []
    completed: list[RequestOutcome] = []
    busy_during_completion: list[bool] = []
    session.event_received.connect(events.append)
    session.completed.connect(completed.append)
    session.completed.connect(lambda _outcome: busy_during_completion.append(coordinator.is_busy))

    with pytest.raises(RuntimeError, match="already active"):
        coordinator.start_request("inspection", "inspect_source", {"source_path": "source"})
    transport.event_received.emit(WorkerEvent(request_id=uuid4(), type="accepted"))
    assert events == []
    transport.emit_event("accepted", {"request_type": "describe_capabilities"})
    transport.emit_event("phase", {"name": "capabilities", "cancellable": False})
    transport.finish(payload={"model": "heos"})

    assert [event.type for event in events] == ["accepted", "phase"]
    assert len(completed) == 1
    outcome = completed[0]
    assert outcome.result_payload == {"model": "heos"}
    assert busy_during_completion == [True]
    assert not coordinator.is_busy
    assert coordinator.active_owner is None
    assert set(outcome.terminal_envelope) == {
        "request_id",
        "request_type",
        "terminal_event",
        "client_failure",
        "stderr",
        "exit_code",
        "exit_status",
        "force_stopped",
        "cleanup_error",
    }
    assert not session.cancel()
    assert not session.force_stop()


def test_configuration_owner_admits_only_its_generic_requests(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)

    for request_type in ("load_configuration", "validate_configuration"):
        session = coordinator.start_request("configuration", request_type, {})
        assert session.request_type == request_type
        assert transport.started[-1][1] == request_type
        transport.finish(payload={})

    with pytest.raises(ValueError, match="not owned by 'sweep'"):
        coordinator.start_request("sweep", "load_configuration", {})


def test_scene_owner_admits_exact_pick_resolution(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)

    session = coordinator.start_request("scene", "resolve_scene_pick", {"point": 4})

    assert session.owner == "scene"
    assert session.request_type == "resolve_scene_pick"
    transport.finish(payload={})


def test_reservation_is_nonbusy_blocks_reentry_and_preserves_uuid(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    busy: list[bool] = []
    coordinator.busy_changed.connect(busy.append)

    reservation = coordinator.reserve_request("execution", "generate_dataset")

    assert not coordinator.is_busy
    assert coordinator.active_owner is None
    assert busy == []
    with pytest.raises(RuntimeError, match="already active"):
        coordinator.reserve_request("execution", "validate_config")
    with pytest.raises(RuntimeError, match="already active"):
        coordinator.start_request("inspection", "inspect_source", {})

    session = coordinator.start_reserved_request(reservation, {"value": 1})

    assert session.request_id == reservation.request_id
    assert transport.started == [(reservation.request_id, "generate_dataset", {"value": 1})]
    assert coordinator.is_busy
    assert busy == [True]
    transport.finish(payload={})


def test_abandoned_and_foreign_reservations_never_start_transport(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    reservation = coordinator.reserve_request("execution", "validate_config")
    coordinator.abandon_reserved_request(reservation)

    assert not coordinator.is_busy
    assert transport.started == []
    with pytest.raises(RuntimeError, match="stale or foreign"):
        coordinator.start_reserved_request(reservation, {})

    replacement = coordinator.reserve_request("execution", "validate_config")
    coordinator.abandon_reserved_request(reservation)
    session = coordinator.start_reserved_request(replacement, {})
    transport.finish(payload={})
    assert session.request_id == replacement.request_id


def test_execution_cancel_policy_rejects_foreign_and_stale_sessions(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    session = coordinator.start_request("execution", "generate_dataset", {})

    assert not session.cooperative_cancel_available
    transport.emit_event("phase", {"name": "generation", "cancellable": True})
    assert session.cooperative_cancel_available
    assert not session.force_stop_available
    assert not coordinator.request_cancel(session.request_id, "plot")
    assert not coordinator.request_cancel(uuid4(), "execution")
    assert session.cancel()
    assert transport.cancelled == [session.request_id]
    assert not session.cooperative_cancel_available
    assert coordinator._force_timer.interval() == 5_000
    assert not session.force_stop_available

    coordinator._enable_delayed_force_stop()
    assert session.force_stop_available
    assert not coordinator.force_stop(session.request_id, "plot")
    assert session.force_stop()
    assert transport.force_stopped == [session.request_id]
    assert not session.force_stop_available
    transport.finish(
        terminal_type=None,
        client_failure={
            "category": "process",
            "code": "force_stopped",
            "message": "worker process was force-stopped",
        },
        exit_code=9,
        exit_status="crash",
        force_stopped=True,
    )

    assert session.outcome is not None
    assert session.outcome.failure_payload is not None
    assert session.outcome.failure_payload["code"] == "force_stopped"
    assert not session.cancel()
    assert not session.force_stop()


def test_protected_finalization_is_sticky_and_cancels_delayed_force_stop(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    session = coordinator.start_request("sweep", "execute_sweep", {})
    transport.emit_event("accepted")
    transport.emit_event("phase", {"name": "models", "cancellable": True})

    assert session.cancel()
    assert coordinator._force_timer.isActive()
    transport.emit_event(
        "phase",
        {
            "name": "finalization",
            "cancellable": False,
            "termination_protected": True,
        },
    )

    assert not coordinator._force_timer.isActive()
    assert not session.cooperative_cancel_available
    assert not session.force_stop_available
    assert not session.cancel()
    assert not session.force_stop()
    coordinator._enable_delayed_force_stop()
    assert not session.force_stop_available
    transport.emit_event("phase", {"name": "late", "cancellable": True})
    assert not session.cooperative_cancel_available
    assert not session.force_stop_available
    transport.finish(payload={"output_directory": "/tmp/final"})


def test_plot_force_stop_is_immediate_and_configuration_cannot_cancel(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    plot = coordinator.start_request("plot", "render_plot", {})

    assert not plot.cooperative_cancel_available
    assert plot.force_stop_available
    transport.finish(payload={})

    configuration = coordinator.start_request(
        "configuration",
        "validate_dataset_config",
        {},
    )
    assert not configuration.cooperative_cancel_available
    assert not configuration.force_stop_available
    assert not configuration.cancel()
    assert not configuration.force_stop()
    transport.finish(payload={})


def test_cleanup_finishes_once_before_owner_completion_and_busy_clear(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    finalizer = RecordingFinalizer(cleanup_error="simulated cleanup warning")
    session = coordinator.start_request(
        "plot",
        "render_plot",
        {},
        finalizer=finalizer,
    )
    observations: list[tuple[int, bool, str | None]] = []

    def completed(outcome: RequestOutcome) -> None:
        observations.append((finalizer.calls, coordinator.is_busy, outcome.cleanup_error))

    session.completed.connect(completed)
    transport.finish(payload={"image_path": "figure.png"})

    assert finalizer.calls == 1
    assert finalizer.successful is True
    assert observations == [(1, True, "simulated cleanup warning")]
    assert session.outcome is not None
    assert session.outcome.terminal_envelope["cleanup_error"] == "simulated cleanup warning"
    assert str(session.outcome.terminal_envelope["stderr"]).endswith("simulated cleanup warning\n")
    assert not coordinator.is_busy


def test_start_failure_cleans_registered_export_and_clears_busy_state(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    transport.raise_on_start = True
    coordinator = coordinator_for(transport)
    finalizer = RecordingFinalizer()
    busy: list[bool] = []
    coordinator.busy_changed.connect(busy.append)

    with pytest.raises(RuntimeError, match="simulated start failure"):
        coordinator.start_request("plot", "render_plot", {}, finalizer=finalizer)

    assert finalizer.calls == 1
    assert finalizer.successful is False
    assert busy == [True, False]
    assert not coordinator.is_busy


def test_destroyed_owner_drops_delivery_but_still_finalizes_and_clears_busy(
    application: QCoreApplication,
) -> None:
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    finalizer = RecordingFinalizer()
    session = coordinator.start_request(
        "plot",
        "render_plot",
        {},
        finalizer=finalizer,
    )
    calls: list[RequestOutcome] = []
    receiver = CompletionReceiver(calls)
    session.completed.connect(receiver.receive)
    receiver.deleteLater()
    QCoreApplication.sendPostedEvents(receiver, QEvent.Type.DeferredDelete)
    application.processEvents()

    transport.finish(payload={"image_path": "figure.png"})

    assert calls == []
    assert finalizer.calls == 1
    assert not coordinator.is_busy


def test_missing_terminal_event_becomes_owner_failure(
    application: QCoreApplication,
) -> None:
    del application
    transport = StubTransport()
    coordinator = coordinator_for(transport)
    session = coordinator.start_request("inspection", "inspect_source", {})
    completed: list[RequestOutcome] = []
    session.completed.connect(completed.append)

    transport.finish(
        terminal_type=None,
        client_failure={
            "category": "process",
            "code": "missing_terminal_event",
            "message": "worker exited without a terminal event",
        },
        exit_code=1,
    )

    assert completed[0].failure_payload is not None
    assert completed[0].failure_payload["code"] == "missing_terminal_event"
