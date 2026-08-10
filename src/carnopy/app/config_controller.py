from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml
from PySide6.QtCore import Property, QObject, Signal

from carnopy.app.client import WorkerClient
from carnopy.app.config_document import (
    ConfigDocumentError,
    ConfigurationDocument,
    DocumentType,
    ExternalModificationError,
    SavedConfigSnapshot,
    document_from_worker_payload,
    new_document,
    replace_config_atomic,
    sha256_bytes,
    source_matches,
    write_new_config,
)
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.protocol import RequestType
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.sweep_draft import SweepDraft
from carnopy.app.visualization_draft import VisualizationDraft
from carnopy.app.workspace import Workspace
from carnopy.templates import template_text


class ConfigurationController(QObject):
    """Own one exact desktop configuration document and its file lifecycle."""

    state_changed = Signal()
    status_message_changed = Signal()
    draft_changed = Signal(bool)
    document_state_changed = Signal()
    configuration_document_opened = Signal(str)
    warning_requested = Signal(str, str)
    mode_change_requested = Signal(str)
    save_path_requested = Signal(str)
    reformat_confirmation_requested = Signal(str)
    external_change_requested = Signal()
    savePathRequested = Signal(str)
    reformatConfirmationRequested = Signal(str)
    externalChangeRequested = Signal()
    operationFailed = Signal(str, str, str, list)
    saveSucceeded = Signal(str)
    importSucceeded = Signal(str, bool)

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator | None = None,
        dataset_draft: DatasetDraft | None = None,
        visualization_draft: VisualizationDraft | None = None,
        parent: QObject | None = None,
        *,
        sweep_draft: SweepDraft | None = None,
    ) -> None:
        super().__init__(parent)
        self._owns_coordinator = coordinator is None
        if coordinator is None:
            client = WorkerClient(self)
            coordinator = DesktopRequestCoordinator(client, self)
        self.coordinator = coordinator
        self.dataset_draft = dataset_draft or DatasetDraft(self)
        self.visualization_draft = visualization_draft or VisualizationDraft(self)
        self.sweep_draft = sweep_draft or SweepDraft(self)
        self.workspace: Workspace | None = None
        self.document: ConfigurationDocument | None = None
        self.capabilities: dict[str, Any] | None = None
        self._capability_cache: dict[str, dict[str, Any]] = {}
        self._session: RequestSession | None = None
        self._pending_action: str | None = None
        self._pending_path: Path | None = None
        self._pending_content: bytes | None = None
        self._awaiting_save_path = False
        self._locally_valid = False
        self._syncing_document = False
        self._yaml_preview = ""
        self._worker_validation_state = "unavailable"
        self._worker_validation_issue = ""
        self._worker_validation_issues: list[dict[str, str]] = []
        self._validation_attempted = False
        self._validation_content: bytes | None = None
        self._validation_sha256: str | None = None
        self._file_display = "No configuration is open."
        self._status_message = "Open a workspace to create or import a configuration."
        self._lifecycle_guard: Callable[[str], bool] | None = None

        self.dataset_draft.changed.connect(self._refresh_document)
        self.visualization_draft.changed.connect(self._refresh_document)
        self.sweep_draft.changed.connect(self._refresh_document)
        self.sweep_draft.validity_changed.connect(self._sweep_validity_changed)
        self.dataset_draft.mode_change_requested.connect(self.mode_change_requested)
        self.dataset_draft.message.connect(self._set_status)
        self.visualization_draft.message.connect(self._set_status)
        self.visualization_draft.active_plot_draft_changed.connect(self._active_plot_edit_changed)
        self.sweep_draft.active_comparison_draft_changed.connect(self._active_nested_edit_changed)
        self.sweep_draft.message.connect(self._set_status)
        self.coordinator.busy_changed.connect(self._worker_busy_changed)

    def set_lifecycle_guard(self, guard: Callable[[str], bool]) -> None:
        """Install the composition-owned guard for destructive workflow operations."""

        self._lifecycle_guard = guard

    def get_editor_available(self) -> bool:
        return self.workspace is not None and self.capabilities is not None

    editorAvailable = Property(bool, get_editor_available, notify=state_changed)

    def get_has_document(self) -> bool:
        return self.document is not None

    hasDocument = Property(bool, get_has_document, notify=state_changed)

    def get_document_kind(self) -> str:
        document = self.document
        return "none" if document is None else document.document_type

    documentKind = Property(str, get_document_kind, notify=state_changed)

    def get_reformat_required(self) -> bool:
        document = self.document
        return document is not None and document.imported

    reformatRequired = Property(bool, get_reformat_required, notify=state_changed)

    def get_locally_valid(self) -> bool:
        return self._locally_valid

    locallyValid = Property(bool, get_locally_valid, notify=state_changed)

    def get_dirty(self) -> bool:
        document = self.document
        if document is None:
            return False
        if document.document_type == "model_sweep":
            return document.needs_save or self.sweep_draft.get_dirty()
        if document.document_type != "dataset":
            return document.needs_save
        return (
            document.needs_save
            or self.dataset_draft.get_dirty()
            or self.visualization_draft.get_dirty()
        )

    dirty = Property(bool, get_dirty, notify=state_changed)

    def get_yaml_preview(self) -> str:
        return self._yaml_preview

    yamlPreview = Property(str, get_yaml_preview, notify=state_changed)

    def get_yaml_available(self) -> bool:
        return self.document is not None and self._locally_valid and bool(self._yaml_preview)

    yamlAvailable = Property(bool, get_yaml_available, notify=state_changed)

    def get_can_validate(self) -> bool:
        return (
            self.document is not None
            and self._locally_valid
            and not self._has_active_nested_edit()
            and self._pending_action is None
            and not self.coordinator.is_busy
        )

    canValidate = Property(bool, get_can_validate, notify=state_changed)

    def get_worker_validation_state(self) -> str:
        return self._worker_validation_state

    workerValidationState = Property(
        str,
        get_worker_validation_state,
        notify=state_changed,
    )

    def get_worker_validation_issue(self) -> str:
        return self._worker_validation_issue

    workerValidationIssue = Property(
        str,
        get_worker_validation_issue,
        notify=state_changed,
    )

    def get_worker_validation_issues(self) -> list[dict[str, str]]:
        return [dict(issue) for issue in self._worker_validation_issues]

    workerValidationIssues = Property(
        list,
        get_worker_validation_issues,
        notify=state_changed,
    )

    def get_blocking_section(self) -> str:
        if self.document is None:
            return "none"
        if self.document.document_type == "model_sweep" and (
            not self._locally_valid or self.sweep_draft.get_has_active_comparison_edit()
        ):
            return "sweep"
        if self._locally_valid:
            return "none"
        if not self.dataset_draft.get_locally_valid():
            return "dataset"
        if not self.visualization_draft.get_locally_valid():
            return "visualization"
        return "none"

    blockingSection = Property(str, get_blocking_section, notify=state_changed)

    def get_blocking_field(self) -> str:
        section = self.get_blocking_section()
        if section == "sweep":
            return self.sweep_draft.get_first_invalid_field()
        if section == "dataset":
            return self.dataset_draft.get_first_invalid_field()
        if section == "visualization":
            return self.visualization_draft.get_first_invalid_field()
        return ""

    blockingField = Property(str, get_blocking_field, notify=state_changed)

    def get_blocking_row(self) -> int:
        section = self.get_blocking_section()
        if section == "sweep":
            return self.sweep_draft.get_first_invalid_row()
        if section == "dataset":
            return self.dataset_draft.get_first_invalid_row()
        if section == "visualization":
            return self.visualization_draft.get_first_invalid_row()
        return -1

    blockingRow = Property(int, get_blocking_row, notify=state_changed)

    def get_blocking_issue(self) -> str:
        section = self.get_blocking_section()
        if section == "sweep":
            return self.sweep_draft.get_issue()
        if section == "dataset":
            return self.dataset_draft.get_issue()
        if section == "visualization":
            return self.visualization_draft.get_issue()
        return ""

    blockingIssue = Property(str, get_blocking_issue, notify=state_changed)

    def get_first_invalid_field(self) -> str:
        return self.get_blocking_field()

    firstInvalidField = Property(str, get_first_invalid_field, notify=state_changed)

    def get_first_invalid_row(self) -> int:
        return self.get_blocking_row()

    firstInvalidRow = Property(int, get_first_invalid_row, notify=state_changed)

    def get_first_invalid_issue(self) -> str:
        return self.get_blocking_issue()

    firstInvalidIssue = Property(str, get_first_invalid_issue, notify=state_changed)

    def get_file_display(self) -> str:
        return self._file_display

    fileDisplay = Property(str, get_file_display, notify=state_changed)

    def get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, get_status_message, notify=status_message_changed)

    def get_default_save_path(self) -> str:
        workspace = self.workspace
        if workspace is None:
            return ""
        filename = {
            "model_sweep": "model-sweep.yaml",
            "preparation": "preparation.yaml",
        }.get(self.get_document_kind(), "dataset.yaml")
        return str(workspace.configs / filename)

    defaultSavePath = Property(str, get_default_save_path, notify=state_changed)

    def get_can_create(self) -> bool:
        return (
            self.get_editor_available()
            and not self.coordinator.is_busy
            and not self._has_active_nested_edit()
        )

    canCreate = Property(bool, get_can_create, notify=state_changed)

    def get_can_import(self) -> bool:
        return (
            self.workspace is not None
            and not self.coordinator.is_busy
            and not self._has_active_nested_edit()
        )

    canImport = Property(bool, get_can_import, notify=state_changed)

    def get_can_edit(self) -> bool:
        if not self.get_editor_available():
            return False
        session = getattr(self.coordinator, "active_session", None)
        if session is not None and session.owner == "sweep":
            return bool(session.request_type == "execute_sweep")
        return not self.coordinator.is_busy or self.coordinator.active_owner != "configuration"

    canEdit = Property(bool, get_can_edit, notify=state_changed)

    def get_can_save(self) -> bool:
        return (
            self.document is not None
            and self._locally_valid
            and self._pending_action is None
            and not self.coordinator.is_busy
            and not self._has_active_nested_edit()
        )

    canSave = Property(bool, get_can_save, notify=state_changed)
    canSaveAs = Property(bool, get_can_save, notify=state_changed)

    def request_validation(self) -> bool:
        """Run informational worker validation for the exact current YAML revision."""

        if not self._lifecycle_allowed("Validation") or not self.get_can_validate():
            return False
        document = self.document
        if document is None:
            return False
        content = document.yaml_bytes
        source_name = str(document.source_path) if document.source_path is not None else "<gui>"
        self._begin_worker_validation("validate", content)
        self._set_status("Validating the current exact YAML…")
        return self._start_worker(
            _validation_request_type(document.document_type),
            _validation_payload(document.document_type, content, source_name),
        )

    def get_dataset_draft(self) -> QObject:
        return self.dataset_draft

    datasetDraft = Property(QObject, get_dataset_draft, constant=True)

    def get_visualization_draft(self) -> QObject:
        return self.visualization_draft

    visualizationDraft = Property(QObject, get_visualization_draft, constant=True)

    def get_sweep_draft(self) -> QObject:
        return self.sweep_draft

    sweepDraft = Property(QObject, get_sweep_draft, constant=True)

    def set_workspace(self, value: object) -> None:
        workspace = value if isinstance(value, Workspace) else None
        changed = self.workspace != workspace
        if changed and (
            self._has_active_sweep_edit() or not self._lifecycle_allowed("workspace replacement")
        ):
            return
        self.workspace = workspace
        if changed:
            self._clear_document()
            self.capabilities = None
        if workspace is None:
            self.capabilities = None
            self._set_status("Open a workspace to create or import a configuration.")
            self.state_changed.emit()
            return
        cached = self._capability_cache.get("heos")
        if cached is not None:
            self._apply_capabilities(cached)
            return
        self._set_status("Loading current Carnopy capabilities…")
        self._pending_action = "capabilities"
        self._start_worker("describe_capabilities", {"model": "heos"})

    def needs_discard_confirmation(self) -> bool:
        return self.get_dirty()

    def new_dataset(self, mode: str, discard_confirmed: bool = False) -> bool:
        if not self._lifecycle_allowed("New Dataset"):
            return False
        capabilities = self.capabilities
        if self.workspace is None or capabilities is None or self._has_active_sweep_edit():
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before replacing it.")
            return False
        modes = capabilities.get("modes")
        if not isinstance(modes, list) or mode not in modes:
            self._set_status(f"Unsupported dataset mode: {mode}")
            return False
        self.open_document(new_document(_template_payload(mode)))
        self._set_status("New configuration. Save it under the workspace configs folder.")
        return True

    def new_sweep(self, discard_confirmed: bool = False) -> bool:
        if not self._lifecycle_allowed("New Model Sweep") or not self.get_can_create():
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before replacing it.")
            return False
        self.open_document(new_document(_template_payload("model_sweep")))
        self._set_status("New model sweep. Save it under the workspace configs folder.")
        return True

    def import_dataset(self, path: str, discard_confirmed: bool = False) -> bool:
        if not self._lifecycle_allowed("Import"):
            return False
        if self.workspace is None or self._has_active_sweep_edit():
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before replacing it.")
            return False
        candidate = path.strip()
        if not candidate:
            return False
        self._pending_action = "import"
        self._pending_path = Path(candidate).expanduser().resolve()
        self._set_status("Validating imported configuration…")
        return self._start_worker(
            "load_dataset_config",
            {"config_path": str(self._pending_path)},
        )

    def import_configuration(self, path: str, discard_confirmed: bool = False) -> bool:
        """Open any current public configuration by its explicit discriminator."""

        if not self._lifecycle_allowed("Open Configuration"):
            return False
        if not self.get_can_import():
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before replacing it.")
            return False
        candidate = path.strip()
        if not candidate:
            return False
        self._pending_action = "import"
        self._pending_path = Path(candidate).expanduser().resolve()
        self._set_status("Validating imported configuration…")
        return self._start_worker(
            "load_configuration",
            {"config_path": str(self._pending_path)},
        )

    def request_save(self, allow_reformat: bool = False) -> bool:
        if not self._lifecycle_allowed("Save"):
            return False
        document = self.document
        if (
            document is None
            or not self._locally_valid
            or self.coordinator.is_busy
            or self._has_active_sweep_edit()
        ):
            return False
        if document.source_path is None or not document.workspace_owned:
            return self._request_save_as(allow_reformat=allow_reformat)
        expected = document.source_sha256
        if expected is None or not source_matches(document.source_path, expected):
            self._handle_external_change()
            return True
        if document.imported and not allow_reformat:
            self.reformat_confirmation_requested.emit("save")
            self.reformatConfirmationRequested.emit("save")
            return True
        self._validate_before_save(document.source_path, replace=True)
        return True

    def request_save_as(self, allow_reformat: bool = False) -> bool:
        if not self._lifecycle_allowed("Save As"):
            return False
        if (
            self.document is None
            or not self._locally_valid
            or self.coordinator.is_busy
            or self._has_active_sweep_edit()
        ):
            return False
        return self._request_save_as(allow_reformat=allow_reformat)

    def confirm_reformat(self, action: str) -> None:
        if action == "save":
            self.request_save(allow_reformat=True)
        elif action == "save_as":
            self.request_save_as(allow_reformat=True)

    def save_path_selected(self, path: str) -> bool:
        if not self._lifecycle_allowed("Save As"):
            self._awaiting_save_path = False
            return False
        if self._has_active_sweep_edit():
            return False
        if not self._awaiting_save_path:
            self._set_status("Save As is not awaiting a destination.")
            return False
        self._awaiting_save_path = False
        requested = path.strip()
        if not requested:
            self._set_status("Choose a configuration filename for Save As.")
            return False
        candidate = Path(requested).expanduser()
        if not candidate.suffix:
            candidate = candidate.with_suffix(".yaml")
        self._validate_before_save(candidate.resolve(), replace=False)
        return True

    def cancel_save_path(self) -> None:
        self._awaiting_save_path = False

    def reload_source(self, discard_confirmed: bool = False) -> bool:
        if not self._lifecycle_allowed("Reload"):
            return False
        document = self.document
        if (
            document is None
            or document.source_path is None
            or self.coordinator.is_busy
            or self._has_active_sweep_edit()
        ):
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding local changes before reloading the source.")
            return False
        self._pending_action = "reload"
        self._set_status("Reloading configuration changed outside Carnopy…")
        return self._start_worker(
            _load_request_type(document.document_type),
            {"config_path": str(document.source_path)},
        )

    def apply_mode_change(self, selected: str) -> bool:
        if not self._lifecycle_allowed("dataset mode change"):
            return False
        document = self.document
        if document is None or document.document_type != "dataset":
            return False
        self._syncing_document = True
        changed = False
        try:
            changed = self.dataset_draft.apply_mode_change(selected)
            if not changed:
                return False
            payload = self.dataset_draft.merge_into(document.payload)
            payload.pop("visualization", None)
            document.set_payload(payload)
            self.visualization_draft.set_dataset_context(payload)
            self.visualization_draft.reset_for_mode_change()
        finally:
            self._syncing_document = False
        self._refresh_document()
        return changed

    def apply_coordinate_change(self, selected: str) -> bool:
        if not self._lifecycle_allowed("dataset coordinate change"):
            return False
        if self.document is None or self.document.document_type != "dataset":
            return False
        return self.dataset_draft.set_coordinate(selected)

    def open_document(self, document: ConfigurationDocument) -> bool:
        if self._has_active_sweep_edit() or not self._lifecycle_allowed("document replacement"):
            return False
        self.document = document
        self._reset_worker_validation("not_run")
        self._syncing_document = True
        try:
            payload = document.payload
            if document.document_type == "dataset":
                self.dataset_draft.load_payload(payload)
                self.visualization_draft.set_dataset_context(payload)
                self.visualization_draft.load_visualization(payload.get("visualization"))
                self.sweep_draft.clear()
            elif document.document_type == "model_sweep":
                self.dataset_draft.clear()
                self.visualization_draft.clear()
                self.sweep_draft.load_payload(payload)
            else:
                self.dataset_draft.clear()
                self.visualization_draft.clear()
                self.sweep_draft.clear()
        finally:
            self._syncing_document = False
        label = document.document_type.replace("_", " ")
        self._file_display = (
            str(document.source_path)
            if document.source_path is not None
            else f"Unsaved {label} configuration"
        )
        self._refresh_document()
        self.configuration_document_opened.emit(document.document_type)
        return True

    def clear_document(self, discard_confirmed: bool = False) -> bool:
        if self._has_active_sweep_edit() or not self._lifecycle_allowed("Close Configuration"):
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before closing it.")
            return False
        self._clear_document()
        self._set_status("Create a new configuration or open a valid YAML file.")
        return True

    def execution_snapshot(
        self,
        *,
        expected_document_type: DocumentType = "dataset",
    ) -> SavedConfigSnapshot:
        if self.workspace is None or self.document is None:
            raise ConfigDocumentError(
                f"open and save a {expected_document_type} configuration before execution"
            )
        if self.document.document_type != expected_document_type:
            raise ConfigDocumentError(
                f"the open configuration is {self.document.document_type}, not "
                f"{expected_document_type}"
            )
        drafts_valid = (
            self.sweep_draft.get_locally_valid()
            if expected_document_type == "model_sweep"
            else expected_document_type != "dataset"
            or (
                self.dataset_draft.get_locally_valid()
                and self.visualization_draft.get_locally_valid()
            )
        )
        if not self._locally_valid or not drafts_valid or self._has_active_sweep_edit():
            raise ConfigDocumentError("complete the configuration form before execution")
        return self.document.execution_snapshot(configs_root=self.workspace.configs)

    def shutdown(self) -> None:
        if self._owns_coordinator:
            self.coordinator.shutdown()

    def _request_save_as(self, *, allow_reformat: bool) -> bool:
        document = self.document
        if document is None:
            return False
        if document.imported and not allow_reformat:
            self.reformat_confirmation_requested.emit("save_as")
            self.reformatConfirmationRequested.emit("save_as")
            return True
        self._awaiting_save_path = True
        default_path = self.get_default_save_path()
        self.save_path_requested.emit(default_path)
        self.savePathRequested.emit(default_path)
        return True

    def _validate_before_save(self, path: Path, *, replace: bool) -> None:
        document = self.document
        if document is None:
            return
        content = document.yaml_bytes
        action = "save_replace" if replace else "save_new"
        self._begin_worker_validation(action, content)
        self._pending_path = path
        self._pending_content = content
        self._set_status("Validating exact YAML before Save…")
        self._start_worker(
            _validation_request_type(document.document_type),
            _validation_payload(document.document_type, content, str(path)),
        )

    def _start_worker(
        self,
        request_type: RequestType,
        payload: dict[str, object],
    ) -> bool:
        try:
            session = self.coordinator.start_request(
                "configuration",
                request_type,
                payload,
            )
        except (RuntimeError, ValueError) as exc:
            action = self._pending_action or request_type
            if action in {"validate", "save_new", "save_replace"}:
                self._set_worker_validation(
                    "failed",
                    str(exc),
                    [],
                )
                self._clear_validation_request()
            self._clear_pending()
            self._set_status(str(exc))
            self._emit_operation_failed(action, _failure_title(action), str(exc), [])
            self.state_changed.emit()
            return False
        self._session = session
        session.completed.connect(self._worker_completed)
        self.state_changed.emit()
        return True

    def _worker_completed(self, value: object) -> None:
        outcome = cast(RequestOutcome, value)
        session = self._session
        if session is None or outcome.request_id != session.request_id:
            return
        self._session = None
        result = outcome.result_payload
        if result is not None:
            self._worker_succeeded(result)
            return
        self._worker_failed(outcome.failure_payload or {})

    def _worker_succeeded(self, payload: object) -> None:
        result = cast(dict[str, Any], payload)
        action = self._pending_action
        if action is None:
            return
        validation_current = self._validation_response_is_current()
        self._clear_pending(keep_paths=action in {"save_new", "save_replace"})
        if action == "capabilities":
            model = result.get("model")
            if isinstance(model, str):
                self._capability_cache[model] = result
            self._apply_capabilities(result)
        elif action in {"import", "reload"}:
            self._finish_import(result, operation=action)
        elif action == "validate":
            self._clear_validation_request()
            if validation_current:
                self._set_worker_validation("valid", "", [])
                self._set_status("Worker validation passed for the current exact YAML.")
        elif action in {"save_new", "save_replace"}:
            self._clear_validation_request()
            if validation_current:
                self._set_worker_validation("valid", "", [])
            self._finish_save(
                replace=action == "save_replace",
                validation_current=validation_current,
            )

    def _worker_failed(self, payload: object) -> None:
        failure = cast(dict[str, Any], payload)
        action = self._pending_action
        if action is None:
            return
        validation_action = action in {"validate", "save_new", "save_replace"}
        validation_current = self._validation_response_is_current()
        self._clear_pending()
        message = str(failure.get("message", "worker request failed"))
        details = failure.get("details")
        raw_issues = details.get("issues") if isinstance(details, dict) else None
        issues = _structured_issues(raw_issues)
        if validation_action:
            self._clear_validation_request()
            if not validation_current:
                if action in {"save_new", "save_replace"}:
                    self._cancel_stale_save(replace=action == "save_replace")
                return
            state = (
                "invalid"
                if failure.get("category") == "config" and failure.get("code") == "invalid_config"
                else "failed"
            )
            self._set_worker_validation(state, message, issues)
            if action == "validate":
                self._set_status(message)
                return
        if issues:
            issue_lines = [
                f"{item.get('path', '$')}: {item.get('message', 'invalid value')}"
                for item in issues
            ]
            if issue_lines:
                message += "\n" + "\n".join(issue_lines)
        self._set_status(message)
        title = "Import Failed" if action in {"import", "reload"} else "Validation Failed"
        self.warning_requested.emit(title, message)
        self._emit_operation_failed(
            action,
            _failure_title(action),
            str(failure.get("message", message)),
            issues,
        )
        self.state_changed.emit()

    def _worker_busy_changed(self, _busy: bool) -> None:
        self.state_changed.emit()

    def _active_plot_edit_changed(self) -> None:
        self._update_worker_validation(validation_revision_changed=True)
        self.state_changed.emit()

    def _active_nested_edit_changed(self) -> None:
        self._update_worker_validation(validation_revision_changed=True)
        self.state_changed.emit()

    def _sweep_validity_changed(self) -> None:
        if not self._syncing_document:
            self.state_changed.emit()

    def _apply_capabilities(self, payload: dict[str, Any]) -> None:
        self.capabilities = payload
        self.dataset_draft.apply_capabilities(payload)
        self.visualization_draft.apply_capabilities(payload)
        self.sweep_draft.apply_capabilities(payload)
        if self.document is not None:
            self._refresh_document()
        else:
            self._set_status("Create a new configuration or open a valid YAML file.")
        self.state_changed.emit()

    def _clear_document(self) -> None:
        self.document = None
        self._syncing_document = True
        try:
            self.dataset_draft.clear()
            self.visualization_draft.clear()
            self.sweep_draft.clear()
        finally:
            self._syncing_document = False
        self._locally_valid = False
        self._yaml_preview = ""
        self._reset_worker_validation("unavailable")
        self._file_display = "No configuration is open."
        self._awaiting_save_path = False
        self._clear_pending()
        self._emit_document_state()

    def _finish_import(self, payload: dict[str, Any], *, operation: str) -> None:
        workspace = self.workspace
        if workspace is None:
            return
        try:
            document = document_from_worker_payload(payload, configs_root=workspace.configs)
        except ConfigDocumentError as exc:
            self._set_status(str(exc))
            self._emit_operation_failed(operation, _failure_title(operation), str(exc), [])
            return
        if not self.open_document(document):
            return
        location = "workspace configuration" if document.workspace_owned else "external import"
        self._set_status(f"Loaded valid {location}: {document.source_path}")
        if operation == "import" and document.source_path is not None:
            self.importSucceeded.emit(str(document.source_path), not document.workspace_owned)

    def _finish_save(self, *, replace: bool, validation_current: bool) -> None:
        if not self._lifecycle_allowed("Save"):
            self._pending_path = None
            self._pending_content = None
            return
        document = self.document
        workspace = self.workspace
        path = self._pending_path
        content = self._pending_content
        self._pending_path = None
        self._pending_content = None
        if document is None or workspace is None or path is None or content is None:
            message = "Save state was lost before the validated YAML could be written."
            self._set_status(message)
            self._emit_operation_failed(
                "save" if replace else "save_as",
                "Save Failed",
                message,
                [],
            )
            return
        if not validation_current or document.yaml_bytes != content:
            self._cancel_stale_save(replace=replace)
            return
        try:
            if replace:
                expected = document.source_sha256
                if expected is None:
                    raise ConfigDocumentError("saved configuration has no source hash")
                destination = replace_config_atomic(
                    path,
                    content,
                    expected_sha256=expected,
                    configs_root=workspace.configs,
                )
            else:
                destination = write_new_config(path, content, configs_root=workspace.configs)
        except ExternalModificationError:
            self._handle_external_change()
            return
        except ConfigDocumentError as exc:
            self._set_status(str(exc))
            self.warning_requested.emit("Save Failed", str(exc))
            self._emit_operation_failed(
                "save" if replace else "save_as",
                "Save Failed",
                str(exc),
                [],
            )
            return
        document.mark_saved(destination, content)
        if document.document_type == "model_sweep":
            self.sweep_draft.mark_baseline()
        elif document.document_type == "dataset":
            self.dataset_draft.mark_baseline()
            self.visualization_draft.mark_baseline()
        self._file_display = str(destination)
        self._refresh_document(validation_revision_changed=False)
        self._set_status(f"Saved valid configuration: {destination}")
        self.saveSucceeded.emit(str(destination))

    def _cancel_stale_save(self, *, replace: bool) -> None:
        message = (
            "The configuration changed while its YAML was being validated. "
            "No file was written; save again."
        )
        self._set_status(message)
        self.warning_requested.emit("Save Cancelled", message)
        self._emit_operation_failed(
            "save" if replace else "save_as",
            "Save Cancelled",
            message,
            [],
        )

    def _refresh_document(self, *, validation_revision_changed: bool = True) -> None:
        if self._syncing_document:
            return
        document = self.document
        if document is None:
            self._locally_valid = False
            self._yaml_preview = ""
            self._update_worker_validation(validation_revision_changed)
            self._emit_document_state()
            return
        try:
            if document.document_type == "model_sweep":
                if not self.sweep_draft.get_locally_valid():
                    raise ValueError(self.sweep_draft.get_issue())
                document.set_payload(self.sweep_draft.payload())
            elif document.document_type == "dataset":
                payload = self.dataset_draft.merge_into(document.payload)
                dataset_context = self.dataset_draft.dataset_payload()
                self.visualization_draft.set_dataset_context(dataset_context)
                if not self.visualization_draft.get_locally_valid():
                    raise ValueError(self.visualization_draft.get_issue())
                visualization = self.visualization_draft.visualization_payload()
                if visualization is None:
                    payload.pop("visualization", None)
                else:
                    payload["visualization"] = visualization
                document.set_payload(payload)
        except ValueError as exc:
            self._locally_valid = False
            self._yaml_preview = ""
            self._set_status(str(exc))
        else:
            self._locally_valid = True
            self._yaml_preview = document.yaml_text
            self._set_status("Ready to save. Full validation runs before writing.")
        self._update_worker_validation(validation_revision_changed)
        self._emit_document_state()

    def _handle_external_change(self) -> None:
        document = self.document
        if document is None or document.source_path is None:
            return
        self._set_status(f"Saved configuration changed outside Carnopy: {document.source_path}")
        self.external_change_requested.emit()
        self.externalChangeRequested.emit()

    def _clear_pending(self, *, keep_paths: bool = False) -> None:
        self._pending_action = None
        if not keep_paths:
            self._pending_path = None
            self._pending_content = None

    def _begin_worker_validation(self, action: str, content: bytes) -> None:
        self._pending_action = action
        self._validation_attempted = True
        self._validation_content = content
        self._validation_sha256 = sha256_bytes(content)
        self._set_worker_validation("running", "", [])

    def _clear_validation_request(self) -> None:
        self._validation_content = None
        self._validation_sha256 = None

    def _reset_worker_validation(self, state: str) -> None:
        self._validation_attempted = False
        self._clear_validation_request()
        self._set_worker_validation(state, "", [])

    def _validation_response_is_current(self) -> bool:
        document = self.document
        content = self._validation_content
        digest = self._validation_sha256
        if (
            self._worker_validation_state != "running"
            or document is None
            or content is None
            or digest is None
            or not self._locally_valid
            or self._has_active_nested_edit()
        ):
            return False
        current = document.yaml_bytes
        return current == content and sha256_bytes(current) == digest

    def _update_worker_validation(self, validation_revision_changed: bool) -> None:
        if self.document is None:
            self._set_worker_validation("unavailable", "", [])
            return
        active_edit = self._has_active_nested_edit()
        if not self._locally_valid or active_edit:
            issue = (
                "Commit or cancel the active nested edit before validation."
                if active_edit
                else self.get_blocking_issue()
            )
            self._set_worker_validation("blocked", issue, [])
            return
        if validation_revision_changed and self._validation_attempted:
            self._set_worker_validation(
                "stale",
                "The configuration changed since the last worker validation attempt.",
                [],
            )
            return
        if self._worker_validation_state in {"unavailable", "blocked"}:
            state = "stale" if self._validation_attempted else "not_run"
            issue = (
                "The configuration changed since the last worker validation attempt."
                if state == "stale"
                else ""
            )
            self._set_worker_validation(state, issue, [])

    def _set_worker_validation(
        self,
        state: str,
        issue: str,
        issues: list[dict[str, str]],
    ) -> None:
        normalized_issues = [dict(item) for item in issues]
        if (
            state == self._worker_validation_state
            and issue == self._worker_validation_issue
            and normalized_issues == self._worker_validation_issues
        ):
            return
        self._worker_validation_state = state
        self._worker_validation_issue = issue
        self._worker_validation_issues = normalized_issues
        self.state_changed.emit()

    def _set_status(self, message: str) -> None:
        if message == self._status_message:
            return
        self._status_message = message
        self.status_message_changed.emit()

    def _emit_operation_failed(
        self,
        action: str,
        title: str,
        message: str,
        issues: list[dict[str, str]],
    ) -> None:
        self.operationFailed.emit(_operation_name(action), title, message, issues)

    def _emit_document_state(self) -> None:
        self.state_changed.emit()
        self.draft_changed.emit(self.get_dirty())
        self.document_state_changed.emit()

    def _lifecycle_allowed(self, operation: str) -> bool:
        return self._lifecycle_guard is None or self._lifecycle_guard(operation)

    def _has_active_nested_edit(self) -> bool:
        return self.visualization_draft.get_has_active_plot_edit() or self._has_active_sweep_edit()

    def _has_active_sweep_edit(self) -> bool:
        return self.sweep_draft.get_has_active_comparison_edit()


