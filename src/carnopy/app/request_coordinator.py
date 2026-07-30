from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.protocol import ErrorCategory, RequestType, WorkerErrorPayload, WorkerEvent

RequestOwner = Literal["configuration", "execution", "inspection", "plot"]
RequestState = Literal[
    "starting",
    "running",
    "cancellation_requested",
    "force_stopping",
    "finishing",
    "completed",
]
CancellationMode = Literal["none", "cooperative", "force_only"]

_OWNER_REQUESTS: dict[RequestOwner, frozenset[RequestType]] = {
    "configuration": frozenset(
        {"describe_capabilities", "load_dataset_config", "validate_dataset_config"}
    ),
    "execution": frozenset({"validate_config", "generate_dataset"}),
    "inspection": frozenset({"inspect_source", "preview_table"}),
    "plot": frozenset({"render_plot"}),
}


class RequestFinalizer(Protocol):
    def finish(self, successful: bool) -> str | None: ...


@dataclass(frozen=True)
class RequestReservation:
    """A non-busy request identity reserved before durable workflow setup."""

    request_id: UUID
    request_type: RequestType
    owner: RequestOwner


@dataclass(frozen=True)
class RequestOutcome:
    request_id: UUID
    request_type: RequestType
    owner: RequestOwner
    terminal_event: WorkerEvent | None
    client_failure: dict[str, object] | None
    stderr: str
    exit_code: int | None
    exit_status: str
    force_stopped: bool
    cleanup_error: str | None
    terminal_envelope: dict[str, object]

    @property
    def successful(self) -> bool:
        return (
            self.client_failure is None
            and self.terminal_event is not None
            and self.terminal_event.type == "result"
            and self.exit_code == 0
            and self.exit_status == "normal"
            and not self.force_stopped
        )

    @property
    def result_payload(self) -> dict[str, object] | None:
        if not self.successful or self.terminal_event is None:
            return None
        return dict(self.terminal_event.payload)

    @property
    def failure_payload(self) -> dict[str, object] | None:
        if self.client_failure is not None:
            return dict(self.client_failure)
        terminal = self.terminal_event
        if terminal is None:
            return _request_error(
                "process",
                "missing_terminal_event",
                "worker request completed without a terminal event",
            )
        if terminal.type == "error":
            return dict(terminal.payload)
        if terminal.type == "cancelled":
            return _request_error(
                "execution",
                str(terminal.payload.get("code", "cancelled")),
                str(terminal.payload.get("message", "worker request was cancelled")),
            )
        if not self.successful:
            return _request_error(
                "process",
                "execution_failed",
                f"worker exited with status {self.exit_status} and code {self.exit_code}",
            )
        return None


