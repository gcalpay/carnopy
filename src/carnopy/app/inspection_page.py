from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.client import WorkerClient
from carnopy.app.table_model import LOCAL_PAGE_SIZE, PreviewTableModel
from carnopy.app.workspace import Workspace

TABLE_ID_ROLE = Qt.ItemDataRole.UserRole


class InspectionPage(QWidget):
    inspection_loaded = Signal(object)
    inspection_failed = Signal(object, str)

    def __init__(self, client: WorkerClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.workspace: Workspace | None = None
        self.source: Path | None = None
        self.payload: dict[str, Any] | None = None
        self._request_id: UUID | None = None
        self._request_kind: str | None = None
        self._requested_page_offset = 0

        root = QVBoxLayout(self)
        heading = QLabel("Inspect and Data")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(heading)
        actions = QHBoxLayout()
        browse_file = QPushButton("Open CSV/Parquet…")
        browse_bundle = QPushButton("Open Run or Bundle…")
        refresh = QPushButton("Refresh Inspection")
        browse_file.clicked.connect(self._browse_file)
        browse_bundle.clicked.connect(self._browse_bundle)
        refresh.clicked.connect(self.refresh)
        actions.addWidget(browse_file)
        actions.addWidget(browse_bundle)
        actions.addWidget(refresh)
        actions.addStretch(1)
        root.addLayout(actions)
        self.source_label = QLabel("No source selected.")
        self.source_label.setWordWrap(True)
        root.addWidget(self.source_label)
        self.status = QLabel("Select a workspace source or browse an external source.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Inspection status")
        root.addWidget(self.status)
        root.addWidget(QLabel("Summary"))
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        root.addWidget(self.summary, 1)
        root.addWidget(QLabel("Tabular artifacts"))
        self.tables = QListWidget()
        self.tables.itemDoubleClicked.connect(lambda _item: self.preview_selected())
        self.tables.currentItemChanged.connect(
            lambda _current, _previous: self._update_preview_actions()
        )
        root.addWidget(self.tables, 1)
        self.arrays_label = QLabel("Array/tensor artifacts: none")
        self.arrays_label.setWordWrap(True)
        root.addWidget(self.arrays_label)
        preview_actions = QHBoxLayout()
        self.preview_button = QPushButton("Preview Selected Table")
        self.previous_button = QPushButton("Previous 100")
        self.next_button = QPushButton("Next 100")
        self.preview_button.clicked.connect(self.preview_selected)
        self.previous_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)
        preview_actions.addWidget(self.preview_button)
        preview_actions.addWidget(self.previous_button)
        preview_actions.addWidget(self.next_button)
        preview_actions.addStretch(1)
        root.addLayout(preview_actions)
        self.preview_range = QLabel("No table preview loaded.")
        root.addWidget(self.preview_range)
        self.table_model = PreviewTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        root.addWidget(self.table_view, 2)
        self._update_preview_actions()

        client.request_succeeded.connect(self._request_succeeded)
        client.request_failed.connect(self._request_failed)
        client.busy_changed.connect(self._busy_changed)

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace

    def inspect(self, source: Path) -> None:
        if self.client.is_busy:
            self.status.setText("Another Carnopy worker request is active.")
            return
        self.source = source.expanduser().absolute()
        self.payload = None
        self.source_label.setText(str(self.source))
        self.status.setText("Inspecting source…")
        self.summary.clear()
        self.tables.clear()
        self.table_model.set_block(
            {"columns": [], "rows": [], "total_row_count": 0, "block_offset": 0},
            page_offset=0,
        )
        self.arrays_label.setText("Array/tensor artifacts: inspection pending")
        self._request_id = self.client.start_request(
            "inspect_source", {"source_path": str(self.source)}
        )
        self._request_kind = "inspection"

    def refresh(self) -> None:
        if self.source is not None:
            self.inspect(self.source)

    def selected_table_id(self) -> str | None:
        item = self.tables.currentItem()
        return None if item is None else str(item.data(TABLE_ID_ROLE))

    def preview_selected(self) -> None:
        self._request_preview(0)

    def previous_page(self) -> None:
        self._show_page(max(0, self.table_model.page_offset - LOCAL_PAGE_SIZE))

    def next_page(self) -> None:
        self._show_page(self.table_model.page_offset + LOCAL_PAGE_SIZE)

    def _show_page(self, page_offset: int) -> None:
        if page_offset >= self.table_model.total_rows:
            return
        if self.table_model.contains_page(page_offset):
            self.table_model.set_page(page_offset)
            self._update_preview_range()
            return
        block_offset = (page_offset // 500) * 500
        self._request_preview(block_offset, page_offset=page_offset)

    def _request_preview(self, offset: int, *, page_offset: int | None = None) -> None:
        payload = self.payload
        source = self.source
        table_id = self.selected_table_id()
        if payload is None or source is None or table_id is None or self.client.is_busy:
            return
        self._requested_page_offset = offset if page_offset is None else page_offset
        self.status.setText(f"Loading rows {offset}-{offset + 499}…")
        self._request_id = self.client.start_request(
            "preview_table",
            {
                "source_path": str(source),
                "table_id": table_id,
                "inspection_revision": payload["revision"],
                "offset": offset,
                "limit": 500,
            },
        )
        self._request_kind = "preview"

    def _browse_file(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Inspect Carnopy CSV or Parquet",
            str(self.workspace.root if self.workspace else Path.home()),
            "Carnopy tables (*.csv *.parquet)",
        )
        if selected:
            self.inspect(Path(selected))

    def _browse_bundle(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Inspect Carnopy Run or Bundle",
            str(self.workspace.outputs if self.workspace else Path.home()),
        )
        if selected:
            self.inspect(Path(selected))

    def _request_succeeded(self, value: object) -> None:
        if self._request_id is None:
            return
        payload = cast(dict[str, Any], value)
        if self._request_kind == "preview":
            if "rows" not in payload or "columns" not in payload:
                return
            self.table_model.set_block(payload, page_offset=self._requested_page_offset)
            self.status.setText("Table preview loaded without changing source row order.")
            self._request_id = None
            self._request_kind = None
            self._update_preview_range()
            return
        if self._request_kind != "inspection" or "source_kind" not in payload:
            return
        self.payload = payload
        self._request_id = None
        self._request_kind = None
        self.status.setText(
            f"Inspection complete: {payload.get('source_kind')} — "
            f"{len(payload.get('tables', []))} table(s)."
        )
        self.summary.setPlainText(
            json.dumps(payload.get("summary", {}), indent=2, sort_keys=True, ensure_ascii=False)
        )
        self.tables.clear()
        for descriptor in payload.get("tables", []):
            if not isinstance(descriptor, dict):
                continue
            item = QListWidgetItem(
                f"{descriptor.get('label', descriptor.get('id'))} "
                f"({descriptor.get('format', 'unknown')})"
            )
            item.setData(TABLE_ID_ROLE, descriptor.get("id"))
            self.tables.addItem(item)
        arrays = payload.get("arrays")
        count = len(arrays) if isinstance(arrays, list) else 0
        self.arrays_label.setText(f"Array/tensor artifacts listed in manifest: {count}")
        if self.source is not None:
            self.inspection_loaded.emit(self.source)
        self._update_preview_actions()

    def _request_failed(self, value: object) -> None:
        if self._request_id is None:
            return
        payload = cast(dict[str, Any], value)
        message = str(payload.get("message", "inspection failed"))
        request_kind = self._request_kind
        self._request_id = None
        self._request_kind = None
        self.status.setText(f"Uninspectable: {message}")
        if request_kind == "inspection" and self.source is not None:
            self.inspection_failed.emit(self.source, message)

    def _busy_changed(self, _busy: bool) -> None:
        self._update_preview_actions()

    def _update_preview_range(self) -> None:
        count = self.table_model.rowCount()
        if count == 0:
            self.preview_range.setText(
                f"No rows visible ({self.table_model.total_rows} total rows)."
            )
        else:
            first = self.table_model.page_offset
            last = first + count - 1
            self.preview_range.setText(
                f"Rows {first}-{last} of {self.table_model.total_rows}; "
                "100 rows per local page, 500 rows per worker block."
            )
        self._update_preview_actions()

    def _update_preview_actions(self) -> None:
        available = not self.client.is_busy
        self.preview_button.setEnabled(available and self.selected_table_id() is not None)
        self.previous_button.setEnabled(available and self.table_model.page_offset > 0)
        self.next_button.setEnabled(
            available
            and self.table_model.page_offset + self.table_model.rowCount()
            < self.table_model.total_rows
        )
