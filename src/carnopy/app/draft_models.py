from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from carnopy.app.sampler_draft import SamplerDraft

DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole)
VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
CANONICAL_ROLE = VALUE_ROLE + 1
COMPATIBLE_ROLE = VALUE_ROLE + 2
SELECTED_ROLE = VALUE_ROLE + 3
ISSUE_ROLE = VALUE_ROLE + 4
AXIS_ROLE = VALUE_ROLE + 5
DRAFT_ROLE = VALUE_ROLE + 6
INVALID_INDEX = QModelIndex()


@dataclass(frozen=True)
class DraftItem:
    value: str
    display: str
    canonical: str
    compatible: bool = True
    selected: bool = False
    issue: str = ""


class DraftListModel(QAbstractListModel):
    """Expose stable roles for choices and ordered draft selections."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        disable_incompatible: bool = False,
    ) -> None:
        super().__init__(parent)
        self._items: tuple[DraftItem, ...] = ()
        self._disable_incompatible = disable_incompatible

    @property
    def items(self) -> tuple[DraftItem, ...]:
        return self._items

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(item.value for item in self._items)

    def replace(self, items: Iterable[DraftItem]) -> bool:
        updated = tuple(items)
        if updated == self._items:
            return False
        if len(updated) == len(self._items) and all(
            _item_structure(before) == _item_structure(after)
            for before, after in zip(self._items, updated, strict=True)
        ):
            changed_rows = [
                row
                for row, (before, after) in enumerate(zip(self._items, updated, strict=True))
                if before.selected != after.selected
            ]
            self._items = updated
            for row in changed_rows:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [SELECTED_ROLE])
            return True
        self.beginResetModel()
        self._items = updated
        self.endResetModel()
        return True

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._items)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = DISPLAY_ROLE,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        values: dict[int, object] = {
            DISPLAY_ROLE: item.display,
            int(Qt.ItemDataRole.ToolTipRole): item.issue,
            VALUE_ROLE: item.value,
            CANONICAL_ROLE: item.canonical,
            COMPATIBLE_ROLE: item.compatible,
            SELECTED_ROLE: item.selected,
            ISSUE_ROLE: item.issue,
        }
        return values.get(role)

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        if (
            index.isValid()
            and 0 <= index.row() < len(self._items)
            and self._disable_incompatible
            and not self._items[index.row()].compatible
        ):
            flags &= ~Qt.ItemFlag.ItemIsEnabled
        return flags

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            DISPLAY_ROLE: QByteArray(b"display"),
            VALUE_ROLE: QByteArray(b"value"),
            CANONICAL_ROLE: QByteArray(b"canonical"),
            COMPATIBLE_ROLE: QByteArray(b"compatible"),
            SELECTED_ROLE: QByteArray(b"selected"),
            ISSUE_ROLE: QByteArray(b"issue"),
        }


class SamplerDraftModel(QAbstractListModel):
    """Expose active sampler drafts in deterministic grid-axis order."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._drafts: tuple[SamplerDraft, ...] = ()

    @property
    def drafts(self) -> tuple[SamplerDraft, ...]:
        return self._drafts

    def replace(self, drafts: Iterable[SamplerDraft]) -> bool:
        updated = tuple(drafts)
        if updated == self._drafts:
            return False
        self.beginResetModel()
        self._drafts = updated
        self.endResetModel()
        return True

    def refresh(self, draft: SamplerDraft) -> None:
        try:
            row = self._drafts.index(draft)
        except ValueError:
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [COMPATIBLE_ROLE, ISSUE_ROLE])

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._drafts)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = DISPLAY_ROLE,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._drafts):
            return None
        draft = self._drafts[index.row()]
        if role == DISPLAY_ROLE:
            return draft.get_axis().replace("_", " ").title()
        if role == AXIS_ROLE:
            return draft.get_axis()
        if role == DRAFT_ROLE:
            return draft
        if role == COMPATIBLE_ROLE:
            return draft.get_valid()
        if role == ISSUE_ROLE:
            return draft.get_issue()
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            DISPLAY_ROLE: QByteArray(b"display"),
            AXIS_ROLE: QByteArray(b"axis"),
            DRAFT_ROLE: QByteArray(b"draft"),
            COMPATIBLE_ROLE: QByteArray(b"compatible"),
            ISSUE_ROLE: QByteArray(b"issue"),
        }


def _item_structure(item: DraftItem) -> tuple[object, ...]:
    return (
        item.value,
        item.display,
        item.canonical,
        item.compatible,
        item.issue,
    )
