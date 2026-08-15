from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
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
from carnopy.app.workflow_models import (
    PreparationPlanModel,
    PreparationPlanProjection,
    WorkflowIssue,
    WorkflowIssueModel,
)
from carnopy.app.workspace import Workspace

if TYPE_CHECKING:
    from carnopy.app.config_controller import ConfigurationController

WorkflowKind = Literal["sweep", "preparation"]
ResultRelation = Literal["unavailable", "current", "stale", "unrelated"]


@dataclass(frozen=True)
class _WorkflowRequestContext:
    operation: str
    workspace_root: Path | None
    requested_path: Path | None
    snapshot_path: Path | None
    snapshot_sha256: str
    plan_context_json: str


@dataclass(frozen=True)
class _PreparationSourceBinding:
    source_path: Path
    inspection_revision: str
    descriptor_json: str
    profile_json: str

    @classmethod
    def create(
        cls,
        source_path: Path,
        inspection_revision: str,
        descriptor: dict[str, Any],
        profile: dict[str, Any],
    ) -> _PreparationSourceBinding:
        return cls(
            source_path=source_path.resolve(),
            inspection_revision=inspection_revision,
            descriptor_json=_canonical_mapping_json(descriptor),
            profile_json=_canonical_mapping_json(profile),
        )

    def descriptor(self) -> dict[str, Any]:
        return _mapping_from_json(self.descriptor_json)

    def profile(self) -> dict[str, Any]:
        return _mapping_from_json(self.profile_json)

    def plan_context(self) -> dict[str, object]:
        return {
            "source_path": str(self.source_path),
            "inspection_revision": self.inspection_revision,
            "inspection_descriptor": self.descriptor(),
        }


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
        self._request_context: _WorkflowRequestContext | None = None
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
        issues.extend(self._workflow_input_issues())
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
        issues.extend(self._workflow_input_issues())
        if issue := self._worker_availability_issue():
            issues.append(issue)
        return tuple(issues)

    def _workflow_input_issues(self) -> tuple[WorkflowIssue, ...]:
        return ()

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
        origin: Literal["local", "source", "dependency", "plan", "runtime"],
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
        if issues := self._workflow_input_issues():
            self._set_local_failure("request", "plan_unavailable", issues[0].message)
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
        request_context = self._capture_request_context(operation, payload, snapshot)
        reservation: RequestReservation
        try:
            reservation = self.coordinator.reserve_request(self.owner, request_type)
        except (RuntimeError, ValueError) as exc:
            self._clear_active_attempt()
            self._set_local_failure("request", "request_unavailable", str(exc))
            return False
        self._set_activity_persistence_issue("")
        if persist_execution:
            try:
                self._start_activity(reservation, snapshot)
            except (OSError, UnicodeError, ValueError) as exc:
                self.coordinator.abandon_reserved_request(reservation)
                self._clear_active_attempt()
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
            self._clear_active_attempt()
            if operation == "load":
                self._clear_loaded_configuration()
            self._set_local_failure("process", "worker_start_failed", str(exc))
            return False
        self._session = session
        self._request_context = request_context
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
        context = self._request_context
        self._request_context = None
        if context is None or not self._response_context_is_current(context):
            if self._active_record is not None:
                self._finish_activity(outcome)
            self._session = None
            self._clear_active_attempt()
            self.state_changed.emit()
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
            try:
                self._accept_loaded(result, requested_path=context.requested_path)
            except ValueError as exc:
                self._clear_loaded_configuration()
                self._set_local_failure("request", "invalid_load_result", str(exc))
            else:
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
        self._clear_active_attempt()
        self.state_changed.emit()

    def _accept_loaded(
        self,
        result: dict[str, object],
        *,
        requested_path: Path | None,
    ) -> None:
        source = result.get("source_name")
        digest = result.get("source_sha256")
        config = result.get("config")
        if (
            not isinstance(source, str)
            or not isinstance(digest, str)
            or not isinstance(config, dict)
        ):
            raise ValueError("workflow load result is missing configuration identity")
        source_path = Path(source).expanduser().resolve()
        if requested_path is None or source_path != requested_path:
            raise ValueError("workflow load result does not match its requested source")
        self._loaded_config = copy.deepcopy(config)
        self._config_path = source_path
        self._config_sha256 = digest
        self._validation = None

    def _capture_request_context(
        self,
        operation: str,
        payload: dict[str, object],
        snapshot: SavedConfigSnapshot | None,
    ) -> _WorkflowRequestContext:
        requested = payload.get("config_path")
        requested_path = (
            Path(requested).expanduser().resolve() if isinstance(requested, str) else None
        )
        plan_context = self._active_plan_context
        return _WorkflowRequestContext(
            operation=operation,
            workspace_root=None if self.workspace is None else self.workspace.root,
            requested_path=requested_path,
            snapshot_path=None if snapshot is None else snapshot.path,
            snapshot_sha256="" if snapshot is None else snapshot.sha256,
            plan_context_json=(
                "" if plan_context is None else _canonical_mapping_json(plan_context)
            ),
        )

    def _response_context_is_current(self, context: _WorkflowRequestContext) -> bool:
        workspace_root = None if self.workspace is None else self.workspace.root
        if workspace_root != context.workspace_root or self._operation != context.operation:
            return False
        snapshot = self._active_snapshot
        if snapshot is None:
            if context.snapshot_path is not None or context.snapshot_sha256:
                return False
        elif snapshot.path != context.snapshot_path or snapshot.sha256 != context.snapshot_sha256:
            return False
        plan_context = self._active_plan_context
        current_plan_context_json = (
            "" if plan_context is None else _canonical_mapping_json(plan_context)
        )
        return current_plan_context_json == context.plan_context_json

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

    def _clear_active_attempt(self) -> None:
        self._active_snapshot = None
        self._active_plan_context = None
        self._active_record = None
        self._request_context = None

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
    source_binding_changed = Signal()

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        inspection: InspectionController,
        parent: QObject | None = None,
        *,
        configuration_controller: ConfigurationController | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            kind="preparation",
            configuration_controller=configuration_controller,
            parent=parent,
        )
        self.inspection = inspection
        self._source_binding: _PreparationSourceBinding | None = None
        self._source_binding_issue = ""
        self.preparation_plan_model = PreparationPlanModel(self)
        inspection.inspection_changed.connect(self._inspection_changed)
        if configuration_controller is not None:
            configuration_controller.preparation_draft.profile_changed.connect(
                self.state_changed.emit
            )
            configuration_controller.preparation_draft.capability_changed.connect(
                self.state_changed.emit
            )
        self._refresh_typed_projections()

    def get_preparation_plan_model(self) -> QObject:
        return self.preparation_plan_model

    preparationPlan = Property(QObject, get_preparation_plan_model, constant=True)

    def get_has_bound_source(self) -> bool:
        return self._source_binding is not None

    hasBoundSource = Property(bool, get_has_bound_source, notify=source_binding_changed)

    def get_bound_source_path(self) -> str:
        binding = self._source_binding
        return "" if binding is None else str(binding.source_path)

    boundSourcePath = Property(str, get_bound_source_path, notify=source_binding_changed)

    def get_bound_source_kind(self) -> str:
        binding = self._source_binding
        if binding is None:
            return ""
        value = binding.profile().get("source_kind")
        return value if isinstance(value, str) else ""

    boundSourceKind = Property(str, get_bound_source_kind, notify=source_binding_changed)

    def get_bound_source_revision(self) -> str:
        binding = self._source_binding
        return "" if binding is None else binding.inspection_revision

    boundSourceRevision = Property(
        str,
        get_bound_source_revision,
        notify=source_binding_changed,
    )

    def get_source_binding_issue(self) -> str:
        return self._source_binding_issue

    sourceBindingIssue = Property(
        str,
        get_source_binding_issue,
        notify=source_binding_changed,
    )

    def get_inspected_source_matches_binding(self) -> bool:
        candidate = self._inspected_source_binding()
        return candidate is not None and candidate == self._source_binding

    inspectedSourceMatchesBinding = Property(
        bool,
        get_inspected_source_matches_binding,
        notify=source_binding_changed,
    )

    def get_inspected_source_available(self) -> bool:
        candidate = self._inspected_source_binding()
        return candidate is not None and candidate != self._source_binding

    inspectedSourceAvailable = Property(
        bool,
        get_inspected_source_available,
        notify=source_binding_changed,
    )

    def get_bound_source_refresh_available(self) -> bool:
        binding = self._source_binding
        candidate = self._inspected_source_binding()
        return bool(
            binding is not None
            and candidate is not None
            and candidate.source_path == binding.source_path
            and candidate != binding
        )

    boundSourceRefreshAvailable = Property(
        bool,
        get_bound_source_refresh_available,
        notify=source_binding_changed,
    )

    def bind_inspected_source(self) -> bool:
        candidate = self._inspected_source_binding()
        if candidate is None:
            reason = self.inspection.get_preparation_ineligible_reason()
            self._set_source_binding_issue(
                reason or "Inspect an eligible source before using it for ML Preparation."
            )
            return False
        if candidate == self._source_binding:
            self._set_source_binding_issue("")
            return True
        if self._source_binding_change_blocked():
            self._set_source_binding_issue(
                "The Preparation source cannot change while a worker operation is active."
            )
            return False
        self._source_binding = candidate
        self._set_source_binding_issue("")
        self.source_binding_changed.emit()
        self.state_changed.emit()
        return True

    def clear_bound_source(self) -> bool:
        if self._source_binding is None:
            self._set_source_binding_issue("")
            return True
        if self._source_binding_change_blocked():
            self._set_source_binding_issue(
                "The Preparation source cannot change while a worker operation is active."
            )
            return False
        self._source_binding = None
        self._set_source_binding_issue("")
        self.source_binding_changed.emit()
        self.state_changed.emit()
        return True

    def bound_source_snapshot(
        self,
    ) -> tuple[Path, str, dict[str, Any], dict[str, Any]] | None:
        binding = self._source_binding
        if binding is None:
            return None
        return (
            binding.source_path,
            binding.inspection_revision,
            binding.descriptor(),
            binding.profile(),
        )

    def set_workspace(self, workspace: Workspace | None) -> None:
        changed = workspace != self.workspace
        if changed:
            self._source_binding = None
            self._source_binding_issue = ""
        super().set_workspace(workspace)
        if changed:
            self.source_binding_changed.emit()

    def _plan_context(self) -> dict[str, object]:
        binding = self._source_binding
        if binding is None:
            raise ValueError("use an inspected source for ML Preparation first")
        return binding.plan_context()

    def _workflow_input_issues(self) -> tuple[WorkflowIssue, ...]:
        controller = self.configuration_controller
        if controller is None or controller.get_document_kind() != "preparation":
            return ()
        draft = controller.preparation_draft
        issues: list[WorkflowIssue] = []
        if source_issue := draft.get_source_issue():
            issues.append(
                self._blocking_issue(
                    origin="source",
                    code="preparation_source_incompatible",
                    message=source_issue,
                    section="source",
                    field_id="preparation.source",
                )
            )
        if dependency_issue := draft.get_dependency_issue():
            issues.append(
                self._blocking_issue(
                    origin="dependency",
                    code="preparation_dependency_unavailable",
                    message=dependency_issue,
                    section="outputs",
                    field_id="preparation.outputs",
                )
            )
        return tuple(issues)

    def _accept_plan(self, result: dict[str, object]) -> None:
        projection = PreparationPlanProjection.from_worker_payload(result)
        super()._accept_plan(result)
        self.preparation_plan_model.replace(projection)

    def _clear_plan(self) -> None:
        super()._clear_plan()
        self.preparation_plan_model.clear()

    def _plan_result_matches_current_context(self, result: dict[str, object]) -> bool:
        binding = self._source_binding
        source_revision = result.get("source_revision")
        if binding is None or not isinstance(source_revision, dict):
            return False
        descriptor = binding.descriptor()
        return (
            source_revision.get("inspection_revision") == binding.inspection_revision
            and source_revision.get("inspection_descriptor") == descriptor
            and descriptor.get("source_path") == str(binding.source_path)
        )

    def _activity_source_identity(self) -> dict[str, Any] | None:
        binding = self._source_binding
        if binding is None:
            return None
        profile = binding.profile()
        return {
            "source_path": str(binding.source_path),
            "source_kind": profile.get("source_kind"),
            "inspection_revision": binding.inspection_revision,
            "descriptor": binding.descriptor(),
            "source_identity": copy.deepcopy(profile.get("source_identity")),
        }

    def _inspection_changed(self, _payload: object) -> None:
        self.source_binding_changed.emit()
        self.state_changed.emit()

    def _inspected_source_binding(self) -> _PreparationSourceBinding | None:
        source_snapshot = self.inspection.preparation_source_snapshot()
        profile = self.inspection.preparation_profile_snapshot()
        if source_snapshot is None or profile is None:
            return None
        source, revision, descriptor = source_snapshot
        if (
            profile.get("source_path") != str(source)
            or profile.get("inspection_revision") != revision
            or profile.get("source_kind") != descriptor.get("source_kind")
        ):
            return None
        return _PreparationSourceBinding.create(source, revision, descriptor, profile)

    def _source_binding_change_blocked(self) -> bool:
        return self._session is not None or self.coordinator.is_busy

    def _set_source_binding_issue(self, issue: str) -> None:
        if issue == self._source_binding_issue:
            return
        self._source_binding_issue = issue
        self.source_binding_changed.emit()
        self.state_changed.emit()


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _canonical_mapping_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _mapping_from_json(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):  # pragma: no cover - encoded only by this module
        raise ValueError("Preparation source binding payload is not a mapping")
    return cast(dict[str, Any], decoded)
