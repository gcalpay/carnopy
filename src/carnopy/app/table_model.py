from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

LOCAL_PAGE_SIZE = 100
INVALID_INDEX = QModelIndex()


class PreviewTableModel(QAbstractTableModel):
    """Expose one local page from a bounded worker-fetched table block."""

    def __init__(self) -> None:
        super().__init__()
        self.columns: list[dict[str, Any]] = []
        self.rows: list[list[object]] = []
        self.total_rows = 0
        self.block_offset = 0
        self.page_offset = 0

    def set_block(self, payload: dict[str, Any], *, page_offset: int) -> None:
        self.beginResetModel()
        self.columns = [item for item in payload.get("columns", []) if isinstance(item, dict)]
        self.rows = [list(item) for item in payload.get("rows", []) if isinstance(item, list)]
        self.total_rows = int(payload.get("total_row_count", 0))
        self.block_offset = int(payload.get("block_offset", 0))
        self.page_offset = page_offset
        self.endResetModel()

    def set_page(self, page_offset: int) -> None:
        self.beginResetModel()
        self.page_offset = page_offset
        self.endResetModel()

    def contains_page(self, page_offset: int) -> bool:
        local = page_offset - self.block_offset
        return 0 <= local < len(self.rows)

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        local = self.page_offset - self.block_offset
        return max(0, min(LOCAL_PAGE_SIZE, len(self.rows) - local))

    def columnCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self.columns)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        local = self.page_offset - self.block_offset + index.row()
        value = self.rows[local][index.column()]
        return "" if value is None else str(value)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(self.page_offset + section)
        column = self.columns[section]
        name = str(column.get("name", ""))
        unit = column.get("unit")
        return name if unit in (None, "", "1") else f"{name} [{unit}]"
