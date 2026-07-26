from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.inspection_models import InspectionListModel
from carnopy.app.jobs import JobStore, LoadedJob
from carnopy.app.recovery import (
    StagingCandidate,
    remove_staging_candidate,
    scan_staging_candidates,
)
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import Workspace

_RECORD_ROLES = (
    "recordId",
    "operation",
    "state",
    "stateLabel",
    "createdAtUtc",
    "updatedAtUtc",
    "completedAtUtc",
    "configurationPath",
    "configurationSha256",
    "phase",
    "progressCompleted",
    "progressTotal",
    "runId",
    "outputDirectory",
    "visualizationStatus",
    "readable",
    "issue",
)

_RECOVERY_ROLES = (
    "name",
    "path",
    "modifiedAtUtc",
    "ageSeconds",
    "removable",
    "selected",
    "issue",
)


class ActivityController(QObject):
    """Own persisted Run-activity projection and bounded staging recovery."""

    state_changed = Signal()
    records_changed = Signal()

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.workspace: Workspace | None = None
        self.records_model = InspectionListModel(_RECORD_ROLES, self)
        self.recovery_candidates_model = InspectionListModel(_RECOVERY_ROLES, self)
        self._store: JobStore | None = None
        self._loaded_records: dict[str, LoadedJob] = {}
        self._selected_record_id = ""
        self._selected_record_state = ""
        self._selected_record_summary: dict[str, object] = {}
        self._selected_diagnostic_text = ""
        self._can_inspect_run = False
        self._can_view_plots = False
        self._recovery_candidates: tuple[StagingCandidate, ...] = ()
        self._recovery_selected: set[tuple[str, int, int]] = set()
        self._recovery_state = "unavailable"
        self._recovery_issue = "Open a workspace to inspect staging recovery."
        coordinator.busy_changed.connect(self.refresh_records)

    def get_records_model(self) -> QObject:
        return self.records_model

    recordsModel = Property(QObject, get_records_model, constant=True)

    def get_selected_record_id(self) -> str:
        return self._selected_record_id

    selectedRecordId = Property(str, get_selected_record_id, notify=state_changed)

    def get_selected_record_state(self) -> str:
        return self._selected_record_state

    selectedRecordState = Property(str, get_selected_record_state, notify=state_changed)

    def get_selected_record_summary(self) -> dict[str, object]:
        return dict(self._selected_record_summary)

    selectedRecordSummary = Property(
        object,
        get_selected_record_summary,
        notify=state_changed,
    )

    def get_selected_diagnostic_text(self) -> str:
        return self._selected_diagnostic_text

    selectedDiagnosticText = Property(
        str,
        get_selected_diagnostic_text,
        notify=state_changed,
    )

    def get_can_inspect_run(self) -> bool:
        return self._can_inspect_run

    canInspectRun = Property(bool, get_can_inspect_run, notify=state_changed)

    def get_can_view_plots(self) -> bool:
        return self._can_view_plots

    canViewPlots = Property(bool, get_can_view_plots, notify=state_changed)

    def get_can_remove_record(self) -> bool:
        return self._selected_record_id in self._loaded_records

    canRemoveRecord = Property(bool, get_can_remove_record, notify=state_changed)

    def get_recovery_candidates_model(self) -> QObject:
        return self.recovery_candidates_model

    recoveryCandidatesModel = Property(
        QObject,
        get_recovery_candidates_model,
        constant=True,
    )

    def get_selected_recovery_count(self) -> int:
        return len(self._recovery_selected)

    selectedRecoveryCount = Property(
        int,
        get_selected_recovery_count,
        notify=state_changed,
    )

    def get_recovery_state(self) -> str:
        return self._recovery_state

    recoveryState = Property(str, get_recovery_state, notify=state_changed)

    def get_recovery_issue(self) -> str:
        return self._recovery_issue

    recoveryIssue = Property(str, get_recovery_issue, notify=state_changed)

    def set_workspace(self, workspace: Workspace | None) -> None:
        if workspace == self.workspace:
            self.refresh_records()
            self.refresh_recovery()
            return
        self.workspace = workspace
        self._store = None if workspace is None else JobStore(workspace.private_directory)
        self._selected_record_id = ""
        self._clear_selected_record()
        self._recovery_selected.clear()
        self.refresh_records()
        self.refresh_recovery()

    @Slot(name="refreshRecords")
    def refresh_records(self) -> None:
        store = self._store
        if store is None:
            self._loaded_records.clear()
            self.records_model.clear()
            self._selected_record_id = ""
            self._clear_selected_record()
            self.records_changed.emit()
            self.state_changed.emit()
            return

        loaded = store.load()
        rows: list[dict[str, object]] = []
        records: dict[str, LoadedJob] = {}
        for item in loaded:
            row = self._project_record(item)
            record_id = str(row["recordId"])
            if record_id in records:
                row["readable"] = False
                row["issue"] = "duplicate activity record identifier"
                record_id = item.path.name
                row["recordId"] = record_id
            records[record_id] = item
            rows.append(row)
        self._loaded_records = records
        self.records_model.set_rows(rows, available=True)
        if self._selected_record_id not in records:
            self._selected_record_id = ""
        self._refresh_selected_record()
        self.records_changed.emit()
        self.state_changed.emit()

    def record_payload(self, record_id: str) -> dict[str, object] | None:
        """Return a detached private record for another composition-owned controller."""

        loaded = self._loaded_records.get(record_id)
        if loaded is None or loaded.data is None:
            return None
        return copy.deepcopy(loaded.data)

    @Slot(str, result=bool, name="selectRecord")
    def select_record(self, record_id: str) -> bool:
        if record_id not in self._loaded_records:
            return False
        if record_id == self._selected_record_id:
            return True
        self._selected_record_id = record_id
        self._refresh_selected_record()
        self.state_changed.emit()
        return True

    @Slot(result=bool, name="removeSelectedRecord")
    def remove_selected_record(self) -> bool:
        store = self._store
        loaded = self._loaded_records.get(self._selected_record_id)
        if store is None or loaded is None:
            return False
        try:
            store.remove(loaded.path)
        except (OSError, ValueError) as exc:
            self._selected_diagnostic_text = f"Activity record removal failed: {exc}"
            self.state_changed.emit()
            return False
        self._selected_record_id = ""
        self.refresh_records()
        return True

    @Slot(name="refreshRecovery")
    def refresh_recovery(self) -> None:
        workspace = self.workspace
        if workspace is None:
            self._recovery_candidates = ()
            self._recovery_selected.clear()
            self.recovery_candidates_model.clear()
            self._recovery_state = "unavailable"
            self._recovery_issue = "Open a workspace to inspect staging recovery."
            self.state_changed.emit()
            return
        try:
            candidates = tuple(scan_staging_candidates(workspace.outputs))
        except OSError as exc:
            self._recovery_candidates = ()
            self._recovery_selected.clear()
            self.recovery_candidates_model.clear(available=True)
            self._recovery_state = "failed"
            self._recovery_issue = f"Could not scan staging recovery: {exc}"
            self.state_changed.emit()
            return
        identities = {_candidate_identity(candidate) for candidate in candidates}
        self._recovery_selected.intersection_update(identities)
        self._recovery_candidates = candidates
        self._set_recovery_rows()
        self._recovery_state = "ready" if candidates else "empty"
        self._recovery_issue = ""
        self.state_changed.emit()

    @Slot(int, bool, result=bool, name="setRecoverySelected")
    def set_recovery_selected(self, row: int, selected: bool) -> bool:
        if not 0 <= row < len(self._recovery_candidates):
            return False
        candidate = self._recovery_candidates[row]
        identity = _candidate_identity(candidate)
        if selected:
            if not candidate.removable:
                return False
            self._recovery_selected.add(identity)
        else:
            self._recovery_selected.discard(identity)
        self._set_recovery_rows()
        self.state_changed.emit()
        return True

    def selected_recovery_paths(self) -> tuple[Path, ...]:
        return tuple(
            candidate.path
            for candidate in self._recovery_candidates
            if _candidate_identity(candidate) in self._recovery_selected
        )

    @Slot(result=bool, name="removeSelectedRecovery")
    def remove_selected_recovery(self) -> bool:
        workspace = self.workspace
        if workspace is None or not self._recovery_selected:
            return False
        selected = {
            _candidate_identity(candidate): candidate
            for candidate in self._recovery_candidates
            if _candidate_identity(candidate) in self._recovery_selected
        }
        try:
            rescanned = scan_staging_candidates(workspace.outputs)
        except OSError as exc:
            self._recovery_state = "failed"
            self._recovery_issue = f"Could not rescan staging recovery: {exc}"
            self.state_changed.emit()
            return False

        current_by_path = {str(candidate.path): candidate for candidate in rescanned}
        errors: list[str] = []
        for identity, candidate in selected.items():
            current = current_by_path.get(identity[0])
            if current is None:
                errors.append(f"{candidate.path.name}: candidate is no longer present")
                continue
            if _candidate_identity(current) != identity:
                errors.append(f"{candidate.path.name}: candidate was replaced after selection")
                continue
            try:
                remove_staging_candidate(candidate, workspace.outputs)
            except (OSError, ValueError) as exc:
                errors.append(f"{candidate.path.name}: {exc}")

        self._recovery_selected.clear()
        self.refresh_recovery()
        if errors:
            self._recovery_state = "failed"
            self._recovery_issue = "; ".join(errors)
            self.state_changed.emit()
            return False
        return True

    def _project_record(self, loaded: LoadedJob) -> dict[str, object]:
        data = loaded.data
        if data is None:
            return {
                "recordId": loaded.path.name,
                "operation": "",
                "state": "unreadable",
                "stateLabel": "Unreadable",
                "createdAtUtc": "",
                "updatedAtUtc": "",
                "completedAtUtc": "",
                "configurationPath": "",
                "configurationSha256": "",
                "phase": "",
                "progressCompleted": 0,
                "progressTotal": 0,
                "runId": "",
                "outputDirectory": "",
                "visualizationStatus": "",
                "readable": False,
                "issue": loaded.error or "activity record is unreadable",
            }

        record_id = _text(data.get("request_id"), loaded.path.stem)
        state = self._effective_state(data, record_id)
        configuration = _mapping(data.get("configuration"))
        progress = _mapping(data.get("progress"))
        summary = _mapping(data.get("summary"))
        visualization = _mapping(summary.get("visualization"))
        return {
            "recordId": record_id,
            "operation": _text(data.get("operation")),
            "state": state,
            "stateLabel": _state_label(state),
            "createdAtUtc": _text(data.get("created_at_utc")),
            "updatedAtUtc": _text(data.get("updated_at_utc")),
            "completedAtUtc": _text(data.get("completed_at_utc")),
            "configurationPath": _text(configuration.get("relative_path")),
            "configurationSha256": _text(configuration.get("sha256")),
            "phase": _text(data.get("phase")),
            "progressCompleted": _nonnegative_int(progress.get("completed")),
            "progressTotal": _nonnegative_int(progress.get("total")),
            "runId": _text(summary.get("run_id")),
            "outputDirectory": _text(summary.get("output_directory")),
            "visualizationStatus": _text(visualization.get("status")),
            "readable": True,
            "issue": "",
        }

    def _effective_state(self, data: Mapping[str, object], record_id: str) -> str:
        state = _text(data.get("status"), "unknown")
        if state != "running":
            return state
        session = self.coordinator.active_session
        if (
            session is not None
            and session.owner == "execution"
            and str(session.request_id) == record_id
        ):
            return "running"
        return "interrupted"

    def _refresh_selected_record(self) -> None:
        loaded = self._loaded_records.get(self._selected_record_id)
        if loaded is None:
            self._clear_selected_record()
            return
        row = self._project_record(loaded)
        self._selected_record_state = str(row["state"])
        data = loaded.data
        if data is None:
            self._selected_record_summary = {
                "recordId": self._selected_record_id,
                "readable": False,
                "issue": loaded.error or "activity record is unreadable",
            }
            self._selected_diagnostic_text = (
                f"Unreadable activity record: {loaded.error or 'unknown error'}"
            )
            self._can_inspect_run = False
            self._can_view_plots = False
            return
        summary = _mapping(data.get("summary"))
        visualization = _mapping(summary.get("visualization"))
        output_directory = _text(summary.get("output_directory"))
        operation = _text(data.get("operation"))
        completed_generation = (
            operation == "generate" and self._selected_record_state == "completed"
        )
        visualization_status = _text(visualization.get("status"))
        self._selected_record_summary = {
            **row,
            "runStatus": _text(summary.get("run_status")),
            "rowCount": _nonnegative_int(summary.get("row_count")),
            "validRowCount": _nonnegative_int(summary.get("valid_row_count")),
            "invalidRowCount": _nonnegative_int(summary.get("invalid_row_count")),
            "specId": _text(summary.get("spec_id")),
            "generationContextId": _text(summary.get("generation_context_id")),
            "outputRequestId": _text(summary.get("output_request_id")),
            "visualizationRequestId": _text(visualization.get("visualization_request_id")),
            "visualizationFigureDirectory": _text(visualization.get("figure_directory")),
            "visualizationReportPath": _text(visualization.get("report_path")),
        }
        self._selected_diagnostic_text = json.dumps(data, indent=2, sort_keys=True)
        self._can_inspect_run = completed_generation and bool(output_directory)
        self._can_view_plots = (
            completed_generation
            and visualization_status
            in {"completed", "completed_with_failures", "failed", "skipped_zero_valid_rows"}
            and bool(_text(visualization.get("report_path")))
        )

    def _clear_selected_record(self) -> None:
        self._selected_record_state = ""
        self._selected_record_summary = {}
        self._selected_diagnostic_text = ""
        self._can_inspect_run = False
        self._can_view_plots = False

    def _set_recovery_rows(self) -> None:
        rows = [
            {
                "name": candidate.path.name,
                "path": str(candidate.path),
                "modifiedAtUtc": candidate.modified_at_utc,
                "ageSeconds": candidate.age_seconds,
                "removable": candidate.removable,
                "selected": _candidate_identity(candidate) in self._recovery_selected,
                "issue": candidate.issue or "",
            }
            for candidate in self._recovery_candidates
        ]
        self.recovery_candidates_model.set_rows(rows, available=self.workspace is not None)


def _candidate_identity(candidate: StagingCandidate) -> tuple[str, int, int]:
    return str(candidate.path), candidate.device, candidate.inode


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _state_label(value: str) -> str:
    return value.replace("_", " ").title()
