from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from carnopy.app.config_controller import ConfigurationController
from carnopy.app.config_document import (
    ConfigDocumentError,
    SavedConfigSnapshot,
    source_matches,
)
from carnopy.app.jobs import JobStore
from carnopy.app.protocol import RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestReservation,
    RequestSession,
)
from carnopy.app.workspace import Workspace

_PROGRESS_WRITE_INTERVAL_MS = 250


class DatasetExecutionController(QObject):
    """Own exact saved-config validation, generation, and Run activity writes."""

    state_changed = Signal()
    run_finalized = Signal(object)
    activity_record_changed = Signal()

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        config_controller: ConfigurationController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.config_controller = config_controller
        self.workspace: Workspace | None = None
        self.snapshot: SavedConfigSnapshot | None = None
        self._snapshot_issue = "Open a workspace first."
        self._session: RequestSession | None = None
        self._active_snapshot: SavedConfigSnapshot | None = None
        self._active_workspace_root: Path | None = None
        self._operation = ""
        self._state = "unavailable"
        self._phase = ""
        self._completed_rows = 0
        self._total_rows = 0
        self._failure_category = ""
        self._failure_code = ""
        self._failure_message = ""
        self._result_request_id = ""
        self._result_run_id = ""
        self._result_run_status = ""
        self._result_output_directory = ""
        self._result_row_count = 0
        self._result_valid_row_count = 0
        self._result_invalid_row_count = 0
        self._result_spec_id = ""
        self._result_generation_context_id = ""
        self._result_output_request_id = ""
        self._result_visualization_status = ""
        self._result_mode = ""
        self._result_projected_rows = 0
        self._result_backend_model = ""
        self._result_configuration_path: Path | None = None
        self._result_configuration_sha256 = ""
        self._result_workspace_root: Path | None = None
        self._activity_store: JobStore | None = None
        self._active_record: dict[str, Any] | None = None
        self._activity_record_available = False
        self._activity_persistence_issue = ""
        self._pending_progress: dict[str, Any] | None = None
        self._progress_write_timer = QTimer(self)
        self._progress_write_timer.setSingleShot(True)
        self._progress_write_timer.setInterval(_PROGRESS_WRITE_INTERVAL_MS)
        self._progress_write_timer.timeout.connect(self._flush_progress_record)

        self.config_controller.state_changed.connect(self.refresh_configuration)
        self.coordinator.busy_changed.connect(self._coordinator_busy_changed)

    def get_snapshot_available(self) -> bool:
        return self.snapshot is not None

    snapshotAvailable = Property(bool, get_snapshot_available, notify=state_changed)

    def get_snapshot_path(self) -> str:
        return "" if self.snapshot is None else str(self.snapshot.path)

    snapshotPath = Property(str, get_snapshot_path, notify=state_changed)

    def get_snapshot_sha256(self) -> str:
        return "" if self.snapshot is None else self.snapshot.sha256

    snapshotSha256 = Property(str, get_snapshot_sha256, notify=state_changed)

    def get_snapshot_issue(self) -> str:
        return self._snapshot_issue

    snapshotIssue = Property(str, get_snapshot_issue, notify=state_changed)

    def get_operation(self) -> str:
        return self._operation

    operation = Property(str, get_operation, notify=state_changed)

    def get_state(self) -> str:
        return self._state

    state = Property(str, get_state, notify=state_changed)

    def get_phase(self) -> str:
        return self._phase

    phase = Property(str, get_phase, notify=state_changed)

    def get_phase_cancellable(self) -> bool:
        session = self._session
        return session is not None and session.cooperative_cancel_available

    phaseCancellable = Property(bool, get_phase_cancellable, notify=state_changed)

    def get_completed_rows(self) -> int:
        return self._completed_rows

    completedRows = Property(int, get_completed_rows, notify=state_changed)

    def get_total_rows(self) -> int:
        return self._total_rows

    totalRows = Property(int, get_total_rows, notify=state_changed)

    def get_can_validate(self) -> bool:
        return self._can_start()

    canValidate = Property(bool, get_can_validate, notify=state_changed)

    def get_can_generate(self) -> bool:
        return self._can_start()

    canGenerate = Property(bool, get_can_generate, notify=state_changed)

    def get_can_cancel(self) -> bool:
        session = self._session
        return session is not None and session.cooperative_cancel_available

    canCancel = Property(bool, get_can_cancel, notify=state_changed)

    def get_can_force_stop(self) -> bool:
        session = self._session
        return session is not None and session.force_stop_available

    canForceStop = Property(bool, get_can_force_stop, notify=state_changed)

    def get_result_configuration_path(self) -> str:
        path = self._result_configuration_path
        return "" if path is None else str(path)

    resultConfigurationPath = Property(
        str,
        get_result_configuration_path,
        notify=state_changed,
    )

    def get_result_configuration_sha256(self) -> str:
        return self._result_configuration_sha256

    resultConfigurationSha256 = Property(
        str,
        get_result_configuration_sha256,
        notify=state_changed,
    )

    def get_result_matches_current_saved_baseline(self) -> bool:
        matches, _issue = self._result_relation()
        return matches

    resultMatchesCurrentSavedBaseline = Property(
        bool,
        get_result_matches_current_saved_baseline,
        notify=state_changed,
    )

    def get_current_draft_dirty(self) -> bool:
        return self.config_controller.get_dirty()

    currentDraftDirty = Property(bool, get_current_draft_dirty, notify=state_changed)

    def get_result_relation_issue(self) -> str:
        _matches, issue = self._result_relation()
        return issue

    resultRelationIssue = Property(str, get_result_relation_issue, notify=state_changed)

    def get_failure_category(self) -> str:
        return self._failure_category

    failureCategory = Property(str, get_failure_category, notify=state_changed)

    def get_failure_code(self) -> str:
        return self._failure_code

    failureCode = Property(str, get_failure_code, notify=state_changed)

    def get_failure_message(self) -> str:
        return self._failure_message

    failureMessage = Property(str, get_failure_message, notify=state_changed)

    def get_activity_record_available(self) -> bool:
        return self._activity_record_available

    activityRecordAvailable = Property(
        bool,
        get_activity_record_available,
        notify=state_changed,
    )

    def get_activity_persistence_issue(self) -> str:
        return self._activity_persistence_issue

    activityPersistenceIssue = Property(
        str,
        get_activity_persistence_issue,
        notify=state_changed,
    )

    def get_result_request_id(self) -> str:
        return self._result_request_id

    resultRequestId = Property(str, get_result_request_id, notify=state_changed)

    def get_result_run_id(self) -> str:
        return self._result_run_id

    resultRunId = Property(str, get_result_run_id, notify=state_changed)

    def get_result_run_status(self) -> str:
        return self._result_run_status

    resultRunStatus = Property(str, get_result_run_status, notify=state_changed)

    def get_result_output_directory(self) -> str:
        return self._result_output_directory

    resultOutputDirectory = Property(
        str,
        get_result_output_directory,
        notify=state_changed,
    )

    def get_result_row_count(self) -> int:
        return self._result_row_count

    resultRowCount = Property(int, get_result_row_count, notify=state_changed)

    def get_result_valid_row_count(self) -> int:
        return self._result_valid_row_count

    resultValidRowCount = Property(int, get_result_valid_row_count, notify=state_changed)

    def get_result_invalid_row_count(self) -> int:
        return self._result_invalid_row_count

    resultInvalidRowCount = Property(
        int,
        get_result_invalid_row_count,
        notify=state_changed,
    )

    def get_result_spec_id(self) -> str:
        return self._result_spec_id

    resultSpecId = Property(str, get_result_spec_id, notify=state_changed)

    def get_result_generation_context_id(self) -> str:
        return self._result_generation_context_id

    resultGenerationContextId = Property(
        str,
        get_result_generation_context_id,
        notify=state_changed,
    )

    def get_result_output_request_id(self) -> str:
        return self._result_output_request_id

    resultOutputRequestId = Property(
        str,
        get_result_output_request_id,
        notify=state_changed,
    )

    def get_result_visualization_status(self) -> str:
        return self._result_visualization_status

    resultVisualizationStatus = Property(
        str,
        get_result_visualization_status,
        notify=state_changed,
    )

    def get_result_mode(self) -> str:
        return self._result_mode

    resultMode = Property(str, get_result_mode, notify=state_changed)

    def get_result_projected_rows(self) -> int:
        return self._result_projected_rows

    resultProjectedRows = Property(
        int,
        get_result_projected_rows,
        notify=state_changed,
    )

    def get_result_backend_model(self) -> str:
        return self._result_backend_model

    resultBackendModel = Property(str, get_result_backend_model, notify=state_changed)

    @property
    def owns_active_request(self) -> bool:
        return self._session is not None

    def set_workspace(self, workspace: Workspace | None) -> None:
        if self.workspace == workspace:
            self.refresh_configuration()
            return
        self.workspace = workspace
        self._activity_store = None if workspace is None else JobStore(workspace.private_directory)
        self._active_record = None
        self._activity_record_available = False
        self._set_persistence_issue("")
        self.refresh_configuration()

    @Slot(name="refreshConfiguration")
    def refresh_configuration(self) -> None:
        try:
            snapshot = self.config_controller.execution_snapshot(expected_document_type="dataset")
        except ConfigDocumentError as exc:
            self.snapshot = None
            self._snapshot_issue = str(exc)
        else:
            self.snapshot = snapshot
            self._snapshot_issue = ""
        if self._session is None and self._state in {"unavailable", "ready"}:
            self._state = "ready" if self.snapshot is not None else "unavailable"
        self.state_changed.emit()

    @Slot(result=bool)
    def validate(self) -> bool:
        return self._start("validate", "validate_config")

    @Slot(result=bool)
    def generate(self) -> bool:
        return self._start("generate", "generate_dataset")

    @Slot(result=bool)
    def cancel(self) -> bool:
        session = self._session
        if session is None or not session.cancel():
            return False
        self._state = "cancellation_requested"
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="forceStop")
    def force_stop(self) -> bool:
        session = self._session
        if session is None or not session.force_stop():
            return False
        self._state = "force_stopping"
        self.state_changed.emit()
        return True

    def _can_start(self) -> bool:
        return (
            self.snapshot is not None
            and self.workspace is not None
            and self._activity_store is not None
            and self._session is None
            and not self.coordinator.is_busy
        )

    def _start(self, operation: str, request_type: RequestType) -> bool:
        self.refresh_configuration()
        snapshot = self.snapshot
        workspace = self.workspace
        store = self._activity_store
        if (
            snapshot is None
            or workspace is None
            or store is None
            or self._session is not None
            or self.coordinator.is_busy
        ):
            return False
        self._reset_attempt(operation)
        reservation: RequestReservation
        try:
            reservation = self.coordinator.reserve_request("execution", request_type)
        except (RuntimeError, ValueError) as exc:
            self._set_start_failure("request", "request_unavailable", str(exc))
            return False
        try:
            relative = snapshot.path.relative_to(workspace.root).as_posix()
            record = store.start(
                request_id=str(reservation.request_id),
                operation=operation,
                config_relative_path=relative,
                yaml_snapshot=snapshot.yaml_bytes.decode("utf-8"),
                config_sha256=snapshot.sha256,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            self.coordinator.abandon_reserved_request(reservation)
            message = f"could not persist the initial Run activity record: {exc}"
            self._set_persistence_issue(message)
            self._set_start_failure(
                "process",
                "activity_persistence_failed",
                message,
            )
            return False

        self._active_record = record
        self._activity_record_available = True
        self._active_snapshot = snapshot
        self._active_workspace_root = workspace.root
        payload: dict[str, object] = {
            "config_path": str(snapshot.path),
            "expected_config_sha256": snapshot.sha256,
        }
        if request_type == "generate_dataset":
            payload.update(
                {
                    "output_root": str(workspace.outputs),
                    "figures_root": str(workspace.figures),
                }
            )
        try:
            session = self.coordinator.start_reserved_request(reservation, payload)
        except Exception as exc:
            self._persist_start_failure(store, record, reservation, exc)
            self.coordinator.abandon_reserved_request(reservation)
            self._set_start_failure("process", "worker_start_failed", str(exc))
            return False

        self._session = session
        session.event_received.connect(self._event_received)
        session.state_changed.connect(self._session_state_changed)
        session.policy_changed.connect(self.state_changed)
        session.completed.connect(self._request_completed)
        self.activity_record_changed.emit()
        self.state_changed.emit()
        return True

    def _reset_attempt(self, operation: str) -> None:
        self._progress_write_timer.stop()
        self._pending_progress = None
        self._operation = operation
        self._state = "starting"
        self._phase = ""
        self._completed_rows = 0
        self._total_rows = 0
        self._failure_category = ""
        self._failure_code = ""
        self._failure_message = ""
        self._clear_result()
        self._active_record = None
        self._activity_record_available = False
        self._set_persistence_issue("")

    def _clear_result(self) -> None:
        self._result_request_id = ""
        self._result_run_id = ""
        self._result_run_status = ""
        self._result_output_directory = ""
        self._result_row_count = 0
        self._result_valid_row_count = 0
        self._result_invalid_row_count = 0
        self._result_spec_id = ""
        self._result_generation_context_id = ""
        self._result_output_request_id = ""
        self._result_visualization_status = ""
        self._result_mode = ""
        self._result_projected_rows = 0
        self._result_backend_model = ""
        self._result_configuration_path = None
        self._result_configuration_sha256 = ""
        self._result_workspace_root = None

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        if event.type == "phase":
            self._flush_progress_record()
            self._phase = str(event.payload.get("name", "unknown"))
            self._persist_event(event.type, event.payload)
        elif event.type == "progress":
            self._completed_rows = _int_value(event.payload.get("completed"))
            self._total_rows = _int_value(event.payload.get("total"))
            self._pending_progress = dict(event.payload)
            if not self._progress_write_timer.isActive():
                self._progress_write_timer.start()
        self.state_changed.emit()

    def _session_state_changed(self, state: str) -> None:
        if state in {
            "starting",
            "running",
            "cancellation_requested",
            "force_stopping",
        }:
            self._state = state
            self.state_changed.emit()

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        self._progress_write_timer.stop()
        self._flush_progress_record()
        self._persist_terminal(outcome.terminal_envelope)
        snapshot = self._active_snapshot
        if snapshot is not None:
            self._result_configuration_path = snapshot.path
            self._result_configuration_sha256 = snapshot.sha256
        self._result_workspace_root = self._active_workspace_root
        self._result_request_id = str(outcome.request_id)
        result = outcome.result_payload
        if result is not None:
            self._accept_result(result)
            self._state = "succeeded"
        else:
            self._accept_failure(outcome)
        self._session = None
        self._active_snapshot = None
        self._active_workspace_root = None
        self.state_changed.emit()

    def _accept_result(self, payload: dict[str, object]) -> None:
        self._result_run_id = _text(payload.get("run_id"))
        self._result_run_status = _text(payload.get("run_status"))
        self._result_output_directory = _text(payload.get("output_directory"))
        self._result_row_count = _int_value(payload.get("row_count"))
        self._result_valid_row_count = _int_value(payload.get("valid_row_count"))
        self._result_invalid_row_count = _int_value(payload.get("invalid_row_count"))
        self._result_spec_id = _text(payload.get("spec_id"))
        self._result_generation_context_id = _text(payload.get("generation_context_id"))
        self._result_output_request_id = _text(payload.get("output_request_id"))
        visualization = payload.get("visualization")
        self._result_visualization_status = (
            _text(visualization.get("status")) if isinstance(visualization, dict) else ""
        )
        self._result_mode = _text(payload.get("mode"))
        self._result_projected_rows = _int_value(payload.get("projected_rows"))
        self._result_backend_model = _text(payload.get("backend_model"))
        if self._operation == "generate" and self._result_output_directory:
            self.run_finalized.emit(Path(self._result_output_directory))

    def _accept_failure(self, outcome: RequestOutcome) -> None:
        payload = outcome.failure_payload or {}
        self._failure_category = _text(payload.get("category"))
        self._failure_code = _text(payload.get("code"), "execution_failed")
        self._failure_message = _text(payload.get("message"), "worker request failed")
        if outcome.force_stopped or self._failure_code == "force_stopped":
            self._state = "force_stopped"
        elif self._failure_code == "cancelled":
            self._state = "cancelled"
        elif self._failure_category == "config" and self._failure_code == "invalid_config":
            self._state = "invalid"
        else:
            self._state = "failed"

    def _persist_event(self, event_type: str, payload: dict[str, Any]) -> None:
        store = self._activity_store
        record = self._active_record
        if store is None or record is None:
            return
        try:
            store.update_event(record, event_type, payload)
        except (OSError, ValueError) as exc:
            self._set_persistence_issue(f"could not update Run activity: {exc}")
        else:
            self._set_persistence_issue("")
            self.activity_record_changed.emit()

    @Slot()
    def _flush_progress_record(self) -> None:
        payload, self._pending_progress = self._pending_progress, None
        if payload is not None:
            self._persist_event("progress", payload)

    def _persist_terminal(self, envelope: dict[str, object]) -> None:
        store = self._activity_store
        record = self._active_record
        if store is None or record is None:
            return
        try:
            store.finish(record, cast(dict[str, Any], envelope))
        except (OSError, ValueError):
            try:
                store.write(record)
            except (OSError, ValueError) as retry_exc:
                self._set_persistence_issue(
                    f"could not persist terminal Run activity after one retry: {retry_exc}"
                )
            else:
                self._set_persistence_issue("")
                self.activity_record_changed.emit()
        else:
            self._set_persistence_issue("")
            self.activity_record_changed.emit()

    def _persist_start_failure(
        self,
        store: JobStore,
        record: dict[str, Any],
        reservation: RequestReservation,
        error: Exception,
    ) -> None:
        try:
            store.finish_start_failure(
                record,
                request_type=reservation.request_type,
                category="process",
                code="worker_start_failed",
                message=str(error),
            )
        except (OSError, ValueError) as exc:
            self._set_persistence_issue(f"could not persist worker-start failure: {exc}")
        else:
            self._set_persistence_issue("")
            self.activity_record_changed.emit()

    def _set_start_failure(self, category: str, code: str, message: str) -> None:
        self._failure_category = category
        self._failure_code = code
        self._failure_message = message
        self._state = "failed"
        self._active_snapshot = None
        self._active_workspace_root = None
        self.state_changed.emit()

    def _set_persistence_issue(self, issue: str) -> None:
        if issue == self._activity_persistence_issue:
            return
        self._activity_persistence_issue = issue
        self.state_changed.emit()

    def _coordinator_busy_changed(self, _busy: bool) -> None:
        self.state_changed.emit()

    def _result_relation(self) -> tuple[bool, str]:
        result_path = self._result_configuration_path
        result_digest = self._result_configuration_sha256
        result_workspace = self._result_workspace_root
        if result_path is None or not result_digest or result_workspace is None:
            return False, ""
        workspace = self.workspace
        if workspace is None or workspace.root != result_workspace:
            return False, "The result belongs to another workspace."
        document = self.config_controller.document
        if document is None or document.source_path is None or document.source_sha256 is None:
            return False, "The result belongs to another configuration."
        if document.source_path.resolve() != result_path.resolve():
            return False, "The saved configuration path changed after execution."
        if document.source_sha256 != result_digest:
            return False, "A later Save established a different configuration identity."
        if not source_matches(result_path, result_digest):
            return False, "The saved configuration changed outside Carnopy after execution."
        if self.config_controller.get_dirty():
            return (
                True,
                "Generated from the current saved configuration; unsaved draft changes now exist.",
            )
        return True, ""


def _text(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
