from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .plot_draft import PlotDraft
from .plot_request_dialog import PlotRequestDialog
from .visualization_widgets import ChoiceMappingTable, FluidChoiceList

PLOT_ROLE = Qt.ItemDataRole.UserRole


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
        self.fluids = FluidChoiceList()
        self.filters = ChoiceMappingTable("Shared filter field", "Exact SI value")
        self.display_units = ChoiceMappingTable(
            "Shared field", "Display unit", numeric_values=False
        )
        shared.addRow("Shared format", self.format)
        shared.addRow("Shared fluids", self.fluids)
        shared.addRow("Shared filters", self.filters)
        shared.addRow("Shared display units", self.display_units)
        layout.addLayout(shared)
        layout.addWidget(QLabel("Plot requests (ordered)"))
        plot_name_help = QLabel(
            "Plot names are explicit output identifiers and do not follow the "
            "configuration filename."
        )
        plot_name_help.setWordWrap(True)
        plot_name_help.setAccessibleName("Plot name guidance")
        layout.addWidget(plot_name_help)
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
        self.fluids.changed.connect(self._emit_changed)
        self.filters.changed.connect(self._emit_changed)
        self.display_units.changed.connect(self._emit_changed)
        self._set_controls_enabled(False)

    def apply_capabilities(self, capabilities: dict[str, Any]) -> None:
        self.capabilities = capabilities
        formats = capabilities.get("visualization", {}).get("formats", [])
        self.format.clear()
        self.format.addItems([str(value) for value in formats])
        self._configure_shared_mappings()

    def set_dataset_context(self, payload: dict[str, Any]) -> None:
        selected_fluids = self.fluids.selected_values()
        self.dataset_payload = copy.deepcopy(payload)
        dataset_fluids = payload.get("fluids", [])
        choices = (
            [str(value) for value in dataset_fluids] if isinstance(dataset_fluids, list) else []
        )
        self.fluids.set_choices(choices, selected_fluids)
        self._configure_shared_mappings()

    def load_visualization(self, value: object) -> None:
        self._loading = True
        visualization = value if isinstance(value, dict) else None
        self.enabled.setChecked(visualization is not None)
        self.format.setCurrentText(
            str(visualization.get("format", "png")) if visualization else "png"
        )
        fluids = visualization.get("fluids", []) if visualization else []
        dataset_fluids = self.dataset_payload.get("fluids", [])
        self.fluids.set_choices(
            [str(value) for value in dataset_fluids] if isinstance(dataset_fluids, list) else [],
            [str(item) for item in fluids],
        )
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
        payload: dict[str, Any] = {
            "format": self.format.currentText(),
            "plots": plots,
        }
        fluids = self.fluids.selected_values()
        if fluids:
            payload["fluids"] = fluids
        filters = self.filters.mapping()
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
        draft = PlotDraft(
            self.capabilities,
            self.dataset_payload,
            plot,
        )
        return PlotRequestDialog(draft, self)

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

    def _configure_shared_mappings(self) -> None:
        if self.capabilities is None:
            return
        visualization = self.capabilities.get("visualization", {})
        definitions = visualization.get("fields", [])
        available = self._available_fields()
        filter_fields = sorted(
            str(item["name"])
            for item in definitions
            if isinstance(item, dict)
            and item.get("filter_allowed")
            and str(item.get("name")) in available
        )
        categorical = visualization.get("categorical_values", {})
        self.filters.configure(
            filter_fields,
            field_kinds=self._field_kinds(),
            value_choices={
                str(field): [str(value) for value in values]
                for field, values in categorical.items()
                if isinstance(values, list)
            }
            if isinstance(categorical, dict)
            else {},
        )
        units = visualization.get("display_units", {})
        display_fields = sorted(
            field for field in available if isinstance(units, dict) and field in units
        )
        self.display_units.configure(
            display_fields,
            field_kinds=self._field_kinds(),
            value_choices={
                field: [str(value) for value in units.get(field, [])]
                for field in display_fields
                if isinstance(units, dict)
            },
        )

    def _available_fields(self) -> set[str]:
        properties = self.dataset_payload.get("properties", [])
        fields = {
            "temperature",
            "pressure",
            "phase",
            "fluid",
            *([str(value) for value in properties] if isinstance(properties, list) else []),
        }
        mode = self.dataset_payload.get("mode")
        if mode in {"saturation_table", "vapor_mass_fraction_table"}:
            fields.add("vapor_mass_fraction")
        if mode == "saturation_table":
            fields.add("saturation_endpoint")
        if "mass_density" in fields:
            fields.add("specific_volume")
        return fields

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


def _plot_label(plot: Mapping[str, object]) -> str:
    return f"{plot.get('name', '<unnamed>')} — {plot.get('kind', '<unknown>')}"
