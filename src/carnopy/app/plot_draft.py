from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, SignalInstance, Slot

from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.field_ids import (
    PLOT_DISPLAY_UNITS,
    PLOT_FILTERS,
    PLOT_FLUIDS,
    PLOT_KIND,
    PLOT_NAME,
    PLOT_SERIES,
    plot_field,
)
from carnopy.app.mapping_draft import MappingDraftModel
from carnopy.visualization.requests import PLOT_NAME_PATTERN


@dataclass(frozen=True)
class _PlotIssue:
    field: str
    row: int
    message: str


class PlotDraft(QObject):
    """Workflow-local editable state for one configured or manual plot request."""

    changed = Signal()
    validity_changed = Signal()
    name_changed = Signal()
    kind_changed = Signal()
    property_name_changed = Signal()
    x_field_changed = Signal()
    y_field_changed = Signal()
    group_by_changed = Signal()
    value_scale_changed = Signal()
    color_scale_changed = Signal()
    x_scale_changed = Signal()
    y_scale_changed = Signal()
    output_format_changed = Signal()

    def __init__(
        self,
        capabilities: Mapping[str, object],
        dataset_payload: Mapping[str, object],
        plot: Mapping[str, object] | None = None,
        parent: QObject | None = None,
        *,
        allow_format: bool = True,
    ) -> None:
        super().__init__(parent)
        self.capabilities = copy.deepcopy(dict(capabilities))
        self.dataset_payload = copy.deepcopy(dict(dataset_payload))
        self.allow_format = allow_format
        self.kind_choices = DraftListModel(self)
        self.property_choices = DraftListModel(self)
        self.axis_choices = DraftListModel(self)
        self.group_choices = DraftListModel(self)
        self.fluid_choices = DraftListModel(self)
        self.selected_fluids = DraftListModel(self)
        self.format_choices = DraftListModel(self)
        self.scale_choices = DraftListModel(self)
        self.filters = MappingDraftModel(self)
        self.series = MappingDraftModel(
            self,
            multiple=True,
            allow_text_numeric=True,
        )
        self.display_units = MappingDraftModel(self, numeric_values=False)
        self._refreshing_context = False
        self._name = ""
        self._kind = ""
        self._property_name = ""
        self._x_field = ""
        self._y_field = ""
        self._group_by = ""
        self._fluids: tuple[str, ...] = ()
        self._value_scale = "linear"
        self._color_scale = "linear"
        self._x_scale = "linear"
        self._y_scale = "linear"
        self._output_format = ""
        for mapping in (self.filters, self.series, self.display_units):
            mapping.changed.connect(self._mapping_changed)
        self._refresh_models()
        self.load_payload(plot or self._default_plot())

    def _constant_model(self, model: QObject) -> QObject:
        return model

    kindChoices = Property(
        QObject,
        lambda self: self._constant_model(self.kind_choices),
        constant=True,
    )
    propertyChoices = Property(
        QObject,
        lambda self: self._constant_model(self.property_choices),
        constant=True,
    )
    axisChoices = Property(
        QObject,
        lambda self: self._constant_model(self.axis_choices),
        constant=True,
    )
    groupChoices = Property(
        QObject,
        lambda self: self._constant_model(self.group_choices),
        constant=True,
    )
    fluidChoices = Property(
        QObject,
        lambda self: self._constant_model(self.fluid_choices),
        constant=True,
    )
    selectedFluids = Property(
        QObject,
        lambda self: self._constant_model(self.selected_fluids),
        constant=True,
    )
    formatChoices = Property(
        QObject,
        lambda self: self._constant_model(self.format_choices),
        constant=True,
    )
    scaleChoices = Property(
        QObject,
        lambda self: self._constant_model(self.scale_choices),
        constant=True,
    )
    filterRows = Property(
        QObject,
        lambda self: self._constant_model(self.filters),
        constant=True,
    )
    seriesRows = Property(
        QObject,
        lambda self: self._constant_model(self.series),
        constant=True,
    )
    displayUnitRows = Property(
        QObject,
        lambda self: self._constant_model(self.display_units),
        constant=True,
    )

    def get_applicable_fields(self) -> list[str]:
        return sorted(self._applicable_fields())

    applicableFields = Property(list, get_applicable_fields, notify=changed)

    def get_name(self) -> str:
        return self._name

    @Slot(str)
    def set_name(self, value: str) -> None:
        self._set_scalar("_name", value, self.name_changed)

    name = Property(str, get_name, set_name, notify=name_changed)

    def get_kind(self) -> str:
        return self._kind

    @Slot(str)
    def set_kind(self, value: str) -> None:
        if self._set_scalar("_kind", value, self.kind_changed):
            self._configure_mapping_models()
            self._refresh_models()

    kind = Property(str, get_kind, set_kind, notify=kind_changed)

    def get_property_name(self) -> str:
        return self._property_name

    @Slot(str)
    def set_property_name(self, value: str) -> None:
        if self._set_scalar("_property_name", value, self.property_name_changed):
            self._configure_mapping_models()
            self._refresh_models()

    propertyName = Property(
        str,
        get_property_name,
        set_property_name,
        notify=property_name_changed,
    )

    def get_x_field(self) -> str:
        return self._x_field

    @Slot(str)
    def set_x_field(self, value: str) -> None:
        if self._set_scalar("_x_field", value, self.x_field_changed):
            self._configure_mapping_models()
            self._refresh_models()

    xField = Property(str, get_x_field, set_x_field, notify=x_field_changed)

    def get_y_field(self) -> str:
        return self._y_field

    @Slot(str)
    def set_y_field(self, value: str) -> None:
        if self._set_scalar("_y_field", value, self.y_field_changed):
            self._configure_mapping_models()
            self._refresh_models()

    yField = Property(str, get_y_field, set_y_field, notify=y_field_changed)

    def get_group_by(self) -> str:
        return self._group_by

    @Slot(str)
    def set_group_by(self, value: str) -> None:
        if self._set_scalar("_group_by", value, self.group_by_changed):
            self._configure_mapping_models()
            self._refresh_models()

    groupBy = Property(str, get_group_by, set_group_by, notify=group_by_changed)

    def get_value_scale(self) -> str:
        return self._value_scale

    @Slot(str)
    def set_value_scale(self, value: str) -> None:
        self._set_scalar("_value_scale", value, self.value_scale_changed)

    valueScale = Property(str, get_value_scale, set_value_scale, notify=value_scale_changed)

    def get_color_scale(self) -> str:
        return self._color_scale

    @Slot(str)
    def set_color_scale(self, value: str) -> None:
        self._set_scalar("_color_scale", value, self.color_scale_changed)

    colorScale = Property(str, get_color_scale, set_color_scale, notify=color_scale_changed)

    def get_x_scale(self) -> str:
        return self._x_scale

    @Slot(str)
    def set_x_scale(self, value: str) -> None:
        self._set_scalar("_x_scale", value, self.x_scale_changed)

    xScale = Property(str, get_x_scale, set_x_scale, notify=x_scale_changed)

    def get_y_scale(self) -> str:
        return self._y_scale

    @Slot(str)
    def set_y_scale(self, value: str) -> None:
        self._set_scalar("_y_scale", value, self.y_scale_changed)

    yScale = Property(str, get_y_scale, set_y_scale, notify=y_scale_changed)

    def get_output_format(self) -> str:
        return self._output_format

    @Slot(str)
    def set_output_format(self, value: str) -> None:
        self._set_scalar("_output_format", value, self.output_format_changed)

    outputFormat = Property(
        str,
        get_output_format,
        set_output_format,
        notify=output_format_changed,
    )

    def get_locally_valid(self) -> bool:
        return not self.get_issue()

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        issue = self._validation_problem()
        return "" if issue is None else issue.message

    issue = Property(str, get_issue, notify=validity_changed)

    def get_first_invalid_field(self) -> str:
        issue = self._validation_problem()
        return "" if issue is None else issue.field

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        issue = self._validation_problem()
        return -1 if issue is None else issue.row

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def load_payload(self, plot: Mapping[str, object]) -> None:
        before = self._observable_state()
        self._name = str(plot.get("name", ""))
        self._kind = str(plot.get("kind", self._first_plot_kind()))
        self._property_name = str(plot.get("property", ""))
        self._x_field = str(plot.get("x", ""))
        self._y_field = str(plot.get("y", ""))
        self._group_by = str(plot.get("group_by", ""))
        self._fluids = _string_tuple(plot.get("fluids"))
        self._value_scale = str(plot.get("value_scale", "linear"))
        self._color_scale = str(plot.get("color_scale", "linear"))
        self._x_scale = str(plot.get("x_scale", "linear"))
        self._y_scale = str(plot.get("y_scale", "linear"))
        self._output_format = str(plot.get("format", ""))
        self.filters.load_mapping(_mapping(plot.get("filters")))
        self.series.load_mapping(_mapping(plot.get("series")))
        self.display_units.load_mapping(_mapping(plot.get("display_units")))
        self._configure_mapping_models()
        self._refresh_models()
        self._emit_observable_changes(before)
        self.changed.emit()

    def refresh_context(
        self,
        capabilities: Mapping[str, object],
        dataset_payload: Mapping[str, object],
    ) -> None:
        """Refresh choices and compatibility without replacing raw editable state."""
        before = self._observable_state()
        self._refreshing_context = True
        try:
            self.capabilities = copy.deepcopy(dict(capabilities))
            self.dataset_payload = copy.deepcopy(dict(dataset_payload))
            self._configure_mapping_models()
            self._refresh_models()
        finally:
            self._refreshing_context = False
        self._emit_observable_changes(before)
        self.changed.emit()

    def payload(self) -> dict[str, Any]:
        issue = self._validation_issue()
        if issue:
            raise ValueError(issue)
        applicable = self._applicable_fields()
        payload: dict[str, Any] = {"name": self._name.strip(), "kind": self._kind}
        scalar_fields = {
            "property": self._property_name,
            "x": self._x_field,
            "y": self._y_field,
            "group_by": self._group_by,
            "value_scale": self._value_scale,
            "color_scale": self._color_scale,
            "x_scale": self._x_scale,
            "y_scale": self._y_scale,
            "format": self._output_format,
        }
        for field, value in scalar_fields.items():
            if field in applicable and value:
                payload[field] = value
        if "fluids" in applicable and self._fluids:
            payload["fluids"] = list(self._fluids)
        for field, model in (
            ("filters", self.filters),
            ("series", self.series),
            ("display_units", self.display_units),
        ):
            if field not in applicable:
                continue
            mapping_value = model.mapping()
            if mapping_value:
                payload[field] = mapping_value
        return payload

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._name,
            self._kind,
            self._property_name,
            self._x_field,
            self._y_field,
            self._group_by,
            self._fluids,
            self._value_scale,
            self._color_scale,
            self._x_scale,
            self._y_scale,
            self._output_format,
            self.filters.raw_rows(),
            self.series.raw_rows(),
            self.display_units.raw_rows(),
        )

    @Slot(str, bool, result=bool)
    def set_fluid_selected(self, value: str, selected: bool) -> bool:
        fluids = list(self._fluids)
        if selected and value not in fluids:
            fluids.append(value)
        elif not selected and value in fluids:
            fluids.remove(value)
        else:
            return False
        self._fluids = tuple(fluids)
        self._state_changed()
        return True

    def set_fluids(self, values: Iterable[str]) -> bool:
        updated = tuple(str(value) for value in values)
        if updated == self._fluids:
            return False
        self._fluids = updated
        self._state_changed()
        return True

    def selected_fluid_values(self) -> tuple[str, ...]:
        return self._fluids

    def plot_kind_values(self) -> tuple[str, ...]:
        return self.kind_choices.values

    def property_values(self) -> tuple[str, ...]:
        return tuple(item.value for item in self.property_choices.items if item.compatible)

    def axis_values(self) -> tuple[str, ...]:
        return tuple(item.value for item in self.axis_choices.items if item.compatible)

    def group_values(self) -> tuple[str, ...]:
        return tuple(item.value for item in self.group_choices.items if item.compatible)

    def dataset_fluid_values(self) -> tuple[str, ...]:
        return _string_tuple(self.dataset_payload.get("fluids"))

    def format_values(self) -> tuple[str, ...]:
        return self.format_choices.values

    def scale_values(self) -> tuple[str, ...]:
        return self.scale_choices.values

    def applicable_fields(self) -> frozenset[str]:
        return frozenset(self._applicable_fields())

    def _set_scalar(self, attribute: str, value: str, signal: SignalInstance) -> bool:
        current = getattr(self, attribute)
        if current == value:
            return False
        before = self._observable_state()
        setattr(self, attribute, value)
        signal.emit()
        self._emit_validity_if_changed(before)
        self.changed.emit()
        return True

    def _mapping_changed(self) -> None:
        if self._refreshing_context:
            return
        self.validity_changed.emit()
        self.changed.emit()

    def _state_changed(self) -> None:
        before = self._observable_state()
        self._refresh_models()
        self._emit_validity_if_changed(before)
        self.changed.emit()

    def _refresh_models(self) -> None:
        kinds = self._plot_kinds()
        self.kind_choices.replace(_choice_items(kinds, self._kind))
        self.property_choices.replace(_choice_items(self._properties(), self._property_name))
        self.axis_choices.replace(_choice_items(self._axis_fields(), self._x_field, self._y_field))
        self.group_choices.replace(_choice_items(self._group_fields(), self._group_by))
        dataset_fluids = self.dataset_fluid_values()
        selected_canonical = self._canonical_fluid_values(self._fluids)
        fluid_items = [
            DraftItem(
                value=value,
                display=value,
                canonical=self._canonical_fluid(value),
                selected=self._canonical_fluid(value) in selected_canonical,
            )
            for value in dataset_fluids
        ]
        for value in self._fluids:
            canonical = self._canonical_fluid(value)
            if canonical not in self._canonical_fluid_values(dataset_fluids):
                fluid_items.append(
                    DraftItem(
                        value=value,
                        display=f"Unavailable: {value}",
                        canonical=canonical,
                        compatible=False,
                        selected=True,
                        issue=f"visualization fluid {value!r} is not in the dataset",
                    )
                )
        self.fluid_choices.replace(fluid_items)
        self.selected_fluids.replace([item for item in fluid_items if item.selected])
        self.format_choices.replace(_choice_items(self._formats(), self._output_format))
        scales = self._scales()
        self.scale_choices.replace(
            _choice_items(
                scales,
                self._value_scale,
                self._color_scale,
                self._x_scale,
                self._y_scale,
            )
        )

    def _configure_mapping_models(self) -> None:
        visualization = self._visualization_capabilities()
        field_kinds = self._field_kinds()
        level_choices = self._level_choices()
        level_hints = self._level_hints()
        self.filters.configure(
            self._fields_with("filter_allowed"),
            field_kinds=field_kinds,
            value_choices=level_choices,
            value_hints=level_hints,
        )
        self.series.configure(
            self._series_fields(),
            field_kinds=field_kinds,
            value_choices=level_choices,
            value_hints=level_hints,
            allow_text_numeric=not bool(visualization.get("numeric_levels")),
        )
        display_units = visualization.get("display_units")
        display_fields = self._display_fields()
        self.display_units.configure(
            display_fields,
            field_kinds=field_kinds,
            value_choices={
                field: [str(value) for value in values]
                for field in display_fields
                if isinstance(display_units, Mapping)
                and isinstance((values := display_units.get(field)), (list, tuple))
            },
        )

    def _validation_issue(self) -> str:
        issue = self._validation_problem()
        return "" if issue is None else issue.message

    def _validation_problem(self) -> _PlotIssue | None:
        name = self._name.strip()
        if not name:
            return _PlotIssue(PLOT_NAME, -1, "plot name is required")
        if re.fullmatch(PLOT_NAME_PATTERN, name) is None:
            return _PlotIssue(
                PLOT_NAME,
                -1,
                "plot name must contain lowercase ASCII letters or digits separated "
                "by single '-' or '_' characters",
            )
        if self._kind not in self._plot_kinds():
            return _PlotIssue(
                PLOT_KIND,
                -1,
                f"plot kind {self._kind!r} is unavailable for this dataset",
            )
        if self._kind == "pv" and "mass_density" not in self._properties():
            return _PlotIssue(
                PLOT_KIND,
                -1,
                "pv requires the dataset property 'mass_density'",
            )
        if self._kind == "ts" and "specific_entropy" not in self._properties():
            return _PlotIssue(
                PLOT_KIND,
                -1,
                "ts requires the dataset property 'specific_entropy'",
            )
        applicable = self._applicable_fields()
        required = set(_string_tuple(self._kind_contract().get("required")))
        if self._kind == "property_curves" and self.dataset_payload.get("mode") == "property_table":
            required.add("x")
        scalar_values = {
            "property": self._property_name,
            "x": self._x_field,
            "y": self._y_field,
            "group_by": self._group_by,
            "value_scale": self._value_scale,
            "color_scale": self._color_scale,
            "x_scale": self._x_scale,
            "y_scale": self._y_scale,
            "format": self._output_format,
        }
        missing = sorted(field for field in required if not scalar_values.get(field))
        if missing:
            return _PlotIssue(
                plot_field(missing[0]),
                -1,
                f"{self._kind} requires: {', '.join(missing)}",
            )
        allowed_by_field = {
            "property": self._properties(),
            "x": self._axis_fields(),
            "y": self._axis_fields(),
            "group_by": self._group_fields(),
            "value_scale": self._scales(),
            "color_scale": self._scales(),
            "x_scale": self._scales(),
            "y_scale": self._scales(),
            "format": self._formats(),
        }
        for field, value in scalar_values.items():
            if field not in applicable or not value:
                continue
            if value not in allowed_by_field[field]:
                return _PlotIssue(
                    plot_field(field),
                    -1,
                    f"plot {field} value {value!r} is unavailable",
                )
        canonical_fluids = self._canonical_fluid_values(self._fluids)
        if len(set(canonical_fluids)) != len(canonical_fluids):
            return _PlotIssue(
                PLOT_FLUIDS,
                -1,
                "visualization fluid aliases resolve to duplicate canonical fluids",
            )
        dataset_canonical = set(self._canonical_fluid_values(self.dataset_fluid_values()))
        for value, canonical in zip(self._fluids, canonical_fluids, strict=True):
            if canonical not in dataset_canonical:
                return _PlotIssue(
                    PLOT_FLUIDS,
                    -1,
                    f"visualization fluid {value!r} is not in the dataset",
                )
        for field, field_id, model in (
            ("filters", PLOT_FILTERS, self.filters),
            ("series", PLOT_SERIES, self.series),
            ("display_units", PLOT_DISPLAY_UNITS, self.display_units),
        ):
            if field in applicable and not model.get_valid():
                return _PlotIssue(
                    field_id,
                    model.get_first_invalid_row(),
                    model.get_issue(),
                )
        return None

    def _plot_kinds(self) -> tuple[str, ...]:
        kinds = _string_tuple(self._visualization_capabilities().get("plot_kinds"))
        if self.dataset_payload.get("mode") == "saturation_table":
            kinds = tuple(kind for kind in kinds if kind != "property_heatmap")
        return kinds

    def _formats(self) -> tuple[str, ...]:
        return _string_tuple(self._visualization_capabilities().get("formats"))

    def _scales(self) -> tuple[str, ...]:
        values = _string_tuple(self._visualization_capabilities().get("scales"))
        return values or ("linear", "log")

    def _kind_contract(self) -> Mapping[str, object]:
        contracts = self._visualization_capabilities().get("kind_contracts")
        if not isinstance(contracts, Mapping):
            return {}
        value = contracts.get(self._kind)
        return value if isinstance(value, Mapping) else {}

    def _applicable_fields(self) -> set[str]:
        applicable = set(_string_tuple(self._kind_contract().get("applicable")))
        if not self.allow_format:
            applicable.discard("format")
        if self._kind == "property_curves" and self.dataset_payload.get("mode") != "property_table":
            applicable.discard("x")
        return applicable

    def _properties(self) -> tuple[str, ...]:
        return _string_tuple(self.dataset_payload.get("properties"))

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

    def _fields_with(self, flag: str) -> tuple[str, ...]:
        available = self._available_fields()
        definitions = self._visualization_capabilities().get("fields")
        return tuple(
            sorted(
                str(item["name"])
                for item in (definitions if isinstance(definitions, list) else [])
                if isinstance(item, Mapping)
                and item.get(flag)
                and str(item.get("name")) in available
            )
        )

    def _axis_fields(self) -> tuple[str, ...]:
        return self._fields_with("axis_allowed")

    def _group_fields(self) -> tuple[str, ...]:
        return self._fields_with("group_allowed")

    def _field_kinds(self) -> dict[str, str]:
        definitions = self._visualization_capabilities().get("fields")
        return {
            str(item["name"]): str(item["kind"])
            for item in (definitions if isinstance(definitions, list) else [])
            if isinstance(item, Mapping) and "name" in item and "kind" in item
        }

    def _series_fields(self) -> tuple[str, ...]:
        expected: str | None = None
        mode = str(self.dataset_payload.get("mode", ""))
        if self._kind == "property_curves":
            if mode == "property_table":
                expected = {"temperature": "pressure", "pressure": "temperature"}.get(self._x_field)
            elif mode == "saturation_table":
                expected = "saturation_endpoint"
            else:
                expected = self._saturation_coordinate()
        elif self._kind == "xy":
            expected = self._group_by or None
        elif self._kind in {"pv", "ts"}:
            if mode == "property_table":
                expected = "temperature" if self._kind == "pv" else "pressure"
            elif mode == "saturation_table":
                expected = "saturation_endpoint"
            else:
                expected = self._saturation_coordinate()
        configured = self._visualization_capabilities().get("series_fields")
        if isinstance(configured, Mapping):
            allowed = configured.get(self._kind)
            if isinstance(allowed, (list, tuple)) and expected not in allowed:
                expected = None
        return (expected,) if expected else ()

    def _display_fields(self) -> tuple[str, ...]:
        mode = str(self.dataset_payload.get("mode", ""))
        fields: set[str] = set()
        if self._kind == "property_curves":
            fields.add(self._property_name)
            if mode == "property_table":
                fields.add(self._x_field)
                fields.add("pressure" if self._x_field == "temperature" else "temperature")
            elif mode == "saturation_table":
                fields.add(self._saturation_coordinate() or "")
            else:
                fields.update({"vapor_mass_fraction", self._saturation_coordinate() or ""})
        elif self._kind == "property_heatmap":
            fields.add(self._property_name)
            if mode == "property_table":
                fields.update({"temperature", "pressure"})
            else:
                fields.update({"vapor_mass_fraction", self._saturation_coordinate() or ""})
        elif self._kind == "xy":
            fields.update({self._x_field, self._y_field, self._group_by})
        elif self._kind == "pv":
            fields.update({"specific_volume", "pressure", *self._series_fields()})
        elif self._kind == "ts":
            fields.update({"specific_entropy", "temperature", *self._series_fields()})
        supported = self._visualization_capabilities().get("display_units")
        return tuple(
            sorted(
                field
                for field in fields
                if field and isinstance(supported, Mapping) and field in supported
            )
        )

    def _saturation_coordinate(self) -> str | None:
        grid = self.dataset_payload.get("grid")
        if not isinstance(grid, Mapping):
            return None
        values = [field for field in ("temperature", "pressure") if field in grid]
        return values[0] if len(values) == 1 else None

    def _level_choices(self) -> dict[str, list[str | tuple[str, str]]]:
        visualization = self._visualization_capabilities()
        categorical = visualization.get("categorical_values")
        choices: dict[str, list[str | tuple[str, str]]] = {
            str(field): [str(item) for item in values]
            for field, values in (categorical.items() if isinstance(categorical, Mapping) else ())
            if isinstance(values, list)
        }
        levels = visualization.get("numeric_levels")
        if not isinstance(levels, Mapping):
            return choices
        for field, details in levels.items():
            if not isinstance(details, Mapping) or not isinstance(details.get("choices"), list):
                continue
            choices[str(field)] = [
                (str(item["label"]), _scalar_text(item["value"]))
                for item in details["choices"]
                if isinstance(item, Mapping) and "label" in item and "value" in item
            ]
        return choices

    def _level_hints(self) -> dict[str, str]:
        levels = self._visualization_capabilities().get("numeric_levels")
        if not isinstance(levels, Mapping):
            return {}
        hints: dict[str, str] = {}
        for field, details in levels.items():
            if not isinstance(details, Mapping) or not isinstance(details.get("count"), int):
                continue
            count = details["count"]
            minimum = details.get("minimum_display")
            maximum = details.get("maximum_display")
            unit = str(details.get("display_unit") or "")
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

    def _canonical_fluid(self, value: str) -> str:
        lookup: dict[str, str] = {}
        fluids = self.capabilities.get("fluids")
        if isinstance(fluids, list):
            for entry in fluids:
                if not isinstance(entry, Mapping):
                    continue
                canonical = str(entry.get("name", ""))
                for candidate in (canonical, *_string_tuple(entry.get("aliases"))):
                    lookup[candidate.casefold()] = canonical
        return lookup.get(value.casefold(), value.casefold())

    def _canonical_fluid_values(self, values: Iterable[str]) -> tuple[str, ...]:
        return tuple(self._canonical_fluid(value) for value in values)

    def _visualization_capabilities(self) -> Mapping[str, object]:
        value = self.capabilities.get("visualization")
        return value if isinstance(value, Mapping) else {}

    def _first_plot_kind(self) -> str:
        kinds = self._plot_kinds()
        return kinds[0] if kinds else ""

    def _default_plot(self) -> dict[str, Any]:
        kind = self._first_plot_kind()
        plot: dict[str, Any] = {"name": "plot", "kind": kind}
        if kind in {"property_curves", "property_heatmap"} and self._properties():
            plot["property"] = self._properties()[0]
        if kind == "property_curves" and self.dataset_payload.get("mode") == "property_table":
            plot["x"] = "temperature"
        if kind == "xy" and self._axis_fields():
            axes = self._axis_fields()
            plot["x"] = axes[0]
            plot["y"] = axes[min(1, len(axes) - 1)]
        return plot

    def _observable_state(self) -> tuple[tuple[object, ...], bool, str]:
        return (self.raw_state(), self.get_locally_valid(), self.get_issue())

    def _emit_validity_if_changed(
        self,
        before: tuple[tuple[object, ...], bool, str],
    ) -> None:
        if before[1:] != self._observable_state()[1:]:
            self.validity_changed.emit()

    def _emit_observable_changes(
        self,
        before: tuple[tuple[object, ...], bool, str],
    ) -> None:
        after = self._observable_state()
        signals = (
            (0, self.name_changed),
            (1, self.kind_changed),
            (2, self.property_name_changed),
            (3, self.x_field_changed),
            (4, self.y_field_changed),
            (5, self.group_by_changed),
            (7, self.value_scale_changed),
            (8, self.color_scale_changed),
            (9, self.x_scale_changed),
            (10, self.y_scale_changed),
            (11, self.output_format_changed),
        )
        for index, signal in signals:
            if before[0][index] != after[0][index]:
                signal.emit()
        if before[1:] != after[1:]:
            self.validity_changed.emit()


def _choice_items(values: Iterable[str], *selected: str) -> list[DraftItem]:
    available = tuple(values)
    items = [
        DraftItem(
            value=value,
            display=value,
            canonical=value,
            selected=value in selected,
        )
        for value in available
    ]
    for value in selected:
        if value and value not in available:
            items.append(
                DraftItem(
                    value=value,
                    display=f"Unavailable: {value}",
                    canonical=value,
                    compatible=False,
                    selected=True,
                    issue=f"visualization value {value!r} is unavailable",
                )
            )
    return items


def _mapping(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _scalar_text(value: object) -> str:
    return format(value, ".15g") if isinstance(value, float) else str(value)
