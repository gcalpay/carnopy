from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

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
    kind_changed = Signal()
    unit_changed = Signal()
    fields_changed = Signal()
    available_units_changed = Signal()
    validity_changed = Signal()

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
        self._changed()

    kind = Property(str, get_kind, set_kind, notify=kind_changed)

    def get_unit(self) -> str:
        return self._unit

    def set_unit(self, value: str) -> None:
        if value == self._unit:
            return
        self._unit = value
        self.unit_changed.emit()
        self._changed()

    unit = Property(str, get_unit, set_unit, notify=unit_changed)

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

    def get_valid(self) -> bool:
        return self._valid

    valid = Property(bool, get_valid, notify=validity_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=validity_changed)

    @Slot(str, result=str)
    def text(self, field: str) -> str:
        return self._texts.get(field, "")

    @Slot(str, str)
    def set_text(self, field: str, value: str) -> None:
        if field not in self._texts or self._texts[field] == value:
            return
        self._texts[field] = value
        self.fields_changed.emit()
        self._changed()

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
        previous_validity = (self._valid, self._issue)
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
        if before != self.raw_state():
            self.kind_changed.emit()
            self.unit_changed.emit()
            self.fields_changed.emit()
            self.available_units_changed.emit()
            self.changed.emit()
        if previous_validity != (self._valid, self._issue):
            self.validity_changed.emit()

    def payload(self) -> dict[str, Any]:
        issue = self._validation_issue()
        if issue:
            raise ValueError(issue)
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
                        self._texts[name],
                        self._axis,
                        name.replace("_", " "),
                    )
        payload["unit"] = self._unit
        return payload

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._axis,
            self._kind,
            self._unit,
            tuple((name, self._texts[name]) for name in SAMPLER_FIELDS[self._kind]),
        )

    def _changed(self) -> None:
        self._refresh_validity()
        self.changed.emit()

    def _refresh_validity(self, *, emit: bool = True) -> None:
        issue = self._validation_issue()
        valid = not issue
        changed = (valid, issue) != (self._valid, self._issue)
        self._valid = valid
        self._issue = issue
        if emit and changed:
            self.validity_changed.emit()

    def _validation_issue(self) -> str:
        if self._kind not in SAMPLER_FIELDS:
            return f"{self._axis} uses an unsupported sampler kind"
        if not self._unit:
            return f"{self._axis} requires a unit"
        if self._available_units and self._unit not in self._available_units:
            return f"{self._axis} unit {self._unit!r} is not available"
        try:
            if self._kind == "explicit":
                parts = [part.strip() for part in self._texts["values"].split(",")]
                if not parts or any(not part for part in parts):
                    return f"{self._axis} explicit sampler requires comma-separated values"
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
            return str(exc)
        return ""


def _finite_float(text: str, axis: str, field: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{axis} {field} requires a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{axis} {field} must be finite")
    return value


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
    return format(float(str(value)), ".15g")
