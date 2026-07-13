from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, cast

import yaml
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.config_document import GRID_AXIS_ORDER, serialize_dataset_config
from carnopy.app.draft_models import (
    DraftItem,
    DraftListModel,
    SamplerDraftModel,
)
from carnopy.app.sampler_draft import SamplerDraft
from carnopy.templates import template_text

DATASET_OWNED_FIELDS = (
    "schema_version",
    "document_type",
    "backend",
    "mode",
    "fluids",
    "grid",
    "properties",
    "outputs",
)


class DatasetDraft(QObject):
    """Own QML-ready editable state for dataset-owned configuration fields."""

    changed = Signal()
    model_name_changed = Signal()
    mode_name_changed = Signal()
    coordinate_name_changed = Signal()
    validity_changed = Signal()
    dirty_changed = Signal()
    reference_advisory_changed = Signal()
    mode_change_requested = Signal(str)
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.model_choices = DraftListModel(self)
        self.mode_choices = DraftListModel(self)
        self.coordinate_choices = DraftListModel(self)
        self.fluid_choices = DraftListModel(self)
        self.selected_fluids = DraftListModel(self)
        self.property_choices = DraftListModel(self, disable_incompatible=True)
        self.selected_properties = DraftListModel(self)
        self.output_formats = DraftListModel(self)
        self.samplers = SamplerDraftModel(self)
        self._capabilities: dict[str, Any] | None = None
        self._models: tuple[str, ...] = ()
        self._modes: tuple[str, ...] = ()
        self._dataset_formats: tuple[str, ...] = ()
        self._units_by_axis: dict[str, tuple[str, ...]] = {}
        self._fluid_aliases: dict[str, str] = {}
        self._fluid_choice_values: tuple[tuple[str, str], ...] = ()
        self._property_catalog: dict[str, dict[str, Any]] = {}
        self._reference_fields: frozenset[str] = frozenset()
        self._loaded = False
        self._model_name = ""
        self._mode_name = ""
        self._coordinate_name = "temperature"
        self._fluids: tuple[str, ...] = ()
        self._properties: tuple[str, ...] = ()
        self._selected_formats: tuple[str, ...] = ()
        self._sampler_by_axis: dict[str, SamplerDraft] = {}
        self._baseline_yaml: bytes | None = None
        self._baseline_raw: tuple[object, ...] | None = None
        self._valid = False
        self._issue = "No dataset configuration is open."
        self._dirty = False
        self._reference_advisory = ""

    def get_model_name(self) -> str:
        return self._model_name

    @Slot(str)
    def set_model_name(self, value: str) -> None:
        if not self._loaded or value not in self._models or value == self._model_name:
            return
        self._model_name = value
        self.model_name_changed.emit()
        self._state_changed()

    modelName = Property(
        str,
        get_model_name,
        set_model_name,
        notify=model_name_changed,
    )

    def get_mode_name(self) -> str:
        return self._mode_name

    modeName = Property(str, get_mode_name, notify=mode_name_changed)

    def get_coordinate_name(self) -> str:
        return self._coordinate_name

    coordinateName = Property(
        str,
        get_coordinate_name,
        notify=coordinate_name_changed,
    )

    def get_locally_valid(self) -> bool:
        return self._valid

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=validity_changed)

    def get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, get_dirty, notify=dirty_changed)

    def get_reference_advisory(self) -> str:
        return self._reference_advisory

    referenceAdvisory = Property(
        str,
        get_reference_advisory,
        notify=reference_advisory_changed,
    )

    def _constant_model(self, model: QObject) -> QObject:
        return model

    modelChoices = Property(
        QObject,
        lambda self: self._constant_model(self.model_choices),
        constant=True,
    )
    modeChoices = Property(
        QObject,
        lambda self: self._constant_model(self.mode_choices),
        constant=True,
    )
    coordinateChoices = Property(
        QObject,
        lambda self: self._constant_model(self.coordinate_choices),
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
    propertyChoices = Property(
        QObject,
        lambda self: self._constant_model(self.property_choices),
        constant=True,
    )
    selectedProperties = Property(
        QObject,
        lambda self: self._constant_model(self.selected_properties),
        constant=True,
    )
    outputFormats = Property(
        QObject,
        lambda self: self._constant_model(self.output_formats),
        constant=True,
    )
    samplerDrafts = Property(
        QObject,
        lambda self: self._constant_model(self.samplers),
        constant=True,
    )

    def apply_capabilities(self, payload: Mapping[str, object]) -> None:
        self._capabilities = copy.deepcopy(dict(payload))
        self._models = _string_tuple(payload.get("models"))
        self._modes = _string_tuple(payload.get("modes"))
        self._dataset_formats = _string_tuple(payload.get("dataset_formats"))
        units = payload.get("units_by_axis")
        self._units_by_axis = {
            str(axis): _string_tuple(values)
            for axis, values in (units.items() if isinstance(units, Mapping) else ())
        }
        aliases: dict[str, str] = {}
        choices: list[tuple[str, str]] = []
        fluids = payload.get("fluids")
        if isinstance(fluids, list):
            for entry in fluids:
                if not isinstance(entry, Mapping):
                    continue
                canonical = str(entry.get("name", ""))
                values = (canonical, *_string_tuple(entry.get("aliases")))
                for value in values:
                    folded = value.casefold()
                    if value and folded not in aliases:
                        aliases[folded] = canonical
                        choices.append((value, canonical))
        self._fluid_aliases = aliases
        self._fluid_choice_values = tuple(sorted(choices, key=lambda item: item[0].casefold()))
        properties = payload.get("property_catalog")
        self._property_catalog = {
            str(entry["name"]): copy.deepcopy(dict(entry))
            for entry in (properties if isinstance(properties, list) else [])
            if isinstance(entry, Mapping) and "name" in entry
        }
        self._reference_fields = frozenset(_string_tuple(payload.get("reference_dependent_fields")))
        for axis, sampler in self._sampler_by_axis.items():
            sampler.set_available_units(self._units_by_axis.get(axis, ()))
        self._refresh_models()
        self._refresh_derived()

    def load_payload(self, payload: Mapping[str, object]) -> None:
        previous = self._observable_state()
        dataset = dataset_owned_payload(payload)
        backend = dataset.get("backend")
        self._model_name = str(backend.get("model", "")) if isinstance(backend, Mapping) else ""
        self._mode_name = str(dataset.get("mode", ""))
        self._fluids = _string_tuple(dataset.get("fluids"))
        self._properties = _string_tuple(dataset.get("properties"))
        outputs = dataset.get("outputs")
        selected_formats = (
            _string_tuple(outputs.get("dataset_formats"))
            if isinstance(outputs, Mapping)
            else self._dataset_formats
        )
        self._selected_formats = tuple(
            value for value in self._dataset_formats if value in selected_formats
        )
        grid = dataset.get("grid")
        grid_mapping = grid if isinstance(grid, Mapping) else {}
        coordinate = next(
            (axis for axis in ("temperature", "pressure") if axis in grid_mapping),
            "temperature",
        )
        self._coordinate_name = coordinate
        self._replace_samplers(grid_mapping)
        self._loaded = True
        self._refresh_models()
        self._refresh_derived()
        self._baseline_yaml = serialize_dataset_config(self.dataset_payload())
        self._baseline_raw = self.raw_state()
        self._refresh_derived()
        self._emit_observable_changes(previous)
        self.changed.emit()

    def clear(self) -> None:
        previous = self._observable_state()
        self._loaded = False
        self._model_name = ""
        self._mode_name = ""
        self._coordinate_name = "temperature"
        self._fluids = ()
        self._properties = ()
        self._selected_formats = ()
        self._sampler_by_axis = {}
        self._baseline_yaml = None
        self._baseline_raw = None
        self._refresh_models()
        self._refresh_derived()
        self._emit_observable_changes(previous)
        self.changed.emit()

    def mark_baseline(self) -> None:
        if not self._valid:
            raise ValueError("cannot mark an invalid dataset draft as saved")
        previous_dirty = self._dirty
        self._baseline_yaml = serialize_dataset_config(self.dataset_payload())
        self._baseline_raw = self.raw_state()
        self._refresh_derived()
        if previous_dirty != self._dirty:
            self.dirty_changed.emit()

    def dataset_payload(self) -> dict[str, Any]:
        issue = self._validation_issue()
        if issue:
            raise ValueError(issue)
        return {
            "schema_version": 2,
            "document_type": "dataset",
            "backend": {"name": "coolprop", "model": self._model_name},
            "mode": self._mode_name,
            "fluids": list(self._fluids),
            "grid": {
                axis: self._sampler_by_axis[axis].payload()
                for axis in GRID_AXIS_ORDER
                if axis in self._sampler_by_axis
            },
            "properties": list(self._properties),
            "outputs": {"dataset_formats": list(self._selected_formats)},
        }

    def merge_into(self, complete_payload: Mapping[str, object]) -> dict[str, Any]:
        merged = copy.deepcopy(dict(complete_payload))
        merged.update(self.dataset_payload())
        return merged

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._loaded,
            self._model_name,
            self._mode_name,
            self._coordinate_name,
            self._fluids,
            tuple(
                self._sampler_by_axis[axis].raw_state()
                for axis in GRID_AXIS_ORDER
                if axis in self._sampler_by_axis
            ),
            self._properties,
            self._selected_formats,
        )

    @Slot(str)
    def request_mode_change(self, value: str) -> None:
        if self._loaded and value in self._modes and value != self._mode_name:
            self.mode_change_requested.emit(value)

    @Slot(str, result=bool)
    def apply_mode_change(self, value: str) -> bool:
        if not self._loaded or value not in self._modes or value == self._mode_name:
            return False
        payload = _template_payload(value)
        previous = self._observable_state()
        self._mode_name = value
        grid = payload.get("grid")
        self._coordinate_name = next(
            (
                axis
                for axis in ("temperature", "pressure")
                if isinstance(grid, Mapping) and axis in grid
            ),
            "temperature",
        )
        self._replace_samplers(grid if isinstance(grid, Mapping) else {})
        self._state_changed(previous=previous)
        return True

    @Slot(str, result=bool)
    def set_coordinate(self, axis: str) -> bool:
        if (
            not self._loaded
            or axis not in {"temperature", "pressure"}
            or self._mode_name == "property_table"
            or axis == self._coordinate_name
        ):
            return False
        previous = self._observable_state()
        vapor = self._sampler_by_axis.get("vapor_mass_fraction")
        replacement = _blank_sampler(
            axis,
            self._units_by_axis.get(axis, ()),
            self,
        )
        self._sampler_by_axis = {axis: replacement}
        if self._mode_name == "vapor_mass_fraction_table" and vapor is not None:
            self._sampler_by_axis["vapor_mass_fraction"] = vapor
        self._coordinate_name = axis
        self._connect_sampler(replacement)
        self._state_changed(previous=previous)
        return True

    @Slot(str, result=bool)
    def add_fluid(self, requested: str) -> bool:
        if not self._loaded:
            return False
        value = requested.strip()
        canonical = self._fluid_aliases.get(value.casefold())
        if not value or canonical is None:
            self.message.emit(f"Unknown fluid or alias: {value}")
            return False
        selected = {
            self._fluid_aliases.get(item.casefold(), item).casefold() for item in self._fluids
        }
        if canonical.casefold() in selected:
            self.message.emit(f"Fluid or alias is already selected: {canonical}")
            return False
        self._fluids = (*self._fluids, value)
        self._state_changed()
        return True

    @Slot(int, result=bool)
    def remove_fluid(self, row: int) -> bool:
        if not self._loaded:
            return False
        updated = _remove_row(self._fluids, row)
        if updated is None:
            return False
        self._fluids = updated
        self._state_changed()
        return True

    @Slot(int, int, result=bool)
    def move_fluid(self, row: int, offset: int) -> bool:
        if not self._loaded:
            return False
        updated = _move_row(self._fluids, row, offset)
        if updated is None:
            return False
        self._fluids = updated
        self._state_changed()
        return True

    @Slot(str, result=bool)
    def add_property(self, name: str) -> bool:
        if not self._loaded:
            return False
        if name not in self._property_catalog:
            self.message.emit(f"Unknown property: {name}")
            return False
        if name in self._properties:
            self.message.emit(f"Property is already selected: {name}")
            return False
        if not self._property_supported(name):
            self.message.emit(f"{name} is not supported by {self._model_name}.")
            return False
        self._properties = (*self._properties, name)
        self._state_changed()
        return True

    @Slot(int, result=bool)
    def remove_property(self, row: int) -> bool:
        if not self._loaded:
            return False
        updated = _remove_row(self._properties, row)
        if updated is None:
            return False
        self._properties = updated
        self._state_changed()
        return True

    @Slot(int, int, result=bool)
    def move_property(self, row: int, offset: int) -> bool:
        if not self._loaded:
            return False
        updated = _move_row(self._properties, row, offset)
        if updated is None:
            return False
        self._properties = updated
        self._state_changed()
        return True

    @Slot(str, bool, result=bool)
    def set_output_selected(self, name: str, selected: bool) -> bool:
        if not self._loaded or name not in self._dataset_formats:
            return False
        values = set(self._selected_formats)
        before = set(values)
        if selected:
            values.add(name)
        else:
            values.discard(name)
        if values == before:
            return False
        self._selected_formats = tuple(value for value in self._dataset_formats if value in values)
        self._state_changed()
        return True

    def selected_fluid_values(self) -> tuple[str, ...]:
        return self._fluids

    def selected_property_values(self) -> tuple[str, ...]:
        return self._properties

    def unsupported_properties(self) -> tuple[str, ...]:
        return tuple(name for name in self._properties if not self._property_supported(name))

    def output_selected(self, name: str) -> bool:
        return name in self._selected_formats

    def sampler(self, axis: str) -> SamplerDraft | None:
        return self._sampler_by_axis.get(axis)

    def _state_changed(
        self,
        *,
        previous: tuple[object, ...] | None = None,
    ) -> None:
        before = self._observable_state() if previous is None else previous
        self._refresh_models()
        self._refresh_derived()
        self._emit_observable_changes(before)
        self.changed.emit()

    def _sampler_changed(self, sampler: SamplerDraft) -> None:
        before = self._observable_state()
        self.samplers.refresh(sampler)
        self._refresh_models()
        self._refresh_derived()
        self._emit_observable_changes(before)
        self.changed.emit()

    def _replace_samplers(self, grid: Mapping[str, object]) -> None:
        samplers: dict[str, SamplerDraft] = {}
        for axis in GRID_AXIS_ORDER:
            payload = grid.get(axis)
            if not isinstance(payload, Mapping):
                continue
            sampler = SamplerDraft(axis, self)
            sampler.load_payload(
                payload,
                available_units=self._units_by_axis.get(axis, ()),
            )
            self._connect_sampler(sampler)
            samplers[axis] = sampler
        self._sampler_by_axis = samplers

    def _connect_sampler(self, sampler: SamplerDraft) -> None:
        sampler.changed.connect(lambda draft=sampler: self._sampler_changed(draft))

    def _refresh_models(self) -> None:
        self.model_choices.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=value,
                selected=value == self._model_name,
            )
            for value in self._models
        )
        self.mode_choices.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=value,
                selected=value == self._mode_name,
            )
            for value in self._modes
        )
        self.coordinate_choices.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=value,
                selected=value == self._coordinate_name,
            )
            for value in ("temperature", "pressure")
        )
        selected_canonical = {
            self._fluid_aliases.get(value.casefold(), value).casefold() for value in self._fluids
        }
        self.fluid_choices.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=canonical,
                selected=canonical.casefold() in selected_canonical,
            )
            for value, canonical in self._fluid_choice_values
        )
        self.selected_fluids.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=self._fluid_aliases.get(value.casefold(), value),
            )
            for value in self._fluids
        )
        self.property_choices.replace(
            self._property_item(name, selected=name in self._properties)
            for name in self._property_catalog
        )
        self.selected_properties.replace(
            self._property_item(name, selected=True, selected_row=True) for name in self._properties
        )
        self.output_formats.replace(
            DraftItem(
                value=value,
                display=value.upper(),
                canonical=value,
                selected=value in self._selected_formats,
            )
            for value in self._dataset_formats
        )
        self.samplers.replace(
            self._sampler_by_axis[axis] for axis in GRID_AXIS_ORDER if axis in self._sampler_by_axis
        )

    def _property_item(
        self,
        name: str,
        *,
        selected: bool,
        selected_row: bool = False,
    ) -> DraftItem:
        compatible = self._property_supported(name)
        issue = "" if compatible else "Remove this property or select a model that supports it."
        display = (
            name
            if compatible
            else (
                f"Unsupported by {self._model_name}: {name}"
                if selected_row
                else f"{name} — unsupported by {self._model_name}"
            )
        )
        return DraftItem(
            value=name,
            display=display,
            canonical=name,
            compatible=compatible,
            selected=selected,
            issue=issue,
        )

    def _property_supported(self, name: str) -> bool:
        metadata = self._property_catalog.get(name, {})
        models = metadata.get("supported_models", [])
        return isinstance(models, list) and self._model_name in models

    def _refresh_derived(self) -> None:
        issue = self._validation_issue()
        self._valid = not issue
        self._issue = issue
        selected_reference = self._reference_fields.intersection(self._properties)
        self._reference_advisory = (
            "Reference-state advisory: absolute enthalpy, entropy, and internal-energy "
            "values depend on the recorded reference-state context."
            if selected_reference
            else ""
        )
        if self._baseline_yaml is None or self._baseline_raw is None:
            self._dirty = False
        elif self._valid:
            self._dirty = serialize_dataset_config(self.dataset_payload()) != self._baseline_yaml
        else:
            self._dirty = self.raw_state() != self._baseline_raw

    def _validation_issue(self) -> str:
        if not self._loaded:
            return "No dataset configuration is open."
        if self._capabilities is None:
            return "Dataset capabilities are not loaded."
        if self._model_name not in self._models:
            return "Choose a supported thermodynamic model."
        if self._mode_name not in self._modes:
            return "Choose a supported dataset mode."
        if not self._fluids:
            return "Add at least one fluid."
        expected_axes = _expected_axes(self._mode_name, self._coordinate_name)
        actual_axes = set(self._sampler_by_axis)
        if actual_axes != expected_axes:
            return f"{self._mode_name} has an incomplete sampling grid."
        for axis in GRID_AXIS_ORDER:
            sampler = self._sampler_by_axis.get(axis)
            if sampler is not None and not sampler.get_valid():
                return sampler.get_issue()
        if not self._properties:
            return "Add at least one property."
        if not self._selected_formats:
            return "Select CSV, Parquet, or both."
        unsupported = self.unsupported_properties()
        if unsupported:
            return f"Remove properties unsupported by {self._model_name}: " + ", ".join(unsupported)
        return ""

    def _observable_state(self) -> tuple[object, ...]:
        return (
            self._model_name,
            self._mode_name,
            self._coordinate_name,
            self._valid,
            self._issue,
            self._dirty,
            self._reference_advisory,
            self.raw_state(),
        )

    def _emit_observable_changes(self, previous: tuple[object, ...]) -> None:
        current = self._observable_state()
        if previous[0] != current[0]:
            self.model_name_changed.emit()
        if previous[1] != current[1]:
            self.mode_name_changed.emit()
        if previous[2] != current[2]:
            self.coordinate_name_changed.emit()
        if previous[3:5] != current[3:5]:
            self.validity_changed.emit()
        if previous[5] != current[5]:
            self.dirty_changed.emit()
        if previous[6] != current[6]:
            self.reference_advisory_changed.emit()


