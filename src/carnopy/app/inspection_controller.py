from __future__ import annotations

import copy
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from carnopy.app.inspection_models import InspectionListModel
from carnopy.app.protocol import RequestType
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.table_model import LOCAL_PAGE_SIZE, PreviewTableModel
from carnopy.app.workspace import Workspace

SOURCE_PAGE_SIZE = 20
WORKER_BLOCK_SIZE = 500


@dataclass(frozen=True)
class SourceCandidate:
    path: Path
    kind_hint: str
    modified_ns: int


class InspectionController(QObject):
    """Own source inspection, typed projections, and revision-bound previews."""

    state_changed = Signal()
    inspection_changed = Signal(object)
    inspection_loaded = Signal(object)
    inspection_failed = Signal(object, str)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.workspace: Workspace | None = None
        self._state = "empty"
        self._source: Path | None = None
        self._source_kind = ""
        self._revision = ""
        self._integrity_status = ""
        self._integrity_label = ""
        self._issue = ""
        self._selected_table_id = ""
        self._preview_state = "empty"
        self._payload: dict[str, Any] | None = None
        self._plot_context: dict[str, Any] | None = None
        self._session: RequestSession | None = None
        self._request_kind = ""
        self._requested_page_offset = 0
        self._requested_block_offset = 0
        self._requested_revision = ""
        self._requested_table_id = ""
        self._source_candidates: tuple[SourceCandidate, ...] = ()
        self._source_issues: dict[Path, str] = {}
        self._revealed_source_count = SOURCE_PAGE_SIZE
        self._lifecycle_guard: Callable[[str], bool] | None = None

        self.workspace_sources_model = InspectionListModel(
            ("path", "name", "kindHint", "modifiedNs", "issue", "inspectable"),
            self,
        )
        self.source_summary_model = _summary_model(self)
        self.identity_summary_model = _summary_model(self)
        self.backend_summary_model = _summary_model(self)
        self.row_summary_model = _summary_model(self)
        self.phase_counts_model = InspectionListModel(("phase", "count"), self)
        self.failure_layer_counts_model = InspectionListModel(("failureLayer", "count"), self)
        self.failure_code_counts_model = InspectionListModel(("code", "count"), self)
        self.failure_property_counts_model = InspectionListModel(("property", "count"), self)
        self.sweep_delta_reason_counts_model = InspectionListModel(("reason", "count"), self)
        self.preparation_quality_errors_model = InspectionListModel(("message",), self)
        self.diagnostics_model = InspectionListModel(
            ("section", "label", "value", "severity", "issue"),
            self,
        )
        self.tables_model = InspectionListModel(("id", "label", "format", "sha256"), self)
        self.arrays_model = InspectionListModel(
            (
                "artifactId",
                "artifactLabel",
                "format",
                "artifactSha256",
                "arrayName",
                "shape",
                "shapeDisplay",
                "dtype",
                "metadataAvailable",
                "issue",
            ),
            self,
        )
        self.table_model = PreviewTableModel(self)
        self.table_model.state_changed.connect(self.state_changed)
        self.coordinator.busy_changed.connect(lambda _busy: self.state_changed.emit())

    def get_state(self) -> str:
        return self._state

    state = Property(str, get_state, notify=state_changed)

    def get_source_path(self) -> str:
        return "" if self._source is None else str(self._source)

    sourcePath = Property(str, get_source_path, notify=state_changed)

    def get_source_kind(self) -> str:
        return self._source_kind

    sourceKind = Property(str, get_source_kind, notify=state_changed)

    def get_revision(self) -> str:
        return self._revision

    revision = Property(str, get_revision, notify=state_changed)

    def get_integrity_status(self) -> str:
        return self._integrity_status

    integrityStatus = Property(str, get_integrity_status, notify=state_changed)

    def get_integrity_label(self) -> str:
        return self._integrity_label

    integrityLabel = Property(str, get_integrity_label, notify=state_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=state_changed)

    def get_selected_table_id(self) -> str:
        return self._selected_table_id

    selectedTableId = Property(str, get_selected_table_id, notify=state_changed)

    def get_preview_state(self) -> str:
        return self._preview_state

    previewState = Property(str, get_preview_state, notify=state_changed)

    def get_preview_first_row(self) -> int:
        return self.table_model.first_row

    previewFirstRow = Property(int, get_preview_first_row, notify=state_changed)

    def get_preview_last_row(self) -> int:
        return self.table_model.last_row

    previewLastRow = Property(int, get_preview_last_row, notify=state_changed)

    def get_preview_total_rows(self) -> int:
        return self.table_model.total_rows

    previewTotalRows = Property(int, get_preview_total_rows, notify=state_changed)

    def get_can_explore_plots(self) -> bool:
        return (
            self._state == "ready"
            and self._source_kind == "dataset"
            and isinstance(self._plot_context, dict)
        )

    canExplorePlots = Property(bool, get_can_explore_plots, notify=state_changed)

    def get_can_inspect(self) -> bool:
        return not self.coordinator.is_busy

    canInspect = Property(bool, get_can_inspect, notify=state_changed)

    def get_can_preview(self) -> bool:
        return (
            self._state == "ready"
            and bool(self._selected_table_id)
            and not self.coordinator.is_busy
        )

    canPreview = Property(bool, get_can_preview, notify=state_changed)

    def get_has_more_workspace_sources(self) -> bool:
        return self._revealed_source_count < len(self._source_candidates)

    hasMoreWorkspaceSources = Property(
        bool,
        get_has_more_workspace_sources,
        notify=state_changed,
    )

    def get_diagnostic_text(self) -> str:
        payload = self._payload
        if payload is None:
            return ""
        summary = payload.get("summary")
        return (
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False)
            if isinstance(summary, dict)
            else ""
        )

    diagnosticText = Property(str, get_diagnostic_text, notify=state_changed)

    def _model_property(self, model: InspectionListModel) -> QObject:
        return model

    def get_workspace_sources_model(self) -> QObject:
        return self._model_property(self.workspace_sources_model)

    workspaceSourcesModel = Property(QObject, get_workspace_sources_model, constant=True)

    def get_source_summary_model(self) -> QObject:
        return self._model_property(self.source_summary_model)

    sourceSummaryModel = Property(QObject, get_source_summary_model, constant=True)

    def get_identity_summary_model(self) -> QObject:
        return self._model_property(self.identity_summary_model)

    identitySummaryModel = Property(QObject, get_identity_summary_model, constant=True)

    def get_backend_summary_model(self) -> QObject:
        return self._model_property(self.backend_summary_model)

    backendSummaryModel = Property(QObject, get_backend_summary_model, constant=True)

    def get_row_summary_model(self) -> QObject:
        return self._model_property(self.row_summary_model)

    rowSummaryModel = Property(QObject, get_row_summary_model, constant=True)

    def get_phase_counts_model(self) -> QObject:
        return self._model_property(self.phase_counts_model)

    phaseCountsModel = Property(QObject, get_phase_counts_model, constant=True)

    def get_failure_layer_counts_model(self) -> QObject:
        return self._model_property(self.failure_layer_counts_model)

    failureLayerCountsModel = Property(
        QObject,
        get_failure_layer_counts_model,
        constant=True,
    )

    def get_failure_code_counts_model(self) -> QObject:
        return self._model_property(self.failure_code_counts_model)

    failureCodeCountsModel = Property(
        QObject,
        get_failure_code_counts_model,
        constant=True,
    )

    def get_failure_property_counts_model(self) -> QObject:
        return self._model_property(self.failure_property_counts_model)

    failurePropertyCountsModel = Property(
        QObject,
        get_failure_property_counts_model,
        constant=True,
    )

    def get_sweep_delta_reason_counts_model(self) -> QObject:
        return self._model_property(self.sweep_delta_reason_counts_model)

    sweepDeltaReasonCountsModel = Property(
        QObject,
        get_sweep_delta_reason_counts_model,
        constant=True,
    )

    def get_preparation_quality_errors_model(self) -> QObject:
        return self._model_property(self.preparation_quality_errors_model)

    preparationQualityErrorsModel = Property(
        QObject,
        get_preparation_quality_errors_model,
        constant=True,
    )

    def get_diagnostics_model(self) -> QObject:
        return self._model_property(self.diagnostics_model)

    diagnosticsModel = Property(QObject, get_diagnostics_model, constant=True)

    def get_tables_model(self) -> QObject:
        return self._model_property(self.tables_model)

    tablesModel = Property(QObject, get_tables_model, constant=True)

    def get_arrays_model(self) -> QObject:
        return self._model_property(self.arrays_model)

    arraysModel = Property(QObject, get_arrays_model, constant=True)

    def get_table_model(self) -> QObject:
        return self.table_model

    tableModel = Property(QObject, get_table_model, constant=True)

    def set_workspace(self, workspace: Workspace | None) -> None:
        if self.workspace == workspace:
            self.refresh_sources()
            return
        self.workspace = workspace
        self._source_issues.clear()
        self._clear_inspection()
        self.refresh_sources()

    def set_lifecycle_guard(self, guard: Callable[[str], bool]) -> None:
        self._lifecycle_guard = guard

    @Slot(name="refreshWorkspaceSources")
    def refresh_sources(self) -> None:
        workspace = self.workspace
        self._revealed_source_count = SOURCE_PAGE_SIZE
        self._source_candidates = (
            () if workspace is None else discover_workspace_sources(workspace.outputs)
        )
        known = {candidate.path for candidate in self._source_candidates}
        self._source_issues = {
            path: issue for path, issue in self._source_issues.items() if path in known
        }
        self._update_workspace_sources_model()
        self.state_changed.emit()

    @Slot(name="revealMoreWorkspaceSources")
    def reveal_more_sources(self) -> None:
        if not self.get_has_more_workspace_sources():
            return
        self._revealed_source_count = min(
            len(self._source_candidates),
            self._revealed_source_count + SOURCE_PAGE_SIZE,
        )
        self._update_workspace_sources_model()
        self.state_changed.emit()

    @Slot(str, result=bool, name="inspectSource")
    def inspect_source(self, source: str) -> bool:
        if self._lifecycle_guard is not None and not self._lifecycle_guard(
            "replacing the inspected source"
        ):
            return False
        if self.coordinator.is_busy:
            self._issue = "Another Carnopy worker request is active."
            self.state_changed.emit()
            return False
        path = Path(source).expanduser().resolve()
        self._clear_inspection(source=path, state="loading")
        self._issue = ""
        self.state_changed.emit()
        try:
            self._start_request("inspect_source", {"source_path": str(path)}, kind="inspection")
        except Exception as exc:
            self._state = "failed"
            self._issue = str(exc)
            self.state_changed.emit()
            self.inspection_failed.emit(path, self._issue)
            return False
        return True

    @Slot(result=bool, name="refreshInspection")
    def refresh_inspection(self) -> bool:
        return False if self._source is None else self.inspect_source(str(self._source))

    @Slot(str, result=bool, name="selectTable")
    def select_table(self, table_id: str) -> bool:
        available = {
            str(row.get("id")) for row in self.tables_model.rows() if isinstance(row.get("id"), str)
        }
        if table_id not in available or self.coordinator.is_busy:
            return False
        self._selected_table_id = table_id
        self.table_model.clear()
        self._preview_state = "empty"
        self.state_changed.emit()
        QTimer.singleShot(0, lambda: self.request_preview_page(0))
        return True

    @Slot(int, result=bool, name="requestPreviewPage")
    def request_preview_page(self, page_offset: int) -> bool:
        if (
            page_offset < 0
            or self._state != "ready"
            or not self._selected_table_id
            or self.coordinator.is_busy
        ):
            return False
        if page_offset >= self.table_model.total_rows and self.table_model.total_rows > 0:
            return False
        if self.table_model.contains_page(page_offset):
            self.table_model.set_page(page_offset)
            self._preview_state = "ready"
            self.state_changed.emit()
            return True
        block_offset = (page_offset // WORKER_BLOCK_SIZE) * WORKER_BLOCK_SIZE
        return self._request_preview_block(block_offset, page_offset)

    @Slot(result=bool, name="previousPreviewPage")
    def previous_preview_page(self) -> bool:
        return self.request_preview_page(max(0, self.table_model.page_offset - LOCAL_PAGE_SIZE))

    @Slot(result=bool, name="nextPreviewPage")
    def next_preview_page(self) -> bool:
        return self.request_preview_page(self.table_model.page_offset + LOCAL_PAGE_SIZE)

    def mark_uninspectable(self, path: Path, message: str) -> None:
        resolved = path.expanduser().resolve()
        self._source_issues[resolved] = message
        self._update_workspace_sources_model()

    def mark_inspectable(self, path: Path) -> None:
        self._source_issues.pop(path.expanduser().resolve(), None)
        self._update_workspace_sources_model()

    def current_payload(self) -> dict[str, Any] | None:
        return None if self._payload is None else copy.deepcopy(self._payload)

    def _start_request(
        self,
        request_type: RequestType,
        payload: dict[str, object],
        *,
        kind: str,
    ) -> None:
        session = self.coordinator.start_request(
            "inspection",
            request_type,
            payload,
        )
        self._session = session
        self._request_kind = kind
        session.completed.connect(self._request_completed)

    def _request_preview_block(self, block_offset: int, page_offset: int) -> bool:
        if self._source is None or not self._revision or not self._selected_table_id:
            return False
        self._requested_block_offset = block_offset
        self._requested_page_offset = page_offset
        self._requested_revision = self._revision
        self._requested_table_id = self._selected_table_id
        self._preview_state = "loading"
        self._issue = ""
        self.state_changed.emit()
        try:
            self._start_request(
                "preview_table",
                {
                    "source_path": str(self._source),
                    "table_id": self._selected_table_id,
                    "inspection_revision": self._revision,
                    "offset": block_offset,
                    "limit": WORKER_BLOCK_SIZE,
                },
                kind="preview",
            )
        except Exception as exc:
            self._preview_state = "failed"
            self._issue = str(exc)
            self.state_changed.emit()
            return False
        return True

    def _request_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        request_kind = self._request_kind
        self._session = None
        self._request_kind = ""
        result = outcome.result_payload
        if result is not None:
            if request_kind == "inspection":
                self._accept_inspection_payload(cast(dict[str, Any], result))
            elif request_kind == "preview":
                self._accept_preview_payload(cast(dict[str, Any], result))
            return
        self._accept_failure(request_kind, outcome.failure_payload or {})

    def _accept_inspection_payload(self, payload: dict[str, Any]) -> None:
        source_kind = payload.get("source_kind")
        revision = payload.get("revision")
        source_value = payload.get("source")
        if (
            source_kind not in {"dataset", "model_sweep", "preparation"}
            or not isinstance(revision, str)
            or len(revision) != 64
            or any(character not in "0123456789abcdef" for character in revision.lower())
            or not isinstance(source_value, str)
            or not isinstance(payload.get("summary"), dict)
        ):
            self._accept_failure(
                "inspection",
                {
                    "message": "worker inspection result is missing required typed fields",
                },
            )
            return
        inspected_source = Path(source_value).expanduser().resolve()
        if self._source is None or inspected_source != self._source:
            self._accept_failure(
                "inspection",
                {"message": "worker inspection result belongs to another source"},
            )
            return
        self._payload = copy.deepcopy(payload)
        self._source_kind = source_kind
        self._revision = revision
        self._plot_context = (
            copy.deepcopy(payload.get("plot_context"))
            if isinstance(payload.get("plot_context"), dict)
            else None
        )
        self._issue = ""
        self._state = "ready"
        self._preview_state = "empty"
        self._project_payload(payload)
        first = self.tables_model.get(0)
        self._selected_table_id = str(first["id"]) if isinstance(first.get("id"), str) else ""
        self.mark_inspectable(inspected_source)
        self.inspection_changed.emit(copy.deepcopy(payload))
        self.inspection_loaded.emit(inspected_source)
        self.state_changed.emit()
        if self._selected_table_id:
            QTimer.singleShot(0, lambda: self.request_preview_page(0))

    def _accept_preview_payload(self, payload: dict[str, Any]) -> None:
        if (
            self._state != "ready"
            or self._revision != self._requested_revision
            or self._selected_table_id != self._requested_table_id
            or payload.get("table_id") != self._requested_table_id
        ):
            self._mark_stale("Table preview no longer matches the current inspection revision.")
            return
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            self._mark_stale("Worker table preview is missing its typed columns or rows.")
            return
        self.table_model.set_block(payload, page_offset=self._requested_page_offset)
        self._preview_state = "ready"
        self._issue = ""
        self.state_changed.emit()

    def _accept_failure(self, request_kind: str, payload: dict[str, object]) -> None:
        message = str(payload.get("message", "inspection failed"))
        if request_kind == "preview":
            self._mark_stale(f"Table preview failed; refresh inspection: {message}")
            return
        source = self._source
        self._state = "failed"
        self._preview_state = "empty"
        self._issue = message
        self._payload = None
        self._plot_context = None
        self._reset_projection()
        self.inspection_changed.emit(None)
        if source is not None:
            self.mark_uninspectable(source, message)
            self.inspection_failed.emit(source, message)
        self.state_changed.emit()

    def _mark_stale(self, message: str) -> None:
        self._state = "stale"
        self._preview_state = "stale"
        self._issue = message
        self._payload = None
        self._plot_context = None
        self.table_model.clear()
        self.inspection_changed.emit(None)
        self.state_changed.emit()

    def _clear_inspection(
        self,
        *,
        source: Path | None = None,
        state: str = "empty",
    ) -> None:
        had_payload = self._payload is not None or self._plot_context is not None
        self._state = state
        self._source = source
        self._source_kind = ""
        self._revision = ""
        self._integrity_status = ""
        self._integrity_label = ""
        self._issue = ""
        self._selected_table_id = ""
        self._preview_state = "empty"
        self._payload = None
        self._plot_context = None
        self._session = None
        self._request_kind = ""
        self.table_model.clear()
        self._reset_projection()
        if had_payload:
            self.inspection_changed.emit(None)
        self.state_changed.emit()

    def _reset_projection(self) -> None:
        for model in (
            self.source_summary_model,
            self.identity_summary_model,
            self.backend_summary_model,
            self.row_summary_model,
            self.phase_counts_model,
            self.failure_layer_counts_model,
            self.failure_code_counts_model,
            self.failure_property_counts_model,
            self.sweep_delta_reason_counts_model,
            self.preparation_quality_errors_model,
            self.diagnostics_model,
            self.tables_model,
            self.arrays_model,
        ):
            model.clear()

    def _project_payload(self, payload: dict[str, Any]) -> None:
        self._reset_projection()
        summary = cast(dict[str, Any], payload["summary"])
        source_kind = cast(str, payload["source_kind"])
        tables = payload.get("tables")
        arrays = payload.get("arrays")
        self.tables_model.set_rows(
            _table_rows(tables),
            available=isinstance(tables, list),
        )
        self.arrays_model.set_rows(
            _array_rows(arrays),
            available=isinstance(arrays, list),
        )
        if source_kind == "dataset":
            self._project_dataset(summary)
        elif source_kind == "model_sweep":
            self._project_sweep(summary)
        else:
            self._project_preparation(summary)

    def _project_dataset(self, summary: dict[str, Any]) -> None:
        source = _mapping(summary.get("source"))
        identity = _mapping(summary.get("identity"))
        backend = _mapping(summary.get("backend"))
        rows = _mapping(summary.get("rows"))
        self.source_summary_model.set_rows(
            _summary_rows(
                source,
                (
                    ("requested_path", "Requested path"),
                    ("dataset_path", "Dataset path"),
                    ("format", "Format"),
                    ("sha256", "SHA-256"),
                    ("integrity", "Integrity"),
                ),
            ),
            available=bool(source),
        )
        self.identity_summary_model.set_rows(
            _summary_rows(
                identity,
                (
                    ("mode", "Mode"),
                    ("run_id", "Run ID"),
                    ("spec_id", "Spec ID"),
                    ("generation_context_id", "Generation context"),
                ),
            ),
            available=bool(identity),
        )
        self.backend_summary_model.set_rows(
            _summary_rows(
                backend,
                (("name", "Backend"), ("version", "Version"), ("model", "Model")),
            ),
            available=bool(backend),
        )
        self.row_summary_model.set_rows(
            _summary_rows(
                rows,
                (("total", "Total"), ("valid", "Valid"), ("invalid", "Invalid")),
            ),
            available=bool(rows),
        )
        self.phase_counts_model.set_rows(
            _count_rows(summary.get("phase_counts"), "phase"),
            available=isinstance(summary.get("phase_counts"), dict),
        )
        failures = _mapping(summary.get("failure_counts"))
        self.failure_layer_counts_model.set_rows(
            _count_rows(failures.get("layer"), "failureLayer"),
            available=isinstance(failures.get("layer"), dict),
        )
        self.failure_code_counts_model.set_rows(
            _count_rows(failures.get("code"), "code"),
            available=isinstance(failures.get("code"), dict),
        )
        self.failure_property_counts_model.set_rows(
            _count_rows(failures.get("property"), "property"),
            available=isinstance(failures.get("property"), dict),
        )
        integrity = source.get("integrity")
        if integrity == "verified":
            self._integrity_status = "verified"
            self._integrity_label = "Verified recorded artifact"
        else:
            self._integrity_status = "unrecorded"
            self._integrity_label = "Unrecorded source"
        self.diagnostics_model.set_rows(
            _dataset_diagnostics(summary),
            available=True,
        )

    def _project_sweep(self, summary: dict[str, Any]) -> None:
        self.source_summary_model.set_rows(
            _summary_rows(
                summary,
                (("source", "Source"), ("status", "Status"), ("mode", "Mode")),
            ),
            available=True,
        )
        self.identity_summary_model.set_rows(
            _summary_rows(
                summary,
                (("sweep_id", "Sweep ID"), ("sweep_run_id", "Sweep run ID")),
            ),
            available=True,
        )
        self.backend_summary_model.set_rows(
            _summary_rows(
                summary,
                (("models", "Models"), ("reference_model", "Reference model")),
            ),
            available=True,
        )
        comparison = _mapping(summary.get("comparison_artifacts"))
        self.row_summary_model.set_rows(
            _summary_rows(
                comparison,
                (
                    ("values_row_count", "Comparison values"),
                    ("deltas_row_count", "Comparison deltas"),
                ),
            ),
            available=bool(comparison),
        )
        reasons = summary.get("delta_reason_counts")
        self.sweep_delta_reason_counts_model.set_rows(
            _count_rows(reasons, "reason"),
            available=isinstance(reasons, dict),
        )
        self.diagnostics_model.set_rows(_sweep_diagnostics(summary), available=True)
        self._integrity_status = "worker_inspected"
        self._integrity_label = "Worker-inspected model-sweep bundle"

    def _project_preparation(self, summary: dict[str, Any]) -> None:
        self.source_summary_model.set_rows(
            _summary_rows(summary, (("source", "Source"), ("status", "Status"))),
            available=True,
        )
        source_identity = _mapping(summary.get("source_identity"))
        self.identity_summary_model.set_rows(
            _summary_rows(
                source_identity,
                (
                    ("run_id", "Source run ID"),
                    ("spec_id", "Source spec ID"),
                    ("generation_context_id", "Source generation context"),
                ),
            ),
            available=bool(source_identity),
        )
        self.backend_summary_model.set_rows(
            _summary_rows(
                source_identity,
                (
                    ("backend", "Backend"),
                    ("backend_version", "Version"),
                    ("backend_model", "Model"),
                ),
            ),
            available=bool(source_identity),
        )
        row_counts = _mapping(summary.get("row_counts"))
        self.row_summary_model.set_rows(
            _summary_rows(
                row_counts,
                (("source", "Source"), ("eligible", "Eligible"), ("excluded", "Excluded")),
            ),
            available=bool(row_counts),
        )
        quality = _mapping(summary.get("quality"))
        errors = quality.get("errors")
        error_rows = (
            ({"message": str(message)} for message in errors) if isinstance(errors, list) else ()
        )
        self.preparation_quality_errors_model.set_rows(
            error_rows,
            available=isinstance(errors, list),
        )
        self.diagnostics_model.set_rows(
            _preparation_diagnostics(summary),
            available=True,
        )
        self._integrity_status = "worker_inspected"
        self._integrity_label = "Worker-inspected preparation bundle"

    def _update_workspace_sources_model(self) -> None:
        rows = (
            {
                "path": str(candidate.path),
                "name": candidate.path.name,
                "kindHint": candidate.kind_hint,
                "modifiedNs": candidate.modified_ns,
                "issue": self._source_issues.get(candidate.path, ""),
                "inspectable": candidate.path not in self._source_issues,
            }
            for candidate in self._source_candidates[: self._revealed_source_count]
        )
        self.workspace_sources_model.set_rows(rows, available=self.workspace is not None)


def discover_workspace_sources(output_root: Path) -> tuple[SourceCandidate, ...]:
    if not output_root.is_dir():
        return ()
    candidates: list[SourceCandidate] = []
    try:
        children = tuple(output_root.iterdir())
    except OSError:
        return ()
    for path in children:
        kind_hint: str | None = None
        try:
            if path.is_symlink():
                continue
            if path.is_file() and path.suffix.lower() in {".csv", ".parquet"}:
                kind_hint = path.suffix[1:].upper()
            elif path.is_dir():
                kind_hint = _directory_kind_hint(path)
                if kind_hint is None:
                    continue
            else:
                continue
            resolved = path.resolve()
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            continue
        if kind_hint is not None:
            candidates.append(SourceCandidate(resolved, kind_hint, modified_ns))
    return tuple(
        sorted(
            candidates,
            key=lambda item: (-item.modified_ns, os.fspath(item.path)),
        )
    )


def _directory_kind_hint(path: Path) -> str | None:
    if (path / "preparation.normalized.json").is_file():
        return "preparation bundle"
    if (path / "sweep.normalized.json").is_file():
        return "model-sweep bundle"
    if any((path / name).is_file() for name in ("metadata.json", "dataset.csv", "dataset.parquet")):
        return "dataset run"
    return None


def _summary_model(parent: QObject) -> InspectionListModel:
    return InspectionListModel(("key", "label", "value", "available"), parent)


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _summary_rows(
    mapping: dict[str, Any],
    fields: tuple[tuple[str, str], ...],
) -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": label,
            "value": _display(mapping.get(key)),
            "available": mapping.get(key) is not None,
        }
        for key, label in fields
    ]


