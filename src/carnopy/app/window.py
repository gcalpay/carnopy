from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QModelIndex, QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.application_identity import apply_application_identity
from carnopy.app.config_document import ConfigDocumentError
from carnopy.app.config_editor import DatasetConfigEditor
from carnopy.app.desktop_controller import DesktopController
from carnopy.app.execution_page import DatasetExecutionPage
from carnopy.app.inspection_page import InspectionPage
from carnopy.app.jobs_page import JobsDiagnosticsPage
from carnopy.app.plot_page import PlotPage
from carnopy.app.sources_page import WorkspaceSourcesPanel
from carnopy.app.workspace import Workspace
from carnopy.app.workspace_controller import PATH_ROLE

PAGE_TITLES = (
    "Workspace and Sources",
    "Configure",
    "Validate and Generate",
    "Inspect and Data",
    "Plot",
    "Jobs and Diagnostics",
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        desktop_controller: DesktopController | None = None,
        settings: QSettings | None = None,
        initial_workspace: Path | None = None,
    ) -> None:
        if desktop_controller is not None and settings is not None:
            raise ValueError("supply either desktop_controller or settings, not both")
        super().__init__()
        self.desktop_controller = desktop_controller or DesktopController(
            settings=settings,
            parent=self,
        )
        self.settings = self.desktop_controller.settings
        self.client = self.desktop_controller.client
        self.coordinator = self.desktop_controller.request_coordinator
        self.workspace_controller = self.desktop_controller.workspace_controller
        self.dataset_config_controller = self.desktop_controller.dataset_config_controller
        self._close_when_idle = False
        self._close_after_plot_stop = False
        self.setWindowTitle("Carnopy")
        self.resize(1100, 700)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(220)
        self.pages = QStackedWidget()
        self.configure_page = DatasetConfigEditor(
            desktop_controller=self.desktop_controller,
        )
        self.execution_page = DatasetExecutionPage(self.coordinator)
        self.inspection_page = InspectionPage(self.coordinator)
        self.plot_page = PlotPage(self.coordinator)
        self.jobs_page = JobsDiagnosticsPage(self.execution_page)
        for index, title in enumerate(PAGE_TITLES):
            self.navigation.addItem(title)
            if index == 0:
                page = self._workspace_page()
            elif index == 1:
                page = self.configure_page
            elif index == 2:
                page = self.execution_page
            elif index == 3:
                page = self.inspection_page
            elif index == 4:
                page = self.plot_page
            elif index == 5:
                page = self.jobs_page
            else:
                page = self._placeholder_page(title)
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self._set_workspace_pages_enabled(self.workspace_controller.get_available())
        self.dataset_config_controller.document_state_changed.connect(self._sync_execution_config)
        self.coordinator.busy_changed.connect(self._worker_busy_changed)
        self.workspace_controller.workspace_changed.connect(self._workspace_activated)
        self.workspace_controller.available_changed.connect(
            lambda: self._set_workspace_pages_enabled(self.workspace_controller.get_available())
        )
        self.workspace_controller.status_message_changed.connect(self._update_workspace_status)
        self.workspace_controller.error_message_changed.connect(self._update_workspace_status)
        self.sources_panel.inspect_requested.connect(self._inspect_source)
        self.inspection_page.inspection_loaded.connect(self.sources_panel.mark_inspectable)
        self.inspection_page.inspection_failed.connect(self.sources_panel.mark_uninspectable)
        self.inspection_page.inspection_changed.connect(self.plot_page.set_inspection)
        self.plot_page.render_finished.connect(self._plot_render_finished)
        self.execution_page.run_finalized.connect(self._run_finalized)
        self.execution_page.inspect_button.clicked.connect(self._inspect_finalized_run)
        self._update_workspace_status()

        if initial_workspace is not None:
            self.workspace_path.setText(str(initial_workspace.expanduser().resolve()))
            if self.desktop_controller.prepare_open_workspace(str(initial_workspace)):
                self.desktop_controller.commit_workspace_operation()

    @property
    def workspace(self) -> Workspace | None:
        return self.workspace_controller.workspace

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
        self.recent_workspaces = QListView()
        self.recent_workspaces.setModel(self.workspace_controller.recent_model)
        self.recent_workspaces.doubleClicked.connect(self._open_recent_workspace)
        layout.addWidget(self.recent_workspaces, 1)
        self.sources_panel = WorkspaceSourcesPanel()
        layout.addWidget(self.sources_panel, 2)
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

    def _browse_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose or create a Carnopy workspace folder",
            self.workspace_path.text() or str(Path.home()),
        )
        if selected:
            self.workspace_path.setText(selected)

    def _create_workspace(self) -> None:
        if self.desktop_controller.prepare_create_workspace_path(self.workspace_path.text()):
            self._complete_workspace_operation(confirm_initialization=False)

    def _initialize_existing_workspace(self) -> None:
        if self.desktop_controller.prepare_initialize_workspace(self.workspace_path.text()):
            self._complete_workspace_operation(confirm_initialization=True)

    def _open_selected_workspace(self) -> None:
        self._open_workspace_path(self.workspace_path.text())

    def _open_workspace_path(self, path: str | Path) -> None:
        if self.desktop_controller.prepare_open_workspace(str(path)):
            self._complete_workspace_operation(confirm_initialization=False)

    def _open_recent_workspace(self, index: QModelIndex) -> None:
        value = index.data(PATH_ROLE)
        if not isinstance(value, str):
            return
        self.workspace_path.setText(value)
        self._open_workspace_path(value)

    def _complete_workspace_operation(self, *, confirm_initialization: bool) -> None:
        pending_path = self.workspace_controller.get_pending_path()
        pending_operation = self.workspace_controller.get_pending_operation()
        workspace = self.workspace
        opening_active = (
            pending_operation == "open"
            and workspace is not None
            and pending_path == str(workspace.root)
        )
        discard_required = (
            not opening_active and self.dataset_config_controller.needs_discard_confirmation()
        )
        if not opening_active and not self.configure_page.confirm_discard():
            self.desktop_controller.cancel_workspace_operation()
            return
        confirmed = discard_required
        if confirm_initialization:
            answer = QMessageBox.question(
                self,
                "Initialize Existing Folder",
                f"Initialize this folder as a Carnopy workspace?\n\n{pending_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.desktop_controller.cancel_workspace_operation()
                return
            confirmed = True
        self.desktop_controller.commit_workspace_operation(confirmed)

    def _workspace_activated(self, value: object) -> None:
        if not isinstance(value, Workspace):
            return
        workspace = value
        self.workspace_path.setText(str(workspace.root))
        self.execution_page.set_workspace(workspace)
        self.inspection_page.set_workspace(workspace)
        self.plot_page.set_workspace(workspace)
        self.jobs_page.set_workspace(workspace)
        self.sources_panel.set_workspace(workspace)
        self._sync_execution_config()

    def _update_workspace_status(self) -> None:
        message = self.workspace_controller.get_error_message()
        if not message:
            message = self.workspace_controller.get_status_message()
        self.workspace_status.setText(message)

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

    def center_on_primary_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.coordinator.is_busy:
            if self.coordinator.active_owner == "execution":
                self._close_when_idle = True
                self.execution_page.cancel()
                event.ignore()
                return
            if self.coordinator.active_owner == "plot":
                if self._close_after_plot_stop:
                    event.ignore()
                    return
                if self._confirm_force_stop_and_close():
                    self._close_after_plot_stop = True
                    if not self.plot_page.force_stop(confirm=False):
                        self._close_after_plot_stop = False
                event.ignore()
                return
            QMessageBox.warning(
                self,
                "Carnopy Worker Is Busy",
                "An active worker request must finish before the application can close.",
            )
            event.ignore()
            return
        if not self.configure_page.confirm_discard():
            event.ignore()
            return
        self.configure_page.shutdown()
        if not self.desktop_controller.shutdown():
            event.ignore()
            return
        super().closeEvent(event)

    def _sync_execution_config(self) -> None:
        try:
            snapshot = self.dataset_config_controller.execution_snapshot()
        except ConfigDocumentError as exc:
            self.execution_page.set_snapshot(None, str(exc))
        else:
            self.execution_page.set_snapshot(snapshot)

    def _worker_busy_changed(self, busy: bool) -> None:
        if not busy and self._close_when_idle:
            self._close_when_idle = False
            QTimer.singleShot(0, self.close)

    def _plot_render_finished(self, value: object) -> None:
        if not self._close_after_plot_stop:
            return
        envelope = cast(dict[str, object], value)
        cleanup_error = envelope.get("cleanup_error")
        self._close_after_plot_stop = False
        if isinstance(cleanup_error, str):
            self.navigation.setCurrentRow(4)
            self.workspace_controller.report_error(
                "Plot rendering stopped, but private staging cleanup failed. "
                "Review the Plot page before closing."
            )
            return
        QTimer.singleShot(0, self.close)

    def _confirm_force_stop_and_close(self) -> bool:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle("Plot Rendering Is Active")
        message.setText(
            "Force-stop the plot worker and close Carnopy after parent staging cleanup?"
        )
        keep_open = message.addButton("Keep Open", QMessageBox.ButtonRole.RejectRole)
        force_close = message.addButton(
            "Force Stop and Close",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        message.setDefaultButton(keep_open)
        message.exec()
        return message.clickedButton() is force_close

    def _run_finalized(self, _path: object) -> None:
        self.sources_panel.refresh()

    def _inspect_finalized_run(self) -> None:
        value = self.execution_page.inspect_button.property("source_path")
        if isinstance(value, str):
            self._inspect_source(Path(value))

    def _inspect_source(self, value: object) -> None:
        path = value if isinstance(value, Path) else Path(str(value))
        self.inspection_page.inspect(path)
        self.navigation.setCurrentRow(3)


def run_application(initial_workspace: Path | None = None) -> int:
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    if not isinstance(application, QApplication):
        raise RuntimeError("a non-GUI Qt application already exists")
    apply_application_identity(application)
    window = MainWindow(initial_workspace=initial_workspace)
    window.center_on_primary_screen()
    window.show()

    def bring_to_front() -> None:
        if window.isMinimized():
            window.showNormal()
        window.center_on_primary_screen()
        window.raise_()
        window.activateWindow()

    QTimer.singleShot(0, bring_to_front)
    QTimer.singleShot(250, bring_to_front)
    return application.exec()
