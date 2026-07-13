from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.client import WorkerClient
from carnopy.app.config_document import (
    ConfigDocumentError,
    DatasetConfigDocument,
    ExternalModificationError,
    SavedConfigSnapshot,
    document_from_worker_payload,
    new_document,
    replace_config_atomic,
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
from carnopy.app.visualization_draft import VisualizationDraft
from carnopy.app.workspace import Workspace
from carnopy.templates import template_text


class DatasetConfigController(QObject):
    """Own the complete desktop dataset-configuration workflow."""

    state_changed = Signal()
    status_message_changed = Signal()
    draft_changed = Signal(bool)
    document_state_changed = Signal()
    document_opened = Signal()
    warning_requested = Signal(str, str)
    mode_change_requested = Signal(str)
    save_path_requested = Signal(str)
    reformat_confirmation_requested = Signal(str)
    external_change_requested = Signal()

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator | None = None,
        dataset_draft: DatasetDraft | None = None,
        visualization_draft: VisualizationDraft | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._owns_coordinator = coordinator is None
        if coordinator is None:
            client = WorkerClient(self)
            coordinator = DesktopRequestCoordinator(client, self)
        self.coordinator = coordinator
        self.dataset_draft = dataset_draft or DatasetDraft(self)
        self.visualization_draft = visualization_draft or VisualizationDraft(self)
        self.workspace: Workspace | None = None
        self.document: DatasetConfigDocument | None = None
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
        self._file_display = "No dataset configuration is open."
        self._status_message = "Open a workspace to create or import a dataset configuration."

        self.dataset_draft.changed.connect(self._refresh_document)
        self.visualization_draft.changed.connect(self._refresh_document)
        self.dataset_draft.mode_change_requested.connect(self.mode_change_requested)
        self.dataset_draft.message.connect(self._set_status)
        self.visualization_draft.message.connect(self._set_status)
        self.coordinator.busy_changed.connect(self._worker_busy_changed)

    def get_editor_available(self) -> bool:
        return self.workspace is not None and self.capabilities is not None

    editorAvailable = Property(bool, get_editor_available, notify=state_changed)

    def get_has_document(self) -> bool:
        return self.document is not None

    hasDocument = Property(bool, get_has_document, notify=state_changed)

    def get_locally_valid(self) -> bool:
        return self._locally_valid

    locallyValid = Property(bool, get_locally_valid, notify=state_changed)

    def get_dirty(self) -> bool:
        document = self.document
        return document is not None and (
            document.needs_save
            or self.dataset_draft.get_dirty()
            or self.visualization_draft.get_dirty()
        )

    dirty = Property(bool, get_dirty, notify=state_changed)

    def get_yaml_preview(self) -> str:
        return self._yaml_preview

    yamlPreview = Property(str, get_yaml_preview, notify=state_changed)

    def get_file_display(self) -> str:
        return self._file_display

    fileDisplay = Property(str, get_file_display, notify=state_changed)

    def get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, get_status_message, notify=status_message_changed)

    def get_default_save_path(self) -> str:
        workspace = self.workspace
        return "" if workspace is None else str(workspace.configs / "dataset.yaml")

    defaultSavePath = Property(str, get_default_save_path, notify=state_changed)

    def get_can_create(self) -> bool:
        return self.get_editor_available() and not self.coordinator.is_busy

    canCreate = Property(bool, get_can_create, notify=state_changed)

    def get_can_import(self) -> bool:
        return self.workspace is not None and not self.coordinator.is_busy

    canImport = Property(bool, get_can_import, notify=state_changed)

    def get_can_edit(self) -> bool:
        return self.get_editor_available() and (
            not self.coordinator.is_busy or self.coordinator.active_owner != "configuration"
        )

    canEdit = Property(bool, get_can_edit, notify=state_changed)

    def get_can_save(self) -> bool:
        return self.document is not None and self._locally_valid and not self.coordinator.is_busy

    canSave = Property(bool, get_can_save, notify=state_changed)
    canSaveAs = Property(bool, get_can_save, notify=state_changed)

    def get_dataset_draft(self) -> QObject:
        return self.dataset_draft

    datasetDraft = Property(QObject, get_dataset_draft, constant=True)

    def get_visualization_draft(self) -> QObject:
        return self.visualization_draft

    visualizationDraft = Property(QObject, get_visualization_draft, constant=True)

    @Slot(object)
    def set_workspace(self, value: object) -> None:
        workspace = value if isinstance(value, Workspace) else None
        changed = self.workspace != workspace
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

    @Slot(str, bool, result=bool)
    def new_dataset(self, mode: str, discard_confirmed: bool = False) -> bool:
        if self.workspace is None or self.capabilities is None:
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before replacing it.")
            return False
        modes = self.capabilities.get("modes")
        if not isinstance(modes, list) or mode not in modes:
            self._set_status(f"Unsupported dataset mode: {mode}")
            return False
        self.open_document(new_document(_template_payload(mode)))
        self._set_status("New configuration. Save it under the workspace configs folder.")
        return True

    @Slot(str, bool, result=bool)
    def import_dataset(self, path: str, discard_confirmed: bool = False) -> bool:
        if self.workspace is None:
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

    @Slot(bool, result=bool)
    def request_save(self, allow_reformat: bool = False) -> bool:
        document = self.document
        if document is None or not self._locally_valid or self.coordinator.is_busy:
            return False
        if document.source_path is None or not document.workspace_owned:
            return self._request_save_as(allow_reformat=allow_reformat)
        expected = document.source_sha256
        if expected is None or not source_matches(document.source_path, expected):
            self._handle_external_change()
            return True
        if document.imported and not allow_reformat:
            self.reformat_confirmation_requested.emit("save")
            return True
        self._validate_before_save(document.source_path, replace=True)
        return True

    @Slot(bool, result=bool)
    def request_save_as(self, allow_reformat: bool = False) -> bool:
        if self.document is None or not self._locally_valid or self.coordinator.is_busy:
            return False
        return self._request_save_as(allow_reformat=allow_reformat)

    @Slot(str)
    def confirm_reformat(self, action: str) -> None:
        if action == "save":
            self.request_save(allow_reformat=True)
        elif action == "save_as":
            self.request_save_as(allow_reformat=True)

    @Slot(str, result=bool)
    def save_path_selected(self, path: str) -> bool:
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

    @Slot()
    def cancel_save_path(self) -> None:
        self._awaiting_save_path = False

    @Slot(bool, result=bool)
    def reload_source(self, discard_confirmed: bool = False) -> bool:
        document = self.document
        if document is None or document.source_path is None or self.coordinator.is_busy:
            return False
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding local changes before reloading the source.")
            return False
        self._pending_action = "reload"
        self._set_status("Reloading configuration changed outside Carnopy…")
        return self._start_worker(
            "load_dataset_config",
            {"config_path": str(document.source_path)},
        )

    @Slot(str, result=bool)
    def apply_mode_change(self, selected: str) -> bool:
        document = self.document
        if document is None:
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

    def open_document(self, document: DatasetConfigDocument) -> None:
        self.document = document
        self._syncing_document = True
        try:
            payload = document.payload
            self.dataset_draft.load_payload(payload)
            self.visualization_draft.set_dataset_context(payload)
            self.visualization_draft.load_visualization(payload.get("visualization"))
        finally:
            self._syncing_document = False
        self._file_display = (
            str(document.source_path)
            if document.source_path is not None
            else "Unsaved dataset configuration"
        )
        self._refresh_document()
        self.document_opened.emit()

    @Slot(bool, result=bool)
    def clear_document(self, discard_confirmed: bool = False) -> bool:
        if self.needs_discard_confirmation() and not discard_confirmed:
            self._set_status("Confirm discarding the current configuration before closing it.")
            return False
        self._clear_document()
        self._set_status("Create a new dataset configuration or import a valid YAML file.")
        return True

    def execution_snapshot(self) -> SavedConfigSnapshot:
        if self.workspace is None or self.document is None:
            raise ConfigDocumentError("open and save a dataset configuration before execution")
        if not self._locally_valid or not (
            self.dataset_draft.get_locally_valid() and self.visualization_draft.get_locally_valid()
        ):
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
            return True
        self._awaiting_save_path = True
        self.save_path_requested.emit(self.get_default_save_path())
        return True

    def _validate_before_save(self, path: Path, *, replace: bool) -> None:
        document = self.document
        if document is None:
            return
        content = document.yaml_bytes
        self._pending_action = "save_replace" if replace else "save_new"
        self._pending_path = path
        self._pending_content = content
        self._set_status("Validating exact YAML before Save…")
        self._start_worker(
            "validate_dataset_config",
            {"yaml_text": content.decode("utf-8"), "source_name": str(path)},
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
            self._clear_pending()
            self._set_status(str(exc))
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
        self._clear_pending(keep_paths=action in {"save_new", "save_replace"})
        if action == "capabilities":
            model = result.get("model")
            if isinstance(model, str):
                self._capability_cache[model] = result
            self._apply_capabilities(result)
        elif action in {"import", "reload"}:
            self._finish_import(result)
        elif action in {"save_new", "save_replace"}:
            self._finish_save(replace=action == "save_replace")

    def _worker_failed(self, payload: object) -> None:
        failure = cast(dict[str, Any], payload)
        action = self._pending_action
        if action is None:
            return
        self._clear_pending()
        message = str(failure.get("message", "worker request failed"))
        details = failure.get("details")
        issues = details.get("issues") if isinstance(details, dict) else None
        if isinstance(issues, list):
            issue_lines = [
                f"{item.get('path', '$')}: {item.get('message', 'invalid value')}"
                for item in issues
                if isinstance(item, dict)
            ]
            if issue_lines:
                message += "\n" + "\n".join(issue_lines)
        self._set_status(message)
        title = "Import Failed" if action in {"import", "reload"} else "Validation Failed"
        self.warning_requested.emit(title, message)
        self.state_changed.emit()

    def _worker_busy_changed(self, _busy: bool) -> None:
        self.state_changed.emit()

    def _apply_capabilities(self, payload: dict[str, Any]) -> None:
        self.capabilities = payload
        self.dataset_draft.apply_capabilities(payload)
        self.visualization_draft.apply_capabilities(payload)
        if self.document is not None:
            self._refresh_document()
        else:
            self._set_status("Create a new dataset configuration or import a valid YAML file.")
        self.state_changed.emit()

    def _clear_document(self) -> None:
        self.document = None
        self._syncing_document = True
        try:
            self.dataset_draft.clear()
            self.visualization_draft.clear()
        finally:
            self._syncing_document = False
        self._locally_valid = False
        self._yaml_preview = ""
        self._file_display = "No dataset configuration is open."
        self._awaiting_save_path = False
        self._clear_pending()
        self._emit_document_state()

    def _finish_import(self, payload: dict[str, Any]) -> None:
        workspace = self.workspace
        if workspace is None:
            return
        try:
            document = document_from_worker_payload(payload, configs_root=workspace.configs)
        except ConfigDocumentError as exc:
            self._set_status(str(exc))
            return
        self.open_document(document)
        location = "workspace configuration" if document.workspace_owned else "external import"
        self._set_status(f"Loaded valid {location}: {document.source_path}")

    def _finish_save(self, *, replace: bool) -> None:
        document = self.document
        workspace = self.workspace
        path = self._pending_path
        content = self._pending_content
        self._pending_path = None
        self._pending_content = None
        if document is None or workspace is None or path is None or content is None:
            self._set_status("Save state was lost before the validated YAML could be written.")
            return
        if document.yaml_bytes != content:
            message = (
                "The configuration changed while its YAML was being validated. "
                "No file was written; save again."
            )
            self._set_status(message)
            self.warning_requested.emit("Save Cancelled", message)
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
            return
        document.mark_saved(destination, content)
        self.dataset_draft.mark_baseline()
        self.visualization_draft.mark_baseline()
        self._file_display = str(destination)
        self._refresh_document()
        self._set_status(f"Saved valid configuration: {destination}")

    def _refresh_document(self) -> None:
        if self._syncing_document:
            return
        document = self.document
        if document is None:
            self._locally_valid = False
            self._yaml_preview = ""
            self._emit_document_state()
            return
        try:
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
        except ValueError as exc:
            self._locally_valid = False
            self._yaml_preview = (
                f"# YAML preview is unavailable until the form is complete.\n# {exc}\n"
            )
            self._set_status(str(exc))
        else:
            document.set_payload(payload)
            self._locally_valid = True
            self._yaml_preview = document.yaml_text
            self._set_status("Ready to save. Full validation runs before writing.")
        self._emit_document_state()

    def _handle_external_change(self) -> None:
        document = self.document
        if document is None or document.source_path is None:
            return
        self._set_status(f"Saved configuration changed outside Carnopy: {document.source_path}")
        self.external_change_requested.emit()

    def _clear_pending(self, *, keep_paths: bool = False) -> None:
        self._pending_action = None
        if not keep_paths:
            self._pending_path = None
            self._pending_content = None

    def _set_status(self, message: str) -> None:
        if message == self._status_message:
            return
        self._status_message = message
        self.status_message_changed.emit()

    def _emit_document_state(self) -> None:
        self.state_changed.emit()
        self.draft_changed.emit(self.get_dirty())
        self.document_state_changed.emit()


def _template_payload(mode: str) -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    if not isinstance(value, dict):
        raise ConfigDocumentError(f"packaged {mode} template is not a mapping")
    return cast(dict[str, Any], value)
