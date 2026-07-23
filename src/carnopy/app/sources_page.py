from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.inspection_controller import (
    InspectionController,
    SourceCandidate,
    discover_workspace_sources,
)
from carnopy.app.workspace import Workspace

SOURCE_PATH_ROLE = Qt.ItemDataRole.UserRole


class WorkspaceSourcesPanel(QWidget):
    """Temporary Widgets projection of the authoritative workspace source model."""

    inspect_requested = Signal(object)

    def __init__(
        self,
        controller: InspectionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Generated sources"))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(controller.refresh_sources)
        header.addWidget(refresh)
        header.addStretch(1)
        root.addLayout(header)
        self.sources = QListWidget()
        self.sources.itemDoubleClicked.connect(self._inspect_item)
        root.addWidget(self.sources, 1)
        actions = QHBoxLayout()
        inspect = QPushButton("Inspect Selected")
        inspect.clicked.connect(self.inspect_selected)
        self.more = QPushButton("Show 20 more")
        self.more.clicked.connect(controller.reveal_more_sources)
        actions.addWidget(inspect)
        actions.addWidget(self.more)
        root.addLayout(actions)
        controller.workspace_sources_model.modelReset.connect(self._sync_sources)
        controller.state_changed.connect(self._sync_more)
        self._sync_sources()

    @property
    def workspace(self) -> Workspace | None:
        return self.controller.workspace

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.controller.set_workspace(workspace)

    def refresh(self) -> None:
        self.controller.refresh_sources()

    def inspect_selected(self) -> None:
        self._inspect_item(self.sources.currentItem())

    def _inspect_item(self, item: QListWidgetItem | None) -> None:
        if item is not None:
            self.inspect_requested.emit(Path(str(item.data(SOURCE_PATH_ROLE))))

    def mark_uninspectable(self, path: Path, message: str) -> None:
        self.controller.mark_uninspectable(path, message)

    def mark_inspectable(self, path: Path) -> None:
        self.controller.mark_inspectable(path)

    def _sync_sources(self) -> None:
        selected_path = ""
        selected = self.sources.currentItem()
        if selected is not None:
            selected_path = str(selected.data(SOURCE_PATH_ROLE))
        self.sources.clear()
        selected_row = -1
        for row, candidate in enumerate(self.controller.workspace_sources_model.rows()):
            path = str(candidate.get("path", ""))
            issue = str(candidate.get("issue", ""))
            label = f"{candidate.get('name', '')} — {candidate.get('kindHint', '')}"
            if issue:
                label += f" — Uninspectable: {issue}"
            item = QListWidgetItem(label)
            item.setData(SOURCE_PATH_ROLE, path)
            item.setToolTip(issue or path)
            self.sources.addItem(item)
            if path == selected_path:
                selected_row = row
        if selected_row >= 0:
            self.sources.setCurrentRow(selected_row)
        self._sync_more()

    def _sync_more(self) -> None:
        self.more.setVisible(self.controller.get_has_more_workspace_sources())


__all__ = [
    "SourceCandidate",
    "WorkspaceSourcesPanel",
    "discover_workspace_sources",
]
