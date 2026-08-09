from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.mapping_draft import MappingDraftModel

COMPARISON_KINDS = ("property_comparison", "property_delta")
COMPARISON_AXES = ("temperature", "pressure", "vapor_mass_fraction")
COMPARISON_GROUP_FIELDS = (*COMPARISON_AXES, "saturation_endpoint")
COMPARISON_FILTER_FIELDS = COMPARISON_GROUP_FIELDS
DELTA_METRICS = ("signed_relative_difference", "signed_absolute_difference")
PLOT_SCALES = ("linear", "log")
PLOT_FORMATS = ("png", "svg", "pdf")


class ComparisonPlotDraft(QObject):
    """Own one detached, temporary model-sweep comparison-plot edit."""

    changed = Signal()
    validity_changed = Signal()

    def __init__(
        self,
        *,
        selected_models: Sequence[str],
        reference_model: str,
        fluids: Sequence[str],
        properties: Sequence[str],
        fluid_aliases: Mapping[str, str] | None = None,
        categorical_values: Mapping[str, Sequence[str]] | None = None,
        payload: Mapping[str, object] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.model_choices = DraftListModel(self)
        self.filters = MappingDraftModel(self, numeric_values=True)
        self.filters.changed.connect(self._state_changed)
        self._selected_models = tuple(selected_models)
        self._reference_model = reference_model
        self._fluids = tuple(fluids)
        self._properties = tuple(properties)
        self._fluid_aliases = {
            str(alias).casefold(): str(canonical)
            for alias, canonical in (fluid_aliases or {}).items()
        }
        categorical = {
            str(field): tuple(str(value) for value in values)
            for field, values in (categorical_values or {}).items()
        }
        self._name = ""
        self._kind = "property_comparison"
        self._fluid = self._fluids[0] if self._fluids else ""
        self._property_name = self._properties[0] if self._properties else ""
        self._x_field = "temperature"
        self._group_by = ""
        self._explicit_models = False
        self._models: tuple[str, ...] = ()
        self._delta_metric = "signed_relative_difference"
        self._value_scale = "linear"
        self._output_format = ""
        self.filters.configure(
            COMPARISON_FILTER_FIELDS,
            field_kinds={"saturation_endpoint": "categorical"},
            value_choices={"saturation_endpoint": categorical.get("saturation_endpoint", ())},
        )
        if payload is not None:
            self.load_payload(payload)
        else:
            self._refresh_models()

    def get_name(self) -> str:
        return self._name

    @Slot(str)
    def set_name(self, value: str) -> None:
        self._set_scalar("_name", value)

    name = Property(str, get_name, set_name, notify=changed)

    def get_kind(self) -> str:
        return self._kind

    @Slot(str)
    def set_kind(self, value: str) -> None:
        self._set_scalar("_kind", value)

    kind = Property(str, get_kind, set_kind, notify=changed)

    def get_fluid(self) -> str:
        return self._fluid

    @Slot(str)
    def set_fluid(self, value: str) -> None:
        self._set_scalar("_fluid", value)

    fluid = Property(str, get_fluid, set_fluid, notify=changed)

    def get_property_name(self) -> str:
        return self._property_name

    @Slot(str)
    def set_property_name(self, value: str) -> None:
        self._set_scalar("_property_name", value)

    propertyName = Property(str, get_property_name, set_property_name, notify=changed)

    def get_x_field(self) -> str:
        return self._x_field

    @Slot(str)
    def set_x_field(self, value: str) -> None:
        self._set_scalar("_x_field", value)

    xField = Property(str, get_x_field, set_x_field, notify=changed)

    def get_group_by(self) -> str:
        return self._group_by

    @Slot(str)
    def set_group_by(self, value: str) -> None:
        self._set_scalar("_group_by", value)

    groupBy = Property(str, get_group_by, set_group_by, notify=changed)

    def get_explicit_models(self) -> bool:
        return self._explicit_models

    @Slot(bool)
    def set_explicit_models(self, value: bool) -> None:
        updated = bool(value)
        if updated == self._explicit_models:
            return
        self._explicit_models = updated
        if updated and not self._models:
            self._models = tuple(
                model
                for model in self._selected_models
                if self._kind != "property_delta" or model != self._reference_model
            )
        self._state_changed()

    explicitModels = Property(bool, get_explicit_models, set_explicit_models, notify=changed)

    def get_delta_metric(self) -> str:
        return self._delta_metric

    @Slot(str)
    def set_delta_metric(self, value: str) -> None:
        self._set_scalar("_delta_metric", value)

    deltaMetric = Property(str, get_delta_metric, set_delta_metric, notify=changed)

    def get_value_scale(self) -> str:
        return self._value_scale

    @Slot(str)
    def set_value_scale(self, value: str) -> None:
        self._set_scalar("_value_scale", value)

    valueScale = Property(str, get_value_scale, set_value_scale, notify=changed)

    def get_output_format(self) -> str:
        return self._output_format

    @Slot(str)
    def set_output_format(self, value: str) -> None:
        self._set_scalar("_output_format", value)

    outputFormat = Property(str, get_output_format, set_output_format, notify=changed)

    def get_model_choices(self) -> QObject:
        return self.model_choices

    modelChoices = Property(QObject, get_model_choices, constant=True)

    def get_fluid_choices(self) -> list[str]:
        values = list(self._fluids)
        if self._fluid and not self._fluid_matches_selected(self._fluid):
            values.append(self._fluid)
        return values

    fluidChoices = Property(list, get_fluid_choices, notify=changed)
    propertyChoices = Property(list, lambda self: list(self._properties), constant=True)
    kindChoices = Property(list, lambda _self: list(COMPARISON_KINDS), constant=True)
    xChoices = Property(list, lambda _self: list(COMPARISON_AXES), constant=True)
    groupByChoices = Property(
        list,
        lambda _self: ["", *COMPARISON_GROUP_FIELDS],
        constant=True,
    )
    deltaMetricChoices = Property(list, lambda _self: list(DELTA_METRICS), constant=True)
    scaleChoices = Property(list, lambda _self: list(PLOT_SCALES), constant=True)
    formatChoices = Property(list, lambda _self: ["", *PLOT_FORMATS], constant=True)

    def get_filters(self) -> QObject:
        return self.filters

    filtersModel = Property(QObject, get_filters, constant=True)

    def get_locally_valid(self) -> bool:
        return not self.get_issue()

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        try:
            self.payload()
        except ValueError as exc:
            return str(exc)
        return ""

    issue = Property(str, get_issue, notify=validity_changed)

    def get_first_invalid_field(self) -> str:
        issue = self.get_issue().casefold()
        if not issue:
            return ""
        if not self.filters.get_valid():
            return "sweep.comparison.active.filters"
        if "name" in issue:
            return "sweep.comparison.active.name"
        if "fluid" in issue:
            return "sweep.comparison.active.fluid"
        if "model" in issue or "reference" in issue:
            return "sweep.comparison.active.models"
        if "property" in issue:
            return "sweep.comparison.active.property"
        if "kind" in issue:
            return "sweep.comparison.active.kind"
        if "group" in issue:
            return "sweep.comparison.active.group_by"
        if "x field" in issue or "\nx\n" in issue:
            return "sweep.comparison.active.x"
        if "metric" in issue:
            return "sweep.comparison.active.delta_metric"
        if "scale" in issue:
            return "sweep.comparison.active.value_scale"
        if "format" in issue:
            return "sweep.comparison.active.format"
        return "sweep.comparison.active"

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        return self.filters.get_first_invalid_row() if not self.filters.get_valid() else -1

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    @Slot(str, bool, result=bool)
    def set_model_selected(self, model: str, selected: bool) -> bool:
        if model not in self._selected_models:
            return False
        if selected and self._kind == "property_delta" and model == self._reference_model:
            return False
        values = list(self._models)
        if selected and model not in values:
            values.append(model)
        elif not selected and model in values:
            values.remove(model)
        else:
            return False
        self._models = tuple(item for item in self._selected_models if item in values)
        self._state_changed()
        return True

    def load_payload(self, value: Mapping[str, object]) -> None:
        self._name = str(value.get("name", ""))
        self._kind = str(value.get("kind", "property_comparison"))
        self._fluid = str(value.get("fluid", ""))
        self._property_name = str(value.get("property", ""))
        self._x_field = str(value.get("x", "temperature"))
        self._group_by = str(value.get("group_by", ""))
        raw_models = value.get("models")
        self._explicit_models = isinstance(raw_models, (list, tuple))
        self._models = (
            tuple(str(item) for item in raw_models) if isinstance(raw_models, (list, tuple)) else ()
        )
        self._delta_metric = str(value.get("delta_metric", "signed_relative_difference"))
        self._value_scale = str(value.get("value_scale", "linear"))
        self._output_format = str(value.get("format", ""))
        raw_filters = value.get("filters")
        self.filters.load_mapping(raw_filters if isinstance(raw_filters, Mapping) else {})
        self._refresh_models()
        self.validity_changed.emit()
        self.changed.emit()

    def payload(self) -> dict[str, Any]:
        from carnopy.config.sweep import ComparisonPlotConfig

        if not self._fluid_matches_selected(self._fluid):
            raise ValueError(f"comparison plot fluid {self._fluid!r} is not selected")
        if self._property_name not in self._properties:
            raise ValueError(f"comparison plot property {self._property_name!r} is not selected")
        if self._kind not in COMPARISON_KINDS:
            raise ValueError("comparison plot kind is invalid")
        if self._x_field not in COMPARISON_AXES:
            raise ValueError("comparison plot x field is invalid")
        if self._group_by and self._group_by not in COMPARISON_GROUP_FIELDS:
            raise ValueError("comparison plot group_by field is invalid")
        selected_models: list[str] | None = None
        if self._explicit_models:
            selected_models = list(self._models)
            if any(model not in self._selected_models for model in selected_models):
                raise ValueError("comparison models must be selected sweep models")
            if self._kind == "property_delta" and self._reference_model in selected_models:
                raise ValueError("property_delta models cannot include the reference model")
        result: dict[str, Any] = {
            "name": self._name.strip(),
            "kind": self._kind,
            "fluid": self._fluid,
            "property": self._property_name,
            "x": self._x_field,
        }
        if self._group_by:
            result["group_by"] = self._group_by
        filters = self.filters.mapping()
        if filters:
            result["filters"] = filters
        if selected_models is not None:
            result["models"] = selected_models
        result["delta_metric"] = self._delta_metric
        if self._value_scale != "linear":
            result["value_scale"] = self._value_scale
        if self._output_format:
            result["format"] = self._output_format
        try:
            validated = ComparisonPlotConfig.model_validate(result)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return validated.model_dump(mode="json", by_alias=True, exclude_none=True)

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._name,
            self._kind,
            self._fluid,
            self._property_name,
            self._x_field,
            self._group_by,
            self._explicit_models,
            self._models,
            self._delta_metric,
            self._value_scale,
            self._output_format,
            self.filters.raw_rows(),
        )

    def detached_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload())

    def _set_scalar(self, attribute: str, value: str) -> None:
        if getattr(self, attribute) == value:
            return
        setattr(self, attribute, value)
        self._state_changed()

    def _state_changed(self) -> None:
        self._refresh_models()
        self.validity_changed.emit()
        self.changed.emit()

    def _refresh_models(self) -> None:
        self.model_choices.replace(
            DraftItem(
                value=model,
                display=model.upper(),
                canonical=model,
                compatible=(self._kind != "property_delta" or model != self._reference_model),
                selected=model in self._models,
                issue=(
                    "Delta plots compare against the reference model implicitly."
                    if self._kind == "property_delta" and model == self._reference_model
                    else ""
                ),
            )
            for model in self._selected_models
        )

    def _fluid_matches_selected(self, value: str) -> bool:
        requested = self._canonical_fluid(value)
        return any(self._canonical_fluid(selected) == requested for selected in self._fluids)

    def _canonical_fluid(self, value: str) -> str:
        return self._fluid_aliases.get(value.casefold(), value).casefold()
