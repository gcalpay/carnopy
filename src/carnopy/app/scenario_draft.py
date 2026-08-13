from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.field_ids import preparation_scenario_field
from carnopy.app.workflow_models import WorkflowListModel

SCENARIO_KINDS = (
    "unsplit",
    "shuffle",
    "stratified_hash",
    "coordinate_block",
    "range_holdout",
    "leave_fluid_out",
    "phase_holdout",
    "model_holdout",
)
PARTITIONS = ("train", "validation", "test", "all")
TRANSFORM_METHODS = ("log10", "standard", "minmax", "robust")


class ScenarioDraft(QObject):
    """Own one detached, Python-authoritative Preparation scenario edit."""

    changed = Signal()
    validity_changed = Signal()
    field_choices_changed = Signal()
    kind_change_requested = Signal(str)

    def __init__(
        self,
        *,
        field_choices: Sequence[str] = (),
        payload: Mapping[str, object] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.partition_rows = WorkflowListModel(("partition", "ratio"), self)
        self.holdout_rows = WorkflowListModel(("partition", "summary", "kind"), self)
        self.strata_rows = WorkflowListModel(("field",), self)
        self.numeric_bin_rows = WorkflowListModel(
            ("field", "boundaries", "summary"),
            self,
        )
        self.transformation_rows = WorkflowListModel(
            ("field", "methods", "summary"),
            self,
        )
        self._field_choices = _unique_strings(field_choices)
        self._name = "scenario"
        self._kind = "unsplit"
        self._seed_text = ""
        self._field = ""
        self._remainder = ""
        self._partitions: dict[str, float] = {"all": 1.0}
        self._holdouts: dict[str, Any] = {}
        self._strata_categorical: tuple[str, ...] = ()
        self._numeric_bins: dict[str, tuple[float, ...]] = {}
        self._transformations: tuple[dict[str, Any], ...] = ()
        if payload is None:
            self._refresh_models()
        else:
            self.load_payload(payload)

    def get_name(self) -> str:
        return self._name

    @Slot(str, result=bool)
    def set_name(self, value: str) -> bool:
        return self._set_scalar("_name", value)

    def _set_name_property(self, value: str) -> None:
        self.set_name(value)

    name = Property(str, get_name, _set_name_property, notify=changed)

    def get_kind(self) -> str:
        return self._kind

    kind = Property(str, get_kind, notify=changed)

    def get_seed_text(self) -> str:
        return self._seed_text

    @Slot(str, result=bool)
    def set_seed_text(self, value: str) -> bool:
        return self._set_scalar("_seed_text", value.strip())

    def _set_seed_text_property(self, value: str) -> None:
        self.set_seed_text(value)

    seedText = Property(str, get_seed_text, _set_seed_text_property, notify=changed)

    def get_field(self) -> str:
        return self._field

    @Slot(str, result=bool)
    def set_field(self, value: str) -> bool:
        return self._set_scalar("_field", value.strip())

    def _set_field_property(self, value: str) -> None:
        self.set_field(value)

    field = Property(str, get_field, _set_field_property, notify=changed)

    def get_remainder(self) -> str:
        return self._remainder

    @Slot(str, result=bool)
    def set_remainder(self, value: str) -> bool:
        return self._set_scalar("_remainder", value.strip())

    def _set_remainder_property(self, value: str) -> None:
        self.set_remainder(value)

    remainder = Property(str, get_remainder, _set_remainder_property, notify=changed)

    def get_kind_choices(self) -> list[str]:
        return list(SCENARIO_KINDS)

    kindChoices = Property(list, get_kind_choices, constant=True)

    def get_partition_choices(self) -> list[str]:
        return list(PARTITIONS)

    partitionChoices = Property(list, get_partition_choices, constant=True)

    def get_field_choices(self) -> list[str]:
        referenced = [self._field, *self._numeric_bins]
        for holdout in self._holdouts.values():
            if isinstance(holdout, Mapping) and set(holdout) != {"min", "max"}:
                referenced.extend(str(field) for field in holdout)
        referenced.extend(str(item.get("field", "")) for item in self._transformations)
        return list(_unique_strings((*self._field_choices, *referenced)))

    fieldChoices = Property(list, get_field_choices, notify=field_choices_changed)

    def get_transform_method_choices(self) -> list[str]:
        return list(TRANSFORM_METHODS)

    transformationMethodChoices = Property(
        list,
        get_transform_method_choices,
        constant=True,
    )

    def get_strata_categorical_text(self) -> str:
        return ", ".join(self._strata_categorical)

    strataCategoricalText = Property(str, get_strata_categorical_text, notify=changed)

    def get_partition_rows(self) -> QObject:
        return self.partition_rows

    partitionsModel = Property(QObject, get_partition_rows, constant=True)

    def get_holdout_rows(self) -> QObject:
        return self.holdout_rows

    holdoutsModel = Property(QObject, get_holdout_rows, constant=True)

    def get_strata_rows(self) -> QObject:
        return self.strata_rows

    strataCategoricalModel = Property(QObject, get_strata_rows, constant=True)

    def get_numeric_bin_rows(self) -> QObject:
        return self.numeric_bin_rows

    numericBinsModel = Property(QObject, get_numeric_bin_rows, constant=True)

    def get_transformation_rows(self) -> QObject:
        return self.transformation_rows

    transformationsModel = Property(QObject, get_transformation_rows, constant=True)

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
        if "name" in issue:
            field = "name"
        elif "partition" in issue:
            field = "partitions"
        elif "holdout" in issue or "remainder" in issue:
            field = "holdouts"
        elif "strat" in issue or "bin" in issue:
            field = "strata"
        elif "transform" in issue:
            field = "transformations"
        elif "seed" in issue:
            field = "seed"
        elif "field" in issue:
            field = "field"
        else:
            field = "kind"
        return preparation_scenario_field(field)

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        field = self.get_first_invalid_field()
        if field.endswith(".partitions") and self.partition_rows.get_count():
            return 0
        if field.endswith(".holdouts") and self.holdout_rows.get_count():
            return 0
        if field.endswith(".strata"):
            if self.strata_rows.get_count():
                return 0
            if self.numeric_bin_rows.get_count():
                return 0
        if field.endswith(".transformations") and self.transformation_rows.get_count():
            return 0
        return -1

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def load_payload(self, payload: Mapping[str, object]) -> None:
        from carnopy.preparation.models import ScenarioConfig

        validated = ScenarioConfig.model_validate(payload)
        value = validated.model_dump(mode="json", exclude_none=True)
        self._name = str(value["name"])
        self._kind = str(value["kind"])
        seed = value.get("seed")
        self._seed_text = "" if seed is None else str(seed)
        self._field = str(value.get("field", ""))
        self._remainder = str(value.get("remainder", ""))
        self._partitions = {
            str(key): float(item) for key, item in _mapping(value.get("partitions")).items()
        }
        self._holdouts = copy.deepcopy(_mapping(value.get("holdouts")))
        strata = _mapping(value.get("strata"))
        self._strata_categorical = _strings(strata.get("categorical"))
        self._numeric_bins = {
            str(field): tuple(float(item) for item in boundaries)
            for field, boundaries in _mapping(strata.get("numeric_bins")).items()
            if isinstance(boundaries, list | tuple)
        }
        transformations = value.get("transformations")
        self._transformations = (
            tuple(copy.deepcopy(item) for item in transformations if isinstance(item, dict))
            if isinstance(transformations, list)
            else ()
        )
        self._refresh_models()
        self.validity_changed.emit()
        self.field_choices_changed.emit()
        self.changed.emit()

    def set_field_choices(self, values: Sequence[str]) -> bool:
        updated = _unique_strings(values)
        if updated == self._field_choices:
            return False
        self._field_choices = updated
        self.field_choices_changed.emit()
        return True

    @Slot(str, result=bool)
    def request_kind_change(self, value: str) -> bool:
        if value not in SCENARIO_KINDS or value == self._kind:
            return False
        if self._shape_has_state():
            self.kind_change_requested.emit(value)
            return False
        return self.apply_kind_change(value, True)

    @Slot(str, bool, result=bool)
    def apply_kind_change(self, value: str, confirmed: bool) -> bool:
        if not confirmed or value not in SCENARIO_KINDS or value == self._kind:
            return False
        self._kind = value
        self._field = ""
        self._remainder = ""
        self._holdouts = {}
        self._strata_categorical = ()
        self._numeric_bins = {}
        if value == "unsplit":
            self._partitions = {"all": 1.0}
        elif value in {"shuffle", "stratified_hash"}:
            self._partitions = {"train": 0.8, "test": 0.2}
            if not self._seed_text:
                self._seed_text = "42"
        else:
            self._partitions = {}
            self._remainder = "train"
        self._state_changed()
        return True

    @Slot(str, str, result=bool)
    def set_partition(self, partition: str, raw_ratio: str) -> bool:
        if partition not in PARTITIONS:
            return False
        try:
            ratio = _finite_float(raw_ratio, "partition ratio")
        except ValueError:
            return False
        if self._partitions.get(partition) == ratio:
            return False
        self._partitions[partition] = ratio
        self._state_changed()
        return True

    @Slot(str, result=bool)
    def remove_partition(self, partition: str) -> bool:
        if partition not in self._partitions:
            return False
        del self._partitions[partition]
        self._state_changed()
        return True

    @Slot(str, str, result=bool)
    def set_categorical_holdout(self, partition: str, comma_values: str) -> bool:
        if partition not in PARTITIONS or partition == "all":
            return False
        values = tuple(item.strip() for item in comma_values.split(",") if item.strip())
        if not values or len(values) != len(set(values)):
            return False
        return self._set_holdout(partition, list(values))

    @Slot(str, str, str, result=bool)
    def set_range_holdout(self, partition: str, raw_minimum: str, raw_maximum: str) -> bool:
        if partition not in PARTITIONS or partition == "all":
            return False
        try:
            minimum = _finite_float(raw_minimum, "range minimum")
            maximum = _finite_float(raw_maximum, "range maximum")
        except ValueError:
            return False
        if maximum < minimum:
            return False
        return self._set_holdout(partition, {"min": minimum, "max": maximum})

    @Slot(str, str, str, str, result=bool)
    def set_coordinate_holdout(
        self,
        partition: str,
        field: str,
        raw_minimum: str,
        raw_maximum: str,
    ) -> bool:
        cleaned = field.strip()
        if partition not in PARTITIONS or partition == "all" or not cleaned:
            return False
        try:
            minimum = _finite_float(raw_minimum, "coordinate minimum")
            maximum = _finite_float(raw_maximum, "coordinate maximum")
        except ValueError:
            return False
        if maximum < minimum:
            return False
        current = self._holdouts.get(partition)
        block = copy.deepcopy(current) if isinstance(current, dict) else {}
        block[cleaned] = {"min": minimum, "max": maximum}
        return self._set_holdout(partition, block)

    @Slot(str, str, result=bool)
    def remove_coordinate_field(self, partition: str, field: str) -> bool:
        current = self._holdouts.get(partition)
        if not isinstance(current, dict) or field not in current:
            return False
        block = copy.deepcopy(current)
        del block[field]
        if block:
            self._holdouts[partition] = block
        else:
            del self._holdouts[partition]
        self._state_changed()
        return True

    @Slot(str, result=bool)
    def remove_holdout(self, partition: str) -> bool:
        if partition not in self._holdouts:
            return False
        del self._holdouts[partition]
        self._state_changed()
        return True

    @Slot(str, result=bool)
    def set_strata_categorical(self, comma_fields: str) -> bool:
        values = tuple(item.strip() for item in comma_fields.split(",") if item.strip())
        if len(values) != len(set(values)) or values == self._strata_categorical:
            return False
        self._strata_categorical = values
        self._state_changed()
        return True

    @Slot(str, str, result=bool)
    def set_numeric_bins(self, field: str, comma_boundaries: str) -> bool:
        cleaned = field.strip()
        if not cleaned:
            return False
        try:
            boundaries = tuple(
                _finite_float(item.strip(), "numeric bin boundary")
                for item in comma_boundaries.split(",")
                if item.strip()
            )
        except ValueError:
            return False
        if not boundaries or any(right <= left for left, right in pairwise(boundaries)):
            return False
        if self._numeric_bins.get(cleaned) == boundaries:
            return False
        self._numeric_bins[cleaned] = boundaries
        self._state_changed()
        return True

    @Slot(str, result=bool)
    def remove_numeric_bins(self, field: str) -> bool:
        if field not in self._numeric_bins:
            return False
        del self._numeric_bins[field]
        self._state_changed()
        return True

    @Slot(str, str, result=bool)
    def add_transformation(self, field: str, comma_methods: str) -> bool:
        cleaned = field.strip()
        methods = tuple(item.strip() for item in comma_methods.split(",") if item.strip())
        if (
            not cleaned
            or not methods
            or len(methods) != len(set(methods))
            or any(item not in TRANSFORM_METHODS for item in methods)
        ):
            return False
        updated = [*self._transformations, {"field": cleaned, "methods": list(methods)}]
        if not _transformations_valid(updated):
            return False
        self._transformations = tuple(updated)
        self._state_changed()
        return True

    @Slot(int, result=bool)
    def remove_transformation(self, row: int) -> bool:
        if not 0 <= row < len(self._transformations):
            return False
        self._transformations = (
            *self._transformations[:row],
            *self._transformations[row + 1 :],
        )
        self._state_changed()
        return True

    @Slot(int, int, result=bool)
    def move_transformation(self, source: int, destination: int) -> bool:
        values = list(self._transformations)
        if (
            not 0 <= source < len(values)
            or not 0 <= destination < len(values)
            or source == destination
        ):
            return False
        item = values.pop(source)
        values.insert(destination, item)
        self._transformations = tuple(values)
        self._state_changed()
        return True

    def payload(self) -> dict[str, Any]:
        from carnopy.preparation.models import ScenarioConfig

        result: dict[str, Any] = {"name": self._name.strip(), "kind": self._kind}
        if self._seed_text:
            try:
                result["seed"] = int(self._seed_text)
            except ValueError as exc:
                raise ValueError("scenario seed must be an integer") from exc
        if self._partitions:
            result["partitions"] = copy.deepcopy(self._partitions)
        if self._field:
            result["field"] = self._field
        if self._holdouts:
            result["holdouts"] = copy.deepcopy(self._holdouts)
        if self._remainder:
            result["remainder"] = self._remainder
        if self._strata_categorical or self._numeric_bins:
            result["strata"] = {
                "categorical": list(self._strata_categorical),
                "numeric_bins": {
                    field: list(boundaries) for field, boundaries in self._numeric_bins.items()
                },
            }
        if self._transformations:
            result["transformations"] = copy.deepcopy(list(self._transformations))
        try:
            validated = ScenarioConfig.model_validate(result)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return validated.model_dump(mode="json", exclude_none=True)

    def detached_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload())

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._name,
            self._kind,
            self._seed_text,
            self._field,
            self._remainder,
            tuple(self._partitions.items()),
            copy.deepcopy(self._holdouts),
            self._strata_categorical,
            tuple(self._numeric_bins.items()),
            copy.deepcopy(self._transformations),
        )

    def _shape_has_state(self) -> bool:
        default_partitions = (
            self._partitions in ({}, {"all": 1.0})
            if self._kind == "unsplit"
            else not self._partitions
        )
        return bool(
            not default_partitions
            or self._holdouts
            or self._field
            or self._remainder
            or self._strata_categorical
            or self._numeric_bins
        )

    def _set_scalar(self, attribute: str, value: str) -> bool:
        if getattr(self, attribute) == value:
            return False
        setattr(self, attribute, value)
        self._state_changed()
        return True

    def _set_holdout(self, partition: str, value: object) -> bool:
        if self._holdouts.get(partition) == value:
            return False
        self._holdouts[partition] = copy.deepcopy(value)
        self._state_changed()
        return True

    def _state_changed(self) -> None:
        self._refresh_models()
        self.validity_changed.emit()
        self.field_choices_changed.emit()
        self.changed.emit()

    def _refresh_models(self) -> None:
        self.partition_rows.replace(
            {"partition": partition, "ratio": ratio}
            for partition, ratio in self._partitions.items()
        )
        self.holdout_rows.replace(
            {
                "partition": partition,
                "summary": _holdout_summary(value),
                "kind": self._kind,
            }
            for partition, value in self._holdouts.items()
        )
        self.strata_rows.replace({"field": field} for field in self._strata_categorical)
        self.numeric_bin_rows.replace(
            {
                "field": field,
                "boundaries": list(boundaries),
                "summary": ", ".join(_number_text(item) for item in boundaries),
            }
            for field, boundaries in self._numeric_bins.items()
        )
        self.transformation_rows.replace(
            {
                "field": str(item.get("field", "")),
                "methods": list(item.get("methods", [])),
                "summary": f"{item.get('field', '')} · {' → '.join(item.get('methods', []))}",
            }
            for item in self._transformations
        )


def _mapping(value: object) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value)


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item)))


def _finite_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return 0.0 if number == 0.0 else number


def _transformations_valid(values: list[dict[str, Any]]) -> bool:
    outputs = [
        f"{item['field']}__{'__'.join(str(method) for method in item['methods'])}"
        for item in values
    ]
    return len(outputs) == len(set(outputs))


def _holdout_summary(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        if set(value) == {"min", "max"}:
            return f"{_number_text(value['min'])} … {_number_text(value['max'])}"
        return "; ".join(f"{field}: {_holdout_summary(bounds)}" for field, bounds in value.items())
    return str(value)


def _number_text(value: object) -> str:
    return format(float(value), ".12g") if isinstance(value, int | float) else str(value)