def dataset_owned_payload(payload: Mapping[str, object]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(payload[field]) for field in DATASET_OWNED_FIELDS if field in payload
    }


def _expected_axes(mode: str, coordinate: str) -> set[str]:
    if mode == "property_table":
        return {"temperature", "pressure"}
    if mode == "saturation_table":
        return {coordinate}
    if mode == "vapor_mass_fraction_table":
        return {coordinate, "vapor_mass_fraction"}
    return set()


def _blank_sampler(
    axis: str,
    units: Sequence[str],
    parent: QObject,
) -> SamplerDraft:
    unit = str(units[0]) if units else ""
    sampler = SamplerDraft(axis, parent)
    sampler.load_payload(
        {"kind": "explicit", "values": [1.0], "unit": unit},
        available_units=units,
    )
    return sampler


def _template_payload(mode: str) -> dict[str, Any]:
    value = yaml.safe_load(template_text(cast(Any, mode)))
    if not isinstance(value, dict):
        raise ValueError(f"packaged {mode} template is not a mapping")
    return cast(dict[str, Any], value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _remove_row(values: tuple[str, ...], row: int) -> tuple[str, ...] | None:
    if not 0 <= row < len(values):
        return None
    return (*values[:row], *values[row + 1 :])


def _move_row(
    values: tuple[str, ...],
    row: int,
    offset: int,
) -> tuple[str, ...] | None:
    target = row + offset
    if not 0 <= row < len(values) or not 0 <= target < len(values):
        return None
    updated = list(values)
    value = updated.pop(row)
    updated.insert(target, value)
    return tuple(updated)
