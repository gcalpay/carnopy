from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSettings,
    Qt,
    QTimer,
    Signal,
)

from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import (
    Workspace,
    WorkspaceError,
    WorkspaceOperation,
    WorkspaceOperationPlan,
    commit_workspace_operation,
    preflight_workspace_operation,
)

RECENT_WORKSPACES_KEY = "recent_workspaces"
MAX_RECENT_WORKSPACES = 10
PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 1
INVALID_INDEX = QModelIndex()


class RecentWorkspaceModel(QAbstractListModel):
    """Expose canonical recent workspace paths without copying view state."""

    def __init__(
        self,
        paths: Iterable[str] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = tuple(paths)

    @property
    def paths(self) -> tuple[str, ...]:
        return self._paths

    def replace(self, paths: Iterable[str]) -> bool:
        updated = tuple(paths)
        if updated == self._paths:
            return False
        self.beginResetModel()
        self._paths = updated
        self.endResetModel()
        return True

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._paths)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._paths):
            return None
        if role in {int(Qt.ItemDataRole.DisplayRole), PATH_ROLE}:
            return self._paths[index.row()]
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            int(Qt.ItemDataRole.DisplayRole): QByteArray(b"display"),
            PATH_ROLE: QByteArray(b"path"),
        }


class WorkspaceController(QObject):
    """Own validated workspace state and trusted two-phase operations."""

    workspace_changed = Signal(object)
    available_changed = Signal()
    can_change_workspace_changed = Signal()
    paths_changed = Signal()
    status_message_changed = Signal()
    error_message_changed = Signal()
    pending_operation_changed = Signal()

    def __init__(
        self,
        coordinator: DesktopRequestCoordinator,
        settings: QSettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._coordinator = coordinator
        self._settings = settings
        self._workspace: Workspace | None = None
        self._can_change_workspace = not coordinator.is_busy
        self._status_message = "No workspace is open."
        self._error_message = ""
        self._pending_plan: WorkspaceOperationPlan | None = None
        restored = cast(
            list[object],
            settings.value(RECENT_WORKSPACES_KEY, [], type=list),
        )
        raw_paths = [str(value) for value in restored]
        recent_paths = _normalize_recent_paths(raw_paths)
        self.recent_model = RecentWorkspaceModel(recent_paths, self)
        self._pending_recent_paths: tuple[str, ...] | None = None
        self._recent_model_update_timer = QTimer(self)
        self._recent_model_update_timer.setSingleShot(True)
        self._recent_model_update_timer.timeout.connect(self._flush_recent_model_update)
        if raw_paths != list(recent_paths):
            settings.setValue(RECENT_WORKSPACES_KEY, list(recent_paths))
        coordinator.busy_changed.connect(self._busy_changed)

    @property
    def workspace(self) -> Workspace | None:
        return self._workspace

    @property
    def coordinator(self) -> DesktopRequestCoordinator:
        return self._coordinator

    def get_available(self) -> bool:
        return self._workspace is not None

    available = Property(bool, get_available, notify=available_changed)

    def get_can_change_workspace(self) -> bool:
        return self._can_change_workspace

    canChangeWorkspace = Property(
        bool,
        get_can_change_workspace,
        notify=can_change_workspace_changed,
    )

    def get_root_path(self) -> str:
        return self._active_path("root")

    rootPath = Property(str, get_root_path, notify=paths_changed)

    def get_configs_path(self) -> str:
        return self._active_path("configs")

    configsPath = Property(str, get_configs_path, notify=paths_changed)

    def get_outputs_path(self) -> str:
        return self._active_path("outputs")

    outputsPath = Property(str, get_outputs_path, notify=paths_changed)

    def get_figures_path(self) -> str:
        return self._active_path("figures")

    figuresPath = Property(str, get_figures_path, notify=paths_changed)

    def get_private_path(self) -> str:
        return self._active_path("private_directory")

    privatePath = Property(str, get_private_path, notify=paths_changed)

    def get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, get_status_message, notify=status_message_changed)

    def get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, get_error_message, notify=error_message_changed)

    def get_pending_operation(self) -> str:
        plan = self._pending_plan
        return "" if plan is None else plan.operation

    pendingOperation = Property(
        str,
        get_pending_operation,
        notify=pending_operation_changed,
    )

    def get_pending_path(self) -> str:
        plan = self._pending_plan
        return "" if plan is None else str(plan.workspace.root)

    pendingPath = Property(str, get_pending_path, notify=pending_operation_changed)

    def get_recent_workspaces(self) -> QObject:
        return self.recent_model

    recentWorkspaces = Property(QObject, get_recent_workspaces, constant=True)

    def prepare_create(self, path: str | Path) -> bool:
        return self._prepare(path, "create")

    def prepare_initialize_existing(self, path: str | Path) -> bool:
        return self._prepare(path, "initialize_existing")

    def prepare_open(self, path: str | Path) -> bool:
        return self._prepare(path, "open")

    def commit_pending(self) -> bool:
        plan = self._pending_plan
        self._set_pending_plan(None)
        if plan is None:
            self._set_error("No workspace operation is pending.")
            return False
        if self._coordinator.is_busy:
            self._set_error(_BUSY_MESSAGE)
            return False
        self._set_error("")
        try:
            workspace = commit_workspace_operation(plan)
        except (OSError, WorkspaceError) as exc:
            self._set_error(str(exc))
            return False
        self._activate(workspace)
        return True

    def cancel_pending(self) -> None:
        self._set_pending_plan(None)

    def report_error(self, message: str) -> None:
        self._set_error(message)

    def _prepare(self, path: str | Path, operation: WorkspaceOperation) -> bool:
        self.cancel_pending()
        self._set_error("")
        if self._coordinator.is_busy:
            self._set_error(_BUSY_MESSAGE)
            return False
        candidate = str(path).strip()
        if not candidate:
            self._set_error("Choose a workspace folder first.")
            return False
        try:
            plan = preflight_workspace_operation(Path(candidate), operation)
        except (OSError, WorkspaceError) as exc:
            self._set_error(str(exc))
            return False
        self._set_pending_plan(plan)
        return True

    def _activate(self, workspace: Workspace) -> None:
        previous = self._workspace
        changed = previous != workspace
        availability_changed = (previous is None) != (workspace is None)
        self._workspace = workspace
        self._set_error("")
        self._set_status(f"Open workspace: {workspace.root}")
        self._remember_workspace(workspace.root)
        if not changed:
            return
        if availability_changed:
            self.available_changed.emit()
        self.paths_changed.emit()
        self.workspace_changed.emit(workspace)

    def _remember_workspace(self, path: Path) -> None:
        current = self._pending_recent_paths or self.recent_model.paths
        value = str(path.expanduser().resolve())
        updated = _normalize_recent_paths((value, *current))
        if updated == current:
            return
        self._pending_recent_paths = updated
        self._settings.setValue(RECENT_WORKSPACES_KEY, list(updated))
        self._recent_model_update_timer.start(0)

    def _flush_recent_model_update(self) -> None:
        updated, self._pending_recent_paths = self._pending_recent_paths, None
        if updated is not None:
            self.recent_model.replace(updated)

    def _active_path(self, attribute: str) -> str:
        workspace = self._workspace
        if workspace is None:
            return ""
        return str(getattr(workspace, attribute))

    def _busy_changed(self, busy: bool) -> None:
        if not busy and self._error_message == _BUSY_MESSAGE:
            self._set_error("")
        updated = not busy
        if updated == self._can_change_workspace:
            return
        self._can_change_workspace = updated
        self.can_change_workspace_changed.emit()

    def _set_status(self, message: str) -> None:
        if message == self._status_message:
            return
        self._status_message = message
        self.status_message_changed.emit()

    def _set_error(self, message: str) -> None:
        if message == self._error_message:
            return
        self._error_message = message
        self.error_message_changed.emit()

    def _set_pending_plan(self, plan: WorkspaceOperationPlan | None) -> None:
        if plan == self._pending_plan:
            return
        self._pending_plan = plan
        self.pending_operation_changed.emit()


_BUSY_MESSAGE = (
    "A worker request is active. Wait for it to finish or stop it before "
    "creating, initializing, or opening another workspace."
)


def _normalize_recent_paths(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        try:
            canonical = str(Path(value).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
        if canonical in normalized:
            continue
        normalized.append(canonical)
        if len(normalized) == MAX_RECENT_WORKSPACES:
            break
    return tuple(normalized)
