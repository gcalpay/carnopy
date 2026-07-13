from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
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

from carnopy.app.plot_draft import PlotDraft
from carnopy.app.visualization_widgets import ChoiceMappingTable, FluidChoiceList


class PlotRequestDialog(QDialog):
    """Present one workflow-local plot draft without owning durable state."""

    def __init__(
        self,
        draft: PlotDraft,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plot Request")
        self.resize(720, 760)
        self.draft = draft
        if draft.parent() is None:
            draft.setParent(self)

        content = QWidget()
        self.form = QFormLayout(content)
        self.name = QLineEdit()
        self.kind = QComboBox()
        self.property_name = _optional_combo(draft.property_values())
        self.x_field = _optional_combo(draft.axis_values())
        self.y_field = _optional_combo(draft.axis_values())
        self.group_by = _optional_combo(draft.group_values())
        self.fluids = FluidChoiceList()
        self.value_scale = _combo(draft.scale_values())
        self.color_scale = _combo(draft.scale_values())
        self.x_scale = _combo(draft.scale_values())
        self.y_scale = _combo(draft.scale_values())
        self.output_format = _optional_combo(
            draft.format_values(),
            empty_label="Use shared format",
        )
        self.filters = ChoiceMappingTable("Filter field", "Exact SI value")
        self.series = ChoiceMappingTable(
            "Series field",
            "Exact values (comma-separated)",
            multiple=True,
            allow_text_numeric=draft.series.allow_text_numeric,
        )
        self.display_units = ChoiceMappingTable(
            "Field",
            "Display unit",
            numeric_values=False,
        )

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

        self.name.textChanged.connect(draft.set_name)
        self.kind.currentTextChanged.connect(self._kind_changed)
        self.property_name.currentTextChanged.connect(self._property_changed)
        self.x_field.currentTextChanged.connect(self._x_changed)
        self.y_field.currentTextChanged.connect(self._y_changed)
        self.group_by.currentTextChanged.connect(self._group_changed)
        self.fluids.changed.connect(self._fluids_changed)
        self.value_scale.currentTextChanged.connect(draft.set_value_scale)
        self.color_scale.currentTextChanged.connect(draft.set_color_scale)
        self.x_scale.currentTextChanged.connect(draft.set_x_scale)
        self.y_scale.currentTextChanged.connect(draft.set_y_scale)
        self.output_format.currentTextChanged.connect(self._format_changed)
        self._load_from_draft()

    def load_plot(self, plot: dict[str, object]) -> None:
        self.draft.load_payload(plot)
        self._load_from_draft()

    def plot_payload(self) -> dict[str, object]:
        self._sync_draft()
        return self.draft.payload()

    def accept(self) -> None:
        try:
            self.plot_payload()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Plot Request", str(exc))
            return
        super().accept()

    def _load_from_draft(self) -> None:
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.name,
                self.kind,
                self.property_name,
                self.x_field,
                self.y_field,
                self.group_by,
                self.fluids,
                self.value_scale,
                self.color_scale,
                self.x_scale,
                self.y_scale,
                self.output_format,
            )
        ]
        self.name.setText(self.draft.get_name())
        _replace_combo(self.kind, self.draft.plot_kind_values(), self.draft.get_kind())
        _replace_optional_combo(
            self.property_name,
            self.draft.property_values(),
            self.draft.get_property_name(),
        )
        _replace_optional_combo(
            self.x_field,
            self.draft.axis_values(),
            self.draft.get_x_field(),
        )
        _replace_optional_combo(
            self.y_field,
            self.draft.axis_values(),
            self.draft.get_y_field(),
        )
        _replace_optional_combo(
            self.group_by,
            self.draft.group_values(),
            self.draft.get_group_by(),
        )
        self.fluids.set_choices(
            list(self.draft.dataset_fluid_values()),
            list(self.draft.selected_fluid_values()),
        )
        _replace_combo(self.value_scale, self.draft.scale_values(), self.draft.get_value_scale())
        _replace_combo(self.color_scale, self.draft.scale_values(), self.draft.get_color_scale())
        _replace_combo(self.x_scale, self.draft.scale_values(), self.draft.get_x_scale())
        _replace_combo(self.y_scale, self.draft.scale_values(), self.draft.get_y_scale())
        _replace_optional_combo(
            self.output_format,
            self.draft.format_values(),
            self.draft.get_output_format(),
            empty_label="Use shared format",
        )
        self._bind_mapping_views()
        self._update_visibility()
        del blockers

    def _bind_mapping_views(self) -> None:
        self.filters.bind_draft(self.draft.filters)
        self.series.bind_draft(self.draft.series)
        self.display_units.bind_draft(self.draft.display_units)

    def _sync_draft(self) -> None:
        self.draft.set_name(self.name.text())
        self.draft.set_kind(_combo_value(self.kind))
        self.draft.set_property_name(_combo_value(self.property_name))
        self.draft.set_x_field(_combo_value(self.x_field))
        self.draft.set_y_field(_combo_value(self.y_field))
        self.draft.set_group_by(_combo_value(self.group_by))
        self.draft.set_fluids(self.fluids.selected_values())
        self.draft.set_value_scale(_combo_value(self.value_scale))
        self.draft.set_color_scale(_combo_value(self.color_scale))
        self.draft.set_x_scale(_combo_value(self.x_scale))
        self.draft.set_y_scale(_combo_value(self.y_scale))
        self.draft.set_output_format(_combo_value(self.output_format))
        self.filters.mapping()
        self.series.mapping()
        self.display_units.mapping()

    def _kind_changed(self, value: str) -> None:
        self.draft.set_kind(value)
        self._refresh_dynamic_controls()

    def _property_changed(self, value: str) -> None:
        self.draft.set_property_name(_combo_value(self.property_name))
        self._refresh_dynamic_controls()

    def _x_changed(self, value: str) -> None:
        del value
        self.draft.set_x_field(_combo_value(self.x_field))
        self._refresh_dynamic_controls()

    def _y_changed(self, value: str) -> None:
        del value
        self.draft.set_y_field(_combo_value(self.y_field))
        self._refresh_dynamic_controls()

    def _group_changed(self, value: str) -> None:
        del value
        self.draft.set_group_by(_combo_value(self.group_by))
        self._refresh_dynamic_controls()

    def _fluids_changed(self) -> None:
        self.draft.set_fluids(self.fluids.selected_values())

    def _format_changed(self, value: str) -> None:
        del value
        self.draft.set_output_format(_combo_value(self.output_format))

    def _refresh_dynamic_controls(self) -> None:
        self._bind_mapping_views()
        self._update_visibility()

    def _update_visibility(self) -> None:
        applicable = self.draft.applicable_fields()
        for field, widget in self._rows.items():
            visible = field in applicable
            widget.setVisible(visible)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(visible)


