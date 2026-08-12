from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

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

IssueOrigin = Literal["local", "schema", "source", "dependency", "plan", "runtime"]
IssueSeverity = Literal["blocking", "advisory"]

ORIGIN_ROLE = int(Qt.ItemDataRole.UserRole) + 1
SEVERITY_ROLE = ORIGIN_ROLE + 1
CODE_ROLE = ORIGIN_ROLE + 2
MESSAGE_ROLE = ORIGIN_ROLE + 3
DOCUMENT_KIND_ROLE = ORIGIN_ROLE + 4
SECTION_ROLE = ORIGIN_ROLE + 5
FIELD_ID_ROLE = ORIGIN_ROLE + 6
ITEM_KEY_ROLE = ORIGIN_ROLE + 7
NESTED_ROW_ROLE = ORIGIN_ROLE + 8
PATH_ROLE = ORIGIN_ROLE + 9
INVALID_INDEX = QModelIndex()


class WorkflowListModel(QAbstractListModel):
    """Expose detached workflow rows through one explicit, stable role set."""

    count_changed = Signal()

    def __init__(self, roles: Sequence[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        if not roles or len(set(roles)) != len(roles):
            raise ValueError("workflow model roles must be non-empty and unique")
        self._roles = tuple(roles)
        self._role_names = {
            int(Qt.ItemDataRole.UserRole) + offset: name
            for offset, name in enumerate(self._roles, start=1)
        }
        self._rows: tuple[dict[str, object], ...] = ()

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode("utf-8")) for role, name in self._role_names.items()}

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_names.get(role)
        return None if name is None else copy.deepcopy(self._rows[index.row()].get(name))

    def replace(self, rows: Iterable[Mapping[str, object]]) -> bool:
        updated = tuple(
            {name: copy.deepcopy(row.get(name)) for name in self._roles} for row in rows
        )
        if updated == self._rows:
            return False
        previous_count = len(self._rows)
        self.beginResetModel()
        self._rows = updated
        self.endResetModel()
        if len(updated) != previous_count:
            self.count_changed.emit()
        return True

    def clear(self) -> bool:
        return self.replace(())

    def get_count(self) -> int:
        return len(self._rows)

    count = Property(int, get_count, notify=count_changed)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, object]:
        return copy.deepcopy(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def rows(self) -> tuple[dict[str, object], ...]:
        return tuple(copy.deepcopy(row) for row in self._rows)


@dataclass(frozen=True)
class WorkflowIssue:
    """One private, stable workflow issue projected to QML."""

    origin: IssueOrigin
    severity: IssueSeverity
    code: str
    message: str
    document_kind: str
    section: str
    field_id: str = ""
    item_key: str = ""
    nested_row: int = -1
    path: tuple[str | int, ...] = ()


class WorkflowIssueModel(QAbstractListModel):
    """Expose structured workflow issues through fixed QML model roles."""

    count_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._issues: tuple[WorkflowIssue, ...] = ()

    @property
    def issues(self) -> tuple[WorkflowIssue, ...]:
        return self._issues

    def replace(self, issues: tuple[WorkflowIssue, ...]) -> bool:
        if issues == self._issues:
            return False
        previous_count = len(self._issues)
        self.beginResetModel()
        self._issues = issues
        self.endResetModel()
        if len(self._issues) != previous_count:
            self.count_changed.emit()
        return True

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._issues)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._issues):
            return None
        issue = self._issues[index.row()]
        values: dict[int, object] = {
            int(Qt.ItemDataRole.DisplayRole): issue.message,
            int(Qt.ItemDataRole.ToolTipRole): issue.message,
            ORIGIN_ROLE: issue.origin,
            SEVERITY_ROLE: issue.severity,
            CODE_ROLE: issue.code,
            MESSAGE_ROLE: issue.message,
            DOCUMENT_KIND_ROLE: issue.document_kind,
            SECTION_ROLE: issue.section,
            FIELD_ID_ROLE: issue.field_id,
            ITEM_KEY_ROLE: issue.item_key,
            NESTED_ROW_ROLE: issue.nested_row,
            PATH_ROLE: list(issue.path),
        }
        return values.get(role)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            ORIGIN_ROLE: QByteArray(b"origin"),
            SEVERITY_ROLE: QByteArray(b"severity"),
            CODE_ROLE: QByteArray(b"code"),
            MESSAGE_ROLE: QByteArray(b"message"),
            DOCUMENT_KIND_ROLE: QByteArray(b"documentKind"),
            SECTION_ROLE: QByteArray(b"section"),
            FIELD_ID_ROLE: QByteArray(b"fieldId"),
            ITEM_KEY_ROLE: QByteArray(b"itemKey"),
            NESTED_ROW_ROLE: QByteArray(b"nestedRow"),
            PATH_ROLE: QByteArray(b"path"),
        }

    def get_count(self) -> int:
        return len(self._issues)

    count = Property(int, get_count, notify=count_changed)