class RequestSession(QObject):
    """Owner-scoped observable state for one desktop worker request."""

    event_received = Signal(object)
    phase_changed = Signal(str, bool)
    progress_received = Signal(object)
    policy_changed = Signal()
    state_changed = Signal(str)
    stderr_received = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        request_id: UUID,
        request_type: RequestType,
        owner: RequestOwner,
        cancellation_mode: CancellationMode,
    ) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._request_id = request_id
        self._request_type = request_type
        self._owner = owner
        self._cancellation_mode = cancellation_mode
        self._state: RequestState = "starting"
        self._phase: str | None = None
        self._worker_cancellable = False
        self._force_stop_available = cancellation_mode == "force_only"
        self._terminal_seen = False
        self._outcome: RequestOutcome | None = None

    @property
    def request_id(self) -> UUID:
        return self._request_id

    @property
    def request_type(self) -> RequestType:
        return self._request_type

    @property
    def owner(self) -> RequestOwner:
        return self._owner

    @property
    def phase(self) -> str | None:
        return self._phase

    @property
    def state(self) -> RequestState:
        return self._state

    @property
    def cooperative_cancel_available(self) -> bool:
        return (
            self._cancellation_mode == "cooperative"
            and self._worker_cancellable
            and self._state in {"starting", "running"}
            and not self._terminal_seen
        )

    @property
    def force_stop_available(self) -> bool:
        return self._force_stop_available and not self._terminal_seen

    @property
    def outcome(self) -> RequestOutcome | None:
        return self._outcome

    def cancel(self) -> bool:
        return self._coordinator.request_cancel(self._request_id, self._owner)

    def force_stop(self) -> bool:
        return self._coordinator.force_stop(self._request_id, self._owner)

    def _accept_event(self, event: WorkerEvent) -> None:
        if event.type == "accepted":
            self._set_state("running")
        elif event.type == "phase":
            self._phase = str(event.payload.get("name", "unknown"))
            self._worker_cancellable = bool(event.payload.get("cancellable", False))
            self.phase_changed.emit(self._phase, self._worker_cancellable)
            self.policy_changed.emit()
        elif event.type == "progress":
            self.progress_received.emit(event.payload)
        elif event.type in {"result", "error", "cancelled"}:
            self._terminal_seen = True
            self._worker_cancellable = False
            self._force_stop_available = False
            self._set_state("finishing")
            self.policy_changed.emit()
        self.event_received.emit(event)

    def _mark_cancel_requested(self) -> None:
        self._worker_cancellable = False
        self._set_state("cancellation_requested")
        self.policy_changed.emit()

    def _enable_force_stop(self) -> None:
        if self._state == "cancellation_requested" and not self._terminal_seen:
            self._force_stop_available = True
            self.policy_changed.emit()

    def _mark_force_stopping(self) -> None:
        self._force_stop_available = False
        self._set_state("force_stopping")
        self.policy_changed.emit()

    def _complete(self, outcome: RequestOutcome) -> None:
        self._outcome = outcome
        self._worker_cancellable = False
        self._force_stop_available = False
        self._set_state("completed")
        self.policy_changed.emit()
        self.completed.emit(outcome)

    def _set_state(self, state: RequestState) -> None:
        if self._state == state:
            return
        self._state = state
        self.state_changed.emit(state)


