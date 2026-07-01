from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.workspace import (
    Workspace,
    WorkspaceError,
    initialize_workspace,
    open_workspace,
)

PAGE_TITLES = (
    "Workspace and Sources",
    "Configure",
    "Validate and Generate",
    "Inspect and Data",
    "Plot",
    "Jobs and Diagnostics",
)
RECENT_WORKSPACES_KEY = "recent_workspaces"
WINDOW_GEOMETRY_KEY = "window_geometry"


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        initial_workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings or QSettings()
        self.workspace: Workspace | None = None
        self.setWindowTitle("Carnopy")
        self.resize(1100, 700)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(220)
        self.pages = QStackedWidget()
        for index, title in enumerate(PAGE_TITLES):
            self.navigation.addItem(title)
            page = self._workspace_page() if index == 0 else self._placeholder_page(title)
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self._set_workspace_pages_enabled(False)
        self._restore_preferences()

        if initial_workspace is not None:
            self.workspace_path.setText(str(initial_workspace.expanduser().resolve()))
            try:
                self._activate_workspace(open_workspace(initial_workspace))
            except WorkspaceError as exc:
                self.workspace_status.setText(str(exc))

    def _workspace_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel("Workspace")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel(
                "Choose a folder for Carnopy configurations, generated outputs, and figures. "
                "Existing folders are initialized only after confirmation."
            )
        )

        path_row = QHBoxLayout()
        self.workspace_path = QLineEdit()
        self.workspace_path.setPlaceholderText("Workspace folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_workspace)
        path_row.addWidget(self.workspace_path, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        actions = QHBoxLayout()
        create = QPushButton("Create Workspace")
        initialize = QPushButton("Initialize Existing Folder")
        open_button = QPushButton("Open Workspace")
        create.clicked.connect(self._create_workspace)
        initialize.clicked.connect(self._initialize_existing_workspace)
        open_button.clicked.connect(self._open_selected_workspace)
        actions.addWidget(create)
        actions.addWidget(initialize)
        actions.addWidget(open_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.workspace_status = QLabel("No workspace is open.")
        self.workspace_status.setWordWrap(True)
        layout.addWidget(self.workspace_status)
        layout.addWidget(QLabel("Recent workspaces"))
        self.recent_workspaces = QListWidget()
        self.recent_workspaces.itemDoubleClicked.connect(
            lambda item: self._open_workspace_path(Path(item.text()))
        )
        layout.addWidget(self.recent_workspaces, 1)
        return page

    @staticmethod
    def _placeholder_page(title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        layout.addWidget(QLabel("This page will be implemented in a later GUI-1 stage."))
        layout.addStretch(1)
        return page

    def _selected_path(self) -> Path | None:
        value = self.workspace_path.text().strip()
        if not value:
            self.workspace_status.setText("Choose a workspace folder first.")
            return None
        return Path(value).expanduser().resolve()

    def _browse_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose or create a Carnopy workspace folder",
            self.workspace_path.text() or str(Path.home()),
        )
        if selected:
            self.workspace_path.setText(selected)

    def _create_workspace(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        if path.exists():
            self.workspace_status.setText(
                "The selected path already exists. Use Initialize Existing Folder."
            )
            return
        self._initialize_path(path)

    def _initialize_existing_workspace(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        if not path.is_dir():
            self.workspace_status.setText(f"Existing folder does not exist: {path}")
            return
        answer = QMessageBox.question(
            self,
            "Initialize Existing Folder",
            f"Initialize this folder as a Carnopy workspace?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._initialize_path(path)

    def _initialize_path(self, path: Path) -> None:
        try:
            workspace = initialize_workspace(path)
        except (OSError, WorkspaceError) as exc:
            self.workspace_status.setText(str(exc))
            return
        self._activate_workspace(workspace)

    def _open_selected_workspace(self) -> None:
        path = self._selected_path()
        if path is not None:
            self._open_workspace_path(path)

    def _open_workspace_path(self, path: Path) -> None:
        try:
            workspace = open_workspace(path)
        except WorkspaceError as exc:
            self.workspace_status.setText(str(exc))
            return
        self._activate_workspace(workspace)

    def _activate_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.workspace_path.setText(str(workspace.root))
        self.workspace_status.setText(f"Open workspace: {workspace.root}")
        self._set_workspace_pages_enabled(True)
        self._remember_workspace(workspace.root)

    def _set_workspace_pages_enabled(self, enabled: bool) -> None:
        for index in range(1, self.navigation.count()):
            item = self.navigation.item(index)
            flags = item.flags()
            if enabled:
                item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
            page = self.pages.widget(index)
            if page is not None:
                page.setEnabled(enabled)

    def _remember_workspace(self, path: Path) -> None:
        stored = cast(list[object], self.settings.value(RECENT_WORKSPACES_KEY, [], type=list))
        current = [str(value) for value in stored]
        value = str(path)
        recent = [value, *(item for item in current if item != value)][:10]
        self.settings.setValue(RECENT_WORKSPACES_KEY, recent)
        self._load_recent_workspaces(recent)

    def _load_recent_workspaces(self, values: list[str]) -> None:
        self.recent_workspaces.clear()
        self.recent_workspaces.addItems(values)

    def _restore_preferences(self) -> None:
        stored = cast(list[object], self.settings.value(RECENT_WORKSPACES_KEY, [], type=list))
        recent = [str(value) for value in stored]
        self._load_recent_workspaces(recent)
        geometry = self.settings.value(WINDOW_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.setValue(WINDOW_GEOMETRY_KEY, self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)


def run_application(initial_workspace: Path | None = None) -> int:
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    if not isinstance(application, QApplication):
        raise RuntimeError("a non-GUI Qt application already exists")
    application.setOrganizationName("Carnopy")
    application.setApplicationName("Carnopy Desktop")
    window = MainWindow(initial_workspace=initial_workspace)
    window.show()
    return application.exec()
