from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

PLOT_ROLE = Qt.ItemDataRole.UserRole


class MappingTable(QWidget):
    changed = Signal()

    def __init__(
        self,
        key_label: str,
        value_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([key_label, value_label])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(lambda _item: self.changed.emit())
        add = QPushButton("Add Row")
        remove = QPushButton("Remove Row")
        add.clicked.connect(self.add_row)
        remove.clicked.connect(self.remove_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def add_row(self, key: str = "", value: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self.changed.emit()

    def load_mapping(self, value: Mapping[str, object], *, multiple: bool = False) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for key, item in value.items():
            if multiple and isinstance(item, (list, tuple)):
                rendered = ", ".join(_scalar_text(entry) for entry in item)
            else:
                rendered = _scalar_text(item)
            self.add_row(str(key), rendered)
        self.table.blockSignals(False)

    def mapping(
        self,
        *,
        multiple: bool = False,
        field_kinds: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            key = key_item.text().strip() if key_item is not None else ""
            raw = value_item.text().strip() if value_item is not None else ""
            if not key and not raw:
                continue
            if not key or not raw:
                raise ValueError("mapping rows require both a field and a value")
            if key in result:
                raise ValueError(f"mapping contains duplicate field {key!r}")
            kind = field_kinds.get(key) if field_kinds is not None else None
            if multiple:
                parts = [part.strip() for part in raw.split(",")]
                if any(not part for part in parts):
                    raise ValueError(f"series field {key!r} contains an empty value")
                result[key] = [_parse_scalar(part, kind=kind) for part in parts]
            else:
                result[key] = _parse_scalar(raw, kind=kind)
        return result


class PlotRequestDialog(QDialog):
    def __init__(
        self,
        capabilities: dict[str, Any],
        dataset_payload: dict[str, Any],
        plot: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plot Request")
        self.resize(720, 760)
        self.capabilities = capabilities
        self.dataset_payload = dataset_payload
        visualization = capabilities.get("visualization", {})
        self.contracts = visualization.get("kind_contracts", {})
        self.field_kinds = {
            str(item["name"]): str(item["kind"])
            for item in visualization.get("fields", [])
            if isinstance(item, dict) and "name" in item and "kind" in item
        }

        content = QWidget()
        self.form = QFormLayout(content)
        self.name = QLineEdit()
        self.kind = QComboBox()
        kinds = [str(value) for value in visualization.get("plot_kinds", [])]
        if dataset_payload.get("mode") == "saturation_table":
            kinds = [value for value in kinds if value != "property_heatmap"]
        self.kind.addItems(kinds)
        self.property_name = _optional_combo(self._properties())
        self.x_field = _optional_combo(self._axis_fields())
        self.y_field = _optional_combo(self._axis_fields())
        self.group_by = _optional_combo(self._group_fields())
        self.fluids = QLineEdit()
        self.fluids.setPlaceholderText("Comma-separated; blank uses all dataset fluids")
        self.value_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.color_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.x_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.y_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.output_format = _optional_combo(
            [str(value) for value in visualization.get("formats", [])],
            empty_label="Use shared format",
        )
        self.filters = MappingTable("Filter field", "Exact SI value")
        self.series = MappingTable("Series field", "Values (comma-separated)")
        self.display_units = MappingTable("Field", "Display unit")

        self._rows: dict[str, QWidget] = {
            "property": self.property_name,
            "x": self.x_field,
            "y": self.y_field,
            "group_by": self.group_by,
            "fluids": self.fluids,
            "value_scale": self.value_scale,
            "color_scale": self.color_scale,
            "x_scale": self.x_scale,
            "y_scale": self.y_scale,
            "format": self.output_format,
            "filters": self.filters,
            "series": self.series,
            "display_units": self.display_units,
        }
        self.form.addRow("Name", self.name)
        self.form.addRow("Kind", self.kind)
        self.form.addRow("Property", self.property_name)
        self.form.addRow("X axis", self.x_field)
        self.form.addRow("Y axis", self.y_field)
        self.form.addRow("Group by", self.group_by)
        self.form.addRow("Fluids", self.fluids)
        self.form.addRow("Value scale", self.value_scale)
        self.form.addRow("Color scale", self.color_scale)
        self.form.addRow("X scale", self.x_scale)
        self.form.addRow("Y scale", self.y_scale)
        self.form.addRow("Format", self.output_format)
        self.form.addRow("Filters", self.filters)
        self.form.addRow("Series", self.series)
        self.form.addRow("Display units", self.display_units)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

        self.kind.currentTextChanged.connect(self._update_visibility)
        self.load_plot(plot or self._default_plot())

    def load_plot(self, plot: dict[str, Any]) -> None:
        self.name.setText(str(plot.get("name", "")))
        self.kind.setCurrentText(str(plot.get("kind", self.kind.currentText())))
        self.property_name.setCurrentText(str(plot.get("property", "")))
        self.x_field.setCurrentText(str(plot.get("x", "")))
        self.y_field.setCurrentText(str(plot.get("y", "")))
        self.group_by.setCurrentText(str(plot.get("group_by", "")))
        self.fluids.setText(", ".join(str(value) for value in plot.get("fluids", [])))
        self.value_scale.setCurrentText(str(plot.get("value_scale", "linear")))
        self.color_scale.setCurrentText(str(plot.get("color_scale", "linear")))
        self.x_scale.setCurrentText(str(plot.get("x_scale", "linear")))
        self.y_scale.setCurrentText(str(plot.get("y_scale", "linear")))
        format_index = self.output_format.findData(str(plot.get("format", "")))
        self.output_format.setCurrentIndex(max(0, format_index))
        self.filters.load_mapping(plot.get("filters", {}))
        self.series.load_mapping(plot.get("series", {}), multiple=True)
        self.display_units.load_mapping(plot.get("display_units", {}))
        self._update_visibility(self.kind.currentText())

    def plot_payload(self) -> dict[str, Any]:
        name = self.name.text().strip()
        kind = self.kind.currentText()
        if not name:
            raise ValueError("plot name is required")
        if not kind:
            raise ValueError("plot kind is required")
        applicable = set(self.contracts.get(kind, {}).get("applicable", []))
        payload: dict[str, Any] = {"name": name, "kind": kind}
        scalar_fields = {
            "property": _combo_value(self.property_name),
            "x": _combo_value(self.x_field),
            "y": _combo_value(self.y_field),
            "group_by": _combo_value(self.group_by),
            "value_scale": self.value_scale.currentText(),
            "color_scale": self.color_scale.currentText(),
            "x_scale": self.x_scale.currentText(),
            "y_scale": self.y_scale.currentText(),
            "format": _combo_value(self.output_format),
        }
        for field, value in scalar_fields.items():
            if field in applicable and value:
                payload[field] = value
        fluids = _comma_values(self.fluids.text())
        if "fluids" in applicable and fluids:
            payload["fluids"] = fluids
        if "filters" in applicable:
            filters = self.filters.mapping(field_kinds=self.field_kinds)
            if filters:
                payload["filters"] = filters
        if "series" in applicable:
            series = self.series.mapping(
                multiple=True,
                field_kinds=self.field_kinds,
            )
            if series:
                payload["series"] = series
        if "display_units" in applicable:
            display_units = self.display_units.mapping()
            if display_units:
                payload["display_units"] = display_units
        self._validate_required(payload)
        return payload

    def accept(self) -> None:
        try:
            self.plot_payload()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Plot Request", str(exc))
            return
        super().accept()

    def _validate_required(self, payload: dict[str, Any]) -> None:
        kind = str(payload["kind"])
        required = set(self.contracts.get(kind, {}).get("required", []))
        if kind == "property_curves" and self.dataset_payload.get("mode") == "property_table":
            required.add("x")
        missing = sorted(field for field in required if not payload.get(field))
        if missing:
            raise ValueError(f"{kind} requires: {', '.join(missing)}")
        if kind == "xy" and (not payload.get("x") or not payload.get("y")):
            raise ValueError("xy requires x and y fields")

    def _update_visibility(self, kind: str) -> None:
        applicable = set(self.contracts.get(kind, {}).get("applicable", []))
        if kind == "property_curves" and self.dataset_payload.get("mode") != "property_table":
            applicable.discard("x")
        for field, widget in self._rows.items():
            visible = field in applicable
            widget.setVisible(visible)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(visible)

    def _properties(self) -> list[str]:
        return [str(value) for value in self.dataset_payload.get("properties", [])]

    def _available_fields(self) -> set[str]:
        fields = {"temperature", "pressure", "phase", "fluid", *self._properties()}
        mode = self.dataset_payload.get("mode")
        if mode in {"saturation_table", "vapor_mass_fraction_table"}:
            fields.add("vapor_mass_fraction")
        if mode == "saturation_table":
            fields.add("saturation_endpoint")
        if "mass_density" in self._properties():
            fields.add("specific_volume")
        return fields

    def _axis_fields(self) -> list[str]:
        return self._fields_with("axis_allowed")

    def _group_fields(self) -> list[str]:
        return self._fields_with("group_allowed")

    def _fields_with(self, flag: str) -> list[str]:
        available = self._available_fields()
        definitions = self.capabilities.get("visualization", {}).get("fields", [])
        return sorted(
            str(item["name"])
            for item in definitions
            if isinstance(item, dict) and item.get(flag) and str(item.get("name")) in available
        )

    def _default_plot(self) -> dict[str, Any]:
        kind = self.kind.currentText()
        plot: dict[str, Any] = {"name": "plot", "kind": kind}
        if kind in {"property_curves", "property_heatmap"} and self._properties():
            plot["property"] = self._properties()[0]
        if kind == "property_curves" and self.dataset_payload.get("mode") == "property_table":
            plot["x"] = "temperature"
        if kind == "xy":
            axes = self._axis_fields()
            if axes:
                plot["x"] = axes[0]
                plot["y"] = axes[min(1, len(axes) - 1)]
        return plot


class VisualizationEditor(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capabilities: dict[str, Any] | None = None
        self.dataset_payload: dict[str, Any] = {}
        self._loading = False

        layout = QVBoxLayout(self)
        self.enabled = QPushButton("Enable Configured Visualization")
        self.enabled.setCheckable(True)
        layout.addWidget(self.enabled)
        shared = QFormLayout()
        self.format = QComboBox()
        self.fluids = QLineEdit()
        self.fluids.setPlaceholderText("Comma-separated; blank uses all dataset fluids")
        self.filters = MappingTable("Shared filter field", "Exact SI value")
        self.display_units = MappingTable("Shared field", "Display unit")
        shared.addRow("Shared format", self.format)
        shared.addRow("Shared fluids", self.fluids)
        shared.addRow("Shared filters", self.filters)
        shared.addRow("Shared display units", self.display_units)
        layout.addLayout(shared)
        layout.addWidget(QLabel("Plot requests (ordered)"))
        self.plots = QListWidget()
        layout.addWidget(self.plots, 1)
        actions = QHBoxLayout()
        self.action_buttons: list[QPushButton] = []
        for label, slot in (
            ("Add Plot…", self.add_plot),
            ("Edit Plot…", self.edit_plot),
            ("Remove Plot", self.remove_plot),
            ("Move Up", lambda: self.move_plot(-1)),
            ("Move Down", lambda: self.move_plot(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            self.action_buttons.append(button)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.enabled.toggled.connect(self._enabled_changed)
        self.format.currentTextChanged.connect(self._emit_changed)
        self.fluids.textChanged.connect(self._emit_changed)
        self.filters.changed.connect(self._emit_changed)
        self.display_units.changed.connect(self._emit_changed)
        self._set_controls_enabled(False)

    def apply_capabilities(self, capabilities: dict[str, Any]) -> None:
        self.capabilities = capabilities
        formats = capabilities.get("visualization", {}).get("formats", [])
        self.format.clear()
        self.format.addItems([str(value) for value in formats])

    def set_dataset_context(self, payload: dict[str, Any]) -> None:
        self.dataset_payload = copy.deepcopy(payload)

    def load_visualization(self, value: object) -> None:
        self._loading = True
        visualization = value if isinstance(value, dict) else None
        self.enabled.setChecked(visualization is not None)
        self.format.setCurrentText(
            str(visualization.get("format", "png")) if visualization else "png"
        )
        fluids = visualization.get("fluids", []) if visualization else []
        self.fluids.setText(", ".join(str(item) for item in fluids))
        self.filters.load_mapping(visualization.get("filters", {}) if visualization else {})
        self.display_units.load_mapping(
            visualization.get("display_units", {}) if visualization else {}
        )
        self.plots.clear()
        for plot in visualization.get("plots", []) if visualization else []:
            if isinstance(plot, dict):
                self._append_plot(plot)
        self._set_controls_enabled(visualization is not None)
        self._loading = False

    def visualization_payload(self) -> dict[str, Any] | None:
        if not self.enabled.isChecked():
            return None
        plots = self.plot_payloads()
        if not plots:
            raise ValueError("configured visualization requires at least one plot")
        names = [str(plot.get("name", "")) for plot in plots]
        if len(set(names)) != len(names):
            raise ValueError("configured visualization plot names must be unique")
        field_kinds = self._field_kinds()
        payload: dict[str, Any] = {
            "format": self.format.currentText(),
            "plots": plots,
        }
        fluids = _comma_values(self.fluids.text())
        if fluids:
            payload["fluids"] = fluids
        filters = self.filters.mapping(field_kinds=field_kinds)
        if filters:
            payload["filters"] = filters
        display_units = self.display_units.mapping()
        if display_units:
            payload["display_units"] = display_units
        return payload

    def plot_payloads(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item.data(PLOT_ROLE))
            for index in range(self.plots.count())
            if (item := self.plots.item(index)) is not None
        ]

    def add_plot(self) -> None:
        dialog = self._dialog()
        if dialog is not None and dialog.exec() == QDialog.DialogCode.Accepted:
            self._append_plot(dialog.plot_payload())
            self._emit_changed()

    def edit_plot(self) -> None:
        item = self.plots.currentItem()
        if item is None:
            return
        dialog = self._dialog(copy.deepcopy(item.data(PLOT_ROLE)))
        if dialog is not None and dialog.exec() == QDialog.DialogCode.Accepted:
            payload = dialog.plot_payload()
            item.setData(PLOT_ROLE, payload)
            item.setText(_plot_label(payload))
            self._emit_changed()

    def remove_plot(self) -> None:
        row = self.plots.currentRow()
        if row >= 0:
            self.plots.takeItem(row)
            self._emit_changed()

    def move_plot(self, offset: int) -> None:
        row = self.plots.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.plots.count():
            return
        item = self.plots.takeItem(row)
        if item is not None:
            self.plots.insertItem(target, item)
            self.plots.setCurrentRow(target)
            self._emit_changed()

    def _dialog(self, plot: dict[str, Any] | None = None) -> PlotRequestDialog | None:
        if self.capabilities is None or not self.dataset_payload:
            return None
        return PlotRequestDialog(
            self.capabilities,
            self.dataset_payload,
            plot,
            self,
        )

    def _append_plot(self, plot: dict[str, Any]) -> None:
        payload = copy.deepcopy(plot)
        item = QListWidgetItem(_plot_label(payload))
        item.setData(PLOT_ROLE, payload)
        self.plots.addItem(item)

    def _field_kinds(self) -> dict[str, str]:
        if self.capabilities is None:
            return {}
        return {
            str(item["name"]): str(item["kind"])
            for item in self.capabilities.get("visualization", {}).get("fields", [])
            if isinstance(item, dict) and "name" in item and "kind" in item
        }

    def _enabled_changed(self, enabled: bool) -> None:
        self._set_controls_enabled(enabled)
        self._emit_changed()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.format,
            self.fluids,
            self.filters,
            self.display_units,
            self.plots,
            *self.action_buttons,
        ):
            widget.setEnabled(enabled)

    def _emit_changed(self, *_args: object) -> None:
        if not self._loading:
            self.changed.emit()


def _optional_combo(values: list[str], *, empty_label: str = "") -> QComboBox:
    combo = QComboBox()
    combo.addItem(empty_label, "")
    for value in values:
        combo.addItem(value, value)
    return combo


def _combo(values: object) -> QComboBox:
    combo = QComboBox()
    if isinstance(values, (list, tuple)):
        combo.addItems([str(value) for value in values])
    return combo


def _combo_value(combo: QComboBox) -> str:
    value = combo.currentData()
    return str(value) if isinstance(value, str) else combo.currentText()


def _comma_values(text: str) -> list[str]:
    values = [value.strip() for value in text.split(",") if value.strip()]
    if len({value.casefold() for value in values}) != len(values):
        raise ValueError("fluid selection contains duplicate names")
    return values


def _parse_scalar(value: str, *, kind: str | None) -> float | str:
    if kind == "categorical":
        return value
    try:
        return float(value)
    except ValueError:
        return value


def _scalar_text(value: object) -> str:
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)


def _plot_label(plot: Mapping[str, object]) -> str:
    return f"{plot.get('name', '<unnamed>')} — {plot.get('kind', '<unknown>')}"
