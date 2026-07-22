from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.field_ids import dataset_grid_field
from carnopy.domain.numbers import stable_number_text
from carnopy.domain.units import validate_axis_unit
from carnopy.sampling.canonical import (
    CanonicalSamplerKey,
    canonical_sampler_key,
    canonicalize_sampler,
    convert_sampler_unit,
)
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)
from carnopy.sampling.projection import sampler_point_count

SAMPLER_FIELDS: dict[str, tuple[str, ...]] = {
    "explicit": ("values",),
    "linspace": ("start", "stop", "num"),
    "stepspace": ("start", "stop", "step"),
    "geomspace": ("start", "stop", "num"),
    "logspace": ("start_exp", "stop_exp", "num", "base"),
}
SAMPLER_TEXT_FIELDS = (
    "values",
    "start",
    "stop",
    "step",
    "start_exp",
    "stop_exp",
    "num",
    "base",
)
MAX_SAMPLE_COUNT = 1_000_000


class SamplerDraft(QObject):
    """Keep one sampler's raw editable state outside the presentation layer."""

    changed = Signal()
    kind_changed = Signal(name="kindChanged")
    unit_changed = Signal(name="unitChanged")
    fields_changed = Signal(name="fieldsChanged")
    available_units_changed = Signal(name="availableUnitsChanged")
    validity_changed = Signal(name="validityChanged")
    sample_count_changed = Signal(name="sampleCountChanged")
    unitChangeRejected = Signal(str, str)

    def __init__(self, axis: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._axis = axis
        self._kind = "explicit"
        self._unit = ""
        self._available_units: tuple[str, ...] = ()
        self._texts = {name: "" for name in SAMPLER_TEXT_FIELDS}
        self._texts["num"] = "2"
        self._valid = False
        self._issue = ""
        self._first_invalid_field = ""
        self._sample_count = 0
        self._anchor_sampler: Sampler | None = None
        self._anchor_key: CanonicalSamplerKey | None = None
        self._refresh_validity()

    def get_axis(self) -> str:
        return self._axis

    axis = Property(str, get_axis, constant=True)

    def get_kind(self) -> str:
        return self._kind

    def set_kind(self, value: str) -> None:
        if value not in SAMPLER_FIELDS or value == self._kind:
            return
        self._kind = value
        self.kind_changed.emit()
        self.fields_changed.emit()
        self._changed(update_anchor=True)

    kind = Property(str, get_kind, set_kind, notify=kind_changed)

    def get_unit(self) -> str:
        return self._unit

    unit = Property(str, get_unit, notify=unit_changed)

    def get_available_units(self) -> list[str]:
        return list(self._available_units)

    availableUnits = Property(
        list,
        get_available_units,
        notify=available_units_changed,
    )

    def get_active_fields(self) -> list[str]:
        return list(SAMPLER_FIELDS[self._kind])

    activeFields = Property(list, get_active_fields, notify=fields_changed)

    def get_available_kinds(self) -> list[str]:
        return list(SAMPLER_FIELDS)

    availableKinds = Property(list, get_available_kinds, constant=True)

    def get_valid(self) -> bool:
        return self._valid

    valid = Property(bool, get_valid, notify=validity_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=validity_changed)

    def get_first_invalid_field(self) -> str:
        return self._first_invalid_field

    firstInvalidField = Property(
        str,
        get_first_invalid_field,
        notify=validity_changed,
    )

    def get_sample_count(self) -> int:
        return self._sample_count

    sampleCount = Property(
        "qlonglong",  # type: ignore[arg-type]
        get_sample_count,
        notify=sample_count_changed,
    )

    @Slot(str, result=str)
    def text(self, field: str) -> str:
        return self._texts.get(field, "")

    @Slot(str, str, name="setText")
    def set_text(self, field: str, value: str) -> None:
        if field not in self._texts or self._texts[field] == value:
            return
        self._texts[field] = value
        self.fields_changed.emit()
        self._changed(update_anchor=True)

    def set_available_units(self, values: Sequence[str]) -> None:
        units = tuple(dict.fromkeys(str(value) for value in values if str(value)))
        if units == self._available_units:
            return
        self._available_units = units
        self.available_units_changed.emit()
        self._refresh_validity()

    def load_payload(
        self,
        payload: Mapping[str, object],
        *,
        available_units: Sequence[str],
    ) -> None:
        before = self.raw_state()
        previous_validity = (self._valid, self._issue, self._first_invalid_field)
        previous_sample_count = self._sample_count
        self.clear_anchor()
        self._available_units = tuple(
            dict.fromkeys(str(value) for value in available_units if str(value))
        )
        kind = str(payload.get("kind", "explicit"))
        self._kind = kind if kind in SAMPLER_FIELDS else "explicit"
        self._unit = str(payload.get("unit", ""))
        texts = {name: "" for name in SAMPLER_TEXT_FIELDS}
        texts["num"] = "2"
        values = payload.get("values", [])
        if isinstance(values, list):
            texts["values"] = ", ".join(_number_text(value) for value in values)
        for name in ("start", "stop", "step", "start_exp", "stop_exp", "base"):
            value = payload.get(name)
            texts[name] = "" if value is None else _number_text(value)
        if payload.get("num") is not None:
            texts["num"] = str(payload["num"])
        self._texts = texts
        self._refresh_validity(emit=False)
        self._establish_anchor_if_valid()
        if before != self.raw_state():
            self.kind_changed.emit()
            self.unit_changed.emit()
            self.fields_changed.emit()
            self.available_units_changed.emit()
            self.changed.emit()
        if previous_validity != (self._valid, self._issue, self._first_invalid_field):
            self.validity_changed.emit()
        if previous_sample_count != self._sample_count:
            self.sample_count_changed.emit()

    def payload(self) -> dict[str, Any]:
        issue = self._validation_issue()
        if issue:
            raise ValueError(issue)
        return self._payload_without_validation()

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._axis,
            self._kind,
            self._unit,
            tuple((name, self._texts[name]) for name in SAMPLER_FIELDS[self._kind]),
        )

    @Slot(str, result=bool)
    def requestUnitChange(self, target_unit: str) -> bool:
        """Atomically express the anchored sampler in another compatible unit."""

        target = target_unit.strip()
        if target == self._unit:
            return True
        field, issue, _sample_count = self._validation_result()
        if issue:
            self.unitChangeRejected.emit(
                self._field_id(field),
                "Complete the current sampler before changing its unit.",
            )
            return False
        if target not in self._available_units:
            self.unitChangeRejected.emit(
                self._field_id("unit"),
                f"Unit {target!r} is not available for {self._axis}.",
            )
            return False
        try:
            validate_axis_unit(self._axis, target)
        except ValueError as exc:
            self.unitChangeRejected.emit(self._field_id("unit"), str(exc))
            return False
        anchor = self._anchor_sampler
        anchor_key = self._anchor_key
        if anchor is None or anchor_key is None:
            self.unitChangeRejected.emit(
                self._field_id("unit"),
                "This sampler has no valid conversion anchor.",
            )
            return False
        try:
            candidate = convert_sampler_unit(self._axis, anchor, target)
            candidate_key = canonical_sampler_key(self._axis, candidate)
        except (TypeError, ValueError, ValidationError) as exc:
            self.unitChangeRejected.emit(self._field_id("unit"), str(exc))
            return False
        if candidate_key != anchor_key:
            self.unitChangeRejected.emit(
                self._field_id("unit"),
                "The target unit cannot exactly preserve this sampler's canonical identity.",
            )
            return False
        candidate = _compact_exact_representation(self._axis, candidate, anchor_key)

        before_validity = (self._valid, self._issue, self._first_invalid_field)
        self._unit = target
        self._apply_sampler_text(candidate)
        self._refresh_validity(emit=False)
        self.unit_changed.emit()
        self.fields_changed.emit()
        if before_validity != (self._valid, self._issue, self._first_invalid_field):
            self.validity_changed.emit()
        self.changed.emit()
        return True

    def clear_anchor(self) -> None:
        self._anchor_sampler = None
        self._anchor_key = None

    def _changed(self, *, update_anchor: bool) -> None:
        self._refresh_validity()
        if update_anchor:
            self._establish_anchor_if_valid()
        self.changed.emit()

    def _refresh_validity(self, *, emit: bool = True) -> None:
        field, issue, sample_count = self._validation_result()
        valid = not issue
        first_invalid_field = self._field_id(field) if issue else ""
        changed = (valid, issue, first_invalid_field) != (
            self._valid,
            self._issue,
            self._first_invalid_field,
        )
        sample_count_changed = sample_count != self._sample_count
        self._valid = valid
        self._issue = issue
        self._first_invalid_field = first_invalid_field
        self._sample_count = sample_count
        if emit and changed:
            self.validity_changed.emit()
        if emit and sample_count_changed:
            self.sample_count_changed.emit()

    def _validation_issue(self) -> str:
        return self._validation_result()[1]

    def _validation_result(self) -> tuple[str, str, int]:
        if self._kind not in SAMPLER_FIELDS:
            return "kind", f"{self._axis} uses an unsupported sampler kind", 0
        if not self._unit:
            return "unit", f"{self._axis} requires a unit", 0
        if self._available_units and self._unit not in self._available_units:
            return "unit", f"{self._axis} unit {self._unit!r} is not available", 0
        try:
            if self._kind == "explicit":
                parts = [part.strip() for part in self._texts["values"].split(",")]
                if not parts or any(not part for part in parts):
                    return (
                        "values",
                        f"{self._axis} explicit sampler requires comma-separated values",
                        0,
                    )
                for part in parts:
                    _finite_float(part, self._axis, "value")
            else:
                for name in SAMPLER_FIELDS[self._kind]:
                    if name == "num":
                        _sample_count(self._texts[name], self._axis)
                    else:
                        _finite_float(
                            self._texts[name],
                            self._axis,
                            name.replace("_", " "),
                        )
        except ValueError as exc:
            field = "values" if self._kind == "explicit" else name
            return field, str(exc), 0
        try:
            sampler = self._sampler_model()
            canonical = canonicalize_sampler(self._axis, sampler)
            count = sampler_point_count(canonical)
        except ValidationError as exc:
            error = exc.errors(include_url=False)[0]
            location = error.get("loc", ())
            field = str(location[-1]) if location else SAMPLER_FIELDS[self._kind][0]
            return field, str(error.get("msg", "invalid sampler")), 0
        except (TypeError, ValueError) as exc:
            field = "step" if self._kind == "stepspace" else SAMPLER_FIELDS[self._kind][0]
            return field, str(exc), 0
        return "", "", count

    def _sampler_model(self) -> Sampler:
        payload = self._payload_without_validation()
        kind = self._kind
        if kind == "explicit":
            return ExplicitSampler.model_validate(payload)
        if kind == "linspace":
            return LinspaceSampler.model_validate(payload)
        if kind == "stepspace":
            return StepspaceSampler.model_validate(payload)
        if kind == "geomspace":
            return GeomspaceSampler.model_validate(payload)
        if kind == "logspace":
            return LogspaceSampler.model_validate(payload)
        raise ValueError(f"unsupported sampler kind: {kind}")

    def _payload_without_validation(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self._kind}
        if self._kind == "explicit":
            parts = [part.strip() for part in self._texts["values"].split(",")]
            payload["values"] = [_finite_float(part, self._axis, "value") for part in parts]
        else:
            for name in SAMPLER_FIELDS[self._kind]:
                if name == "num":
                    payload[name] = _sample_count(self._texts[name], self._axis)
                else:
                    payload[name] = _finite_float(
                        self._texts[name], self._axis, name.replace("_", " ")
                    )
        payload["unit"] = self._unit
        return payload

    def _establish_anchor_if_valid(self) -> None:
        if not self._valid:
            return
        sampler = self._sampler_model()
        self._anchor_sampler = sampler.model_copy(deep=True)
        self._anchor_key = canonical_sampler_key(self._axis, sampler)

    def _apply_sampler_text(self, sampler: Sampler) -> None:
        payload = sampler.model_dump(mode="python")
        if isinstance(sampler, ExplicitSampler):
            self._texts["values"] = ", ".join(stable_number_text(value) for value in sampler.values)
            return
        for name in SAMPLER_FIELDS[sampler.kind]:
            value = payload[name]
            self._texts[name] = str(value) if name == "num" else stable_number_text(float(value))

    def _field_id(self, field: str) -> str:
        return dataset_grid_field(self._axis, field)


