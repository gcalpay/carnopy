from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class ChoiceMappingTable(QWidget):
    changed = Signal()

    def __init__(
        self,
        key_label: str,
        value_label: str,
        *,
        multiple: bool = False,
        numeric_values: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.multiple = multiple
        self.numeric_values = numeric_values
        self.field_choices: list[str] = []
        self.field_kinds: dict[str, str] = {}
        self.value_choices: dict[str, list[str]] = {}
        self._loading = False
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([key_label, value_label])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(130)
        self.add_button = QPushButton("Add Row")
        remove = QPushButton("Remove Row")
        self.add_button.clicked.connect(lambda: self.add_row())
        remove.clicked.connect(self.remove_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.add_button.setEnabled(False)

    def configure(
        self,
        fields: list[str],
        *,
        field_kinds: Mapping[str, str] | None = None,
        value_choices: Mapping[str, list[str]] | None = None,
    ) -> None:
        rows = self._raw_rows()
        self.field_choices = list(fields)
        self.field_kinds = dict(field_kinds or {})
        self.value_choices = {
            field: list(values) for field, values in (value_choices or {}).items()
        }
        self.add_button.setEnabled(bool(self.field_choices))
        self._load_rows(rows)

    def add_row(self, key: str = "", value: str = "") -> None:
        if not self.field_choices:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        field = QComboBox()
        field.addItems(self.field_choices)
        if key and key not in self.field_choices:
            field.addItem(f"Unsupported: {key}", key)
        if key:
            index = field.findData(key)
            field.setCurrentIndex(index if index >= 0 else field.findText(key))
        field.currentTextChanged.connect(lambda _text, combo=field: self._field_changed(combo))
        self.table.setCellWidget(row, 0, field)
        self._set_value_widget(row, self._field_value(field), value)
        self._emit_changed()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self.changed.emit()

    def load_mapping(self, value: Mapping[str, object], *, multiple: bool | None = None) -> None:
        use_multiple = self.multiple if multiple is None else multiple
        rows = []
        for key, item in value.items():
            if use_multiple and isinstance(item, (list, tuple)):
                rendered = ", ".join(_scalar_text(entry) for entry in item)
            else:
                rendered = _scalar_text(item)
            rows.append((str(key), rendered))
        self._load_rows(rows)

    def mapping(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, raw in self._raw_rows():
            if not key and not raw:
                continue
            if not key or not raw:
                raise ValueError("mapping rows require both a field and a value")
            if key in result:
                raise ValueError(f"mapping contains duplicate field {key!r}")
            kind = self.field_kinds.get(key)
            if self.multiple:
                parts = [part.strip() for part in raw.split(",")]
                if any(not part for part in parts):
                    raise ValueError(f"series field {key!r} contains an empty value")
                result[key] = [self._parse_value(part, kind=kind) for part in parts]
            else:
                result[key] = self._parse_value(raw, kind=kind)
        return result

    def _parse_value(self, value: str, *, kind: str | None) -> float | str:
        if not self.numeric_values or kind == "categorical":
            return value
        try:
            return float(value)
        except ValueError:
            if self.multiple:
                return value
            raise ValueError(f"numeric field requires a number; received {value!r}") from None

    def _load_rows(self, rows: list[tuple[str, str]]) -> None:
        self._loading = True
        self.table.setRowCount(0)
        for key, value in rows:
            self.add_row(key, value)
        self._loading = False

    def _raw_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for row in range(self.table.rowCount()):
            field = self.table.cellWidget(row, 0)
            value = self.table.cellWidget(row, 1)
            key = self._field_value(field) if isinstance(field, QComboBox) else ""
            if isinstance(value, QComboBox):
                raw = str(value.currentData() or value.currentText()).strip()
            elif isinstance(value, QLineEdit):
                raw = value.text().strip()
            else:
                raw = ""
            rows.append((key, raw))
        return rows

    def _field_changed(self, combo: QComboBox) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0) is combo:
                self._set_value_widget(row, self._field_value(combo), "")
                self._emit_changed()
                return

    def _set_value_widget(self, row: int, field: str, value: str) -> None:
        choices = self.value_choices.get(field, [])
        if choices:
            combo_editor = QComboBox()
            combo_editor.addItems(choices)
            if value and value not in choices:
                combo_editor.addItem(f"Unsupported: {value}", value)
            if value:
                index = combo_editor.findData(value)
                combo_editor.setCurrentIndex(index if index >= 0 else combo_editor.findText(value))
            combo_editor.currentTextChanged.connect(lambda _text: self._emit_changed())
            editor: QWidget = combo_editor
        else:
            line_editor = QLineEdit(value)
            if self.multiple:
                line_editor.setPlaceholderText("Comma-separated exact values, e.g. 1bar, 3bar")
            elif self.field_kinds.get(field) == "numeric":
                validator = QDoubleValidator(line_editor)
                validator.setLocale(QLocale.c())
                validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
                line_editor.setValidator(validator)
                line_editor.setPlaceholderText("Canonical SI numeric value")
            line_editor.textChanged.connect(lambda _text: self._emit_changed())
            editor = line_editor
        self.table.setCellWidget(row, 1, editor)

    def _emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    @staticmethod
    def _field_value(widget: QWidget) -> str:
        if not isinstance(widget, QComboBox):
            return ""
        value = widget.currentData()
        return str(value) if isinstance(value, str) else widget.currentText()


class FluidChoiceList(QListWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(100)
        self.itemChanged.connect(lambda _item: self.changed.emit())

    def set_choices(self, choices: list[str], selected: list[str] | None = None) -> None:
        selected_values = set(selected if selected is not None else self.selected_values())
        self.blockSignals(True)
        self.clear()
        for value in choices:
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if value in selected_values else Qt.CheckState.Unchecked
            )
            self.addItem(item)
        self.blockSignals(False)

    def selected_values(self) -> list[str]:
        return [
            item.text()
            for index in range(self.count())
            if (item := self.item(index)) is not None and item.checkState() == Qt.CheckState.Checked
        ]


def _scalar_text(value: object) -> str:
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)
