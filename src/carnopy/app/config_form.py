from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.config_widgets import SamplerEditor

REFERENCE_FIELDS = {
    "specific_enthalpy",
    "specific_entropy",
    "specific_internal_energy",
}
ITEM_VALUE_ROLE = Qt.ItemDataRole.UserRole


class DatasetConfigForm(QWidget):
    """Editable dataset fields without worker or file-lifecycle concerns."""

    changed = Signal()
    mode_change_requested = Signal(str)
    coordinate_change_requested = Signal(str)
    message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capabilities: dict[str, Any] | None = None
        self._loading = False
        self._samplers: dict[str, SamplerEditor] = {}
        self._fluid_aliases: dict[str, str] = {}
        self._property_catalog: dict[str, dict[str, Any]] = {}

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
        self.csv_output.toggled.connect(self._emit_changed)
        self.parquet_output.toggled.connect(self._emit_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll)

    @property
    def model_name(self) -> str:
        return self.model.currentText()

    @property
    def mode_name(self) -> str:
        return self.mode.currentText()

    def apply_capabilities(self, payload: dict[str, Any]) -> None:
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
        self._update_property_choices()

    def load_payload(self, payload: dict[str, Any]) -> None:
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
        self.set_grid(grid)
        self._loading = False
        self._update_property_choices()
        self._update_selected_property_states()
        self._update_reference_advisory()

    def current_payload(self, base: dict[str, Any]) -> dict[str, Any]:
        payload = base
        payload["schema_version"] = 2
        payload["document_type"] = "dataset"
        payload["backend"] = {"name": "coolprop", "model": self.model_name}
        payload["mode"] = self.mode_name
        payload["fluids"] = self.list_values(self.fluids)
        payload["grid"] = {
            axis: editor.sampler_payload() for axis, editor in self._samplers.items()
        }
        payload["properties"] = self.list_values(self.properties)
        payload["outputs"] = {
            "dataset_formats": [
                name
                for name, checked in (
                    ("csv", self.csv_output.isChecked()),
                    ("parquet", self.parquet_output.isChecked()),
                )
                if checked
            ]
        }
        return payload

    def obvious_issue(self, payload: dict[str, Any]) -> str | None:
        if not payload["fluids"]:
            return "Add at least one fluid."
        if not payload["properties"]:
            return "Add at least one property."
        if not payload["outputs"]["dataset_formats"]:
            return "Select CSV, Parquet, or both."
        unsupported = self.unsupported_selected_properties()
        if unsupported:
            return f"Remove properties unsupported by {self.model_name}: " + ", ".join(unsupported)
        return None

    def clear(self) -> None:
        self.fluids.clear()
        self.properties.clear()
        self.set_grid({})
        self.reference_advisory.clear()

    def set_grid(self, grid: dict[str, dict[str, Any]]) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._samplers.clear()
        units_by_axis = self.capabilities.get("units_by_axis", {}) if self.capabilities else {}
        for axis, sampler in grid.items():
            editor = SamplerEditor(axis)
            editor.configure_units([str(value) for value in units_by_axis.get(axis, [])])
            editor.load_sampler(sampler)
            editor.changed.connect(self._emit_changed)
            self.grid_layout.addWidget(editor)
            self._samplers[axis] = editor
        visible = self.mode_name != "property_table"
        self.coordinate.setVisible(visible)
        self.coordinate_label.setVisible(visible)

    def blank_sampler(self, axis: str) -> dict[str, Any]:
        units = (
            self.capabilities.get("units_by_axis", {}).get(axis, []) if self.capabilities else []
        )
        return {"kind": "explicit", "values": [1.0], "unit": str(units[0]) if units else ""}

    def selected_properties(self) -> list[str]:
        return self.list_values(self.properties)

    def unsupported_selected_properties(self) -> list[str]:
        return [name for name in self.selected_properties() if not self._property_supported(name)]

    def move_selected(self, widget: QListWidget, offset: int) -> None:
        row = widget.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= widget.count():
            return
        item = widget.takeItem(row)
        if item is None:
            return
        widget.insertItem(target, item)
        widget.setCurrentRow(target)
        self._emit_changed()

    @staticmethod
    def list_values(widget: QListWidget) -> list[str]:
        return [
            str(item.data(ITEM_VALUE_ROLE))
            for index in range(widget.count())
            if (item := widget.item(index)) is not None
        ]

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
        up.clicked.connect(lambda: self.move_selected(widget, -1))
        down.clicked.connect(lambda: self.move_selected(widget, 1))
        layout.addWidget(remove)
        layout.addWidget(up)
        layout.addWidget(down)
        layout.addStretch(1)
        return layout

    def _mode_changed(self, selected: str) -> None:
        if not self._loading and selected:
            self.mode_change_requested.emit(selected)

    def _model_changed(self, _model: str) -> None:
        if self._loading:
            return
        self._update_property_choices()
        self._update_selected_property_states()
        self._emit_changed()

    def _coordinate_changed(self, axis: str) -> None:
        if not self._loading and self.mode_name != "property_table":
            self.coordinate_change_requested.emit(axis)

    def _emit_changed(self, *_args: object) -> None:
        if not self._loading:
            self._update_reference_advisory()
            self.changed.emit()

    def _add_fluid(self) -> None:
        requested = self.fluid_input.currentText().strip()
        if not requested:
            return
        if requested.casefold() not in self._fluid_aliases:
            self.message.emit(f"Unknown fluid or alias: {requested}")
            return
        canonical = self._fluid_aliases[requested.casefold()]
        selected_canonical = {
            self._fluid_aliases.get(value.casefold(), value).casefold()
            for value in self.list_values(self.fluids)
        }
        if canonical.casefold() in selected_canonical:
            self.message.emit(f"Fluid or alias is already selected: {canonical}")
            return
        self._append_list_item(self.fluids, requested)
        self._emit_changed()

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
        if name in self.selected_properties():
            self.message.emit(f"Property is already selected: {name}")
            return
        if not self._property_supported(name):
            self.message.emit(f"{name} is not supported by {self.model_name}.")
            return
        self._append_list_item(self.properties, name)
        self._update_selected_property_states()
        self._emit_changed()

    def _remove_property(self) -> None:
        self._remove_selected(self.properties)
        self._update_selected_property_states()

    def _update_property_choices(self) -> None:
        model = QStandardItemModel(self.property_input)
        for name, metadata in self._property_catalog.items():
            supported = self.model_name in metadata.get("supported_models", [])
            label = name if supported else f"{name} — unsupported by {self.model_name}"
            item = QStandardItem(label)
            item.setData(name, ITEM_VALUE_ROLE)
            item.setEnabled(supported)
            model.appendRow(item)
        self.property_input.setModel(model)

    def _update_selected_property_states(self) -> None:
        for index in range(self.properties.count()):
            item = self.properties.item(index)
            if item is None:
                continue
            name = str(item.data(ITEM_VALUE_ROLE))
            supported = self._property_supported(name)
            item.setText(name if supported else f"Unsupported by {self.model_name}: {name}")
            item.setToolTip(
                "Supported by the selected model."
                if supported
                else "Remove this property or select a model that supports it."
            )
            item.setForeground(QColor() if supported else QColor("#a33a00"))

    def _property_supported(self, name: str) -> bool:
        metadata = self._property_catalog.get(name, {})
        return self.model_name in metadata.get("supported_models", [])

    def _update_reference_advisory(self) -> None:
        selected = REFERENCE_FIELDS.intersection(self.selected_properties())
        self.reference_advisory.setText(
            "Reference-state advisory: absolute enthalpy, entropy, and internal-energy values "
            "depend on the recorded reference-state context."
            if selected
            else ""
        )

    def _remove_selected(self, widget: QListWidget) -> None:
        row = widget.currentRow()
        if row < 0:
            return
        widget.takeItem(row)
        self._emit_changed()

    @staticmethod
    def _append_list_item(widget: QListWidget, value: str) -> None:
        item = QListWidgetItem(value)
        item.setData(ITEM_VALUE_ROLE, value)
        widget.addItem(item)

    def _load_list(self, widget: QListWidget, values: list[str]) -> None:
        widget.clear()
        for value in values:
            self._append_list_item(widget, value)