class DesktopRequestCoordinator(QObject):
    """Own one global desktop request and route it to one owner session."""

    busy_changed = Signal(bool)
    active_owner_changed = Signal(object)

    def __init__(self, client: WorkerClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self._active_session: RequestSession | None = None
        self._reservation: RequestReservation | None = None
        self._finalizer: RequestFinalizer | None = None
        self._force_timer = QTimer(self)
        self._force_timer.setSingleShot(True)
        self._force_timer.setInterval(5_000)
        self._force_timer.timeout.connect(self._enable_delayed_force_stop)
        client.event_received.connect(self._event_received)
        client.stderr_received.connect(self._stderr_received)
        client.transport_finished.connect(self._transport_finished)

    @property
    def is_busy(self) -> bool:
        return self._active_session is not None

    @property
    def active_session(self) -> RequestSession | None:
        return self._active_session

    @property
    def active_owner(self) -> RequestOwner | None:
        session = self._active_session
        return None if session is None else session.owner

    def start_request(
        self,
        owner: RequestOwner,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
        *,
        finalizer: RequestFinalizer | None = None,
    ) -> RequestSession:
        reservation = self.reserve_request(owner, request_type)
        try:
            return self.start_reserved_request(
                reservation,
                payload,
                finalizer=finalizer,
            )
        except Exception:
            self.abandon_reserved_request(reservation)
            raise

    def reserve_request(
        self,
        owner: RequestOwner,
        request_type: RequestType,
    ) -> RequestReservation:
        """Reserve one request UUID without publishing a busy session."""

        if self.is_busy or self._reservation is not None:
            raise RuntimeError("a Carnopy desktop request is already active")
        if request_type not in _OWNER_REQUESTS[owner]:
            raise ValueError(f"request type {request_type!r} is not owned by {owner!r}")
        reservation = RequestReservation(
            request_id=uuid4(),
            request_type=request_type,
            owner=owner,
        )
        self._reservation = reservation
        return reservation

    def start_reserved_request(
        self,
        reservation: RequestReservation,
        payload: Mapping[str, object] | None = None,
        *,
        finalizer: RequestFinalizer | None = None,
    ) -> RequestSession:
        """Promote the exact current reservation and start its worker."""

        if reservation is not self._reservation:
            raise RuntimeError("request reservation is stale or foreign")
        request_type = reservation.request_type
        owner = reservation.owner
        if finalizer is not None and request_type != "render_plot":
            raise ValueError("parent export finalizers are supported only for render_plot")

        cancellation_mode: CancellationMode
        if owner == "execution":
            cancellation_mode = "cooperative"
        elif owner == "plot":
            cancellation_mode = "force_only"
        else:
            cancellation_mode = "none"
        session = RequestSession(
            self,
            reservation.request_id,
            request_type,
            owner,
            cancellation_mode,
        )
        self._active_session = session
        self._finalizer = finalizer
        self.busy_changed.emit(True)
        self.active_owner_changed.emit(owner)
        try:
            self.client.start_request(session.request_id, request_type, payload)
        except Exception:
            if finalizer is not None:
                finalizer.finish(False)
            self._active_session = None
            self._finalizer = None
            self.busy_changed.emit(False)
            self.active_owner_changed.emit(None)
            raise
        self._reservation = None
        return session

    def abandon_reserved_request(self, reservation: RequestReservation) -> None:
        """Release the exact current reservation without starting a worker."""

        if reservation is self._reservation:
            self._reservation = None

    def request_cancel(self, request_id: UUID, owner: RequestOwner) -> bool:
        session = self._matching_session(request_id, owner)
        if session is None or not session.cooperative_cancel_available:
            return False
        if not self.client.send_cancel(request_id):
            return False
        session._mark_cancel_requested()
        self._force_timer.start()
        return True

    def force_stop(self, request_id: UUID, owner: RequestOwner) -> bool:
        session = self._matching_session(request_id, owner)
        if session is None or not session.force_stop_available:
            return False
        if not self.client.force_stop(request_id):
            return False
        self._force_timer.stop()
        session._mark_force_stopping()
        return True

    def shutdown(self) -> None:
        if self.is_busy or self._reservation is not None:
            raise RuntimeError("cannot shut down the request coordinator while it is busy")
        self.client.shutdown()

    def _matching_session(
        self,
        request_id: UUID,
        owner: RequestOwner,
    ) -> RequestSession | None:
        session = self._active_session
        if session is None or session.request_id != request_id or session.owner != owner:
            return None
        return session

    def _event_received(self, value: object) -> None:
        event = value if isinstance(value, WorkerEvent) else None
        session = self._active_session
        if event is None or session is None or event.request_id != session.request_id:
            return
        session._accept_event(event)

    def _stderr_received(self, text: str) -> None:
        session = self._active_session
        if session is not None:
            session.stderr_received.emit(text)

    def _enable_delayed_force_stop(self) -> None:
        session = self._active_session
        if session is not None and session.owner == "execution":
            session._enable_force_stop()

    def _transport_finished(self, value: object) -> None:
        transport = value if isinstance(value, TransportOutcome) else None
        session = self._active_session
        if transport is None or session is None or transport.request_id != session.request_id:
            return
        self._force_timer.stop()
        finalizer, self._finalizer = self._finalizer, None
        cleanup_error = None if finalizer is None else finalizer.finish(transport.successful)
        stderr = transport.stderr
        if cleanup_error is not None:
            cleanup_line = cleanup_error + "\n"
            stderr += cleanup_line
            session.stderr_received.emit(cleanup_line)
        envelope: dict[str, object] = {
            "request_id": str(transport.request_id),
            "request_type": transport.request_type,
            "terminal_event": (
                None
                if transport.terminal_event is None
                else transport.terminal_event.model_dump(mode="json")
            ),
            "client_failure": transport.client_failure,
            "stderr": stderr,
            "exit_code": transport.exit_code,
            "exit_status": transport.exit_status,
            "force_stopped": transport.force_stopped,
            "cleanup_error": cleanup_error,
        }
        outcome = RequestOutcome(
            request_id=transport.request_id,
            request_type=transport.request_type,
            owner=session.owner,
            terminal_event=transport.terminal_event,
            client_failure=transport.client_failure,
            stderr=stderr,
            exit_code=transport.exit_code,
            exit_status=transport.exit_status,
            force_stopped=transport.force_stopped,
            cleanup_error=cleanup_error,
            terminal_envelope=envelope,
        )
        session._complete(outcome)
        self._active_session = None
        self.busy_changed.emit(False)
        self.active_owner_changed.emit(None)


def _request_error(category: ErrorCategory, code: str, message: str) -> dict[str, object]:
    return WorkerErrorPayload(
        category=category,
        code=code,
        message=message,
    ).model_dump(exclude_none=True)
