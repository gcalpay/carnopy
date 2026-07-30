from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

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

INVALID_INDEX = QModelIndex()


class InspectionListModel(QAbstractListModel):
    """Small role-stable list model for worker inspection projections."""

    available_changed = Signal()
    count_changed = Signal()

    def __init__(
        self,
        roles: Sequence[str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not roles or len(set(roles)) != len(roles):
            raise ValueError("inspection model roles must be non-empty and unique")
        self._roles = tuple(roles)
        self._role_numbers = {
            Qt.ItemDataRole.UserRole + offset: name
            for offset, name in enumerate(self._roles, start=1)
        }
        self._role_lookup = {name: role for role, name in self._role_numbers.items()}
        self._rows: tuple[dict[str, object], ...] = ()
        self._available = False

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode("utf-8")) for role, name in self._role_numbers.items()}

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_numbers.get(role)
        return None if name is None else self._rows[index.row()].get(name)

    def set_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        available: bool,
    ) -> None:
        normalized = tuple({name: row.get(name) for name in self._roles} for row in rows)
        old_count = len(self._rows)
        old_available = self._available
        self.beginResetModel()
        self._rows = normalized
        self._available = available
        self.endResetModel()
        if len(self._rows) != old_count:
            self.count_changed.emit()
        if self._available != old_available:
            self.available_changed.emit()

    def clear(self, *, available: bool = False) -> None:
        self.set_rows((), available=available)

    def get_available(self) -> bool:
        return self._available

    available = Property(bool, get_available, notify=available_changed)

    def get_count(self) -> int:
        return len(self._rows)

    count = Property(int, get_count, notify=count_changed)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, object]:
        if not 0 <= row < len(self._rows):
            return {}
        return dict(self._rows[row])

    def role(self, name: str) -> int:
        return int(self._role_lookup[name])

    def rows(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self._rows)
