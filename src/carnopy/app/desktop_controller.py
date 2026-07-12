from __future__ import annotations

from PySide6.QtCore import Property, QObject, QSettings

from carnopy.app.client import WorkerClient
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace_controller import WorkspaceController


class DesktopController(QObject):
    """Compose the process-wide desktop state and worker transport."""

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings()
        self.client = WorkerClient(self)
        self.request_coordinator = DesktopRequestCoordinator(self.client, self)
        self.workspace_controller = WorkspaceController(
            self.request_coordinator,
            self.settings,
            self,
        )
        self._shutdown = False

    def get_workspace_controller(self) -> QObject:
        return self.workspace_controller

    workspaceController = Property(QObject, get_workspace_controller, constant=True)

    def shutdown(self) -> bool:
        self.workspace_controller.cancel_pending()
        if self.request_coordinator.is_busy:
            return False
        if self._shutdown:
            return True
        self.request_coordinator.shutdown()
        self.settings.sync()
        self._shutdown = True
        return True