def _template_payload(mode: str) -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    if not isinstance(value, dict):
        raise ConfigDocumentError(f"packaged {mode} template is not a mapping")
    return cast(dict[str, Any], value)


def _operation_name(action: str) -> str:
    return {
        "save_new": "save_as",
        "save_replace": "save",
        "load_dataset_config": "import",
        "load_configuration": "import",
        "validate_dataset_config": "save",
        "validate_configuration": "save",
        "describe_capabilities": "capabilities",
    }.get(action, action)


def _failure_title(action: str) -> str:
    operation = _operation_name(action)
    return {
        "capabilities": "Capability Loading Failed",
        "import": "Import Failed",
        "reload": "Reload Failed",
        "validate": "Validation Failed",
        "save": "Validation Failed",
        "save_as": "Validation Failed",
    }.get(operation, "Operation Failed")


def _load_request_type(document_type: DocumentType) -> RequestType:
    return "load_dataset_config" if document_type == "dataset" else "load_configuration"


def _validation_request_type(document_type: DocumentType) -> RequestType:
    return "validate_dataset_config" if document_type == "dataset" else "validate_configuration"


def _validation_payload(
    document_type: DocumentType,
    content: bytes,
    source_name: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "yaml_text": content.decode("utf-8"),
        "source_name": source_name,
    }
    if document_type != "dataset":
        payload["expected_document_type"] = document_type
    return payload


def _structured_issues(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    issues: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        issue: dict[str, str] = {}
        for key in ("path", "code", "message"):
            candidate = item.get(key)
            if candidate is not None:
                issue[key] = str(candidate)
        if issue:
            issues.append(issue)
    return issues
