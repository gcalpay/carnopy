from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.client import WorkerClient
from carnopy.app.config_document import (
    ConfigDocumentError,
    DatasetConfigDocument,
    ExternalModificationError,
    document_from_worker_payload,
    new_document,
    replace_config_atomic,
    source_matches,
    write_new_config,
)
from carnopy.app.config_widgets import SamplerEditor
from carnopy.app.workspace import Workspace
from carnopy.templates import template_text

MODE_LABELS = {
    "property_table": "Property table",
    "saturation_table": "Saturation table",
    "vapor_mass_fraction_table": "Vapor-mass-fraction table",
}
REFERENCE_FIELDS = {
    "specific_enthalpy",
    "specific_entropy",
    "specific_internal_energy",
}
ITEM_VALUE_ROLE = Qt.ItemDataRole.UserRole


class DatasetConfigEditor(QWidget):
    """Structured editor for the current dataset configuration contract."""

    draft_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace: Workspace | None = None
        self.document: DatasetConfigDocument | None = None
        self.client = WorkerClient(self)
        self.capabilities: dict[str, Any] | None = None
        self._pending_action: str | None = None
        self._pending_path: Path | None = None
        self._pending_content: bytes | None = None
        self._loading = False
        self._form_valid = False
        self._samplers: dict[str, SamplerEditor] = {}
        self._fluid_aliases: dict[str, str] = {}
        self._property_catalog: dict[str, dict[str, Any]] = {}

        root = QVBoxLayout(self)
        root.addLayout(self._build_actions())
        self.file_label = QLabel("No dataset configuration is open.")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.file_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_dataset_tab(), "Dataset")
        self.tabs.addTab(self._build_visualization_tab(), "Visualization")
        self.tabs.addTab(self._build_preview_tab(), "YAML Preview")
        root.addWidget(self.tabs, 1)

        self.status = QLabel("Open a workspace to create or import a dataset configuration.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Configuration status")
        root.addWidget(self.status)

        self.client.request_succeeded.connect(self._worker_succeeded)
        self.client.request_failed.connect(self._worker_failed)
        self.client.busy_changed.connect(self._worker_busy_changed)
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

    def _build_dataset_tab(self) -> QWidget:
        body = QWidget()
        body_layout = QVBoxLayout(body)
        form = QFormLayout()
        self.model = QComboBox()
        self.model.setAccessibleName("Thermodynamic model")
        self.mode = QComboBox()
        self.mode.setAccessibleName("Dataset mode")
        form.addRow("Model", self.model)
        form.addRow("Mode", self.mode)
        body_layout.addLayout(form)

        body_layout.addWidget(QLabel("Fluids (ordered)"))
        fluid_entry = QHBoxLayout()
        self.fluid_input = QComboBox()
        self.fluid_input.setEditable(True)
        self.fluid_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.fluid_input.setAccessibleName("Fluid or alias")
        self.fluid_feedback = QLabel()
        self.fluid_feedback.setAccessibleName("Canonical fluid name")
        add_fluid = QPushButton("Add Fluid")
        add_fluid.clicked.connect(self._add_fluid)
        fluid_entry.addWidget(self.fluid_input, 1)
        fluid_entry.addWidget(add_fluid)
        body_layout.addLayout(fluid_entry)
        body_layout.addWidget(self.fluid_feedback)
        self.fluids = QListWidget()
        self.fluids.setAccessibleName("Selected fluids")
        body_layout.addWidget(self.fluids)
        body_layout.addLayout(self._list_actions(self.fluids, self._remove_fluid, "fluid"))

        body_layout.addWidget(QLabel("Sampling grid"))
        coordinate_form = QFormLayout()
        self.coordinate = QComboBox()
        self.coordinate.addItems(["temperature", "pressure"])
        self.coordinate.setAccessibleName("Independent saturation coordinate")
        self.coordinate_label = QLabel("Independent coordinate")
        self.coordinate_label.setBuddy(self.coordinate)
        coordinate_form.addRow(self.coordinate_label, self.coordinate)
        body_layout.addLayout(coordinate_form)
        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self.grid_container)

        body_layout.addWidget(QLabel("Properties (ordered)"))
        property_entry = QHBoxLayout()
        self.property_input = QComboBox()
        self.property_input.setAccessibleName("Available property")
        add_property = QPushButton("Add Property")
        add_property.clicked.connect(self._add_property)
        property_entry.addWidget(self.property_input, 1)
        property_entry.addWidget(add_property)
        body_layout.addLayout(property_entry)
        self.properties = QListWidget()
        self.properties.setAccessibleName("Selected properties")
        body_layout.addWidget(self.properties)
        body_layout.addLayout(
            self._list_actions(self.properties, self._remove_property, "property")
        )
        self.reference_advisory = QLabel()
        self.reference_advisory.setWordWrap(True)
        self.reference_advisory.setAccessibleName("Reference-state advisory")
        body_layout.addWidget(self.reference_advisory)

        body_layout.addWidget(QLabel("Dataset outputs"))
        output_row = QHBoxLayout()
        self.csv_output = QCheckBox("CSV")
        self.parquet_output = QCheckBox("Parquet")
        output_row.addWidget(self.csv_output)
        output_row.addWidget(self.parquet_output)
        output_row.addStretch(1)
        body_layout.addLayout(output_row)
        body_layout.addStretch(1)

        self.model.currentTextChanged.connect(self._model_changed)
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.coordinate.currentTextChanged.connect(self._coordinate_changed)
        self.fluid_input.currentTextChanged.connect(self._fluid_text_changed)
        self.csv_output.toggled.connect(self._form_changed)
        self.parquet_output.toggled.connect(self._form_changed)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        return scroll

    def _build_visualization_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.visualization_summary = QLabel(
            "Configured visualization is preserved when a file is imported. "
            "Structured plot editing is the next Stage 3 slice."
        )
        self.visualization_summary.setWordWrap(True)
        layout.addWidget(self.visualization_summary)
        layout.addStretch(1)
        return page

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

    def _list_actions(
        self,
        widget: QListWidget,
        remove_slot: Any,
        noun: str,
    ) -> QHBoxLayout:
        layout = QHBoxLayout()
        remove = QPushButton(f"Remove {noun.title()}")
        up = QPushButton("Move Up")
        down = QPushButton("Move Down")
        remove.clicked.connect(remove_slot)
        up.clicked.connect(lambda: self._move_selected(widget, -1))
        down.clicked.connect(lambda: self._move_selected(widget, 1))
        layout.addWidget(remove)
        layout.addWidget(up)
        layout.addWidget(down)
        layout.addStretch(1)
        return layout

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
        cached = self.client.cached_capabilities("heos")
        if cached is not None:
            self._apply_capabilities(cached)
            return
        self.status.setText("Loading current Carnopy capabilities…")
        self._pending_action = "capabilities"
        self.client.start_request("describe_capabilities", {"model": "heos"})

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
        self.client.shutdown()

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
        payload = _template_payload(mode)
        self._open_document(new_document(payload))
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
        self.client.start_request(
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
        self.client.start_request(
            "validate_dataset_config",
            {"yaml_text": content.decode("utf-8"), "source_name": str(path)},
        )

    def _worker_succeeded(self, payload: object) -> None:
        result = cast(dict[str, Any], payload)
        action = self._pending_action
        self._clear_pending(keep_paths=action in {"save_new", "save_replace"})
        if action == "capabilities":
            self._apply_capabilities(result)
        elif action in {"import", "reload"}:
            self._finish_import(result)
        elif action in {"save_new", "save_replace"}:
            self._finish_save(replace=action == "save_replace")

    def _worker_failed(self, payload: object) -> None:
        failure = cast(dict[str, Any], payload)
        action = self._pending_action
        self._clear_pending()
        message = str(failure.get("message", "worker request failed"))
        issues = failure.get("issues")
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
        self._property_catalog = {
            str(item["name"]): item
            for item in payload.get("property_catalog", [])
            if isinstance(item, dict) and "name" in item
        }
        self._fluid_aliases.clear()
        fluid_values: list[str] = []
        for entry in payload.get("fluids", []):
            if not isinstance(entry, dict):
                continue
            canonical = str(entry.get("name", ""))
            for value in [canonical, *entry.get("aliases", [])]:
                text = str(value)
                if text and text.casefold() not in self._fluid_aliases:
                    self._fluid_aliases[text.casefold()] = canonical
                    fluid_values.append(text)
        self.fluid_input.clear()
        self.fluid_input.addItems(sorted(fluid_values, key=str.casefold))
        completer = self.fluid_input.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)

        self._loading = True
        self.model.clear()
        self.model.addItems([str(value) for value in payload.get("models", [])])
        self.mode.clear()
        self.mode.addItems([str(value) for value in payload.get("modes", [])])
        self._loading = False
        self._set_editor_enabled(True)
        self.status.setText("Create a new dataset configuration or import a valid YAML file.")
        self._update_property_choices()
        self._update_actions()

    def _clear_document(self) -> None:
        self.document = None
        self.file_label.setText("No dataset configuration is open.")
        self.preview.clear()
        self.fluids.clear()
        self.properties.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._samplers.clear()
        self.reference_advisory.clear()
        self.visualization_summary.setText("No dataset configuration is open.")
        self._form_valid = False
        self._update_actions()

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

    def _open_document(self, document: DatasetConfigDocument) -> None:
        self.document = document
        self._load_form(document.payload)
        self.file_label.setText(
            str(document.source_path) if document.source_path else "Unsaved dataset configuration"
        )
        self.tabs.setCurrentIndex(0)
        self._refresh_form_state()

    def _load_form(self, payload: dict[str, Any]) -> None:
        if self.capabilities is None:
            return
        self._loading = True
        self.model.setCurrentText(str(payload["backend"]["model"]))
        self.mode.setCurrentText(str(payload["mode"]))
        self._load_list(self.fluids, [str(value) for value in payload.get("fluids", [])])
        self._load_list(
            self.properties,
            [str(value) for value in payload.get("properties", [])],
        )
        formats = payload.get("outputs", {}).get("dataset_formats", ["csv", "parquet"])
        self.csv_output.setChecked("csv" in formats)
        self.parquet_output.setChecked("parquet" in formats)
        grid = cast(dict[str, dict[str, Any]], payload.get("grid", {}))
        coordinate = next(
            (axis for axis in ("temperature", "pressure") if axis in grid),
            "temperature",
        )
        self.coordinate.setCurrentText(coordinate)
        self._rebuild_grid(grid)
        self._loading = False
        self._update_property_choices()
        self._update_selected_property_states()
        self._update_reference_advisory()
        self._update_visualization_summary()

    def _rebuild_grid(self, grid: dict[str, dict[str, Any]]) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._samplers.clear()
        units_by_axis = self.capabilities.get("units_by_axis", {}) if self.capabilities else {}
        for axis, sampler in grid.items():
            editor = SamplerEditor(axis)
            editor.configure_units([str(value) for value in units_by_axis.get(axis, [])])
            editor.load_sampler(sampler)
            editor.changed.connect(self._form_changed)
            self.grid_layout.addWidget(editor)
            self._samplers[axis] = editor
        self.coordinate.setVisible(self.mode.currentText() != "property_table")
        self.coordinate_label.setVisible(self.mode.currentText() != "property_table")

    def _mode_changed(self, selected: str) -> None:
        if self._loading or self.document is None or not selected:
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
            self._loading = True
            self.mode.setCurrentText(previous)
            self._loading = False
            return
        payload = self.document.payload
        target = _template_payload(selected)
        payload["mode"] = selected
        payload["grid"] = target["grid"]
        payload.pop("visualization", None)
        self.document.set_payload(payload)
        self._load_form(payload)
        self._refresh_form_state()

    def _model_changed(self, _model: str) -> None:
        if self._loading:
            return
        self._update_property_choices()
        self._update_selected_property_states()
        self._form_changed()

    def _coordinate_changed(self, axis: str) -> None:
        if self._loading or self.document is None or self.mode.currentText() == "property_table":
            return
        payload = self.document.payload
        grid = cast(dict[str, dict[str, Any]], copy.deepcopy(payload.get("grid", {})))
        current = next((name for name in ("temperature", "pressure") if name in grid), None)
        if current == axis:
            return
        if current is not None:
            grid.pop(current)
        grid[axis] = self._blank_sampler(axis)
        if self.mode.currentText() == "vapor_mass_fraction_table":
            grid = {
                axis: grid[axis],
                "vapor_mass_fraction": grid["vapor_mass_fraction"],
            }
        payload["grid"] = grid
        self.document.set_payload(payload)
        self._loading = True
        self._rebuild_grid(grid)
        self._loading = False
        self._refresh_form_state()

    def _blank_sampler(self, axis: str) -> dict[str, Any]:
        units = (
            self.capabilities.get("units_by_axis", {}).get(axis, []) if self.capabilities else []
        )
        return {"kind": "explicit", "values": [1.0], "unit": str(units[0]) if units else ""}

    def _form_changed(self, *_args: object) -> None:
        if not self._loading:
            self._refresh_form_state()

    def _refresh_form_state(self) -> None:
        document = self.document
        if document is None:
            self.preview.clear()
            self._form_valid = False
            self._update_actions()
            return
        try:
            payload = self._payload_from_form()
            issue = self._obvious_issue(payload)
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
        self._update_reference_advisory()
        self._update_visualization_summary()
        self._update_actions()
        self.draft_changed.emit(document.needs_save)

    def _payload_from_form(self) -> dict[str, Any]:
        if self.document is None:
            raise ValueError("no dataset configuration is open")
        payload = self.document.payload
        payload["schema_version"] = 2
        payload["document_type"] = "dataset"
        payload["backend"] = {"name": "coolprop", "model": self.model.currentText()}
        payload["mode"] = self.mode.currentText()
        payload["fluids"] = self._list_values(self.fluids)
        payload["grid"] = {
            axis: editor.sampler_payload() for axis, editor in self._samplers.items()
        }
        payload["properties"] = self._list_values(self.properties)
        formats = [
            name
            for name, checked in (
                ("csv", self.csv_output.isChecked()),
                ("parquet", self.parquet_output.isChecked()),
            )
            if checked
        ]
        payload["outputs"] = {"dataset_formats": formats}
        return payload

    def _obvious_issue(self, payload: dict[str, Any]) -> str | None:
        if not payload["fluids"]:
            return "Add at least one fluid."
        if not payload["properties"]:
            return "Add at least one property."
        if not payload["outputs"]["dataset_formats"]:
            return "Select CSV, Parquet, or both."
        unsupported = self._unsupported_selected_properties()
        if unsupported:
            return f"Remove properties unsupported by {self.model.currentText()}: " + ", ".join(
                unsupported
            )
        return None

    def _add_fluid(self) -> None:
        requested = self.fluid_input.currentText().strip()
        if not requested:
            return
        if requested.casefold() not in self._fluid_aliases:
            self.status.setText(f"Unknown fluid or alias: {requested}")
            return
        canonical = self._fluid_aliases[requested.casefold()]
        selected_canonical = {
            self._fluid_aliases.get(value.casefold(), value).casefold()
            for value in self._list_values(self.fluids)
        }
        if canonical.casefold() in selected_canonical:
            self.status.setText(f"Fluid or alias is already selected: {canonical}")
            return
        self._append_list_item(self.fluids, requested)
        self._form_changed()

    def _remove_fluid(self) -> None:
        self._remove_selected(self.fluids)

    def _fluid_text_changed(self, text: str) -> None:
        canonical = self._fluid_aliases.get(text.strip().casefold())
        self.fluid_feedback.setText(
            f"Canonical fluid: {canonical}" if canonical else "Choose a known fluid or alias."
        )

    def _add_property(self) -> None:
        name = self.property_input.currentData(ITEM_VALUE_ROLE)
        if not isinstance(name, str) or not name:
            return
        if name in self._list_values(self.properties):
            self.status.setText(f"Property is already selected: {name}")
            return
        if not self._property_supported(name):
            self.status.setText(f"{name} is not supported by {self.model.currentText()}.")
            return
        self._append_list_item(self.properties, name)
        self._update_selected_property_states()
        self._form_changed()

    def _remove_property(self) -> None:
        self._remove_selected(self.properties)
        self._update_selected_property_states()
        self._form_changed()

    def _update_property_choices(self) -> None:
        model = QStandardItemModel(self.property_input)
        for name, metadata in self._property_catalog.items():
            supported = self.model.currentText() in metadata.get("supported_models", [])
            label = name if supported else f"{name} — unsupported by {self.model.currentText()}"
            item = QStandardItem(label)
            item.setData(name, ITEM_VALUE_ROLE)
            item.setEnabled(supported)
            model.appendRow(item)
        self.property_input.setModel(model)

    def _update_selected_property_states(self) -> None:
        model = self.model.currentText()
        for index in range(self.properties.count()):
            item = self.properties.item(index)
            if item is None:
                continue
            name = str(item.data(ITEM_VALUE_ROLE))
            supported = self._property_supported(name)
            item.setText(name if supported else f"Unsupported by {model}: {name}")
            item.setToolTip(
                "Supported by the selected model."
                if supported
                else "Remove this property or select a model that supports it."
            )
            item.setForeground(QColor() if supported else QColor("#a33a00"))

    def _property_supported(self, name: str) -> bool:
        metadata = self._property_catalog.get(name, {})
        return self.model.currentText() in metadata.get("supported_models", [])

    def _unsupported_selected_properties(self) -> list[str]:
        return [
            name
            for name in self._list_values(self.properties)
            if not self._property_supported(name)
        ]

    def _update_reference_advisory(self) -> None:
        selected = REFERENCE_FIELDS.intersection(self._list_values(self.properties))
        self.reference_advisory.setText(
            "Reference-state advisory: absolute enthalpy, entropy, and internal-energy values "
            "depend on the recorded reference-state context."
            if selected
            else ""
        )

    def _update_visualization_summary(self) -> None:
        if self.document is None:
            return
        visualization = self.document.payload.get("visualization")
        plots = visualization.get("plots", []) if isinstance(visualization, dict) else []
        if plots:
            self.visualization_summary.setText(
                f"{len(plots)} configured plot request(s) are preserved. "
                "Structured editing is implemented in the next Stage 3 slice."
            )
        else:
            self.visualization_summary.setText(
                "No configured visualization requests. Structured editing is implemented "
                "in the next Stage 3 slice."
            )

    def _move_selected(self, widget: QListWidget, offset: int) -> None:
        row = widget.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= widget.count():
            return
        item = widget.takeItem(row)
        if item is None:
            return
        widget.insertItem(target, item)
        widget.setCurrentRow(target)
        self._form_changed()

    def _remove_selected(self, widget: QListWidget) -> None:
        row = widget.currentRow()
        if row < 0:
            return
        widget.takeItem(row)
        self._form_changed()

    @staticmethod
    def _append_list_item(widget: QListWidget, value: str) -> None:
        item = QListWidgetItem(value)
        item.setData(ITEM_VALUE_ROLE, value)
        widget.addItem(item)

    def _load_list(self, widget: QListWidget, values: list[str]) -> None:
        widget.clear()
        for value in values:
            self._append_list_item(widget, value)

    @staticmethod
    def _list_values(widget: QListWidget) -> list[str]:
        return [
            str(item.data(ITEM_VALUE_ROLE))
            for index in range(widget.count())
            if (item := widget.item(index)) is not None
        ]

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
            self.client.start_request(
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
        busy = self.client.is_busy
        self.save_button.setEnabled(not busy and self.document is not None and self._form_valid)
        self.save_as_button.setEnabled(not busy and self.document is not None and self._form_valid)


def _template_payload(mode: str) -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    if not isinstance(value, dict):
        raise ConfigDocumentError(f"packaged {mode} template is not a mapping")
    return cast(dict[str, Any], value)
