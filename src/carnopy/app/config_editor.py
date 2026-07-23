from __future__ import annotations

from typing import TYPE_CHECKING, Any

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

from carnopy.app.config_controller import DatasetConfigController
from carnopy.app.config_document import DatasetConfigDocument, SavedConfigSnapshot
from carnopy.app.config_form import DatasetConfigForm
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.visualization_draft import VisualizationDraft
from carnopy.app.visualization_editor import VisualizationEditor
from carnopy.app.workspace import Workspace

if TYPE_CHECKING:
    from carnopy.app.desktop_controller import DesktopController

MODE_LABELS = {
    "property_table": "Property table",
    "saturation_table": "Saturation table",
    "vapor_mass_fraction_table": "Vapor-mass-fraction table",
}


class DatasetConfigEditor(QWidget):
    """Present the configured-dataset controller through Qt Widgets."""

    draft_changed = Signal(bool)
    document_state_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        controller: DatasetConfigController | None = None,
        coordinator: DesktopRequestCoordinator | None = None,
        dataset_draft: DatasetDraft | None = None,
        visualization_draft: VisualizationDraft | None = None,
        desktop_controller: DesktopController | None = None,
    ) -> None:
        super().__init__(parent)
        if desktop_controller is not None:
            if (
                controller is not None
                and controller is not desktop_controller.dataset_config_controller
            ):
                raise ValueError("desktop_controller and controller must share one composition")
            controller = desktop_controller.dataset_config_controller
        if controller is not None and any(
            value is not None for value in (coordinator, dataset_draft, visualization_draft)
        ):
            raise ValueError("supply either controller or its component objects, not both")
        if controller is None:
            controller = DatasetConfigController(
                coordinator,
                dataset_draft,
                visualization_draft,
                self,
            )
        self.controller = controller
        self.desktop_controller = desktop_controller
        self.coordinator = controller.coordinator
        self.dataset_draft = controller.dataset_draft
        self.visualization_draft = controller.visualization_draft

        root = QVBoxLayout(self)
        root.addLayout(self._build_actions())
        self.file_label = QLabel("No dataset configuration is open.")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.file_label)

        self.tabs = QTabWidget()
        self.form = DatasetConfigForm(self.dataset_draft)
        self.visualization = VisualizationEditor(self.visualization_draft)
        self.tabs.addTab(self.form, "Dataset")
        self.tabs.addTab(self.visualization, "Visualization")
        self.tabs.addTab(self._build_preview_tab(), "YAML Preview")
        root.addWidget(self.tabs, 1)

        self.status = QLabel("Open a workspace to create or import a dataset configuration.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Configuration status")
        root.addWidget(self.status)

        self.controller.state_changed.connect(self._sync_view)
        self.controller.status_message_changed.connect(self._sync_status)
        self.controller.draft_changed.connect(self.draft_changed.emit)
        self.controller.document_state_changed.connect(self.document_state_changed.emit)
        self.controller.document_opened.connect(lambda: self.tabs.setCurrentIndex(0))
        self.controller.warning_requested.connect(self._show_warning)
        self.controller.mode_change_requested.connect(self._mode_changed)
        self.form.coordinate_change_requested.connect(self._coordinate_changed)
        self.controller.save_path_requested.connect(self._choose_save_path)
        self.controller.reformat_confirmation_requested.connect(self._confirm_import_reformat)
        self.controller.external_change_requested.connect(self._handle_external_change)
        if self.desktop_controller is not None:
            self.desktop_controller.attentionRequested.connect(self._attention_requested)
        self._sync_view()

    @property
    def workspace(self) -> Workspace | None:
        return self.controller.workspace

    @property
    def document(self) -> DatasetConfigDocument | None:
        return self.controller.document

    @property
    def capabilities(self) -> dict[str, Any] | None:
        return self.controller.capabilities

    @property
    def _form_valid(self) -> bool:
        return self.controller.get_locally_valid()

    @property
    def _capability_cache(self) -> dict[str, dict[str, Any]]:
        return self.controller._capability_cache

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
        self.controller.set_workspace(workspace)

    def confirm_discard(self) -> bool:
        if not self.controller.needs_discard_confirmation():
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
        self.controller.shutdown()

    def execution_snapshot(self) -> SavedConfigSnapshot:
        return self.controller.execution_snapshot()

    def new_dataset(self) -> None:
        capabilities = self.capabilities
        if self.workspace is None or capabilities is None or not self.confirm_discard():
            return
        modes = capabilities.get("modes")
        if not isinstance(modes, list):
            return
        labels = [MODE_LABELS[name] for name in modes if name in MODE_LABELS]
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
        if self.desktop_controller is None:
            self.controller.new_dataset(mode, discard_confirmed=True)
        else:
            self.desktop_controller.request_new_dataset(mode, discard_confirmed=True)

    def import_dataset(self) -> None:
        workspace = self.workspace
        if workspace is None or not self.confirm_discard():
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Valid Dataset Configuration",
            str(workspace.configs),
            "YAML configurations (*.yaml *.yml)",
        )
        if selected:
            if self.desktop_controller is None:
                self.controller.import_dataset(selected, discard_confirmed=True)
            else:
                self.desktop_controller.request_import_dataset(
                    selected,
                    discard_confirmed=True,
                )

    def save(self) -> None:
        if self.desktop_controller is None:
            self.controller.request_save()
        else:
            self.desktop_controller.request_save()

    def save_as(self) -> None:
        if self.desktop_controller is None:
            self.controller.request_save_as()
        else:
            self.desktop_controller.request_save_as()

    def _apply_capabilities(self, payload: dict[str, Any]) -> None:
        self.controller._apply_capabilities(payload)

    def _open_document(self, document: DatasetConfigDocument) -> None:
        self.controller.open_document(document)

    def _refresh_form_state(self) -> None:
        self.controller._refresh_document()

    def _mode_changed(self, selected: str) -> None:
        if self.document is None:
            return
        answer = QMessageBox.question(
            self,
            "Change Dataset Mode?",
            "Changing mode resets the sampling grid and removes configured visualization "
            "requests. Shared model, fluids, properties, and output formats are preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self.desktop_controller is None:
                self.controller.apply_mode_change(selected)
            elif self.desktop_controller.request_dataset_mode_change(selected):
                self.desktop_controller.commit_dataset_decision(True)
        else:
            self.form.sync_from_draft()

    def _coordinate_changed(self, selected: str) -> None:
        answer = QMessageBox.question(
            self,
            "Change Sampling Coordinate?",
            "Changing the independent coordinate replaces that coordinate's sampler. "
            "Other compatible dataset selections are retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self.desktop_controller is None:
                self.controller.apply_coordinate_change(selected)
            elif self.desktop_controller.request_dataset_coordinate_change(selected):
                self.desktop_controller.commit_dataset_decision(True)
        self.form.sync_from_draft()

    def _choose_save_path(self, suggested: str) -> None:
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Dataset Configuration As",
            suggested,
            "YAML configurations (*.yaml *.yml)",
        )
        if selected:
            if self.desktop_controller is None:
                self.controller.save_path_selected(selected)
            else:
                self.desktop_controller.request_save_path_selected(selected)
        else:
            if self.desktop_controller is None:
                self.controller.cancel_save_path()
            else:
                self.desktop_controller.request_cancel_save_path()

    def _confirm_import_reformat(self, action: str) -> None:
        answer = QMessageBox.question(
            self,
            "Save Imported Configuration?",
            "Carnopy writes deterministic YAML. Comments and original formatting from the "
            "imported file are not preserved. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self.desktop_controller is None:
                self.controller.confirm_reformat(action)
            else:
                self.desktop_controller.request_confirm_reformat(action)

    def _handle_external_change(self) -> None:
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
            if self.desktop_controller is None:
                self.controller.reload_source(discard_confirmed=True)
            else:
                self.desktop_controller.request_reload_source(discard_confirmed=True)
        elif clicked is save_as_button:
            self.save_as()

    def _attention_requested(self, section: str, _field: str, _row: int) -> None:
        if section == "visualization":
            self.tabs.setCurrentIndex(1)

    def _show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _sync_status(self) -> None:
        self.status.setText(self.controller.get_status_message())

    def _sync_view(self) -> None:
        self.file_label.setText(self.controller.get_file_display())
        self.preview.setPlainText(self.controller.get_yaml_preview())
        self.tabs.setEnabled(self.controller.get_can_edit())
        self.new_button.setEnabled(self.controller.get_can_create())
        self.import_button.setEnabled(self.controller.get_can_import())
        self.save_button.setEnabled(self.controller.get_can_save())
        self.save_as_button.setEnabled(self.controller.get_can_save())
        self._sync_status()