def _optional_combo(values: tuple[str, ...], *, empty_label: str = "") -> QComboBox:
    combo = QComboBox()
    _replace_optional_combo(combo, values, "", empty_label=empty_label)
    return combo


def _combo(values: tuple[str, ...]) -> QComboBox:
    combo = QComboBox()
    _replace_combo(combo, values, values[0] if values else "")
    return combo


def _replace_optional_combo(
    combo: QComboBox,
    values: tuple[str, ...],
    selected: str,
    *,
    empty_label: str = "",
) -> None:
    blocker = QSignalBlocker(combo)
    combo.clear()
    combo.addItem(empty_label, "")
    for value in values:
        combo.addItem(value, value)
    if selected and combo.findData(selected) < 0:
        combo.addItem(f"Unavailable: {selected}", selected)
    combo.setCurrentIndex(max(0, combo.findData(selected)))
    del blocker


def _replace_combo(combo: QComboBox, values: tuple[str, ...], selected: str) -> None:
    blocker = QSignalBlocker(combo)
    combo.clear()
    for value in values:
        combo.addItem(value, value)
    if selected and combo.findData(selected) < 0:
        combo.addItem(f"Unavailable: {selected}", selected)
    index = combo.findData(selected)
    combo.setCurrentIndex(index if index >= 0 else 0)
    del blocker


def _combo_value(combo: QComboBox) -> str:
    value = combo.currentData()
    return str(value) if isinstance(value, str) else combo.currentText()
