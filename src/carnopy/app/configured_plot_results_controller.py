from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from carnopy.app.activity_controller import ActivityController
from carnopy.app.config_controller import DatasetConfigController
from carnopy.app.inspection_models import InspectionListModel
from carnopy.app.plot_artifacts import (
    PlotArtifactError,
    VerifiedConfiguredPlotBundle,
    VerifiedPlotArtifact,
    VerifiedPlotOutcome,
    export_verified_plot_bundle,
    validated_plot_bytes,
    verify_configured_plot_record,
)
from carnopy.app.plot_preview_provider import VerifiedPlotPreviewRegistry
from carnopy.app.workspace import Workspace

_RECORD_ROLES = (
    "requestId",
    "runId",
    "createdAtUtc",
    "configurationPath",
    "configurationSha256",
    "visualizationStatus",
    "hasRecordedVisualization",
)
_OUTCOME_ROLES = (
    "index",
    "name",
    "kind",
    "status",
    "format",
    "previewAvailable",
    "openExternally",
    "validSampleCount",
    "excludedSampleCount",
    "issue",
)


class ConfiguredPlotResultsController(QObject):
    """Project configured plot evidence exclusively from persisted generation records."""

    state_changed = Signal()
    export_succeeded = Signal(str, str)

    def __init__(
        self,
        activity: ActivityController,
        configuration: DatasetConfigController,
        previews: VerifiedPlotPreviewRegistry,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.activity = activity
        self.configuration = configuration
        self.previews = previews
        self.workspace: Workspace | None = None
        self.records_model = InspectionListModel(_RECORD_ROLES, self)
        self.outcomes_model = InspectionListModel(_OUTCOME_ROLES, self)
        self._state = "unavailable"
        self._issue = "Open a workspace to review configured plot results."
        self._selected_record_id = ""
        self._selected_outcome_index = -1
        self._bundle: VerifiedConfiguredPlotBundle | None = None
        self._preview_token = ""
        self._preview_url = ""
        self._result_configuration_path = ""
        self._result_configuration_sha256 = ""
        self._result_matches_current_saved_baseline = False
        self._current_draft_dirty = False
        self._result_relation_issue = ""
        self.activity.records_changed.connect(self.refresh)
        self.configuration.state_changed.connect(self._refresh_relation)

    def get_records_model(self) -> QObject:
        return self.records_model

    generationRecordsModel = Property(QObject, get_records_model, constant=True)

    def get_outcomes_model(self) -> QObject:
        return self.outcomes_model

    outcomesModel = Property(QObject, get_outcomes_model, constant=True)

    def get_state(self) -> str:
        return self._state

    state = Property(str, get_state, notify=state_changed)

    def get_evidence_label(self) -> str:
        return {
            "consistent": "Recorded provenance consistent",
            "incomplete": "Evidence incomplete",
            "mismatch": "Provenance mismatch",
        }.get(self._state, "")

    evidenceLabel = Property(str, get_evidence_label, notify=state_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=state_changed)

    def get_selected_record_id(self) -> str:
        return self._selected_record_id

    selectedRecordId = Property(str, get_selected_record_id, notify=state_changed)

    def get_selected_outcome_index(self) -> int:
        return self._selected_outcome_index

    selectedOutcomeIndex = Property(int, get_selected_outcome_index, notify=state_changed)

    def get_preview_url(self) -> str:
        return self._preview_url

    previewUrl = Property(str, get_preview_url, notify=state_changed)

    def get_selected_format(self) -> str:
        artifact = self._selected_artifact()
        return "" if artifact is None else artifact.image_format

    selectedFormat = Property(str, get_selected_format, notify=state_changed)

    def get_can_preview(self) -> bool:
        return bool(self._preview_url)

    canPreview = Property(bool, get_can_preview, notify=state_changed)

    def get_can_open_pdf(self) -> bool:
        artifact = self._selected_artifact()
        return artifact is not None and artifact.image_format == "pdf"

    canOpenPdf = Property(bool, get_can_open_pdf, notify=state_changed)

    def get_can_export(self) -> bool:
        return self._selected_artifact() is not None

    canExport = Property(bool, get_can_export, notify=state_changed)

    def get_result_configuration_path(self) -> str:
        return self._result_configuration_path

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
        return self._result_matches_current_saved_baseline

    resultMatchesCurrentSavedBaseline = Property(
        bool,
        get_result_matches_current_saved_baseline,
        notify=state_changed,
    )

    def get_current_draft_dirty(self) -> bool:
        return self._current_draft_dirty

    currentDraftDirty = Property(bool, get_current_draft_dirty, notify=state_changed)

    def get_result_relation_issue(self) -> str:
        return self._result_relation_issue

    resultRelationIssue = Property(str, get_result_relation_issue, notify=state_changed)

    def set_workspace(self, workspace: Workspace | None) -> None:
        if workspace != self.workspace:
            self.workspace = workspace
            self._selected_record_id = ""
            self._clear_bundle()
        self.refresh()

    @Slot(name="refresh")
    def refresh(self) -> None:
        workspace = self.workspace
        rows: list[dict[str, object]] = []
        if workspace is not None:
            for projected in self.activity.records_model.rows():
                record_id = _text(projected.get("recordId"))
                record = self.activity.record_payload(record_id)
                if not _is_successful_generation(record):
                    continue
                assert record is not None
                configuration = _mapping(record.get("configuration"))
                summary = _mapping(record.get("summary"))
                visualization = _mapping(summary.get("visualization"))
                rows.append(
                    {
                        "requestId": record_id,
                        "runId": _text(summary.get("run_id")),
                        "createdAtUtc": _text(record.get("created_at_utc")),
                        "configurationPath": _text(configuration.get("relative_path")),
                        "configurationSha256": _text(configuration.get("sha256")),
                        "visualizationStatus": _text(visualization.get("status")),
                        "hasRecordedVisualization": bool(_text(visualization.get("report_path"))),
                    }
                )
        self.records_model.set_rows(rows, available=workspace is not None)
        record_ids = {str(row["requestId"]) for row in rows}
        if self._selected_record_id not in record_ids:
            self._selected_record_id = ""
            self._clear_bundle()
        if workspace is None:
            self._state = "unavailable"
            self._issue = "Open a workspace to review configured plot results."
        elif not rows:
            self._state = "empty"
            self._issue = "No successful generated runs have configured plot evidence."
        elif not self._selected_record_id:
            self._state = "unselected"
            self._issue = "Select a generated run to verify its configured plot evidence."
        else:
            self._verify_selected_record()
        self._refresh_relation(emit=False)
        self.state_changed.emit()

    @Slot(str, result=bool, name="selectGeneration")
    def select_generation(self, request_id: str) -> bool:
        if not any(row.get("requestId") == request_id for row in self.records_model.rows()):
            return False
        self._selected_record_id = request_id
        self._selected_outcome_index = -1
        self._verify_selected_record()
        self._refresh_relation(emit=False)
        self.state_changed.emit()
        return self._state in {"consistent", "incomplete"}

    @Slot(int, result=bool, name="selectOutcome")
    def select_outcome(self, index: int) -> bool:
        bundle = self._bundle
        if bundle is None or not 0 <= index < len(bundle.outcomes):
            return False
        self._selected_outcome_index = index
        self._replace_preview_token()
        self.state_changed.emit()
        return True

    @Slot(str, result=bool, name="exportSelected")
    def export_selected(self, destination: str) -> bool:
        artifact = self._fresh_selected_artifact()
        if artifact is None:
            return False
        try:
            image_path, sidecar_path = export_verified_plot_bundle(
                artifact,
                Path(destination),
            )
        except (OSError, PlotArtifactError) as exc:
            self._state = "mismatch"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        self.export_succeeded.emit(str(image_path), str(sidecar_path))
        return True

    @Slot(result=bool, name="openSelectedPdf")
    def open_selected_pdf(self) -> bool:
        artifact = self._fresh_selected_artifact()
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
            self._state = "mismatch"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(artifact.image_path)))

    def _verify_selected_record(self) -> None:
        workspace = self.workspace
        record = self.activity.record_payload(self._selected_record_id)
        self._clear_bundle(keep_record=True)
        if workspace is None or record is None:
            self._state = "incomplete"
            self._issue = "The selected activity record is unavailable."
            return
        summary = _mapping(record.get("summary"))
        visualization = _mapping(summary.get("visualization"))
        if not visualization or not _text(visualization.get("report_path")):
            self._state = "incomplete"
            self._issue = "The selected run has no recorded configured visualization report."
            return
        try:
            bundle = verify_configured_plot_record(workspace, record)
        except PlotArtifactError as exc:
            self._state = "mismatch"
            self._issue = str(exc)
            return
        self._bundle = bundle
        self._state = "consistent"
        self._issue = ""
        self.outcomes_model.set_rows(
            (_outcome_row(outcome) for outcome in bundle.outcomes),
            available=True,
        )
        if bundle.outcomes:
            self._selected_outcome_index = 0
            self._replace_preview_token()

    def _fresh_selected_artifact(self) -> VerifiedPlotArtifact | None:
        selected_index = self._selected_outcome_index
        self._verify_selected_record()
        bundle = self._bundle
        if bundle is None or not 0 <= selected_index < len(bundle.outcomes):
            self.state_changed.emit()
            return None
        self._selected_outcome_index = selected_index
        self._replace_preview_token()
        outcome = bundle.outcomes[selected_index]
        if outcome.artifact is None:
            self.state_changed.emit()
            return None
        return outcome.artifact

    def _selected_artifact(self) -> VerifiedPlotArtifact | None:
        bundle = self._bundle
        index = self._selected_outcome_index
        if bundle is None or not 0 <= index < len(bundle.outcomes):
            return None
        return bundle.outcomes[index].artifact

    def _replace_preview_token(self) -> None:
        if self._preview_token:
            self.previews.revoke(self._preview_token)
        self._preview_token = ""
        self._preview_url = ""
        artifact = self._selected_artifact()
        bundle = self._bundle
        workspace = self.workspace
        if (
            artifact is None
            or bundle is None
            or workspace is None
            or artifact.image_format not in {"png", "svg"}
        ):
            return
        self._preview_token = self.previews.issue(
            workspace_identity=str(workspace.root),
            figures_root=workspace.figures,
            image_path=artifact.image_path,
            image_sha256=artifact.image_sha256,
            image_format=artifact.image_format,
            verification_revision=bundle.verification_revision,
        )
        self._preview_url = self.previews.url(self._preview_token)

    def _clear_bundle(self, *, keep_record: bool = False) -> None:
        if self._preview_token:
            self.previews.revoke(self._preview_token)
        self._preview_token = ""
        self._preview_url = ""
        self._bundle = None
        self._selected_outcome_index = -1
        self.outcomes_model.clear()
        if not keep_record:
            self._selected_record_id = ""

    def _refresh_relation(self, *, emit: bool = True) -> None:
        workspace = self.workspace
        record = self.activity.record_payload(self._selected_record_id)
        self._current_draft_dirty = self.configuration.get_dirty()
        self._result_configuration_path = ""
        self._result_configuration_sha256 = ""
        self._result_matches_current_saved_baseline = False
        self._result_relation_issue = ""
        if workspace is None or record is None:
            if emit:
                self.state_changed.emit()
            return
        configuration = _mapping(record.get("configuration"))
        relative_path = _text(configuration.get("relative_path"))
        digest = _text(configuration.get("sha256"))
        if relative_path:
            self._result_configuration_path = str(workspace.root / relative_path)
        self._result_configuration_sha256 = digest
        document = self.configuration.document
        if document is None or document.source_path is None or document.source_sha256 is None:
            self._result_relation_issue = "No saved configuration baseline is currently open."
        elif not relative_path or not digest:
            self._result_relation_issue = "The activity record lacks saved configuration identity."
        else:
            recorded_path = (workspace.root / relative_path).resolve(strict=False)
            current_path = document.source_path.resolve(strict=False)
            on_disk = _file_sha256(current_path)
            self._result_matches_current_saved_baseline = (
                recorded_path == current_path
                and digest == document.source_sha256
                and on_disk == digest
            )
            if not self._result_matches_current_saved_baseline:
                self._result_relation_issue = (
                    "The result belongs to a different or externally replaced saved baseline."
                )
            elif self._current_draft_dirty:
                self._result_relation_issue = (
                    "Generated from the current saved configuration; unsaved draft changes "
                    "now exist."
                )
        if emit:
            self.state_changed.emit()


def _outcome_row(outcome: VerifiedPlotOutcome) -> dict[str, object]:
    artifact = outcome.artifact
    return {
        "index": outcome.index,
        "name": outcome.name,
        "kind": outcome.kind,
        "status": outcome.status,
        "format": "" if artifact is None else artifact.image_format,
        "previewAvailable": artifact is not None and artifact.image_format in {"png", "svg"},
        "openExternally": artifact is not None and artifact.image_format == "pdf",
        "validSampleCount": 0 if artifact is None else artifact.valid_sample_count,
        "excludedSampleCount": 0 if artifact is None else artifact.excluded_sample_count,
        "issue": outcome.error_message,
    }


def _is_successful_generation(record: Mapping[str, object] | None) -> bool:
    return bool(
        record is not None
        and record.get("operation") == "generate"
        and record.get("status") == "completed"
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
