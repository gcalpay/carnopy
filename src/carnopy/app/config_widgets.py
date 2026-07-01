from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QWidget,
)

SAMPLER_FIELDS: dict[str, tuple[str, ...]] = {
    "explicit": ("values",),
    "linspace": ("start", "stop", "num"),
    "stepspace": ("start", "stop", "step"),
    "geomspace": ("start", "stop", "num"),
    "logspace": ("start_exp", "stop_exp", "num", "base"),
}


class SamplerEditor(QGroupBox):
    changed = Signal()

    def __init__(self, axis: str, parent: QWidget | None = None) -> None:
        super().__init__(axis.replace("_", " ").title(), parent)
        self.axis = axis
        self._loading = False
        self.form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItems(list(SAMPLER_FIELDS))
        self.kind.setAccessibleName(f"{axis} sampler kind")
        self.unit = QComboBox()
        self.unit.setAccessibleName(f"{axis} unit")
        self.values = QLineEdit()
        self.values.setPlaceholderText("Comma-separated values")
        self.values.setAccessibleName(f"{axis} explicit values")
        self.start = _numeric_line(axis, "start")
        self.stop = _numeric_line(axis, "stop")
        self.step = _numeric_line(axis, "step")
        self.start_exp = _numeric_line(axis, "start exponent")
        self.stop_exp = _numeric_line(axis, "stop exponent")
        self.base = _numeric_line(axis, "base")
        self.num = QSpinBox()
        self.num.setRange(2, 1_000_000)
        self.num.setAccessibleName(f"{axis} number of samples")

        self.form.addRow("Sampler", self.kind)
        self.form.addRow("Values", self.values)
        self.form.addRow("Start", self.start)
        self.form.addRow("Stop", self.stop)
        self.form.addRow("Step", self.step)
        self.form.addRow("Start exponent", self.start_exp)
        self.form.addRow("Stop exponent", self.stop_exp)
        self.form.addRow("Number", self.num)
        self.form.addRow("Base", self.base)
        self.form.addRow("Unit", self.unit)

        self.kind.currentTextChanged.connect(self._kind_changed)
        self.unit.currentTextChanged.connect(self._emit_changed)
        self.values.textChanged.connect(self._emit_changed)
        for widget in (
            self.start,
            self.stop,
            self.step,
            self.start_exp,
            self.stop_exp,
            self.base,
        ):
            widget.textChanged.connect(self._emit_changed)
        self.num.valueChanged.connect(self._emit_changed)
        self._kind_changed(self.kind.currentText())

    def configure_units(self, units: list[str]) -> None:
        selected = self.unit.currentText()
        self.unit.blockSignals(True)
        self.unit.clear()
        self.unit.addItems(units)
        if selected in units:
            self.unit.setCurrentText(selected)
        self.unit.blockSignals(False)

    def load_sampler(self, sampler: dict[str, Any]) -> None:
        self._loading = True
        kind = str(sampler.get("kind", "explicit"))
        self.kind.setCurrentText(kind)
        self.unit.setCurrentText(str(sampler.get("unit", "")))
        values = sampler.get("values", [])
        self.values.setText(", ".join(_number_text(value) for value in values))
        for name in ("start", "stop", "step", "start_exp", "stop_exp", "base"):
            value = sampler.get(name)
            getattr(self, name).setText("" if value is None else _number_text(value))
        self.num.setValue(int(sampler.get("num", 2)))
        self._loading = False
        self._kind_changed(kind)

    def sampler_payload(self) -> dict[str, Any]:
        kind = self.kind.currentText()
        payload: dict[str, Any] = {"kind": kind}
        if kind == "explicit":
            parts = [part.strip() for part in self.values.text().split(",")]
            if not parts or any(not part for part in parts):
                raise ValueError(f"{self.axis} explicit sampler requires comma-separated values")
            payload["values"] = [_finite_float(part, self.axis, "value") for part in parts]
        else:
            for name in SAMPLER_FIELDS[kind]:
                if name == "num":
                    payload[name] = self.num.value()
                else:
                    payload[name] = _finite_float(
                        getattr(self, name).text(),
                        self.axis,
                        name.replace("_", " "),
                    )
        unit = self.unit.currentText()
        if not unit:
            raise ValueError(f"{self.axis} requires a unit")
        payload["unit"] = unit
        return payload

    def _kind_changed(self, kind: str) -> None:
        visible = set(SAMPLER_FIELDS[kind])
        for name in (
            "values",
            "start",
            "stop",
            "step",
            "start_exp",
            "stop_exp",
            "num",
            "base",
        ):
            widget = getattr(self, name)
            widget.setVisible(name in visible)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(name in visible)
        self._emit_changed()

    def _emit_changed(self, *_args: object) -> None:
        if not self._loading:
            self.changed.emit()


def _numeric_line(axis: str, label: str) -> QLineEdit:
    widget = QLineEdit()
    widget.setAccessibleName(f"{axis} {label}")
    return widget


def _finite_float(text: str, axis: str, field: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{axis} {field} requires a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{axis} {field} must be finite")
    return value


def _number_text(value: object) -> str:
    return format(float(str(value)), ".15g")
