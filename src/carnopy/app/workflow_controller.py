from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from PySide6.QtCore import Property, QObject, Signal

from carnopy.app.config_document import (
    ConfigDocumentError,
    DocumentType,
    SavedConfigSnapshot,
    is_path_within,
    source_matches,
)
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.jobs import JobStore
from carnopy.app.protocol import RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestOwner,
    RequestReservation,
    RequestSession,
)
from carnopy.app.workflow_models import WorkflowIssue, WorkflowIssueModel
from carnopy.app.workspace import Workspace

if TYPE_CHECKING:
    from carnopy.app.config_controller import ConfigurationController

WorkflowKind = Literal["sweep", "preparation"]
ResultRelation = Literal["unavailable", "current", "stale", "unrelated"]


class WorkflowController(QObject):
    """Private nonvisual load/validate/plan/execute state for one workflow."""

    state_changed = Signal()
    activity_record_changed = Signal()
    output_finalized = Signal(object)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        *,
        kind: WorkflowKind,
        configuration_controller: ConfigurationController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.kind = kind
        self.configuration_controller = configuration_controller
        self.owner: RequestOwner = kind
        self.workspace: Workspace | None = None
        self._store: JobStore | None = None
        self._session: RequestSession | None = None
        self._operation = ""
        self._state = "unavailable"
        self._phase = ""
        self._progress: dict[str, Any] = {}
        self._failure: dict[str, Any] = {}
        self._loaded_config: dict[str, Any] | None = None
        self._config_path: Path | None = None
        self._config_sha256 = ""
        self._validation: dict[str, Any] | None = None
        self._plan: dict[str, Any] | None = None
        self._plan_config_sha256 = ""
        self._planned_context: dict[str, object] | None = None
        self._plan_stale_reason = ""
        self._result: dict[str, Any] | None = None
        self._result_config_sha256 = ""
        self._result_context: dict[str, object] | None = None
        self._activity_persistence_issue = ""
        self._active_snapshot: SavedConfigSnapshot | None = None
        self._active_plan_context: dict[str, object] | None = None
        self._active_record: dict[str, Any] | None = None
        self.plan_blocking_reasons = WorkflowIssueModel(self)
        self.execution_blocking_reasons = WorkflowIssueModel(self)
        coordinator.busy_changed.connect(lambda _busy: self.state_changed.emit())
        if configuration_controller is not None:
            configuration_controller.state_changed.connect(self.state_changed.emit)
        self.state_changed.connect(self._refresh_typed_projections)

    @property
    def state(self) -> str:
        return self._state

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def progress(self) -> dict[str, Any]:
        return copy.deepcopy(self._progress)

    @property
    def failure(self) -> dict[str, Any]:
        return copy.deepcopy(self._failure)

    @property
    def loaded_config(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._loaded_config)

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def config_sha256(self) -> str:
        return self._config_sha256

    @property
    def validation(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._validation)

    @property
    def current_plan(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._plan)

    def get_has_plan(self) -> bool:
        return self._plan is not None

    hasPlan = Property(bool, get_has_plan, notify=state_changed)

    def get_plan_id(self) -> str:
        return _text((self._plan or {}).get("plan_id"))

    planId = Property(str, get_plan_id, notify=state_changed)

    @property
    def plan_current(self) -> bool:
        if self._plan is None or self._plan_stale_reason:
            return False
        try:
            snapshot = self._saved_snapshot()
        except ValueError:
            return False
        return snapshot.sha256 == self._plan_config_sha256 and self._plan_context_matches()

    def get_plan_current(self) -> bool:
        return self.plan_current

    planCurrent = Property(bool, get_plan_current, notify=state_changed)

    @property
    def result(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._result)

    def get_has_result(self) -> bool:
        return self._result is not None

    hasResult = Property(bool, get_has_result, notify=state_changed)

    def get_result_output_directory(self) -> str:
        return _text((self._result or {}).get("output_directory"))

    resultOutputDirectory = Property(
        str,
        get_result_output_directory,
        notify=state_changed,
    )

    def get_result_relation(self) -> ResultRelation:
        if self._result is None:
            return "unavailable"
        controller = self.configuration_controller
        if (
            controller is not None
            and controller.get_document_kind() != self._expected_document_type()
        ):
            return "unrelated"
        try:
            snapshot = self._saved_snapshot()
        except ValueError:
            return "stale"
        if snapshot.sha256 != self._result_config_sha256:
            return "stale"
        if not self._context_matches(self._result_context):
            return "stale"
        return "current"

    resultRelation = Property(str, get_result_relation, notify=state_changed)

    @property
    def activity_persistence_issue(self) -> str:
        return self._activity_persistence_issue

    def get_workflow_kind(self) -> str:
        return self.kind

    workflowKind = Property(str, get_workflow_kind, constant=True)

    def get_document_kind(self) -> str:
        return self._expected_document_type()

    documentKind = Property(str, get_document_kind, constant=True)

    def get_workflow_state(self) -> str:
        return self._state

    workflowState = Property(str, get_workflow_state, notify=state_changed)

    def get_workflow_operation(self) -> str:
        return self._operation

    workflowOperation = Property(str, get_workflow_operation, notify=state_changed)

    def get_workflow_phase(self) -> str:
        return self._phase

    workflowPhase = Property(str, get_workflow_phase, notify=state_changed)

    def get_operation_active(self) -> bool:
        return self._session is not None

    operationActive = Property(bool, get_operation_active, notify=state_changed)

    def get_progress_available(self) -> bool:
        return bool(self._progress)

    progressAvailable = Property(bool, get_progress_available, notify=state_changed)

    def get_progress_completed(self) -> int:
        return _nonnegative_int(self._progress.get("completed"))

    progressCompleted = Property(int, get_progress_completed, notify=state_changed)

    def get_progress_total(self) -> int:
        return _nonnegative_int(self._progress.get("total"))

    progressTotal = Property(int, get_progress_total, notify=state_changed)

    def get_failure_category(self) -> str:
        return _text(self._failure.get("category"))

    failureCategory = Property(str, get_failure_category, notify=state_changed)

    def get_failure_code(self) -> str:
        return _text(self._failure.get("code"))

    failureCode = Property(str, get_failure_code, notify=state_changed)

    def get_failure_message(self) -> str:
        return _text(self._failure.get("message"))

    failureMessage = Property(str, get_failure_message, notify=state_changed)

    def get_activity_persistence_issue(self) -> str:
        return self._activity_persistence_issue

    activityPersistenceIssue = Property(
        str,
        get_activity_persistence_issue,
        notify=state_changed,
    )

    def get_plan_blocking_reasons(self) -> QObject:
        return self.plan_blocking_reasons

    planBlockingReasons = Property(QObject, get_plan_blocking_reasons, constant=True)

    def get_execution_blocking_reasons(self) -> QObject:
        return self.execution_blocking_reasons

    executionBlockingReasons = Property(
        QObject,
        get_execution_blocking_reasons,
        constant=True,
    )

    @property
    def can_cancel(self) -> bool:
        return self._session is not None and self._session.cooperative_cancel_available

    def get_cancellation_available(self) -> bool:
        return self.can_cancel

    cancellationAvailable = Property(bool, get_cancellation_available, notify=state_changed)

    @property
    def can_force_stop(self) -> bool:
        return self._session is not None and self._session.force_stop_available

    def get_force_stop_available(self) -> bool:
        return self.can_force_stop

    forceStopAvailable = Property(bool, get_force_stop_available, notify=state_changed)

    def get_protected_finalization(self) -> bool:
        return self._session is not None and self._session.termination_protected

    protectedFinalization = Property(bool, get_protected_finalization, notify=state_changed)

    @property
    def can_plan(self) -> bool:
        return not self._plan_blocking_issues()

    def get_can_plan(self) -> bool:
        return self.can_plan

    canPlan = Property(bool, get_can_plan, notify=state_changed)

    @property
    def can_execute(self) -> bool:
        return not self._execution_blocking_issues()

    def get_can_execute(self) -> bool:
        return self.can_execute

    canExecute = Property(bool, get_can_execute, notify=state_changed)

    def _plan_blocking_issues(self) -> tuple[WorkflowIssue, ...]:
        issues: list[WorkflowIssue] = []
        if issue := self._saved_configuration_issue():
            issues.append(issue)
        try:
            self._plan_context()
        except ValueError as exc:
            issues.append(
                self._blocking_issue(
                    origin="source" if self.kind == "preparation" else "local",
                    code=(
                        "preparation_source_unavailable"
                        if self.kind == "preparation"
                        else "plan_context_unavailable"
                    ),
                    message=str(exc),
                    section="source" if self.kind == "preparation" else "plan",
                    field_id=(
                        "preparation.source"
                        if self.kind == "preparation"
                        else f"{self.kind}.configuration"
                    ),
                )
            )
        if issue := self._worker_availability_issue():
            issues.append(issue)
        return tuple(issues)

    def _execution_blocking_issues(self) -> tuple[WorkflowIssue, ...]:
        issues: list[WorkflowIssue] = []
        if self._plan is None:
            issues.append(
                self._blocking_issue(
                    origin="plan",
                    code="current_plan_required",
                    message="Create a current plan before execution.",
                    section="plan",
                    field_id=f"{self.kind}.plan",
                )
            )
        elif self._plan_stale_reason:
            issues.append(
                self._blocking_issue(
                    origin="plan",
                    code="plan_rejected_by_worker",
                    message=self._plan_stale_reason,
                    section="plan",
                    field_id=f"{self.kind}.plan",
                )
            )
        elif not self._plan_configuration_matches():
            issues.append(
                self._blocking_issue(
                    origin="plan",
                    code="plan_configuration_changed",
                    message="The plan belongs to a different saved configuration.",
                    section="plan",
                    field_id=f"{self.kind}.plan",
                )
            )
        elif not self._plan_context_matches():
            issues.append(
                self._blocking_issue(
                    origin="source" if self.kind == "preparation" else "plan",
                    code="plan_context_changed",
                    message="The plan no longer matches the current workflow context.",
                    section="source" if self.kind == "preparation" else "plan",
                    field_id=(
                        "preparation.source" if self.kind == "preparation" else f"{self.kind}.plan"
                    ),
                )
            )
        if issue := self._saved_configuration_issue():
            issues.append(issue)
        if issue := self._worker_availability_issue():
            issues.append(issue)
        return tuple(issues)

    def _saved_configuration_issue(self) -> WorkflowIssue | None:
        if self.workspace is None:
            return self._blocking_issue(
                origin="local",
                code="workspace_required",
                message="Open a workspace first.",
                section="workspace",
                field_id="workspace",
            )
        controller = self.configuration_controller
        if controller is not None:
            if controller.get_document_kind() != self._expected_document_type():
                return self._blocking_issue(
                    origin="local",
                    code="saved_configuration_required",
                    message=f"Open and save a {self.kind} configuration first.",
                    section="configuration",
                    field_id=f"{self.kind}.configuration",
                )
            try:
                self._saved_snapshot()
            except ValueError as exc:
                return self._blocking_issue(
                    origin="local",
                    code="saved_configuration_unavailable",
                    message=str(exc),
                    section="configuration",
                    field_id=f"{self.kind}.configuration",
                )
            return None
        if self._config_path is None or not self._config_sha256:
            return self._blocking_issue(
                origin="local",
                code="saved_configuration_required",
                message=f"Load a {self.kind} configuration first.",
                section="configuration",
                field_id=f"{self.kind}.configuration",
            )
        try:
            self._saved_snapshot()
        except ValueError as exc:
            return self._blocking_issue(
                origin="local",
                code="saved_configuration_unavailable",
                message=str(exc),
                section="configuration",
                field_id=f"{self.kind}.configuration",
            )
        return None

    def _worker_availability_issue(self) -> WorkflowIssue | None:
        if self._session is not None:
            operation = self._operation.replace("_", " ") or "workflow"
            return self._blocking_issue(
                origin="runtime",
                code="operation_active",
                message=f"The {operation} operation is already active.",
                section="operation",
                field_id=f"{self.kind}.operation",
            )
        if self.coordinator.is_busy:
            return self._blocking_issue(
                origin="runtime",
                code="desktop_worker_busy",
                message="Another desktop worker operation is active.",
                section="operation",
                field_id=f"{self.kind}.operation",
            )
        return None

    def _blocking_issue(
        self,
        *,
        origin: Literal["local", "source", "plan", "runtime"],
        code: str,
        message: str,
        section: str,
        field_id: str,
    ) -> WorkflowIssue:
        return WorkflowIssue(
            origin=origin,
            severity="blocking",
            code=code,
            message=message,
            document_kind=self.get_document_kind(),
            section=section,
            field_id=field_id,
        )

    def _refresh_typed_projections(self) -> None:
        self.plan_blocking_reasons.replace(self._plan_blocking_issues())
        self.execution_blocking_reasons.replace(self._execution_blocking_issues())

    def set_workspace(self, workspace: Workspace | None) -> None:
        if workspace == self.workspace:
            self.state_changed.emit()
            return
        self.workspace = workspace
        self._store = None if workspace is None else JobStore(workspace.private_directory)
        self._operation = ""
        self._phase = ""
        self._progress = {}
        self._failure = {}
        self._loaded_config = None
        self._config_path = None
        self._config_sha256 = ""
        self._validation = None
        self._clear_result()
        self._clear_plan()
        self._set_activity_persistence_issue("")
        self._state = "ready" if workspace is not None else "unavailable"
        self.state_changed.emit()

    def load_config(self, path: str | Path) -> bool:
        return self._start(
            "load",
            cast(RequestType, f"load_{self.kind}_config"),
            {"config_path": str(Path(path).expanduser().absolute())},
        )

    def validate_text(self, yaml_text: str, *, source_name: str = "<gui>") -> bool:
        return self._start(
            "validate",
            cast(RequestType, f"validate_{self.kind}_config"),
            {"yaml_text": yaml_text, "source_name": source_name},
        )

    def plan(self) -> bool:
        try:
            snapshot = self._saved_snapshot()
            context = self._plan_context()
        except ValueError as exc:
            self._set_local_failure("request", "plan_unavailable", str(exc))
            return False
        workspace = self.workspace
        if workspace is None:
            return False
        payload: dict[str, object] = {
            "config_path": str(snapshot.path),
            "expected_config_sha256": snapshot.sha256,
            "configs_root": str(workspace.configs),
            **context,
        }
        return self._start(
            "plan",
            cast(RequestType, f"plan_{self.kind}"),
            payload,
            snapshot=snapshot,
        )

    def execute(self) -> bool:
        plan = self._plan
        if plan is None or not self.can_execute:
            self._set_local_failure(
                "request",
                "execute_unavailable",
                "create a current plan before execution",
            )
            return False
        try:
            snapshot = self._saved_snapshot()
            context = self._plan_context()
        except ValueError as exc:
            self._set_local_failure("request", "execute_unavailable", str(exc))
            return False
        workspace = self.workspace
        if workspace is None:
            return False
        payload: dict[str, object] = {
            "config_path": str(snapshot.path),
            "expected_config_sha256": snapshot.sha256,
            "configs_root": str(workspace.configs),
            "expected_plan_id": str(plan["plan_id"]),
            "output_root": str(workspace.outputs),
            **context,
        }
        return self._start(
            "execute",
            cast(RequestType, f"execute_{self.kind}"),
            payload,
            snapshot=snapshot,
            persist_execution=True,
        )

    def cancel(self) -> bool:
        session = self._session
        if session is None or not session.cancel():
            return False
        self._state = "cancellation_requested"
        self.state_changed.emit()
        return True

    def force_stop(self) -> bool:
        session = self._session
        if session is None or not session.force_stop():
            return False
        self._state = "force_stopping"
        self.state_changed.emit()
        return True

    def _start(
        self,
        operation: str,
        request_type: RequestType,
        payload: dict[str, object],
        *,
        snapshot: SavedConfigSnapshot | None = None,
        persist_execution: bool = False,
    ) -> bool:
        if self._session is not None or self.coordinator.is_busy:
            return False
        self._operation = operation
        self._state = "starting"
        self._phase = ""
        self._progress = {}
        self._failure = {}
        self._active_record = None
        self._active_snapshot = snapshot
        self._active_plan_context = (
            copy.deepcopy(self._planned_context) if persist_execution else None
        )
        reservation: RequestReservation
        try:
            reservation = self.coordinator.reserve_request(self.owner, request_type)
        except (RuntimeError, ValueError) as exc:
            self._set_local_failure("request", "request_unavailable", str(exc))
            return False
        self._set_activity_persistence_issue("")
        if persist_execution:
            try:
                self._start_activity(reservation, snapshot)
            except (OSError, UnicodeError, ValueError) as exc:
                self.coordinator.abandon_reserved_request(reservation)
                self._set_activity_persistence_issue(
                    f"could not persist workflow Activity record: {exc}"
                )
                self._set_local_failure(
                    "process",
                    "activity_persistence_failed",
                    f"could not persist workflow Activity record: {exc}",
                )
                return False
        try:
            session = self.coordinator.start_reserved_request(reservation, payload)
        except Exception as exc:
            self.coordinator.abandon_reserved_request(reservation)
            self._finish_start_failure(reservation, exc)
            if operation == "load":
                self._clear_loaded_configuration()
            self._set_local_failure("process", "worker_start_failed", str(exc))
            return False
        self._session = session
        session.event_received.connect(self._event_received)
        session.state_changed.connect(self._session_state_changed)
        session.policy_changed.connect(self.state_changed)
        session.completed.connect(self._request_completed)
        self.state_changed.emit()
        return True

    def _start_activity(
        self,
        reservation: RequestReservation,
        snapshot: SavedConfigSnapshot | None,
    ) -> None:
        workspace = self.workspace
        store = self._store
        plan = self._plan
        if workspace is None or store is None or snapshot is None or plan is None:
            raise ValueError("workflow execution Activity context is incomplete")
        relative = snapshot.path.relative_to(workspace.root).as_posix()
        self._active_record = store.start(
            request_id=str(reservation.request_id),
            operation=f"execute_{self.kind}",
            config_relative_path=relative,
            yaml_snapshot=snapshot.yaml_bytes.decode("utf-8"),
            config_sha256=snapshot.sha256,
            owner=self.owner,
            plan_identity={
                "plan_id": plan.get("plan_id"),
                "plan_schema_version": plan.get("plan_schema_version"),
                "fingerprint": plan.get("fingerprint"),
            },
            preparation_source_identity=(
                self._activity_source_identity() if self.kind == "preparation" else None
            ),
        )
        self.activity_record_changed.emit()

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        if event.type == "phase":
            self._phase = str(event.payload.get("name", "unknown"))
            self._persist_event(event)
        elif event.type == "progress":
            self._progress = dict(event.payload)
            self._persist_event(event)
        self.state_changed.emit()

    def _session_state_changed(self, state: str) -> None:
        if state in {"starting", "running", "cancellation_requested", "force_stopping"}:
            self._state = state
            self.state_changed.emit()

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        if self._active_record is not None:
            self._finish_activity(outcome)
        result = outcome.result_payload
        operation = self._operation
        if result is None:
            self._failure = outcome.failure_payload or {}
            code = str(self._failure.get("code", "execution_failed"))
            if operation == "load":
                self._clear_loaded_configuration()
            if code in {"source_changed", "stale_plan"}:
                message = _text(self._failure.get("message"))
                self._mark_plan_stale(
                    message or "The worker rejected the previously accepted plan."
                )
            self._state = (
                "cancelled"
                if code == "cancelled"
                else "force_stopped"
                if outcome.force_stopped
                else "failed"
            )
        elif operation == "load":
            self._accept_loaded(result)
            self._state = "ready"
        elif operation == "validate":
            self._validation = copy.deepcopy(result)
            self._state = "validated" if result.get("valid", True) else "invalid"
        elif operation == "plan":
            try:
                self._accept_plan(result)
            except ValueError as exc:
                self._set_local_failure("request", "stale_plan", str(exc))
            else:
                self._state = "planned"
        else:
            self._result = copy.deepcopy(result)
            active_snapshot = self._active_snapshot
            self._result_config_sha256 = "" if active_snapshot is None else active_snapshot.sha256
            self._result_context = copy.deepcopy(self._active_plan_context)
            self._state = "succeeded"
            output = result.get("output_directory")
            if isinstance(output, str) and output:
                self.output_finalized.emit(Path(output))
        self._session = None
        self._active_snapshot = None
        self._active_plan_context = None
        self._active_record = None
        self.state_changed.emit()

    def _accept_loaded(self, result: dict[str, object]) -> None:
        source = result.get("source_name")
        digest = result.get("source_sha256")
        config = result.get("config")
        if (
            not isinstance(source, str)
            or not isinstance(digest, str)
            or not isinstance(config, dict)
        ):
            raise ValueError("workflow load result is missing configuration identity")
        self._loaded_config = copy.deepcopy(config)
        self._config_path = Path(source).expanduser().resolve()
        self._config_sha256 = digest
        self._validation = None

    def _accept_plan(self, result: dict[str, object]) -> None:
        plan_id = result.get("plan_id")
        config_sha = result.get("configuration_sha256")
        active_snapshot = self._active_snapshot
        if (
            not isinstance(plan_id, str)
            or active_snapshot is None
            or config_sha != active_snapshot.sha256
        ):
            raise ValueError("workflow plan result does not match the loaded configuration")
        current_snapshot = self._saved_snapshot()
        if current_snapshot.sha256 != active_snapshot.sha256:
            raise ValueError("workflow plan result no longer matches the current configuration")
        if not self._plan_result_matches_current_context(result):
            raise ValueError("workflow plan result no longer matches the current inputs")
        self._plan = copy.deepcopy(result)
        self._plan_config_sha256 = active_snapshot.sha256
        self._record_plan_context()
        self._plan_stale_reason = ""

    def _saved_snapshot(self) -> SavedConfigSnapshot:
        controller = self.configuration_controller
        if controller is not None:
            try:
                return controller.execution_snapshot(
                    expected_document_type=self._expected_document_type()
                )
            except ConfigDocumentError as exc:
                raise ValueError(str(exc)) from exc
        workspace = self.workspace
        path = self._config_path
        digest = self._config_sha256
        if workspace is None:
            raise ValueError("open a workspace first")
        if path is None or not digest:
            raise ValueError(f"load a {self.kind} configuration first")
        if not is_path_within(path, workspace.configs):
            raise ValueError(
                "external workflow configurations must be saved under the workspace configs folder"
            )
        if not source_matches(path, digest):
            raise ValueError("saved workflow configuration changed; load it again")
        yaml_bytes = path.read_bytes()
        if hashlib.sha256(yaml_bytes).hexdigest() != digest:
            raise ValueError("saved workflow configuration changed; load it again")
        return SavedConfigSnapshot(
            path=path,
            yaml_bytes=yaml_bytes,
            sha256=digest,
            document_type=self._expected_document_type(),
        )

    def _expected_document_type(self) -> DocumentType:
        return "model_sweep" if self.kind == "sweep" else "preparation"

    def _plan_configuration_matches(self) -> bool:
        if self.configuration_controller is None:
            return self._plan_config_sha256 == self._config_sha256
        try:
            snapshot = self._saved_snapshot()
        except ValueError:
            return False
        return snapshot.sha256 == self._plan_config_sha256

    def _plan_context(self) -> dict[str, object]:
        return {}

    def _record_plan_context(self) -> None:
        self._planned_context = copy.deepcopy(self._plan_context())

    def _plan_context_matches(self) -> bool:
        return self._context_matches(self._planned_context)

    def _context_matches(self, expected: dict[str, object] | None) -> bool:
        if expected is None:
            return False
        try:
            current_context = self._plan_context()
        except ValueError:
            return False
        return current_context == expected

    def _plan_result_matches_current_context(self, _result: dict[str, object]) -> bool:
        return True

    def _activity_source_identity(self) -> dict[str, Any] | None:
        return None

    def _mark_plan_stale(self, reason: str) -> None:
        if self._plan is not None:
            self._plan_stale_reason = reason

    def _clear_plan(self) -> None:
        self._plan = None
        self._plan_config_sha256 = ""
        self._planned_context = None
        self._plan_stale_reason = ""

    def _clear_result(self) -> None:
        self._result = None
        self._result_config_sha256 = ""
        self._result_context = None

    def _clear_loaded_configuration(self) -> None:
        self._loaded_config = None
        self._config_path = None
        self._config_sha256 = ""
        self._validation = None

    def _persist_event(self, event: WorkerEvent) -> None:
        store = self._store
        record = self._active_record
        if store is None or record is None:
            return
        try:
            store.update_event(record, event.type, event.payload)
        except (OSError, ValueError) as exc:
            self._set_activity_persistence_issue(f"could not update workflow Activity: {exc}")
        else:
            self._set_activity_persistence_issue("")
            self.activity_record_changed.emit()

    def _finish_activity(self, outcome: RequestOutcome) -> None:
        store = self._store
        record = self._active_record
        if store is None or record is None:
            return
        try:
            store.finish(record, cast(dict[str, Any], outcome.terminal_envelope))
        except (OSError, ValueError):
            try:
                store.write(record)
            except (OSError, ValueError) as retry_exc:
                self._set_activity_persistence_issue(
                    f"could not persist terminal workflow Activity after one retry: {retry_exc}"
                )
            else:
                self._set_activity_persistence_issue("")
                self.activity_record_changed.emit()
        else:
            self._set_activity_persistence_issue("")
            self.activity_record_changed.emit()

    def _finish_start_failure(
        self,
        reservation: RequestReservation,
        error: Exception,
    ) -> None:
        store = self._store
        record = self._active_record
        if store is None or record is None:
            return
        try:
            store.finish_start_failure(
                record,
                request_type=reservation.request_type,
                category="process",
                code="worker_start_failed",
                message=str(error),
            )
        except (OSError, ValueError):
            try:
                store.write(record)
            except (OSError, ValueError) as retry_exc:
                self._set_activity_persistence_issue(
                    f"could not persist workflow start failure after one retry: {retry_exc}"
                )
            else:
                self._set_activity_persistence_issue("")
                self.activity_record_changed.emit()
        else:
            self._set_activity_persistence_issue("")
            self.activity_record_changed.emit()

    def _set_local_failure(self, category: str, code: str, message: str) -> None:
        self._failure = {"category": category, "code": code, "message": message}
        self._state = "failed"
        self.state_changed.emit()

    def _set_activity_persistence_issue(self, issue: str) -> None:
        if issue == self._activity_persistence_issue:
            return
        self._activity_persistence_issue = issue
        self.state_changed.emit()