def _finite_float(text: str, axis: str, field: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{axis} {field} requires a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{axis} {field} must be finite")
    return value


def _compact_exact_representation(
    axis: str,
    sampler: Sampler,
    anchor_key: CanonicalSamplerKey,
) -> Sampler:
    """Choose shorter decimal fields only when exact identity still holds."""

    compacted = sampler
    if isinstance(compacted, ExplicitSampler):
        values = list(compacted.values)
        for index, value in enumerate(values):
            for candidate_value in _shorter_binary64_candidates(value):
                candidate_values = [*values]
                candidate_values[index] = candidate_value
                explicit_candidate = compacted.model_copy(update={"values": candidate_values})
                if _has_canonical_key(axis, explicit_candidate, anchor_key):
                    compacted = explicit_candidate
                    values = candidate_values
                    break
        return compacted

    payload = compacted.model_dump(mode="python")
    for name in SAMPLER_FIELDS[compacted.kind]:
        if name == "num":
            continue
        value = float(payload[name])
        for candidate_value in _shorter_binary64_candidates(value):
            compact_candidate = compacted.model_copy(update={name: candidate_value})
            if _has_canonical_key(axis, compact_candidate, anchor_key):
                compacted = compact_candidate
                payload[name] = candidate_value
                break
    return compacted


def _shorter_binary64_candidates(value: float) -> tuple[float, ...]:
    stable = stable_number_text(value)
    candidates: list[float] = []
    for significant_digits in range(1, 15):
        candidate = float(format(value, f".{significant_digits}g"))
        if stable_number_text(candidate) == stable:
            break
        if candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def _has_canonical_key(
    axis: str,
    sampler: Sampler,
    anchor_key: CanonicalSamplerKey,
) -> bool:
    try:
        return canonical_sampler_key(axis, sampler) == anchor_key
    except (TypeError, ValueError, ValidationError):
        return False


def _sample_count(text: str, axis: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f"{axis} number of samples requires an integer") from exc
    if str(value) != text.strip() and not (
        text.strip().startswith("+") and str(value) == text.strip()[1:]
    ):
        raise ValueError(f"{axis} number of samples requires an integer")
    if not 2 <= value <= MAX_SAMPLE_COUNT:
        raise ValueError(f"{axis} number of samples must be between 2 and {MAX_SAMPLE_COUNT}")
    return value


def _number_text(value: object) -> str:
    return stable_number_text(float(str(value)))
