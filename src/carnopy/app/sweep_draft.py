from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.draft_models import DraftItem, DraftListModel

MODEL_DISPLAY_NAMES = {
    "heos": "Helmholtz Equation of State (HEOS)",
    "pr": "Peng-Robinson (PR)",
    "srk": "Soave-Redlich-Kwong (SRK)",
}


class SweepDraft(QObject):
    """Compose editable sweep fields from the proven dataset draft models."""

    changed = Signal()
    validity_changed = Signal()
    dirty_changed = Signal()
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.dataset_draft = DatasetDraft(self)
        self.model_choices = DraftListModel(self)
        self._capabilities: dict[str, Any] | None = None
        self._models: tuple[str, ...] = ()
        self._selected_models: tuple[str, ...] = ()
        self._reference_model = ""
        self._comparison_plots: dict[str, Any] | None = None
        self._baseline: dict[str, Any] | None = None
        self._baseline_raw: tuple[object, ...] | None = None
        self._loaded = False
        self._loading = False
        self.dataset_draft.changed.connect(self._dataset_changed)

    def get_dataset_draft(self) -> QObject:
        return self.dataset_draft

    datasetDraft = Property(QObject, get_dataset_draft, constant=True)

    def get_model_choices(self) -> QObject:
        return self.model_choices

    modelChoices = Property(QObject, get_model_choices, constant=True)

    def get_selected_models(self) -> list[str]:
        return list(self._selected_models)

    selectedModels = Property(list, get_selected_models, notify=changed)

    def get_reference_model(self) -> str:
        return self._reference_model

    @Slot(str, result=bool)
    def set_reference_model(self, value: str) -> bool:
        if (
            value not in self._models
            or value not in self._selected_models
            or value == self._reference_model
        ):
            return False
        self._reference_model = value
        self._loading = True
        try:
            self.dataset_draft.set_model_name(value)
        finally:
            self._loading = False
        self._state_changed()
        return True

    def _set_reference_property(self, value: str) -> None:
        self.set_reference_model(value)

    referenceModel = Property(
        str,
        get_reference_model,
        _set_reference_property,
        notify=changed,
    )

    def get_locally_valid(self) -> bool:
        return not self.get_issue()

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        if not self._loaded:
            return "No model sweep configuration is open."
        if self._capabilities is None:
            return "Sweep capabilities are not loaded."
        unavailable = [model for model in self._selected_models if model not in self._models]
        if unavailable:
            return "Selected models are unavailable in this environment: " + ", ".join(unavailable)
        if len(self._selected_models) < 2:
            return "Select at least two backend models."
        if self._reference_model not in self._selected_models:
            return "Select a reference model from the sweep models."
        if not self.dataset_draft.get_locally_valid():
            return self.dataset_draft.get_issue()
        unsupported = self._unsupported_properties()
        if unsupported:
            name, models = unsupported[0]
            return f"Property {name!r} is unavailable for: {', '.join(models)}."
        try:
            self.payload()
        except ValueError as exc:
            return str(exc)
        return ""

    issue = Property(str, get_issue, notify=validity_changed)

    def get_first_invalid_field(self) -> str:
        issue = self.get_issue()
        if not issue:
            return ""
        lowered = issue.casefold()
        if "reference model" in lowered:
            return "sweep.backend.reference_model"
        if "model" in lowered:
            return "sweep.backend.models"
        if not self.dataset_draft.get_locally_valid():
            return self.dataset_draft.get_first_invalid_field().replace("dataset.", "sweep.", 1)
        if "comparison" in lowered:
            return "sweep.comparison_plots"
        if "property" in lowered:
            return "sweep.properties"
        return "sweep.configuration"

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        issue = self.get_issue().casefold()
        if "models are unavailable" in issue:
            return next(
                (
                    row
                    for row, model in enumerate(self._selected_models)
                    if model not in self._models
                ),
                -1,
            )
        if not self.dataset_draft.get_locally_valid():
            return self.dataset_draft.get_first_invalid_row()
        unsupported = self._unsupported_properties()
        if unsupported:
            name = unsupported[0][0]
            try:
                return self.dataset_draft.selected_property_values().index(name)
            except ValueError:  # pragma: no cover - guarded by helper input
                return -1
        return -1

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def get_dirty(self) -> bool:
        if self._baseline is None or self._baseline_raw is None:
            return False
        try:
            return self.payload() != self._baseline
        except ValueError:
            return self.raw_state() != self._baseline_raw

    dirty = Property(bool, get_dirty, notify=dirty_changed)

    def apply_capabilities(self, payload: Mapping[str, object]) -> None:
        self._loading = True
        try:
            self._capabilities = copy.deepcopy(dict(payload))
            self._models = _string_tuple(payload.get("models"))
            self.dataset_draft.apply_capabilities(payload)
            if not self._loaded:
                if not self._selected_models:
                    self._selected_models = self._models
                if self._reference_model not in self._selected_models:
                    self._reference_model = (
                        self._selected_models[0] if self._selected_models else ""
                    )
            self._refresh_models()
        finally:
            self._loading = False
        self.validity_changed.emit()
        self.changed.emit()

    def load_payload(self, payload: Mapping[str, object]) -> None:
        from carnopy.config.sweep import ModelSweepConfig

        validated = ModelSweepConfig.model_validate(payload)
        value = validated.model_dump(mode="json", by_alias=True, exclude_none=True)
        backend = value["backend"]
        assert isinstance(backend, dict)
        selected_models = _string_tuple(backend.get("models"))
        reference_model = str(backend.get("reference_model", ""))
        dataset_payload = copy.deepcopy(value)
        dataset_payload["document_type"] = "dataset"
        dataset_payload["backend"] = {
            "name": "coolprop",
            "model": reference_model,
        }
        dataset_payload.pop("comparison_plots", None)
        comparisons = value.get("comparison_plots")
        self._loading = True
        try:
            permissive = _permissive_dataset_capabilities(
                dataset_payload,
                reference_model=reference_model,
                current=self._capabilities,
            )
            self.dataset_draft.apply_capabilities(permissive)
            self.dataset_draft.load_payload(dataset_payload)
            if self._capabilities is not None:
                self.dataset_draft.apply_capabilities(self._capabilities)
            self._loaded = True
            self._selected_models = selected_models
            self._reference_model = reference_model
            self._comparison_plots = (
                copy.deepcopy(comparisons) if isinstance(comparisons, dict) else None
            )
            self._refresh_models()
        finally:
            self._loading = False
        self._baseline = copy.deepcopy(value)
        self._baseline_raw = self.raw_state()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.changed.emit()

    def clear(self) -> None:
        self._loading = True
        try:
            self.dataset_draft.clear()
            self._loaded = False
            self._selected_models = ()
            self._reference_model = ""
            self._comparison_plots = None
            self._baseline = None
            self._baseline_raw = None
            self._refresh_models()
        finally:
            self._loading = False
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.changed.emit()

    def mark_baseline(self) -> None:
        issue = self.get_issue()
        if issue:
            raise ValueError("cannot mark an invalid model sweep draft as saved")
        value = self.payload()
        self.dataset_draft.mark_baseline()
        self._baseline = value
        self._baseline_raw = self.raw_state()
        self.dirty_changed.emit()

    def payload(self) -> dict[str, Any]:
        from carnopy.config.sweep import ModelSweepConfig

        dataset = self.dataset_draft.dataset_payload()
        result = copy.deepcopy(dataset)
        result["document_type"] = "model_sweep"
        result["backend"] = {
            "name": "coolprop",
            "models": list(self._selected_models),
            "reference_model": self._reference_model,
        }
        if self._comparison_plots is not None:
            result["comparison_plots"] = copy.deepcopy(self._comparison_plots)
        try:
            model = ModelSweepConfig.model_validate(result)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump(mode="json", by_alias=True, exclude_none=True)

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._loaded,
            self._selected_models,
            self._reference_model,
            self.dataset_draft.raw_state(),
            copy.deepcopy(self._comparison_plots),
        )

    def comparison_plots_payload(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._comparison_plots)

    @Slot(str, bool, result=bool)
    def set_model_selected(self, model: str, selected: bool) -> bool:
        if selected and model not in self._models:
            return False
        if not selected and model not in self._selected_models:
            return False
        if not selected and model == self._reference_model:
            self.message.emit("Choose another reference model before removing this model.")
            return False
        values = list(self._selected_models)
        if selected and model not in values:
            values.append(model)
        elif not selected:
            values.remove(model)
        else:
            return False
        self._selected_models = tuple(values)
        self._state_changed()
        return True

    @Slot(str, bool, result=bool)
    def apply_mode_change(self, mode: str, confirmed: bool) -> bool:
        if not confirmed:
            return False
        return self.dataset_draft.apply_mode_change(mode)

    @Slot(str, bool, result=bool)
    def apply_coordinate_change(self, axis: str, confirmed: bool) -> bool:
        if not confirmed:
            return False
        return self.dataset_draft.set_coordinate(axis)

    def _unsupported_properties(self) -> list[tuple[str, list[str]]]:
        capabilities = self._capabilities or {}
        catalog = capabilities.get("property_catalog")
        if not isinstance(catalog, list):
            return []
        support = {
            str(item.get("name")): set(_string_tuple(item.get("supported_models")))
            for item in catalog
            if isinstance(item, Mapping)
        }
        result: list[tuple[str, list[str]]] = []
        for name in self.dataset_draft.selected_property_values():
            missing = [
                model for model in self._selected_models if model not in support.get(name, set())
            ]
            if missing:
                result.append((name, missing))
        return result

    def _dataset_changed(self) -> None:
        if not self._loading:
            self._state_changed()

    def _state_changed(self) -> None:
        self._refresh_models()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.changed.emit()

    def _refresh_models(self) -> None:
        unavailable_selected = (
            model for model in self._selected_models if model not in self._models
        )
        visible_models = (*self._models, *unavailable_selected)
        self.model_choices.replace(
            DraftItem(
                value=model,
                display=MODEL_DISPLAY_NAMES.get(model, model.upper()),
                canonical=model,
                compatible=model in self._models,
                selected=model in self._selected_models,
                issue=(
                    "Unavailable in the current environment."
                    if model not in self._models
                    else "Reference model"
                    if model == self._reference_model
                    else ""
                ),
            )
            for model in visible_models
        )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _permissive_dataset_capabilities(
    payload: Mapping[str, object],
    *,
    reference_model: str,
    current: Mapping[str, object] | None,
) -> dict[str, object]:
    """Let the Dataset draft retain schema-valid imported values before rechecking them."""

    result: dict[str, object] = copy.deepcopy(dict(current or {}))
    result["model"] = reference_model
    result["models"] = list(dict.fromkeys((*_string_tuple(result.get("models")), reference_model)))
    mode = str(payload.get("mode", ""))
    result["modes"] = list(dict.fromkeys((*_string_tuple(result.get("modes")), mode)))

    grid = payload.get("grid")
    units = result.get("units_by_axis")
    units_by_axis = (
        {str(axis): list(_string_tuple(values)) for axis, values in units.items()}
        if isinstance(units, Mapping)
        else {}
    )
    if isinstance(grid, Mapping):
        for axis, sampler in grid.items():
            if not isinstance(sampler, Mapping):
                continue
            unit = str(sampler.get("unit", ""))
            existing = units_by_axis.setdefault(str(axis), [])
            if unit and unit not in existing:
                existing.append(unit)
    result["units_by_axis"] = units_by_axis

    outputs = payload.get("outputs")
    selected_formats = (
        _string_tuple(outputs.get("dataset_formats")) if isinstance(outputs, Mapping) else ()
    )
    result["dataset_formats"] = list(
        dict.fromkeys((*_string_tuple(result.get("dataset_formats")), *selected_formats))
    )

    fluids = result.get("fluids")
    fluid_entries = (
        [copy.deepcopy(dict(entry)) for entry in fluids if isinstance(entry, Mapping)]
        if isinstance(fluids, list)
        else []
    )
    for selected in _string_tuple(payload.get("fluids")):
        entry = _find_fluid_entry(fluid_entries, selected)
        if entry is None:
            entry = {"name": selected, "aliases": []}
            fluid_entries.append(entry)
        entry["supported_models"] = list(
            dict.fromkeys((*_string_tuple(entry.get("supported_models")), reference_model))
        )
    result["fluids"] = fluid_entries

    property_catalog = result.get("property_catalog")
    property_entries = (
        [copy.deepcopy(dict(entry)) for entry in property_catalog if isinstance(entry, Mapping)]
        if isinstance(property_catalog, list)
        else []
    )
    properties_by_name = {str(entry.get("name", "")): entry for entry in property_entries}
    for selected in _string_tuple(payload.get("properties")):
        entry = properties_by_name.get(selected)
        if entry is None:
            entry = {"name": selected}
            property_entries.append(entry)
        entry["supported_models"] = list(
            dict.fromkeys((*_string_tuple(entry.get("supported_models")), reference_model))
        )
    result["property_catalog"] = property_entries
    result.setdefault("reference_dependent_fields", [])
    result.setdefault("reference_state", {})
    return result


def _find_fluid_entry(
    entries: list[dict[str, object]],
    selected: str,
) -> dict[str, object] | None:
    folded = selected.casefold()
    for entry in entries:
        names = (str(entry.get("name", "")), *_string_tuple(entry.get("aliases")))
        if any(name.casefold() == folded for name in names):
            return entry
    return None