class SweepWorkflowController(WorkflowController):
    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        parent: QObject | None = None,
        *,
        configuration_controller: ConfigurationController | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            kind="sweep",
            configuration_controller=configuration_controller,
            parent=parent,
        )
        self._refresh_typed_projections()


class PreparationWorkflowController(WorkflowController):
    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        inspection: InspectionController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(coordinator, kind="preparation", parent=parent)
        self.inspection = inspection
        inspection.inspection_changed.connect(self._inspection_changed)
        self._refresh_typed_projections()

    def _plan_context(self) -> dict[str, object]:
        snapshot = self.inspection.preparation_source_snapshot()
        if snapshot is None:
            reason = self.inspection.get_preparation_ineligible_reason()
            raise ValueError(reason or "inspect an eligible preparation source first")
        source, revision, descriptor = snapshot
        return {
            "source_path": str(source),
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
        }

    def _plan_result_matches_current_context(self, result: dict[str, object]) -> bool:
        snapshot = self.inspection.preparation_source_snapshot()
        source_revision = result.get("source_revision")
        if snapshot is None or not isinstance(source_revision, dict):
            return False
        source, revision, descriptor = snapshot
        return (
            source_revision.get("inspection_revision") == revision
            and source_revision.get("inspection_descriptor") == descriptor
            and descriptor.get("source_path") == str(source)
        )

    def _activity_source_identity(self) -> dict[str, Any] | None:
        snapshot = self.inspection.preparation_source_snapshot()
        if snapshot is None:
            return None
        source, revision, descriptor = snapshot
        return {
            "source_path": str(source),
            "inspection_revision": revision,
            "descriptor": descriptor,
        }

    def _inspection_changed(self, _payload: object) -> None:
        self.state_changed.emit()


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