def _count_rows(value: object, key: str) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    return [
        {key: str(name), "count": int(count)}
        for name, count in value.items()
        if isinstance(count, int) and not isinstance(count, bool)
    ]


def _table_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "id": str(item.get("id", "")),
            "label": str(item.get("label", item.get("id", ""))),
            "format": str(item.get("format", "")),
            "sha256": str(item.get("sha256", "")),
        }
        for item in value
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _array_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("path", ""))
        artifact_label = Path(artifact_id).name if artifact_id else "Array artifact"
        artifact_format = str(item.get("format", ""))
        artifact_sha = str(item.get("sha256", ""))
        arrays = item.get("arrays")
        if not isinstance(arrays, dict) or not arrays:
            rows.append(
                {
                    "artifactId": artifact_id,
                    "artifactLabel": artifact_label,
                    "format": artifact_format,
                    "artifactSha256": artifact_sha,
                    "arrayName": "",
                    "shape": [],
                    "shapeDisplay": "",
                    "dtype": "",
                    "metadataAvailable": False,
                    "issue": "Logical array metadata is unavailable for this legacy artifact.",
                }
            )
            continue
        for name, metadata in arrays.items():
            shape = metadata.get("shape") if isinstance(metadata, dict) else None
            dtype = metadata.get("dtype") if isinstance(metadata, dict) else None
            valid_shape = isinstance(shape, list) and all(
                isinstance(part, int) and not isinstance(part, bool) for part in shape
            )
            metadata_available = valid_shape and isinstance(dtype, str)
            normalized_shape = cast(list[int], shape) if valid_shape else []
            rows.append(
                {
                    "artifactId": artifact_id,
                    "artifactLabel": artifact_label,
                    "format": artifact_format,
                    "artifactSha256": artifact_sha,
                    "arrayName": str(name),
                    "shape": normalized_shape,
                    "shapeDisplay": " x ".join(str(part) for part in normalized_shape),
                    "dtype": dtype if isinstance(dtype, str) else "",
                    "metadataAvailable": metadata_available,
                    "issue": (
                        ""
                        if metadata_available
                        else "Logical array shape or dtype metadata is incomplete."
                    ),
                }
            )
    return rows


