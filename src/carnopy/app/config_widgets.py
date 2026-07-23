from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from carnopy.app.sampler_draft import SAMPLER_FIELDS, SamplerDraft


class SamplerEditor(QGroupBox):
    """Present one controller-owned sampler draft."""

    def __init__(self, draft: SamplerDraft, parent: QWidget | None = None) -> None:
        super().__init__(draft.get_axis().replace("_", " ").title(), parent)
        self.draft = draft
        axis = draft.get_axis()
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

        self.kind.currentTextChanged.connect(draft.set_kind)
        self.unit.currentTextChanged.connect(self._unit_requested)
        self.values.textChanged.connect(lambda value: draft.set_text("values", value))
        for field in ("start", "stop", "step", "start_exp", "stop_exp", "base"):
            widget = getattr(self, field)
            widget.textChanged.connect(lambda value, name=field: draft.set_text(name, value))
        self.num.valueChanged.connect(lambda value: draft.set_text("num", str(value)))
        draft.changed.connect(self.sync_from_draft)
        draft.available_units_changed.connect(self.sync_from_draft)
        draft.unitChangeRejected.connect(self._unit_change_rejected)
        self.sync_from_draft()

    def sampler_payload(self) -> dict[str, object]:
        return self.draft.payload()

    def _unit_requested(self, value: str) -> None:
        if value and not self.draft.requestUnitChange(value):
            self.sync_from_draft()

    def _unit_change_rejected(self, _field: str, message: str) -> None:
        self.unit.setToolTip(message)
        self.unit.setAccessibleDescription(message)
        self.unit.setFocus()

    def sync_from_draft(self) -> None:
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.kind,
                self.unit,
                self.values,
                self.start,
                self.stop,
                self.step,
                self.start_exp,
                self.stop_exp,
                self.base,
                self.num,
            )
        ]
        self.kind.setCurrentText(self.draft.get_kind())
        selected_unit = self.draft.get_unit()
        self.unit.clear()
        self.unit.addItems(self.draft.get_available_units())
        self.unit.setCurrentText(selected_unit)
        self.values.setText(self.draft.text("values"))
        for name in ("start", "stop", "step", "start_exp", "stop_exp", "base"):
            getattr(self, name).setText(self.draft.text(name))
        try:
            count = int(self.draft.text("num"))
        except ValueError:
            count = 2
        self.num.setValue(max(2, min(1_000_000, count)))
        visible = set(SAMPLER_FIELDS[self.draft.get_kind()])
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
        del blockers


def _numeric_line(axis: str, label: str) -> QLineEdit:
    widget = QLineEdit()
    widget.setAccessibleName(f"{axis} {label}")
    return widget
