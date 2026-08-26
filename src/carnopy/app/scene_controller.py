from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.scene_build import BuildScenePayload, adopt_scene_build
from carnopy.app.scene_bundle import VerifiedSceneBundle
from carnopy.app.scene_contracts import SceneContractError, SceneProfile, SceneSourceBinding
from carnopy.app.scene_draft import (
    SceneBuildSubmission,
    SceneDraft,
    SceneProfileSubmission,
)
from carnopy.app.scene_leases import (
    SceneLease,
    SceneLeasePayload,
    SceneSession,
    create_scene_lease,
)
from carnopy.app.scene_pick_contracts import ResolveScenePickPayload, ScenePickResult

SceneOperation = Literal["", "profile", "build", "update", "pick"]


@dataclass(frozen=True)
class _BuildAttempt:
    lease: SceneLease
    submission: SceneBuildSubmission


@dataclass(frozen=True)
class _PickAttempt:
    payload: ResolveScenePickPayload
    scene_content_id: str
    scene_request_id: str


class SceneController(QObject):
    """Own one explicit scene request, accepted scene, and replacement boundary."""

    state_changed = Signal()
    scene_changed = Signal()
    pick_changed = Signal()
    request_finished = Signal(object)
    lease_retirement_requested = Signal(object)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        draft: SceneDraft | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.draft = SceneDraft(self) if draft is None else draft
        self._scene_session: SceneSession | None = None
        self._session: RequestSession | None = None
        self._operation: SceneOperation = ""
        self._state = "unavailable"
        self._phase = ""
        self._progress_completed = 0
        self._progress_total = 0
        self._issue_category = ""
        self._issue_code = ""
        self._issue = ""
        self._profile_submission: SceneProfileSubmission | None = None
        self._build_attempt: _BuildAttempt | None = None
        self._pick_attempt: _PickAttempt | None = None
        self._scene: VerifiedSceneBundle | None = None
        self._pick: ScenePickResult | None = None
        self._accepted_submission: SceneBuildSubmission | None = None
        self._stale_binding: SceneSourceBinding | None = None
        self.draft.changed.connect(self._draft_changed)
        self.coordinator.busy_changed.connect(self._coordinator_busy_changed)
        self._refresh_idle_state()

    def _constant_draft(self) -> QObject:
        return self.draft

    sceneDraft = Property(QObject, _constant_draft, constant=True)

    def get_state(self) -> str:
        return self._state

    state = Property(str, get_state, notify=state_changed)

    def get_operation(self) -> str:
        return self._operation

    operation = Property(str, get_operation, notify=state_changed)

    def get_phase(self) -> str:
        return self._phase

    phase = Property(str, get_phase, notify=state_changed)

    def get_operation_active(self) -> bool:
        return self._session is not None

    operationActive = Property(bool, get_operation_active, notify=state_changed)

    def get_draft_locked(self) -> bool:
        return self.draft.get_operation_locked()

    draftLocked = Property(bool, get_draft_locked, notify=state_changed)

    def get_progress_available(self) -> bool:
        return self._progress_total > 0

    progressAvailable = Property(bool, get_progress_available, notify=state_changed)

    def get_progress_completed(self) -> int:
        return self._progress_completed

    progressCompleted = Property(int, get_progress_completed, notify=state_changed)

    def get_progress_total(self) -> int:
        return self._progress_total

    progressTotal = Property(int, get_progress_total, notify=state_changed)

    def get_issue_category(self) -> str:
        return self._issue_category

    issueCategory = Property(str, get_issue_category, notify=state_changed)

    def get_issue_code(self) -> str:
        return self._issue_code

    issueCode = Property(str, get_issue_code, notify=state_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=state_changed)

    def get_has_scene(self) -> bool:
        return self._scene is not None

    hasScene = Property(bool, get_has_scene, notify=scene_changed)

    def get_scene_request_id(self) -> str:
        submission = self._accepted_submission
        return "" if submission is None else submission.request_id

    sceneRequestId = Property(str, get_scene_request_id, notify=scene_changed)

    def get_scene_content_id(self) -> str:
        scene = self._scene
        return "" if scene is None else scene.manifest.content_id

    sceneContentId = Property(str, get_scene_content_id, notify=scene_changed)

    def get_has_pick(self) -> bool:
        return self._pick is not None

    hasPick = Property(bool, get_has_pick, notify=pick_changed)

    def get_submitted_request_id(self) -> str:
        attempt = self._build_attempt
        return "" if attempt is None else attempt.submission.request_id

    submittedRequestId = Property(str, get_submitted_request_id, notify=state_changed)

    def get_settings_stale(self) -> bool:
        accepted = self._accepted_submission
        if accepted is None:
            return False
        return self.draft.get_request_id() != accepted.request_id

    settingsStale = Property(bool, get_settings_stale, notify=state_changed)

    def get_source_stale(self) -> bool:
        accepted = self._accepted_submission
        binding = (
            accepted.request.binding if accepted is not None else self.draft.binding_snapshot()
        )
        return binding is not None and binding == self._stale_binding

    sourceStale = Property(bool, get_source_stale, notify=state_changed)

    def get_draft_source_stale(self) -> bool:
        binding = self.draft.binding_snapshot()
        return binding is not None and binding == self._stale_binding

    draftSourceStale = Property(bool, get_draft_source_stale, notify=state_changed)

    def get_scene_session_available(self) -> bool:
        session = self._scene_session
        return session is not None and session.is_active

    sceneSessionAvailable = Property(
        bool,
        get_scene_session_available,
        notify=state_changed,
    )

    def get_can_profile(self) -> bool:
        return (
            self._session is None
            and not self.coordinator.is_busy
            and self.draft.get_can_profile()
            and not self.get_draft_source_stale()
        )

    canProfile = Property(bool, get_can_profile, notify=state_changed)

    def get_can_build(self) -> bool:
        return (
            self._session is None
            and not self.coordinator.is_busy
            and self.get_scene_session_available()
            and self.draft.get_can_build()
            and not self.get_draft_source_stale()
        )

    canBuild = Property(bool, get_can_build, notify=state_changed)

    def get_can_resolve_pick(self) -> bool:
        return (
            self._session is None
            and not self.coordinator.is_busy
            and self._scene is not None
            and self._accepted_submission is not None
            and not self.get_source_stale()
        )

    canResolvePick = Property(bool, get_can_resolve_pick, notify=state_changed)

    def get_cancellation_available(self) -> bool:
        session = self._session
        return session is not None and session.cooperative_cancel_available

    cancellationAvailable = Property(
        bool,
        get_cancellation_available,
        notify=state_changed,
    )

    def get_protected_finalization(self) -> bool:
        session = self._session
        return session is not None and session.termination_protected

    protectedFinalization = Property(
        bool,
        get_protected_finalization,
        notify=state_changed,
    )

    def get_force_stop_available(self) -> bool:
        session = self._session
        return session is not None and session.force_stop_available

    forceStopAvailable = Property(
        bool,
        get_force_stop_available,
        notify=state_changed,
    )

    def set_scene_session(self, session: SceneSession | None) -> None:
        """Borrow the workspace session owned by the desktop scene lifecycle."""

        if self._session is not None:
            raise RuntimeError("cannot replace the scene session during an active request")
        if session is not None and not session.is_active:
            raise ValueError("scene controller requires an active scene session")
        if session is self._scene_session:
            return
        self._scene_session = session
        self.state_changed.emit()

    def current_scene_snapshot(self) -> VerifiedSceneBundle | None:
        return self._scene

    def current_submission_snapshot(self) -> SceneBuildSubmission | None:
        return self._accepted_submission

    def current_pick_snapshot(self) -> ScenePickResult | None:
        pick = self._pick
        return None if pick is None else pick.model_copy(deep=True)

    def reset_workspace_state(self) -> bool:
        """Release session-only scene state before its workspace owner changes."""

        if self._session is not None:
            raise RuntimeError("cannot reset scene state during an active request")
        scene = self._scene
        changed = (
            scene is not None
            or self._accepted_submission is not None
            or self._stale_binding is not None
            or self.draft.get_binding_available()
            or self._state != "unavailable"
            or bool(self._phase)
            or self._progress_total > 0
            or bool(self._issue)
        )
        self._scene = None
        self._accepted_submission = None
        self._stale_binding = None
        self._profile_submission = None
        self._build_attempt = None
        self._pick_attempt = None
        self._operation = ""
        self._phase = ""
        self._progress_completed = 0
        self._progress_total = 0
        self._clear_failure()
        self.draft.clear()
        pick_changed = self._clear_pick()
        self._refresh_idle_state()
        if changed:
            self.scene_changed.emit()
            self.state_changed.emit()
        if pick_changed:
            self.pick_changed.emit()
        if scene is not None:
            self.lease_retirement_requested.emit(scene.lease)
        return changed

    @Slot(result=bool)
    def profile(self) -> bool:
        if not self.get_can_profile():
            return False
        try:
            submission = self.draft.create_profile_submission()
        except SceneContractError as exc:
            self._set_local_failure("request", exc.code, exc.message)
            return False
        self._prepare_request("profile", "Starting scene profile")
        self._profile_submission = submission
        try:
            session = self.coordinator.start_request(
                "scene",
                "profile_scene",
                submission.worker_payload(),
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            self._profile_submission = None
            self._finish_start_failure(exc)
            return False
        self._adopt_request_session(session)
        return True

    @Slot(result=bool)
    def build(self) -> bool:
        scene_session = self._scene_session
        if not self.get_can_build() or scene_session is None:
            return False
        try:
            submission = self.draft.create_build_submission()
        except SceneContractError as exc:
            self._set_local_failure("request", exc.code, exc.message)
            return False
        operation: Literal["build", "update"] = "update" if self._scene else "build"
        self._prepare_request(operation, "Starting scene worker")
        lease: SceneLease | None = None
        try:
            lease = create_scene_lease(scene_session)
            attempt = _BuildAttempt(
                lease=lease,
                submission=submission,
            )
            payload = BuildScenePayload(
                workspace_path=scene_session.workspace_root,
                lease=SceneLeasePayload.model_validate(
                    lease.worker_payload(),
                    strict=True,
                ),
                profile=submission.profile,
                request=submission.request,
            )
            self._build_attempt = attempt
            session = self.coordinator.start_request(
                "scene",
                "build_scene",
                payload.model_dump(mode="json"),
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            self._build_attempt = None
            if lease is not None:
                self.lease_retirement_requested.emit(lease)
            self._finish_start_failure(exc)
            return False
        self._adopt_request_session(session)
        return True

    def resolve_pick(self, row_position: int, stable_id: int) -> bool:
        """Resolve one identity emitted by the currently verified scene."""

        scene = self._scene
        submission = self._accepted_submission
        if not self.get_can_resolve_pick() or scene is None or submission is None:
            return False
        try:
            payload = ResolveScenePickPayload(
                binding=submission.request.binding,
                row_position=row_position,
                stable_id=stable_id,
            )
        except ValueError as exc:
            self._set_local_failure("request", "scene_pick_stale", str(exc))
            return False
        if self._clear_pick():
            self.pick_changed.emit()
        self._clear_failure()
        self._operation = "pick"
        self._state = "resolving_pick"
        self._phase = "Resolving exact scene row"
        self._progress_completed = 0
        self._progress_total = 0
        attempt = _PickAttempt(
            payload=payload,
            scene_content_id=scene.manifest.content_id,
            scene_request_id=submission.request_id,
        )
        self._pick_attempt = attempt
        self.state_changed.emit()
        try:
            session = self.coordinator.start_request(
                "scene",
                "resolve_scene_pick",
                payload.model_dump(mode="json"),
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            self._pick_attempt = None
            self._finish_start_failure(exc, unlock_draft=False)
            return False
        self._adopt_request_session(session)
        return True

    def clear_pick(self) -> bool:
        """Clear resolved details without changing the accepted scene."""

        if not self._clear_pick():
            return False
        self.pick_changed.emit()
        return True

    @Slot(result=bool)
    def cancel(self) -> bool:
        session = self._session
        if session is None or not session.cancel():
            return False
        self._state = "cancelling"
        self._phase = "Cancellation requested"
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="forceStop")
    def force_stop(self) -> bool:
        session = self._session
        if session is None or not session.force_stop():
            return False
        self._state = "force_stopping"
        self._phase = "Force-stopping scene worker"
        self.state_changed.emit()
        return True

    def mark_current_source_stale(self) -> bool:
        """Conservatively disable source-dependent actions for the accepted snapshot."""

        accepted = self._accepted_submission
        if accepted is None or accepted.request.binding == self._stale_binding:
            return False
        self._stale_binding = accepted.request.binding.model_copy(deep=True)
        if self._clear_pick():
            self.pick_changed.emit()
        if self._session is None:
            self._state = "source_stale"
        self.state_changed.emit()
        return True

    def _prepare_request(self, operation: SceneOperation, phase: str) -> None:
        self._clear_failure()
        self._operation = operation
        self._state = {
            "profile": "profiling",
            "build": "building",
            "update": "updating",
        }[operation]
        self._phase = phase
        self._progress_completed = 0
        self._progress_total = 0
        self.draft._set_operation_locked(True)
        self.state_changed.emit()

    def _adopt_request_session(self, session: RequestSession) -> None:
        self._session = session
        session.phase_changed.connect(self._phase_changed)
        session.progress_received.connect(self._progress_received)
        session.policy_changed.connect(self.state_changed)
        session.completed.connect(self._request_completed)
        self.state_changed.emit()

    def _phase_changed(self, name: str, _cancellable: bool) -> None:
        self._phase = name
        self.state_changed.emit()

    def _progress_received(self, value: object) -> None:
        if not isinstance(value, Mapping):
            return
        completed = value.get("completed")
        total = value.get("total")
        if (
            isinstance(completed, bool)
            or not isinstance(completed, int)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or total <= 0
            or completed < 0
            or completed > total
        ):
            return
        self._progress_completed = completed
        self._progress_total = total
        self.state_changed.emit()

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        operation = self._operation
        profile_submission = self._profile_submission
        build_attempt = self._build_attempt
        pick_attempt = self._pick_attempt
        self._session = None
        self._operation = ""
        self._profile_submission = None
        self._build_attempt = None
        self._pick_attempt = None
        if operation != "pick":
            self.draft._set_operation_locked(False)
        result = outcome.result_payload
        if operation == "profile" and profile_submission is not None and result is not None:
            self._accept_profile_result(profile_submission, result)
        elif operation in {"build", "update"} and build_attempt is not None:
            if result is None:
                self.lease_retirement_requested.emit(build_attempt.lease)
                self._accept_outcome_failure(outcome, build_attempt.submission.request.binding)
            else:
                self._accept_build_result(build_attempt, result)
        elif operation == "pick" and pick_attempt is not None:
            if result is None:
                self._accept_outcome_failure(outcome, pick_attempt.payload.binding)
            else:
                self._accept_pick_result(pick_attempt, result)
        else:
            self._accept_outcome_failure(
                outcome,
                None if profile_submission is None else profile_submission.binding,
            )
        self.request_finished.emit(outcome.terminal_envelope)
        self.state_changed.emit()

    def _accept_profile_result(
        self,
        submission: SceneProfileSubmission,
        result: Mapping[str, object],
    ) -> None:
        try:
            profile = SceneProfile.model_validate(result)
            if profile.binding != submission.binding:
                raise SceneContractError(
                    "invalid_scene_profile",
                    "scene profile result does not match its submitted binding",
                )
            self.draft.accept_profile(profile)
        except (SceneContractError, ValueError) as exc:
            code = exc.code if isinstance(exc, SceneContractError) else "invalid_scene_profile"
            self._set_local_failure("integrity", code, str(exc))
            return
        if self._stale_binding == submission.binding:
            self._stale_binding = None
        self._phase = "Completed"
        self._clear_failure()
        self._refresh_idle_state()

    def _accept_build_result(
        self,
        attempt: _BuildAttempt,
        result: Mapping[str, object],
    ) -> None:
        try:
            scene = adopt_scene_build(
                attempt.lease,
                attempt.submission.profile,
                attempt.submission.request,
                dict(result),
            )
        except SceneContractError as exc:
            self.lease_retirement_requested.emit(attempt.lease)
            self._set_local_failure("integrity", exc.code, exc.message)
            return
        previous = self._scene
        had_pick = self._clear_pick()
        self._scene = scene
        self._accepted_submission = attempt.submission
        if self._stale_binding == attempt.submission.request.binding:
            self._stale_binding = None
        self._phase = "Completed"
        self._clear_failure()
        self._refresh_idle_state()
        self.scene_changed.emit()
        if had_pick:
            self.pick_changed.emit()
        if previous is not None and previous.lease != scene.lease:
            self.lease_retirement_requested.emit(previous.lease)

    def _accept_pick_result(
        self,
        attempt: _PickAttempt,
        result: Mapping[str, object],
    ) -> None:
        scene = self._scene
        submission = self._accepted_submission
        try:
            pick = ScenePickResult.model_validate(result)
            if (
                scene is None
                or submission is None
                or scene.manifest.content_id != attempt.scene_content_id
                or submission.request_id != attempt.scene_request_id
            ):
                raise SceneContractError(
                    "scene_pick_stale",
                    "scene changed while its picked row was being resolved",
                )
            binding = attempt.payload.binding
            table = binding.selected_table()
            expected_stable_field = (
                "prepared_row_id" if binding.source_kind == "preparation" else "case_id"
            )
            if (
                pick.source_path != binding.source_path
                or pick.source_kind != binding.source_kind
                or pick.inspection_revision != binding.inspection_revision
                or pick.table_id != binding.selected_table_id
                or pick.table_sha256 != table.artifact.sha256
                or pick.row_position != attempt.payload.row_position
                or pick.stable_id_field != expected_stable_field
                or pick.stable_id != attempt.payload.stable_id
            ):
                raise SceneContractError(
                    "scene_pick_stale",
                    "scene pick result does not match its submitted identity",
                )
            if binding.source_kind == "preparation":
                context = pick.prepared_context
                tables = {item.table_id: item for item in binding.tables}
                if (
                    context is None
                    or context.provenance.table_sha256 != tables["provenance"].artifact.sha256
                    or context.diagnostics.table_sha256 != tables["diagnostics"].artifact.sha256
                ):
                    raise SceneContractError(
                        "scene_pick_stale",
                        "prepared scene pick evidence does not match its bound support tables",
                    )
        except (SceneContractError, ValueError) as exc:
            code = exc.code if isinstance(exc, SceneContractError) else "scene_pick_stale"
            self._set_local_failure("integrity", code, str(exc))
            return
        self._pick = pick.model_copy(deep=True)
        self._phase = "Completed"
        self._clear_failure()
        self._refresh_idle_state()
        self.pick_changed.emit()

    def _accept_outcome_failure(
        self,
        outcome: RequestOutcome,
        submitted_binding: SceneSourceBinding | None,
    ) -> None:
        payload = outcome.failure_payload or {}
        code = _text(payload.get("code"), "execution_failed")
        if code == "scene_source_changed" and submitted_binding is not None:
            self._stale_binding = submitted_binding.model_copy(deep=True)
        cancelled = (
            outcome.terminal_event is not None and outcome.terminal_event.type == "cancelled"
        )
        self._state = "cancelled" if cancelled else "failed"
        if code == "scene_source_changed" and self.get_source_stale():
            self._state = "source_stale"
            if self._clear_pick():
                self.pick_changed.emit()
        self._phase = "Cancelled" if cancelled else "Failed"
        self._issue_category = _text(payload.get("category"), "execution")
        self._issue_code = code
        self._issue = _text(payload.get("message"), "scene request failed")

    def _finish_start_failure(self, exc: Exception, *, unlock_draft: bool = True) -> None:
        self._operation = ""
        if unlock_draft:
            self.draft._set_operation_locked(False)
        self._set_local_failure("process", "worker_start_failed", str(exc))

    def _set_local_failure(self, category: str, code: str, message: str) -> None:
        self._state = "failed"
        self._phase = "Failed"
        self._issue_category = category
        self._issue_code = code
        self._issue = message
        self.state_changed.emit()

    def _clear_failure(self) -> None:
        self._issue_category = ""
        self._issue_code = ""
        self._issue = ""

    def _clear_pick(self) -> bool:
        if self._pick is None:
            return False
        self._pick = None
        return True

    def _draft_changed(self) -> None:
        if self._session is None:
            self._refresh_idle_state()
        self.state_changed.emit()

    def _coordinator_busy_changed(self, _busy: bool) -> None:
        self.state_changed.emit()

    def _refresh_idle_state(self) -> None:
        if self._session is not None:
            return
        if self._scene is not None:
            if self.get_source_stale():
                self._state = "source_stale"
            elif self.get_settings_stale():
                self._state = "settings_stale"
            else:
                self._state = "succeeded"
        elif not self.draft.get_binding_available():
            self._state = "unavailable"
        elif not self.draft.get_profile_available():
            self._state = "unprofiled"
        else:
            self._state = "ready"


def _text(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback
