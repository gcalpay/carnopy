from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .visualization_widgets import ChoiceMappingTable, FluidChoiceList


class PlotRequestDialog(QDialog):
    def __init__(
        self,
        capabilities: dict[str, Any],
        dataset_payload: dict[str, Any],
        plot: dict[str, Any] | None = None,
        parent: QWidget | None = None,
        *,
        allow_format: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plot Request")
        self.resize(720, 760)
        self.capabilities = capabilities
        self.dataset_payload = dataset_payload
        self.allow_format = allow_format
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
        self.fluids = FluidChoiceList()
        self.fluids.set_choices(self._dataset_fluids())
        self.value_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.color_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.x_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.y_scale = _combo(visualization.get("scales", ["linear", "log"]))
        self.output_format = _optional_combo(
            [str(value) for value in visualization.get("formats", [])],
            empty_label="Use shared format",
        )
        self.filters = ChoiceMappingTable("Filter field", "Exact SI value")
        self.series = ChoiceMappingTable(
            "Series field",
            "Exact values (comma-separated)",
            multiple=True,
            allow_text_numeric=not bool(visualization.get("numeric_levels")),
        )
        self.display_units = ChoiceMappingTable("Field", "Display unit", numeric_values=False)
        self._configure_filter_controls()

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
        self.kind.currentTextChanged.connect(self._configure_plot_mappings)
        self.property_name.currentTextChanged.connect(self._configure_plot_mappings)
        self.x_field.currentTextChanged.connect(self._configure_plot_mappings)
        self.y_field.currentTextChanged.connect(self._configure_plot_mappings)
        self.group_by.currentTextChanged.connect(self._configure_plot_mappings)
        self.load_plot(plot or self._default_plot())

    def load_plot(self, plot: dict[str, Any]) -> None:
        self.name.setText(str(plot.get("name", "")))
        self.kind.setCurrentText(str(plot.get("kind", self.kind.currentText())))
        self.property_name.setCurrentText(str(plot.get("property", "")))
        self.x_field.setCurrentText(str(plot.get("x", "")))
        self.y_field.setCurrentText(str(plot.get("y", "")))
        self.group_by.setCurrentText(str(plot.get("group_by", "")))
        self.fluids.set_choices(
            self._dataset_fluids(),
            [str(value) for value in plot.get("fluids", [])],
        )
        self.value_scale.setCurrentText(str(plot.get("value_scale", "linear")))
        self.color_scale.setCurrentText(str(plot.get("color_scale", "linear")))
        self.x_scale.setCurrentText(str(plot.get("x_scale", "linear")))
        self.y_scale.setCurrentText(str(plot.get("y_scale", "linear")))
        format_index = self.output_format.findData(str(plot.get("format", "")))
        self.output_format.setCurrentIndex(max(0, format_index))
        self.filters.load_mapping(plot.get("filters", {}))
        self.series.load_mapping(plot.get("series", {}))
        self.display_units.load_mapping(plot.get("display_units", {}))
        self._configure_plot_mappings()
        self._update_visibility(self.kind.currentText())

    def plot_payload(self) -> dict[str, Any]:
        name = self.name.text().strip()
        kind = self.kind.currentText()
        if not name:
            raise ValueError("plot name is required")
        if not kind:
            raise ValueError("plot kind is required")
        applicable = set(self.contracts.get(kind, {}).get("applicable", []))
        if not self.allow_format:
            applicable.discard("format")
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
        fluids = self.fluids.selected_values()
        if "fluids" in applicable and fluids:
            payload["fluids"] = fluids
        if "filters" in applicable:
            filters = self.filters.mapping()
            if filters:
                payload["filters"] = filters
        if "series" in applicable:
            series = self.series.mapping()
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
        if not self.allow_format:
            applicable.discard("format")
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

    def _dataset_fluids(self) -> list[str]:
        values = self.dataset_payload.get("fluids", [])
        return [str(value) for value in values] if isinstance(values, list) else []

    def _configure_filter_controls(self) -> None:
        self.filters.configure(
            self._fields_with("filter_allowed"),
            field_kinds=self.field_kinds,
            value_choices=self._level_choices(),
            value_hints=self._level_hints(),
        )

    def _configure_plot_mappings(self, *_args: object) -> None:
        visualization = self.capabilities.get("visualization", {})
        display_units = visualization.get("display_units", {})
        self.series.configure(
            self._series_fields(),
            field_kinds=self.field_kinds,
            value_choices=self._level_choices(),
            value_hints=self._level_hints(),
        )
        display_fields = self._display_fields()
        self.display_units.configure(
            display_fields,
            field_kinds=self.field_kinds,
            value_choices={
                field: [str(value) for value in display_units.get(field, [])]
                for field in display_fields
                if isinstance(display_units, dict)
            },
        )

    def _level_choices(self) -> dict[str, list[str | tuple[str, str]]]:
        value = self.capabilities.get("visualization", {}).get("categorical_values", {})
        choices: dict[str, list[str | tuple[str, str]]] = {
            str(field): [str(item) for item in items]
            for field, items in (value.items() if isinstance(value, dict) else ())
            if isinstance(items, list)
        }
        levels = self.capabilities.get("visualization", {}).get("numeric_levels", {})
        if not isinstance(levels, dict):
            return choices
        for field, details in levels.items():
            if not isinstance(details, dict) or not isinstance(details.get("choices"), list):
                continue
            choices[str(field)] = [
                (str(item["label"]), _scalar_value(item["value"]))
                for item in details["choices"]
                if isinstance(item, dict) and "label" in item and "value" in item
            ]
        return choices

    def _level_hints(self) -> dict[str, str]:
        levels = self.capabilities.get("visualization", {}).get("numeric_levels", {})
        if not isinstance(levels, dict):
            return {}
        hints: dict[str, str] = {}
        for field, details in levels.items():
            if not isinstance(details, dict):
                continue
            count = details.get("count")
            minimum = details.get("minimum_display")
            maximum = details.get("maximum_display")
            unit = str(details.get("display_unit") or "")
            if not isinstance(count, int):
                continue
            rendered_range = ""
            if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
                suffix = f" {unit}" if unit and unit != "1" else ""
                rendered_range = (
                    f"; display range {format(float(minimum), '.6g')}-"
                    f"{format(float(maximum), '.6g')}{suffix}"
                )
            hints[str(field)] = (
                f"{count} emitted level(s){rendered_range}; enter exact canonical SI values"
            )
        return hints

    def _series_fields(self) -> list[str]:
        kind = self.kind.currentText()
        mode = str(self.dataset_payload.get("mode", ""))
        expected: str | None = None
        if kind == "property_curves":
            if mode == "property_table":
                expected = {
                    "temperature": "pressure",
                    "pressure": "temperature",
                }.get(_combo_value(self.x_field))
            elif mode == "saturation_table":
                expected = "saturation_endpoint"
            else:
                expected = self._saturation_coordinate()
        elif kind == "xy":
            expected = _combo_value(self.group_by) or None
        elif kind in {"pv", "ts"}:
            if mode == "property_table":
                expected = "temperature" if kind == "pv" else "pressure"
            elif mode == "saturation_table":
                expected = "saturation_endpoint"
            else:
                expected = self._saturation_coordinate()
        configured = self.capabilities.get("visualization", {}).get("series_fields")
        if isinstance(configured, dict):
            allowed = configured.get(kind)
            if isinstance(allowed, list) and expected not in allowed:
                expected = None
        return [expected] if expected is not None else []

    def _display_fields(self) -> list[str]:
        kind = self.kind.currentText()
        mode = str(self.dataset_payload.get("mode", ""))
        fields: set[str] = set()
        if kind == "property_curves":
            fields.add(_combo_value(self.property_name))
            if mode == "property_table":
                x_field = _combo_value(self.x_field)
                fields.add(x_field)
                fields.add("pressure" if x_field == "temperature" else "temperature")
            elif mode == "saturation_table":
                fields.add(self._saturation_coordinate() or "")
            else:
                fields.update({"vapor_mass_fraction", self._saturation_coordinate() or ""})
        elif kind == "property_heatmap":
            fields.add(_combo_value(self.property_name))
            if mode == "property_table":
                fields.update({"temperature", "pressure"})
            else:
                fields.update({"vapor_mass_fraction", self._saturation_coordinate() or ""})
        elif kind == "xy":
            fields.update(
                {
                    _combo_value(self.x_field),
                    _combo_value(self.y_field),
                    _combo_value(self.group_by),
                }
            )
        elif kind == "pv":
            fields.update({"specific_volume", "pressure", *self._series_fields()})
        elif kind == "ts":
            fields.update({"specific_entropy", "temperature", *self._series_fields()})
        supported = self.capabilities.get("visualization", {}).get("display_units", {})
        return sorted(field for field in fields if field and field in supported)

    def _saturation_coordinate(self) -> str | None:
        grid = self.dataset_payload.get("grid", {})
        if not isinstance(grid, dict):
            return None
        coordinates = [field for field in ("temperature", "pressure") if field in grid]
        return coordinates[0] if len(coordinates) == 1 else None

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


def _scalar_value(value: object) -> str:
    return format(value, ".15g") if isinstance(value, float) else str(value)
