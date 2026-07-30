from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

LOCAL_PAGE_SIZE = 100
INVALID_INDEX = QModelIndex()


class PreviewTableModel(QAbstractTableModel):
    """Expose one local page from a bounded worker-fetched table block."""

    state_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
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
        self.state_changed.emit()

    def set_page(self, page_offset: int) -> None:
        self.beginResetModel()
        self.page_offset = page_offset
        self.endResetModel()
        self.state_changed.emit()

    def clear(self) -> None:
        self.set_block(
            {"columns": [], "rows": [], "total_row_count": 0, "block_offset": 0},
            page_offset=0,
        )

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
            return str(self.page_offset + section + 1)
        column = self.columns[section]
        name = str(column.get("name", ""))
        unit = column.get("unit")
        return name if unit in (None, "", "1") else f"{name} [{unit}]"

    @property
    def first_row(self) -> int:
        return 0 if self.rowCount() == 0 else self.page_offset + 1

    @property
    def last_row(self) -> int:
        return 0 if self.rowCount() == 0 else self.page_offset + self.rowCount()

    def get_total_rows(self) -> int:
        return self.total_rows

    totalRows = Property(int, get_total_rows, notify=state_changed)

    def get_total_columns(self) -> int:
        return self.columnCount()

    totalColumns = Property(int, get_total_columns, notify=state_changed)

    def get_page_offset(self) -> int:
        return self.page_offset

    pageOffset = Property(int, get_page_offset, notify=state_changed)

    def get_first_row(self) -> int:
        return self.first_row

    firstRow = Property(int, get_first_row, notify=state_changed)

    def get_last_row(self) -> int:
        return self.last_row

    lastRow = Property(int, get_last_row, notify=state_changed)

    @Slot(int, result=str)
    def column_header(self, column: int) -> str:
        if not 0 <= column < len(self.columns):
            return ""
        return str(self.headerData(column, Qt.Orientation.Horizontal) or "")

    @Slot(int, result=str)
    def column_name(self, column: int) -> str:
        if not 0 <= column < len(self.columns):
            return ""
        return str(self.columns[column].get("name", ""))

    @Slot(int, result=str)
    def column_dtype(self, column: int) -> str:
        if not 0 <= column < len(self.columns):
            return ""
        return str(self.columns[column].get("dtype", ""))

    @Slot(int, result=str)
    def column_unit(self, column: int) -> str:
        if not 0 <= column < len(self.columns):
            return ""
        value = self.columns[column].get("unit")
        return "" if value is None else str(value)
