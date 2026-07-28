from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from carnopy.app.export_cleanup import ImageExportFinalizer
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.plot_artifacts import (
    PlotArtifactError,
    VerifiedPlotArtifact,
    export_verified_plot_bundle,
    validated_plot_bytes,
    verify_session_plot_result,
)
from carnopy.app.plot_draft import PlotDraft
from carnopy.app.plot_preview_provider import VerifiedPlotPreviewRegistry
from carnopy.app.plot_staging import create_plot_staging
from carnopy.app.protocol import WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.workspace import Workspace


class SessionPlotController(QObject):
    """Own one inspected-data plot edit, render request, and committed session result."""

    state_changed = Signal()
    active_edit_changed = Signal()
    render_finished = Signal(object)
    attention_requested = Signal(str, int)
    export_succeeded = Signal(str, str)
    exportSucceeded = Signal(str, str)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        inspection: InspectionController,
        previews: VerifiedPlotPreviewRegistry,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.inspection = inspection
        self.previews = previews
        self.workspace: Workspace | None = None
        self._state = "unavailable"
        self._phase = ""
        self._issue_category = ""
        self._issue_code = ""
        self._issue = "Inspect a dataset source before creating a session plot."
        self._issues: list[dict[str, object]] = []
        self._active_draft: PlotDraft | None = None
        self._session: RequestSession | None = None
        self._source_path: Path | None = None
        self._source_revision = ""
        self._context: dict[str, Any] | None = None
        self._submitted_request: dict[str, Any] | None = None
        self._committed_request: dict[str, Any] | None = None
        self._result: dict[str, Any] | None = None
        self._artifact: VerifiedPlotArtifact | None = None
        self._verification_revision = ""
        self._preview_token = ""
        self._preview_url = ""
        self._cleanup_issue = ""
        inspection.inspection_changed.connect(self._inspection_changed)
        coordinator.busy_changed.connect(lambda _busy: self.state_changed.emit())

    def get_state(self) -> str:
        return self._state

    state = Property(str, get_state, notify=state_changed)

    def get_phase(self) -> str:
        return self._phase

    phase = Property(str, get_phase, notify=state_changed)

    def get_issue_category(self) -> str:
        return self._issue_category

    issueCategory = Property(str, get_issue_category, notify=state_changed)

    def get_issue_code(self) -> str:
        return self._issue_code

    issueCode = Property(str, get_issue_code, notify=state_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=state_changed)

    def get_cleanup_issue(self) -> str:
        return self._cleanup_issue

    cleanupIssue = Property(str, get_cleanup_issue, notify=state_changed)

    def get_issues(self) -> list[dict[str, object]]:
        return copy.deepcopy(self._issues)

    issues = Property(object, get_issues, notify=state_changed)

    def get_active_plot_draft(self) -> QObject | None:
        return self._active_draft

    activePlotDraft = Property(
        QObject,
        get_active_plot_draft,
        notify=active_edit_changed,
    )

    def get_has_active_edit(self) -> bool:
        return self._active_draft is not None

    hasActiveEdit = Property(bool, get_has_active_edit, notify=active_edit_changed)

    def get_has_result(self) -> bool:
        return self._result is not None and self._artifact is not None

    hasResult = Property(bool, get_has_result, notify=state_changed)

    def get_is_rendering(self) -> bool:
        return self._session is not None

    isRendering = Property(bool, get_is_rendering, notify=state_changed)

    def get_source_path(self) -> str:
        return "" if self._source_path is None else str(self._source_path)

    sourcePath = Property(str, get_source_path, notify=state_changed)

    def get_committed_request(self) -> dict[str, object]:
        return {} if self._committed_request is None else copy.deepcopy(self._committed_request)

    committedRequest = Property(object, get_committed_request, notify=state_changed)

    def get_result(self) -> dict[str, object]:
        return {} if self._result is None else copy.deepcopy(self._result)

    result = Property(object, get_result, notify=state_changed)

    def get_preview_url(self) -> str:
        return self._preview_url

    previewUrl = Property(str, get_preview_url, notify=state_changed)

    def get_result_name(self) -> str:
        return "" if self._artifact is None else self._artifact.name

    resultName = Property(str, get_result_name, notify=state_changed)

    def get_result_kind(self) -> str:
        return "" if self._artifact is None else self._artifact.kind

    resultKind = Property(str, get_result_kind, notify=state_changed)

    def get_result_format(self) -> str:
        return "" if self._artifact is None else self._artifact.image_format

    resultFormat = Property(str, get_result_format, notify=state_changed)

    def get_valid_sample_count(self) -> int:
        return 0 if self._artifact is None else self._artifact.valid_sample_count

    validSampleCount = Property(int, get_valid_sample_count, notify=state_changed)

    def get_excluded_sample_count(self) -> int:
        return 0 if self._artifact is None else self._artifact.excluded_sample_count

    excludedSampleCount = Property(int, get_excluded_sample_count, notify=state_changed)

    def get_can_preview(self) -> bool:
        return bool(self._preview_url)

    canPreview = Property(bool, get_can_preview, notify=state_changed)

    def get_can_open_pdf(self) -> bool:
        return self._artifact is not None and self._artifact.image_format == "pdf"

    canOpenPdf = Property(bool, get_can_open_pdf, notify=state_changed)

    def get_can_export(self) -> bool:
        return self._artifact is not None

    canExport = Property(bool, get_can_export, notify=state_changed)

    def get_can_begin_edit(self) -> bool:
        return (
            self._context is not None
            and self._active_draft is None
            and not self.coordinator.is_busy
        )

    canBeginEdit = Property(bool, get_can_begin_edit, notify=state_changed)

    def get_can_render(self) -> bool:
        draft = self._active_draft
        return (
            draft is not None
            and draft.get_locally_valid()
            and self.workspace is not None
            and self._source_path is not None
            and bool(self._source_revision)
            and not self.coordinator.is_busy
        )

    canRender = Property(bool, get_can_render, notify=state_changed)

    def get_can_force_stop(self) -> bool:
        return self._session is not None and self._session.force_stop_available

    canForceStop = Property(bool, get_can_force_stop, notify=state_changed)

    def set_workspace(self, workspace: Workspace | None) -> None:
        if workspace == self.workspace:
            return
        if not self.can_replace_inspection("replacing the workspace"):
            return
        self.workspace = workspace
        self._replace_context(None)

    @Slot(str, result=bool, name="beginEdit")
    def begin_edit(self, output_format: str = "png") -> bool:
        context = self._context
        if context is None or self._active_draft is not None or self.coordinator.is_busy:
            return False
        initial = copy.deepcopy(self._committed_request)
        draft = PlotDraft(context, context, initial, self, allow_format=True)
        if initial is None:
            draft.set_name("session-plot")
        draft.set_output_format(output_format)
        self._active_draft = draft
        draft.changed.connect(self.state_changed)
        draft.validity_changed.connect(self.state_changed)
        self._clear_failure()
        self._state = "editing"
        self.active_edit_changed.emit()
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="cancelEdit")
    def cancel_edit(self) -> bool:
        draft = self._active_draft
        if draft is None or self._session is not None:
            return False
        self._active_draft = None
        draft.deleteLater()
        self._state = "succeeded" if self._result is not None else "ready"
        self._clear_failure()
        self.active_edit_changed.emit()
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="render")
    def render(self) -> bool:
        draft = self._active_draft
        workspace = self.workspace
        source = self._source_path
        revision = self._source_revision
        if draft is None:
            return False
        if not draft.get_locally_valid():
            self._state = "editing"
            self._issue_category = "config"
            self._issue_code = "invalid_plot_request"
            self._issue = draft.get_issue()
            self._issues = [
                {
                    "field": draft.get_first_invalid_field(),
                    "row": draft.get_first_invalid_row(),
                    "message": draft.get_issue(),
                }
            ]
            self.attention_requested.emit(
                draft.get_first_invalid_field(),
                draft.get_first_invalid_row(),
            )
            self.state_changed.emit()
            return False
        if workspace is None or source is None or not revision or self.coordinator.is_busy:
            return False
        request = draft.payload()
        output_format = str(request.get("format", ""))
        plot_name = str(request.get("name", ""))
        finalizer: ImageExportFinalizer | None = None
        self._clear_failure()
        self._state = "starting"
        self._phase = "Starting plot worker"
        self.state_changed.emit()
        try:
            lease = create_plot_staging(workspace.root)
            finalizer = ImageExportFinalizer(lease)
            session = self.coordinator.start_request(
                "plot",
                "render_plot",
                {
                    "workspace_path": str(workspace.root),
                    "source_path": str(source),
                    "inspection_revision": revision,
                    "plot_name": plot_name,
                    "format": output_format,
                    "plot": copy.deepcopy(request),
                    "staging": lease.worker_payload(),
                },
                finalizer=finalizer,
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            if finalizer is not None:
                finalizer.finish(False)
            self._state = "editing"
            self._issue_category = "process"
            self._issue_code = "worker_start_failed"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        self._submitted_request = copy.deepcopy(request)
        self._session = session
        session.event_received.connect(self._event_received)
        session.policy_changed.connect(self.state_changed)
        session.completed.connect(self._request_completed)
        self._state = "running"
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="forceStop")
    def force_stop(self) -> bool:
        session = self._session
        if session is None:
            return False
        stopped = session.force_stop()
        if stopped:
            self._state = "force_stopping"
            self._phase = "Force-stopping plot worker"
            self.state_changed.emit()
        return stopped

    @Slot(str, result=bool, name="exportResult")
    def export_result(self, destination: str) -> bool:
        artifact = self._fresh_artifact()
        if artifact is None:
            return False
        try:
            image_path, sidecar_path = export_verified_plot_bundle(
                artifact,
                Path(destination),
            )
        except (OSError, PlotArtifactError) as exc:
            self._issue_category = "integrity"
            self._issue_code = "plot_export_failed"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        self.export_succeeded.emit(str(image_path), str(sidecar_path))
        self.exportSucceeded.emit(str(image_path), str(sidecar_path))
        return True

    @Slot(result=bool, name="openResultPdf")
    def open_result_pdf(self) -> bool:
        artifact = self._fresh_artifact()
        if artifact is None or artifact.image_format != "pdf":
            return False
        try:
            validated_plot_bytes(
                artifact.figures_root,
                artifact.image_path,
                "pdf",
                artifact.image_sha256,
            )
        except PlotArtifactError as exc:
            self._issue_category = "integrity"
            self._issue_code = "plot_evidence_mismatch"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(artifact.image_path)))

    def committed_result_payload(self) -> dict[str, Any] | None:
        return None if self._result is None else copy.deepcopy(self._result)

    def can_replace_inspection(self, operation: str) -> bool:
        if self._active_draft is None:
            return True
        self._issue_category = "lifecycle"
        self._issue_code = "active_session_plot_edit"
        self._issue = f"Render or cancel the session plot edit before {operation}."
        self.state_changed.emit()
        return False

    def _inspection_changed(self, payload: object) -> None:
        self._replace_context(payload if isinstance(payload, dict) else None)

    def _replace_context(self, payload: dict[str, Any] | None) -> None:
        if self._active_draft is not None:
            return
        self._source_path = None
        self._source_revision = ""
        self._context = None
        self._clear_result()
        if payload is not None and payload.get("source_kind") == "dataset":
            source = payload.get("source")
            revision = payload.get("revision")
            context = payload.get("plot_context")
            if isinstance(source, str) and isinstance(revision, str) and isinstance(context, dict):
                self._source_path = Path(source).expanduser().resolve()
                self._source_revision = revision
                self._context = copy.deepcopy(context)
        self._state = "ready" if self._context is not None else "unavailable"
        self._issue = (
            "" if self._context is not None else "Inspect a dataset source before plotting."
        )
        self._issue_category = ""
        self._issue_code = ""
        self._issues = []
        self.state_changed.emit()

    def _event_received(self, value: object) -> None:
        event = cast(WorkerEvent, value)
        if event.type == "phase":
            self._phase = str(event.payload.get("name", "unknown"))
            self.state_changed.emit()

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        self._session = None
        self._cleanup_issue = outcome.cleanup_error or ""
        self.render_finished.emit(outcome.terminal_envelope)
        result = outcome.result_payload
        if result is not None:
            self._accept_result(cast(dict[str, Any], result))
        else:
            self._accept_failure(outcome.failure_payload or {})

    def _accept_result(self, result: dict[str, Any]) -> None:
        workspace = self.workspace
        source = self._source_path
        if workspace is None or source is None:
            self._accept_failure(
                {
                    "category": "lifecycle",
                    "code": "stale_plot_result",
                    "message": "plot result no longer belongs to the active workspace source",
                }
            )
            return
        try:
            artifact, revision = verify_session_plot_result(
                workspace,
                source_path=source,
                inspection_revision=self._source_revision,
                result=result,
            )
        except PlotArtifactError as exc:
            self._accept_failure(
                {
                    "category": "integrity",
                    "code": "plot_evidence_mismatch",
                    "message": str(exc),
                }
            )
            return
        self._artifact = artifact
        self._verification_revision = revision
        self._result = copy.deepcopy(result)
        self._committed_request = copy.deepcopy(self._submitted_request)
        self._submitted_request = None
        self._replace_preview_token()
        draft = self._active_draft
        self._active_draft = None
        if draft is not None:
            draft.deleteLater()
            self.active_edit_changed.emit()
        self._state = "succeeded"
        self._phase = "Completed"
        self._clear_failure()
        if self._cleanup_issue:
            self._issue_category = "cleanup"
            self._issue_code = "cleanup_warning"
            self._issue = self._cleanup_issue
        self.state_changed.emit()

    def _accept_failure(self, payload: Mapping[str, object]) -> None:
        self._state = "editing" if self._active_draft is not None else "failed"
        self._phase = "Render failed"
        self._issue_category = _text(payload.get("category"), "execution")
        self._issue_code = _text(payload.get("code"), "execution_failed")
        self._issue = _text(payload.get("message"), "plot rendering failed")
        if self._cleanup_issue:
            self._issue = f"{self._issue}\nCleanup warning: {self._cleanup_issue}"
        details = payload.get("details")
        raw_issues = details.get("issues") if isinstance(details, Mapping) else None
        self._issues = (
            [dict(item) for item in raw_issues if isinstance(item, Mapping)]
            if isinstance(raw_issues, list)
            else []
        )
        structured = next(
            (
                item
                for item in self._issues
                if isinstance(item.get("field"), str) and item.get("field")
            ),
            None,
        )
        if structured is not None:
            row = structured.get("row")
            self.attention_requested.emit(
                str(structured["field"]),
                row if isinstance(row, int) else -1,
            )
        self.state_changed.emit()

    def _replace_preview_token(self) -> None:
        if self._preview_token:
            self.previews.revoke(self._preview_token)
        self._preview_token = ""
        self._preview_url = ""
        artifact = self._artifact
        workspace = self.workspace
        if artifact is None or workspace is None or artifact.image_format not in {"png", "svg"}:
            return
        self._preview_token = self.previews.issue(
            workspace_identity=str(workspace.root),
            figures_root=workspace.figures,
            image_path=artifact.image_path,
            image_sha256=artifact.image_sha256,
            image_format=artifact.image_format,
            verification_revision=self._verification_revision,
        )
        self._preview_url = self.previews.url(self._preview_token)

    def _fresh_artifact(self) -> VerifiedPlotArtifact | None:
        workspace = self.workspace
        source = self._source_path
        result = self._result
        if self._artifact is None or workspace is None or source is None or result is None:
            return None
        try:
            artifact, revision = verify_session_plot_result(
                workspace,
                source_path=source,
                inspection_revision=self._source_revision,
                result=result,
            )
        except PlotArtifactError as exc:
            self._issue_category = "integrity"
            self._issue_code = "plot_evidence_mismatch"
            self._issue = str(exc)
            self.state_changed.emit()
            return None
        self._artifact = artifact
        self._verification_revision = revision
        self._replace_preview_token()
        self.state_changed.emit()
        return artifact

    def _clear_result(self) -> None:
        if self._preview_token:
            self.previews.revoke(self._preview_token)
        self._preview_token = ""
        self._preview_url = ""
        self._submitted_request = None
        self._committed_request = None
        self._result = None
        self._artifact = None
        self._verification_revision = ""
        self._cleanup_issue = ""

    def _clear_failure(self) -> None:
        self._issue_category = ""
        self._issue_code = ""
        self._issue = ""
        self._issues = []


def _text(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback
