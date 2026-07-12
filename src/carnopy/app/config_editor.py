from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
from carnopy.app.config_form import DatasetConfigForm
from carnopy.app.protocol import RequestType
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
    RequestSession,
)
from carnopy.app.visualization_editor import VisualizationEditor
from carnopy.app.workspace import Workspace
from carnopy.templates import template_text

MODE_LABELS = {
    "property_table": "Property table",
    "saturation_table": "Saturation table",
    "vapor_mass_fraction_table": "Vapor-mass-fraction table",
}


class DatasetConfigEditor(QWidget):
    """Coordinate worker-backed validation and safe dataset-config file handling."""

    draft_changed = Signal(bool)
    document_state_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        coordinator: DesktopRequestCoordinator | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace: Workspace | None = None
        self.document: DatasetConfigDocument | None = None
        self._owns_coordinator = coordinator is None
        if coordinator is None:
            client = WorkerClient(self)
            coordinator = DesktopRequestCoordinator(client, self)
        self.coordinator = coordinator
        self.capabilities: dict[str, Any] | None = None
        self._capability_cache: dict[str, dict[str, Any]] = {}
        self._session: RequestSession | None = None
        self._pending_action: str | None = None
        self._pending_path: Path | None = None
        self._pending_content: bytes | None = None
        self._form_valid = False

        root = QVBoxLayout(self)
        root.addLayout(self._build_actions())
        self.file_label = QLabel("No dataset configuration is open.")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.file_label)

        self.tabs = QTabWidget()
        self.form = DatasetConfigForm()
        self.visualization = VisualizationEditor()
        self.tabs.addTab(self.form, "Dataset")
        self.tabs.addTab(self.visualization, "Visualization")
        self.tabs.addTab(self._build_preview_tab(), "YAML Preview")
        root.addWidget(self.tabs, 1)

        self.status = QLabel("Open a workspace to create or import a dataset configuration.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Configuration status")
        root.addWidget(self.status)

        self.form.changed.connect(self._refresh_form_state)
        self.form.mode_change_requested.connect(self._mode_changed)
        self.form.coordinate_change_requested.connect(self._coordinate_changed)
        self.form.message.connect(self.status.setText)
        self.visualization.changed.connect(self._refresh_form_state)
        self.coordinator.busy_changed.connect(self._worker_busy_changed)
        self._set_editor_enabled(False)

    def _build_actions(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.new_button = QPushButton("New Dataset…")
        self.import_button = QPushButton("Import…")
        self.save_button = QPushButton("Save")
        self.save_as_button = QPushButton("Save As…")
        self.new_button.clicked.connect(self.new_dataset)
        self.import_button.clicked.connect(self.import_dataset)
        self.save_button.clicked.connect(self.save)
        self.save_as_button.clicked.connect(self.save_as)
        for button in (
            self.new_button,
            self.import_button,
            self.save_button,
            self.save_as_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        return layout

    def _build_preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("Read-only preview of the exact deterministic YAML written by Save.")
        )
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("YAML preview")
        layout.addWidget(self.preview, 1)
        return page

    def set_workspace(self, workspace: Workspace | None) -> None:
        changed = self.workspace != workspace
        self.workspace = workspace
        if changed:
            self._clear_document()
        if workspace is None:
            self.capabilities = None
            self._set_editor_enabled(False)
            self.status.setText("Open a workspace to create or import a configuration.")
            return
        self._set_editor_enabled(False)
        cached = self._capability_cache.get("heos")
        if cached is not None:
            self._apply_capabilities(cached)
            return
        self.status.setText("Loading current Carnopy capabilities…")
        self._pending_action = "capabilities"
        self._start_worker("describe_capabilities", {"model": "heos"})

    def confirm_discard(self) -> bool:
        if self.document is None or not self.document.needs_save:
            return True
        answer = QMessageBox.question(
            self,
            "Discard Configuration Changes?",
            "The current dataset configuration has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def shutdown(self) -> None:
        if self._owns_coordinator:
            self.coordinator.shutdown()

    def execution_snapshot(self) -> SavedConfigSnapshot:
        if self.workspace is None or self.document is None:
            raise ConfigDocumentError("open and save a dataset configuration before execution")
        if not self._form_valid:
            raise ConfigDocumentError("complete the configuration form before execution")
        return self.document.execution_snapshot(configs_root=self.workspace.configs)

    def new_dataset(self) -> None:
        if self.workspace is None or self.capabilities is None or not self.confirm_discard():
            return
        labels = [MODE_LABELS[name] for name in self.capabilities["modes"]]
        selected, accepted = QInputDialog.getItem(
            self,
            "New Dataset Configuration",
            "Dataset mode",
            labels,
            editable=False,
        )
        if not accepted:
            return
        mode = next(name for name, label in MODE_LABELS.items() if label == selected)
        self._open_document(new_document(_template_payload(mode)))
        self.status.setText("New configuration. Save it under the workspace configs folder.")

    def import_dataset(self) -> None:
        if self.workspace is None or not self.confirm_discard():
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Valid Dataset Configuration",
            str(self.workspace.configs),
            "YAML configurations (*.yaml *.yml)",
        )
        if not selected:
            return
        self._pending_action = "import"
        self._pending_path = Path(selected).resolve()
        self.status.setText("Validating imported configuration…")
        self._start_worker(
            "load_dataset_config",
            {"config_path": str(self._pending_path)},
        )

    def save(self) -> None:
        document = self.document
        if document is None or not self._form_valid:
            return
        if document.source_path is None or not document.workspace_owned:
            self.save_as()
            return
        expected = document.source_sha256
        if expected is None or not source_matches(document.source_path, expected):
            self._handle_external_change()
            return
        if document.imported and not self._confirm_import_reformat():
            return
        self._validate_before_save(document.source_path, replace=True)

    def save_as(self) -> None:
        if self.workspace is None or self.document is None or not self._form_valid:
            return
        if self.document.imported and not self._confirm_import_reformat():
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Dataset Configuration As",
            str(self.workspace.configs / "dataset.yaml"),
            "YAML configurations (*.yaml *.yml)",
        )
        if not selected:
            return
        path = Path(selected)
        if not path.suffix:
            path = path.with_suffix(".yaml")
        self._validate_before_save(path.resolve(), replace=False)

    def _validate_before_save(self, path: Path, *, replace: bool) -> None:
        if self.document is None:
            return
        content = self.document.yaml_bytes
        self._pending_action = "save_replace" if replace else "save_new"
        self._pending_path = path
        self._pending_content = content
        self.status.setText("Validating exact YAML before Save…")
        self._start_worker(
            "validate_dataset_config",
            {"yaml_text": content.decode("utf-8"), "source_name": str(path)},
        )

    def _start_worker(
        self,
        request_type: RequestType,
        payload: dict[str, object],
    ) -> None:
        try:
            session = self.coordinator.start_request(
                "configuration",
                request_type,
                payload,
            )
        except (RuntimeError, ValueError) as exc:
            self._clear_pending()
            self.status.setText(str(exc))
            self._update_actions()
            return
        self._session = session
        session.completed.connect(self._worker_completed)

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
            details = [
                f"{item.get('path', '$')}: {item.get('message', 'invalid value')}"
                for item in issues
                if isinstance(item, dict)
            ]
            if details:
                message += "\n" + "\n".join(details)
        self.status.setText(message)
        title = "Import Failed" if action in {"import", "reload"} else "Validation Failed"
        QMessageBox.warning(self, title, message)
        self._update_actions()

    def _worker_busy_changed(self, busy: bool) -> None:
        self.new_button.setEnabled(
            not busy and self.workspace is not None and self.capabilities is not None
        )
        self.import_button.setEnabled(not busy and self.workspace is not None)
        self._update_actions()

    def _apply_capabilities(self, payload: dict[str, Any]) -> None:
        self.capabilities = payload
        self.form.apply_capabilities(payload)
        self.visualization.apply_capabilities(payload)
        self._set_editor_enabled(True)
        self.status.setText("Create a new dataset configuration or import a valid YAML file.")

    def _clear_document(self) -> None:
        self.document = None
        self.file_label.setText("No dataset configuration is open.")
        self.preview.clear()
        self.form.clear()
        self.visualization.load_visualization(None)
        self._form_valid = False
        self._update_actions()
        self.document_state_changed.emit()

    def _finish_import(self, payload: dict[str, Any]) -> None:
        if self.workspace is None:
            return
        try:
            document = document_from_worker_payload(payload, configs_root=self.workspace.configs)
        except ConfigDocumentError as exc:
            self.status.setText(str(exc))
            return
        self._open_document(document)
        location = "workspace configuration" if document.workspace_owned else "external import"
        self.status.setText(f"Loaded valid {location}: {document.source_path}")

    def _finish_save(self, *, replace: bool) -> None:
        document = self.document
        workspace = self.workspace
        path = self._pending_path
        content = self._pending_content
        self._pending_path = None
        self._pending_content = None
        if document is None or workspace is None or path is None or content is None:
            self.status.setText("Save state was lost before the validated YAML could be written.")
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
            self.status.setText(str(exc))
            QMessageBox.warning(self, "Save Failed", str(exc))
            return
        document.mark_saved(destination, content)
        self.file_label.setText(str(destination))
        self.status.setText(f"Saved valid configuration: {destination}")
        self._refresh_form_state()
        self.document_state_changed.emit()

    def _open_document(self, document: DatasetConfigDocument) -> None:
        self.document = document
        self.form.load_payload(document.payload)
        self.visualization.set_dataset_context(document.payload)
        self.visualization.load_visualization(document.payload.get("visualization"))
        self.file_label.setText(
            str(document.source_path) if document.source_path else "Unsaved dataset configuration"
        )
        self.tabs.setCurrentIndex(0)
        self._refresh_form_state()

    def _mode_changed(self, selected: str) -> None:
        if self.document is None:
            return
        previous = str(self.document.payload.get("mode", ""))
        if selected == previous:
            return
        answer = QMessageBox.question(
            self,
            "Change Dataset Mode?",
            "Changing mode resets the sampling grid and removes configured visualization "
            "requests. Shared model, fluids, properties, and output formats are preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.form.load_payload(self.document.payload)
            return
        payload = self.document.payload
        payload["mode"] = selected
        payload["grid"] = _template_payload(selected)["grid"]
        payload.pop("visualization", None)
        self.document.set_payload(payload)
        self.form.load_payload(payload)
        self.visualization.set_dataset_context(payload)
        self.visualization.load_visualization(None)
        self._refresh_form_state()

    def _coordinate_changed(self, axis: str) -> None:
        if self.document is None or self.form.mode_name == "property_table":
            return
        payload = self.document.payload
        grid = cast(dict[str, dict[str, Any]], copy.deepcopy(payload.get("grid", {})))
        current = next((name for name in ("temperature", "pressure") if name in grid), None)
        if current == axis:
            return
        if current is not None:
            grid.pop(current)
        grid[axis] = self.form.blank_sampler(axis)
        if self.form.mode_name == "vapor_mass_fraction_table":
            grid = {
                axis: grid[axis],
                "vapor_mass_fraction": grid["vapor_mass_fraction"],
            }
        payload["grid"] = grid
        self.document.set_payload(payload)
        self.form.set_grid(grid)
        self._refresh_form_state()

    def _refresh_form_state(self) -> None:
        document = self.document
        if document is None:
            self.preview.clear()
            self._form_valid = False
            self._update_actions()
            return
        try:
            payload = self.form.current_payload(document.payload)
            self.visualization.set_dataset_context(payload)
            visualization = self.visualization.visualization_payload()
            if visualization is None:
                payload.pop("visualization", None)
            else:
                payload["visualization"] = visualization
            issue = self.form.obvious_issue(payload)
            if issue is not None:
                raise ValueError(issue)
        except ValueError as exc:
            self._form_valid = False
            self.preview.setPlainText(
                f"# YAML preview is unavailable until the form is complete.\n# {exc}\n"
            )
            self.status.setText(str(exc))
        else:
            document.set_payload(payload)
            self._form_valid = True
            self.preview.setPlainText(document.yaml_text)
            self.status.setText("Ready to save. Full validation runs before writing.")
        self._update_actions()
        self.draft_changed.emit(document.needs_save)
        self.document_state_changed.emit()

    def _handle_external_change(self) -> None:
        if self.document is None or self.document.source_path is None:
            return
        message = QMessageBox(self)
        message.setWindowTitle("Configuration Changed Externally")
        message.setText(
            "The saved file changed outside Carnopy. Reload it, save this draft under a new "
            "name, or cancel."
        )
        reload_button = message.addButton("Reload", QMessageBox.ButtonRole.AcceptRole)
        save_as_button = message.addButton("Save As…", QMessageBox.ButtonRole.ActionRole)
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        clicked = message.clickedButton()
        if clicked is reload_button:
            self._pending_action = "reload"
            self._start_worker(
                "load_dataset_config",
                {"config_path": str(self.document.source_path)},
            )
        elif clicked is save_as_button:
            self.save_as()

    def _confirm_import_reformat(self) -> bool:
        if self.document is None or not self.document.imported:
            return True
        answer = QMessageBox.question(
            self,
            "Save Imported Configuration?",
            "Carnopy writes deterministic YAML. Comments and original formatting from the "
            "imported file are not preserved. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _clear_pending(self, *, keep_paths: bool = False) -> None:
        self._pending_action = None
        if not keep_paths:
            self._pending_path = None
            self._pending_content = None

    def _set_editor_enabled(self, enabled: bool) -> None:
        self.tabs.setEnabled(enabled)
        self.new_button.setEnabled(enabled and self.workspace is not None)
        self.import_button.setEnabled(enabled and self.workspace is not None)
        self._update_actions()

    def _update_actions(self) -> None:
        busy = self.coordinator.is_busy
        self.save_button.setEnabled(not busy and self.document is not None and self._form_valid)
        self.save_as_button.setEnabled(not busy and self.document is not None and self._form_valid)


def _template_payload(mode: str) -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    if not isinstance(value, dict):
        raise ConfigDocumentError(f"packaged {mode} template is not a mapping")
    return cast(dict[str, Any], value)