def _dataset_diagnostics(summary: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    coordinates = summary.get("coordinates")
    if isinstance(coordinates, list):
        for item in coordinates:
            if not isinstance(item, dict):
                continue
            unit = item.get("display_unit")
            suffix = "" if unit in {None, "", "1"} else f" {unit}"
            rows.append(
                {
                    "section": "sampling",
                    "label": str(item.get("field", "coordinate")),
                    "value": f"{item.get('level_count', 0)} emitted levels{suffix}",
                    "severity": "information",
                    "issue": "",
                }
            )
    properties = summary.get("properties")
    if isinstance(properties, list):
        for item in properties:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "section": "properties",
                    "label": str(item.get("name", "property")),
                    "value": (
                        f"{item.get('valid_finite_count', 0)} valid finite; "
                        f"min={_display(item.get('minimum'))}; max={_display(item.get('maximum'))}"
                    ),
                    "severity": "information",
                    "issue": "",
                }
            )
    return rows


def _sweep_diagnostics(summary: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    values = summary.get("delta_summaries")
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "section": "relative_deltas",
                    "label": " ".join(
                        str(item.get(key, "")) for key in ("backend_model", "property")
                    ).strip(),
                    "value": (
                        f"count={_display(item.get('count'))}; "
                        f"min={_display(item.get('minimum'))}; "
                        f"max={_display(item.get('maximum'))}; "
                        f"mean={_display(item.get('mean'))}"
                    ),
                    "severity": "information",
                    "issue": "",
                }
            )
    failure = summary.get("failure_message")
    if failure:
        rows.append(
            {
                "section": "sweep",
                "label": "Failure",
                "value": "",
                "severity": "error",
                "issue": str(failure),
            }
        )
    return rows


def _preparation_diagnostics(summary: dict[str, Any]) -> list[dict[str, object]]:
    quality = _mapping(summary.get("quality"))
    quality_summary = _mapping(quality.get("summary"))
    rows: list[dict[str, object]] = [
        {
            "section": "quality",
            "label": "Status",
            "value": _display(quality_summary.get("status")),
            "severity": (
                "error" if quality_summary.get("status") == "corrupt_or_missing" else "information"
            ),
            "issue": "",
        }
    ]
    for key, label in (
        ("matrix_diagnostics", "Matrix diagnostics"),
        ("baseline_diagnostics", "Baseline diagnostics"),
    ):
        value = quality_summary.get(key)
        if isinstance(value, dict):
            rows.append(
                {
                    "section": "quality",
                    "label": label,
                    "value": _display(value.get("status")),
                    "severity": "information",
                    "issue": "",
                }
            )
    return rows
