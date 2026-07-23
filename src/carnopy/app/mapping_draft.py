from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from carnopy.visualization.requests import normalize_series_selections

DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole)
FIELD_ROLE = int(Qt.ItemDataRole.UserRole) + 30
RAW_VALUE_ROLE = FIELD_ROLE + 1
CANONICAL_ROLE = FIELD_ROLE + 2
KIND_ROLE = FIELD_ROLE + 3
COMPATIBLE_ROLE = FIELD_ROLE + 4
ISSUE_ROLE = FIELD_ROLE + 5
CHOICES_ROLE = FIELD_ROLE + 6
HINT_ROLE = FIELD_ROLE + 7
INVALID_INDEX = QModelIndex()


@dataclass(frozen=True)
class MappingDraftRow:
    field: str
    raw_value: str


class MappingDraftModel(QAbstractListModel):
    """Store raw field/value rows independently from a concrete desktop view."""

    changed = Signal()
    validity_changed = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        multiple: bool = False,
        numeric_values: bool = True,
        allow_text_numeric: bool = False,
        mutation_guard: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.multiple = multiple
        self.numeric_values = numeric_values
        self.allow_text_numeric = allow_text_numeric
        self._mutation_guard = mutation_guard
        self._rows: tuple[MappingDraftRow, ...] = ()
        self._fields: tuple[str, ...] = ()
        self._field_kinds: dict[str, str] = {}
        self._value_choices: dict[str, tuple[tuple[str, str], ...]] = {}
        self._value_hints: dict[str, str] = {}

    @property
    def field_choices(self) -> tuple[str, ...]:
        return self._fields

    def get_field_choices(self) -> list[str]:
        return list(self._fields)

    fieldChoices = Property(list, get_field_choices, notify=changed)

    @property
    def field_kinds(self) -> dict[str, str]:
        return dict(self._field_kinds)

    @property
    def value_choices(self) -> dict[str, list[tuple[str, str]]]:
        return {field: list(values) for field, values in self._value_choices.items()}

    @property
    def value_hints(self) -> dict[str, str]:
        return dict(self._value_hints)

    def configure(
        self,
        fields: Iterable[str],
        *,
        field_kinds: Mapping[str, str] | None = None,
        value_choices: Mapping[str, Iterable[str | tuple[str, str]]] | None = None,
        value_hints: Mapping[str, str] | None = None,
        allow_text_numeric: bool | None = None,
    ) -> None:
        updated_fields = tuple(str(field) for field in fields)
        updated_kinds = {str(key): str(value) for key, value in (field_kinds or {}).items()}
        updated_choices = {
            str(field): tuple(
                (str(value), str(value))
                if isinstance(value, str)
                else (str(value[0]), str(value[1]))
                for value in values
            )
            for field, values in (value_choices or {}).items()
        }
        updated_hints = {str(key): str(value) for key, value in (value_hints or {}).items()}
        updated_allow_text = (
            self.allow_text_numeric if allow_text_numeric is None else bool(allow_text_numeric)
        )
        before = self._validation_state()
        if (
            updated_fields == self._fields
            and updated_kinds == self._field_kinds
            and updated_choices == self._value_choices
            and updated_hints == self._value_hints
            and updated_allow_text == self.allow_text_numeric
        ):
            return
        self.beginResetModel()
        self._fields = updated_fields
        self._field_kinds = updated_kinds
        self._value_choices = updated_choices
        self._value_hints = updated_hints
        self.allow_text_numeric = updated_allow_text
        self.endResetModel()
        self._emit_validity_if_changed(before)
        self.changed.emit()

    def raw_rows(self) -> tuple[tuple[str, str], ...]:
        return tuple((row.field, row.raw_value) for row in self._rows)

    def replace_raw_rows(self, rows: Iterable[tuple[str, str]]) -> bool:
        updated = tuple(MappingDraftRow(str(field), str(value)) for field, value in rows)
        if updated == self._rows:
            return False
        if not self._mutation_allowed():
            return False
        return self._replace_raw_rows(updated)

    def _replace_raw_rows(self, updated: tuple[MappingDraftRow, ...]) -> bool:
        before = self._validation_state()
        self.beginResetModel()
        self._rows = updated
        self.endResetModel()
        self._emit_validity_if_changed(before)
        self.changed.emit()
        return True

    def load_mapping(self, value: Mapping[str, object]) -> None:
        rows: list[tuple[str, str]] = []
        for field, item in value.items():
            if self.multiple and isinstance(item, (list, tuple)):
                raw = ", ".join(_scalar_text(entry) for entry in item)
            else:
                raw = _scalar_text(item)
            rows.append((str(field), raw))
        updated = tuple(MappingDraftRow(field, raw) for field, raw in rows)
        if updated != self._rows:
            self._replace_raw_rows(updated)

    @Slot(str, str, result=int)
    def add_row(self, field: str = "", raw_value: str = "") -> int:
        if not self._mutation_allowed():
            return -1
        selected = field or (self._fields[0] if self._fields else "")
        row = len(self._rows)
        before = self._validation_state()
        self.beginInsertRows(INVALID_INDEX, row, row)
        self._rows = (*self._rows, MappingDraftRow(selected, raw_value))
        self.endInsertRows()
        self._emit_validity_if_changed(before)
        self.changed.emit()
        return row

    @Slot(int, result=bool)
    def remove_row(self, row: int) -> bool:
        if not 0 <= row < len(self._rows):
            return False
        if not self._mutation_allowed():
            return False
        before = self._validation_state()
        self.beginRemoveRows(INVALID_INDEX, row, row)
        self._rows = (*self._rows[:row], *self._rows[row + 1 :])
        self.endRemoveRows()
        self._emit_validity_if_changed(before)
        self.changed.emit()
        return True

    @Slot(int, str, result=bool)
    def set_field(self, row: int, field: str) -> bool:
        if not 0 <= row < len(self._rows) or self._rows[row].field == field:
            return False
        if not self._mutation_allowed():
            return False
        return self._replace_row(row, MappingDraftRow(field, ""))

    @Slot(int, str, result=bool)
    def set_raw_value(self, row: int, raw_value: str) -> bool:
        if not 0 <= row < len(self._rows) or self._rows[row].raw_value == raw_value:
            return False
        if not self._mutation_allowed():
            return False
        return self._replace_row(row, MappingDraftRow(self._rows[row].field, raw_value))

    def _replace_row(self, row: int, value: MappingDraftRow) -> bool:
        before = self._validation_state()
        updated = list(self._rows)
        updated[row] = value
        self._rows = tuple(updated)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames()))
        self._emit_validity_if_changed(before)
        self.changed.emit()
        return True

    def mapping(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for row_index, row in enumerate(self._rows):
            issue = self._row_issue(row_index)
            if issue:
                raise ValueError(issue)
            result[row.field] = self._parse_row(row)
        return result

    def get_valid(self) -> bool:
        return not self.get_issue()

    valid = Property(bool, get_valid, notify=validity_changed)

    def get_issue(self) -> str:
        for row in range(len(self._rows)):
            if issue := self._row_issue(row):
                return issue
        return ""

    issue = Property(str, get_issue, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        return next(
            (row for row in range(len(self._rows)) if self._row_issue(row)),
            -1,
        )

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = DISPLAY_ROLE,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        issue = self._row_issue(index.row())
        canonical: object = None
        if not issue:
            canonical = self._parse_row(row)
        values: dict[int, object] = {
            DISPLAY_ROLE: f"{row.field} = {row.raw_value}".strip(),
            FIELD_ROLE: row.field,
            RAW_VALUE_ROLE: row.raw_value,
            CANONICAL_ROLE: canonical,
            KIND_ROLE: self._field_kinds.get(row.field, ""),
            COMPATIBLE_ROLE: row.field in self._fields,
            ISSUE_ROLE: issue,
            CHOICES_ROLE: [
                {"label": label, "value": value}
                for label, value in self._value_choices.get(row.field, ())
            ],
            HINT_ROLE: self._value_hints.get(row.field, ""),
            int(Qt.ItemDataRole.ToolTipRole): issue,
        }
        return values.get(role)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            DISPLAY_ROLE: QByteArray(b"display"),
            FIELD_ROLE: QByteArray(b"field"),
            RAW_VALUE_ROLE: QByteArray(b"rawValue"),
            CANONICAL_ROLE: QByteArray(b"canonical"),
            KIND_ROLE: QByteArray(b"kind"),
            COMPATIBLE_ROLE: QByteArray(b"compatible"),
            ISSUE_ROLE: QByteArray(b"issue"),
            CHOICES_ROLE: QByteArray(b"choices"),
            HINT_ROLE: QByteArray(b"hint"),
        }

    def _row_issue(self, row_index: int) -> str:
        row = self._rows[row_index]
        if not row.field and not row.raw_value.strip():
            return "mapping rows require both a field and a value"
        if not row.field or not row.raw_value.strip():
            return "mapping rows require both a field and a value"
        if row.field not in self._fields:
            return f"visualization field {row.field!r} is not available"
        if sum(candidate.field == row.field for candidate in self._rows) > 1:
            return f"mapping contains duplicate field {row.field!r}"
        try:
            self._parse_row(row)
        except ValueError as exc:
            return str(exc)
        return ""

    def _parse_row(self, row: MappingDraftRow) -> object:
        raw_values = (
            [part.strip() for part in row.raw_value.split(",")]
            if self.multiple
            else [row.raw_value.strip()]
        )
        if any(not value for value in raw_values):
            raise ValueError(f"series field {row.field!r} contains an empty value")
        parsed = [self._parse_value(row.field, value) for value in raw_values]
        return parsed if self.multiple else parsed[0]

    def _parse_value(self, field: str, raw_value: str) -> float | str:
        lookup = {
            candidate: canonical
            for label, canonical in self._value_choices.get(field, ())
            for candidate in (label, canonical)
        }
        value = lookup.get(raw_value, raw_value)
        if not self.numeric_values or self._field_kinds.get(field) == "categorical":
            return value
        try:
            numeric = float(value)
        except ValueError:
            if self.multiple and self.allow_text_numeric:
                try:
                    normalize_series_selections({field: (value,)})
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
                return value
            raise ValueError(
                f"numeric field requires a number; received {raw_value!r} for {field!r}"
            ) from None
        if not math.isfinite(numeric):
            raise ValueError(
                f"numeric field {field!r} requires a finite number; received {raw_value!r}"
            )
        return 0.0 if numeric == 0.0 else numeric

    def _validation_state(self) -> tuple[bool, str]:
        issue = self.get_issue()
        return (not issue, issue)

    def _mutation_allowed(self) -> bool:
        return self._mutation_guard is None or self._mutation_guard()

    def _emit_validity_if_changed(self, before: tuple[bool, str]) -> None:
        if self._validation_state() != before:
            self.validity_changed.emit()


def _scalar_text(value: object) -> str:
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)
