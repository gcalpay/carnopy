from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.inspection_controller import InspectionController
from carnopy.app.table_model import LOCAL_PAGE_SIZE
from carnopy.app.workspace import Workspace

TABLE_ID_ROLE = Qt.ItemDataRole.UserRole


class InspectionPage(QWidget):
    """Temporary Widgets view over the authoritative inspection controller."""

    def __init__(
        self,
        controller: InspectionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.coordinator = controller.coordinator
        self.workspace: Workspace | None = None
        self._updating_tables = False

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
        refresh.clicked.connect(controller.refresh_inspection)
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

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        details = QWidget()
        self.details_widget = details
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(QLabel("Summary"))
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        details_layout.addWidget(self.summary, 1)
        details_layout.addWidget(QLabel("Tabular artifacts"))
        self.tables = QListWidget()
        self.tables.itemDoubleClicked.connect(lambda _item: self.preview_selected())
        self.tables.currentItemChanged.connect(self._table_selected)
        details_layout.addWidget(self.tables, 1)
        self.arrays_label = QLabel("Logical arrays: none")
        self.arrays_label.setWordWrap(True)
        details_layout.addWidget(self.arrays_label)

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_actions = QHBoxLayout()
        self.preview_button = QPushButton("Preview Selected Table")
        self.previous_button = QPushButton("Previous 100")
        self.next_button = QPushButton("Next 100")
        self.focus_table_button = QPushButton("Focus Table")
        self.focus_table_button.setCheckable(True)
        self.focus_table_button.setAccessibleName("Focus table preview")
        self.preview_button.clicked.connect(self.preview_selected)
        self.previous_button.clicked.connect(controller.previous_preview_page)
        self.next_button.clicked.connect(controller.next_preview_page)
        self.focus_table_button.toggled.connect(self._set_table_focus)
        preview_actions.addWidget(self.preview_button)
        preview_actions.addWidget(self.previous_button)
        preview_actions.addWidget(self.next_button)
        preview_actions.addWidget(self.focus_table_button)
        preview_actions.addStretch(1)
        preview_layout.addLayout(preview_actions)
        self.preview_range = QLabel("No table preview loaded.")
        preview_layout.addWidget(self.preview_range)
        self.table_model = controller.table_model
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSortingEnabled(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        preview_layout.addWidget(self.table_view, 1)

        self.splitter.addWidget(details)
        self.splitter.addWidget(preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([240, 460])
        root.addWidget(self.splitter, 1)

        controller.state_changed.connect(self._sync_from_controller)
        controller.tables_model.modelReset.connect(self._sync_tables)
        controller.arrays_model.modelReset.connect(self._sync_arrays)
        self._sync_from_controller()

    @property
    def source(self) -> Path | None:
        value = self.controller.get_source_path()
        return Path(value) if value else None

    @property
    def payload(self) -> dict[str, object] | None:
        return self.controller.current_payload()

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace

    def inspect(self, source: Path) -> None:
        self.controller.inspect_source(str(source))

    def refresh(self) -> None:
        self.controller.refresh_inspection()

    def selected_table_id(self) -> str | None:
        value = self.controller.get_selected_table_id()
        return value or None

    def preview_selected(self) -> None:
        table_id = self.selected_table_id()
        if table_id:
            self.controller.request_preview_page(0)

    def previous_page(self) -> None:
        self.controller.previous_preview_page()

    def next_page(self) -> None:
        self.controller.next_preview_page()

    def _browse_file(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Inspect Carnopy CSV or Parquet",
            str(self.workspace.root if self.workspace else Path.home()),
            "Carnopy tables (*.csv *.parquet)",
        )
        if selected:
            self.controller.inspect_source(selected)

    def _browse_bundle(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Inspect Carnopy Run or Bundle",
            str(self.workspace.outputs if self.workspace else Path.home()),
        )
        if selected:
            self.controller.inspect_source(selected)

    def _table_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if self._updating_tables or current is None:
            self._update_preview_actions()
            return
        table_id = current.data(TABLE_ID_ROLE)
        if isinstance(table_id, str):
            self.controller.select_table(table_id)
        self._update_preview_actions()

    def _sync_tables(self) -> None:
        selected = self.controller.get_selected_table_id()
        self._updating_tables = True
        self.tables.clear()
        selected_row = -1
        for row, descriptor in enumerate(self.controller.tables_model.rows()):
            table_id = str(descriptor.get("id", ""))
            label = str(descriptor.get("label", table_id))
            item = QListWidgetItem(f"{label} ({descriptor.get('format', 'unknown')})")
            item.setData(TABLE_ID_ROLE, table_id)
            self.tables.addItem(item)
            if table_id == selected:
                selected_row = row
        if selected_row >= 0:
            self.tables.setCurrentRow(selected_row)
        self._updating_tables = False
        self._update_preview_actions()

    def _sync_arrays(self) -> None:
        count = self.controller.arrays_model.get_count()
        if self.controller.arrays_model.get_available():
            self.arrays_label.setText(f"Logical arrays listed in manifest: {count}")
        else:
            self.arrays_label.setText("Logical arrays: unavailable")

    def _sync_from_controller(self) -> None:
        state = self.controller.get_state()
        source = self.controller.get_source_path()
        self.source_label.setText(source or "No source selected.")
        issue = self.controller.get_issue()
        if state == "loading":
            status = "Inspecting source…"
        elif state == "ready":
            status = (
                f"Inspection complete: {self.controller.get_source_kind()} — "
                f"{self.controller.tables_model.get_count()} table(s)."
            )
        elif state == "stale":
            status = f"Inspection is stale: {issue}"
        elif state == "failed":
            status = f"Uninspectable: {issue}"
        else:
            status = "Select a workspace source or browse an external source."
        self._select_current_table()
        if self.controller.get_preview_state() == "loading":
            status = "Loading a bounded table block…"
        self.status.setText(status)
        self.summary.setPlainText(self.controller.get_diagnostic_text())
        self._update_preview_range()

    def _select_current_table(self) -> None:
        selected = self.controller.get_selected_table_id()
        if not selected or self.tables.currentItem() is not None:
            return
        for row in range(self.tables.count()):
            item = self.tables.item(row)
            if item is not None and item.data(TABLE_ID_ROLE) == selected:
                self._updating_tables = True
                self.tables.setCurrentRow(row)
                self._updating_tables = False
                return

    def _set_table_focus(self, focused: bool) -> None:
        self.details_widget.setVisible(not focused)
        self.focus_table_button.setText("Show Details" if focused else "Focus Table")

    def _update_preview_range(self) -> None:
        count = self.table_model.rowCount()
        if count == 0:
            self.preview_range.setText(
                f"No rows visible ({self.table_model.total_rows} total rows)."
            )
        else:
            self.preview_range.setText(
                f"Rows {self.table_model.first_row}-{self.table_model.last_row} "
                f"of {self.table_model.total_rows}; {LOCAL_PAGE_SIZE} rows per local "
                "page, 500 rows per worker block."
            )
        self._update_preview_actions()

    def _update_preview_actions(self) -> None:
        available = self.controller.get_can_preview()
        self.preview_button.setEnabled(available and self.selected_table_id() is not None)
        self.previous_button.setEnabled(available and self.table_model.page_offset > 0)
        self.next_button.setEnabled(
            available
            and self.table_model.page_offset + self.table_model.rowCount()
            < self.table_model.total_rows
        )
