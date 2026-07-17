from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot

from carnopy.app.client import WorkerClient
from carnopy.app.config_controller import DatasetConfigController
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.qml_settings import QmlSettingsController
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.visualization_draft import VisualizationDraft
from carnopy.app.workspace_controller import WorkspaceController


class DesktopController(QObject):
    """Compose the process-wide desktop state and worker transport."""

    workspace_state_changed = Signal()
    workspace_feedback_changed = Signal()
    workspace_confirmation_changed = Signal()
    workspaceConfirmationRequested = Signal()

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings()
        self.qml_settings = QmlSettingsController(self.settings, self)
        self.client = WorkerClient(self)
        self.request_coordinator = DesktopRequestCoordinator(self.client, self)
        self.dataset_draft = DatasetDraft(self)
        self.visualization_draft = VisualizationDraft(self)
        self.dataset_config_controller = DatasetConfigController(
            self.request_coordinator,
            self.dataset_draft,
            self.visualization_draft,
            self,
        )
        self.workspace_controller = WorkspaceController(
            self.request_coordinator,
            self.settings,
            self,
        )
        self.workspace_controller.workspace_changed.connect(self._workspace_activated)
        self.workspace_controller.available_changed.connect(self.workspace_state_changed)
        self.workspace_controller.paths_changed.connect(self.workspace_state_changed)
        self.workspace_controller.status_message_changed.connect(self.workspace_feedback_changed)
        self.workspace_controller.error_message_changed.connect(self.workspace_feedback_changed)
        self.workspace_controller.pending_operation_changed.connect(
            self.workspace_confirmation_changed
        )
        self.dataset_config_controller.state_changed.connect(self._configuration_state_changed)
        self.request_coordinator.busy_changed.connect(self._request_state_changed)
        self.visualization_draft.active_plot_draft_changed.connect(self._active_plot_state_changed)
        self._queued_workspace_request: tuple[str, str, str, bool] | None = None
        self._workspace_request_timer = QTimer(self)
        self._workspace_request_timer.setSingleShot(True)
        self._workspace_request_timer.setInterval(0)
        self._workspace_request_timer.timeout.connect(self._run_queued_workspace_request)
        self._shutdown = False

    def get_workspace_controller(self) -> QObject:
        return self.workspace_controller

    workspaceController = Property(QObject, get_workspace_controller, constant=True)

    def get_workspace_available(self) -> bool:
        return self.workspace_controller.get_available()

    workspaceAvailable = Property(
        bool,
        get_workspace_available,
        notify=workspace_state_changed,
    )

    def get_workspace_state(self) -> str:
        if not self.workspace_controller.get_available():
            return "unavailable"
        if self.dataset_config_controller.get_has_document():
            return "editing"
        if (
            not self.dataset_config_controller.get_editor_available()
            and self.request_coordinator.is_busy
            and self.request_coordinator.active_owner == "configuration"
        ):
            return "loading"
        return "landing"

    workspaceState = Property(str, get_workspace_state, notify=workspace_state_changed)

    def get_workspace_root_path(self) -> str:
        return self.workspace_controller.get_root_path()

    workspaceRootPath = Property(
        str,
        get_workspace_root_path,
        notify=workspace_state_changed,
    )

    def get_workspace_status_message(self) -> str:
        return self.workspace_controller.get_status_message()

    workspaceStatusMessage = Property(
        str,
        get_workspace_status_message,
        notify=workspace_feedback_changed,
    )

    def get_workspace_error_message(self) -> str:
        return self.workspace_controller.get_error_message()

    workspaceErrorMessage = Property(
        str,
        get_workspace_error_message,
        notify=workspace_feedback_changed,
    )

    def get_can_change_workspace(self) -> bool:
        return (
            self.workspace_controller.get_can_change_workspace()
            and self.visualization_draft.get_active_plot_draft() is None
        )

    canChangeWorkspace = Property(
        bool,
        get_can_change_workspace,
        notify=workspace_state_changed,
    )

    def get_recent_workspaces(self) -> QObject:
        return self.workspace_controller.recent_model

    recentWorkspaces = Property(QObject, get_recent_workspaces, constant=True)

    def get_pending_workspace_operation(self) -> str:
        return self.workspace_controller.get_pending_operation()

    pendingWorkspaceOperation = Property(
        str,
        get_pending_workspace_operation,
        notify=workspace_confirmation_changed,
    )

    def get_pending_workspace_path(self) -> str:
        return self.workspace_controller.get_pending_path()

    pendingWorkspacePath = Property(
        str,
        get_pending_workspace_path,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_required(self) -> bool:
        operation = self.workspace_controller.get_pending_operation()
        if not operation:
            return False
        if operation == "initialize_existing":
            return True
        workspace = self.workspace_controller.workspace
        if (
            operation == "open"
            and workspace is not None
            and self.workspace_controller.get_pending_path() == str(workspace.root)
        ):
            return False
        return self.dataset_config_controller.needs_discard_confirmation()

    workspaceConfirmationRequired = Property(
        bool,
        get_workspace_confirmation_required,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_title(self) -> str:
        if self.workspace_controller.get_pending_operation() == "initialize_existing":
            return "Initialize Existing Folder"
        return "Replace Workspace"

    workspaceConfirmationTitle = Property(
        str,
        get_workspace_confirmation_title,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_message(self) -> str:
        operation = self.workspace_controller.get_pending_operation()
        path = self.workspace_controller.get_pending_path()
        dirty = self.dataset_config_controller.needs_discard_confirmation()
        if operation == "initialize_existing":
            message = f"Initialize this existing folder as a Carnopy workspace?\n\n{path}"
            if dirty:
                message += (
                    "\n\nThe current configuration has unsaved changes that will be discarded."
                )
            return message
        if dirty:
            return (
                "The current configuration has unsaved changes. Discard them and "
                f"open this workspace?\n\n{path}"
            )
        return ""

    workspaceConfirmationMessage = Property(
        str,
        get_workspace_confirmation_message,
        notify=workspace_confirmation_changed,
    )

    def get_qml_settings(self) -> QObject:
        return self.qml_settings

    qmlSettings = Property(QObject, get_qml_settings, constant=True)

    def get_dataset_draft(self) -> QObject:
        return self.dataset_draft

    datasetDraft = Property(QObject, get_dataset_draft, constant=True)

    def get_visualization_draft(self) -> QObject:
        return self.visualization_draft

    visualizationDraft = Property(QObject, get_visualization_draft, constant=True)

    def get_dataset_config_controller(self) -> QObject:
        return self.dataset_config_controller

    datasetConfigController = Property(
        QObject,
        get_dataset_config_controller,
        constant=True,
    )

    @Slot(str, str, result=bool, name="prepareCreateWorkspace")
    def prepare_create_workspace(self, parent_path: str, child_name: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        parent = _local_path(parent_path)
        name = child_name.strip()
        if not parent:
            self.workspace_controller.report_error("Choose a parent folder first.")
            return False
        if not _valid_workspace_child_name(name):
            self.workspace_controller.report_error(
                "Enter one new folder name without path separators."
            )
            return False
        return self.workspace_controller.prepare_create(Path(parent) / name)

    @Slot(str, result=bool, name="prepareCreateWorkspacePath")
    def prepare_create_workspace_path(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_create(_local_path(path))

    @Slot(str, result=bool, name="prepareInitializeWorkspace")
    def prepare_initialize_workspace(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_initialize_existing(_local_path(path))

    @Slot(str, result=bool, name="prepareOpenWorkspace")
    def prepare_open_workspace(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_open(_local_path(path))

    @Slot(bool, result=bool, name="commitWorkspaceOperation")
    def commit_workspace_operation(self, confirmed: bool = False) -> bool:
        if not self._guard_workspace_change(before_commit=True):
            return False
        if self.get_workspace_confirmation_required() and not confirmed:
            self.workspace_controller.report_error(
                "Confirm the pending workspace operation before continuing."
            )
            return False
        return self.workspace_controller.commit_pending()

    @Slot(name="cancelWorkspaceOperation")
    def cancel_workspace_operation(self) -> None:
        self.workspace_controller.cancel_pending()

    @Slot(str, str, name="requestCreateWorkspace")
    def request_create_workspace(self, parent_path: str, child_name: str) -> None:
        self._queue_workspace_request("create", parent_path, child_name)

    @Slot(str, name="requestCreateWorkspacePath")
    def request_create_workspace_path(self, path: str) -> None:
        self._queue_workspace_request("create_path", path)

    @Slot(str, name="requestInitializeWorkspace")
    def request_initialize_workspace(self, path: str) -> None:
        self._queue_workspace_request("initialize", path)

    @Slot(str, name="requestOpenWorkspace")
    def request_open_workspace(self, path: str) -> None:
        self._queue_workspace_request("open", path)

    @Slot(bool, name="requestCommitWorkspaceOperation")
    def request_commit_workspace_operation(self, confirmed: bool = False) -> None:
        self._queue_workspace_request("commit", "", confirmed=confirmed)

    @Slot(name="requestCancelWorkspaceOperation")
    def request_cancel_workspace_operation(self) -> None:
        self._queue_workspace_request("cancel", "")

    def shutdown(self) -> bool:
        if not self._guard_active_plot_edit():
            return False
        self.workspace_controller.cancel_pending()
        if self.request_coordinator.is_busy:
            return False
        if self._shutdown:
            return True
        self._workspace_request_timer.stop()
        self._queued_workspace_request = None
        self.request_coordinator.shutdown()
        self.settings.sync()
        self._shutdown = True
        return True

    @Slot(result=bool, name="requestShutdown")
    def request_shutdown(self) -> bool:
        return self.shutdown()

    def _workspace_activated(self, value: object) -> None:
        self.dataset_config_controller.set_workspace(value)
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _configuration_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _request_state_changed(self, _busy: bool) -> None:
        self.workspace_state_changed.emit()

    def _active_plot_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _guard_workspace_change(self, *, before_commit: bool) -> bool:
        if self._guard_active_plot_edit():
            return True
        if before_commit:
            self.workspace_controller.cancel_pending()
        return False

    def _guard_active_plot_edit(self) -> bool:
        if self.visualization_draft.get_active_plot_draft() is None:
            return True
        self.workspace_controller.report_error(
            "Commit or cancel the active plot edit before changing the workspace or closing "
            "Carnopy."
        )
        return False

    def _queue_workspace_request(
        self,
        operation: str,
        path: str,
        detail: str = "",
        *,
        confirmed: bool = False,
    ) -> None:
        if self._queued_workspace_request is not None:
            return
        self._queued_workspace_request = (operation, path, detail, confirmed)
        self._workspace_request_timer.start()

    def _run_queued_workspace_request(self) -> None:
        request, self._queued_workspace_request = self._queued_workspace_request, None
        if request is None:
            return
        operation, path, detail, confirmed = request
        if operation == "cancel":
            self.cancel_workspace_operation()
            return
        if operation == "commit":
            self.commit_workspace_operation(confirmed)
            return
        if operation == "create":
            prepared = self.prepare_create_workspace(path, detail)
        elif operation == "create_path":
            prepared = self.prepare_create_workspace_path(path)
        elif operation == "initialize":
            prepared = self.prepare_initialize_workspace(path)
        else:
            prepared = self.prepare_open_workspace(path)
        if not prepared:
            return
        if self.get_workspace_confirmation_required():
            self.workspaceConfirmationRequested.emit()
            return
        self.commit_workspace_operation()


def _local_path(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("file:"):
        return candidate
    return QUrl(candidate).toLocalFile()


def _valid_workspace_child_name(value: str) -> bool:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        return False
    return not Path(value).is_absolute() and Path(value).name == value
