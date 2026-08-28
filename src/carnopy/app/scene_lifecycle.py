from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal

from carnopy.app.scene_contracts import SceneContractError
from carnopy.app.scene_controller import SceneController
from carnopy.app.scene_leases import (
    SceneCleanupReport,
    SceneLease,
    SceneSession,
    acquire_scene_session,
    cleanup_abandoned_scene_leases,
    remove_scene_lease,
)
from carnopy.app.workspace import Workspace


class SceneLeaseLifecycle(QObject):
    """Own workspace scene sessions and conservative lease retirement."""

    state_changed = Signal()

    def __init__(
        self,
        controller: SceneController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._workspace: Workspace | None = None
        self._session: SceneSession | None = None
        self._cleanup_issue = ""
        self._pending_retirements: dict[Path, SceneLease] = {}
        controller.lease_retirement_requested.connect(self._retire_lease)

    def get_cleanup_issue(self) -> str:
        return self._cleanup_issue

    cleanupIssue = Property(str, get_cleanup_issue, notify=state_changed)

    def get_session_available(self) -> bool:
        session = self._session
        return session is not None and session.is_active

    sessionAvailable = Property(bool, get_session_available, notify=state_changed)

    def get_workspace_root(self) -> str:
        workspace = self._workspace
        return "" if workspace is None else str(workspace.root)

    workspaceRoot = Property(str, get_workspace_root, notify=state_changed)

    @property
    def session(self) -> SceneSession | None:
        return self._session

    def set_workspace(self, workspace: Workspace | None) -> bool:
        """Release the old scene context, scan the new workspace, and lock it."""

        if self.controller.get_operation_active():
            raise RuntimeError("cannot replace scene workspace during an active request")
        if workspace == self._workspace and (workspace is None or self.get_session_available()):
            return self.get_session_available()
        self._cleanup_issue = ""
        self._release_workspace()
        if workspace is None:
            self.state_changed.emit()
            return False
        self._workspace = workspace
        self._scan_abandoned(workspace)
        try:
            session = acquire_scene_session(workspace.root)
        except SceneContractError as exc:
            self._set_cleanup_issue(
                f"Scene session could not be acquired for {workspace.root}: {exc.message}"
            )
            self.controller.set_scene_session(None)
            self.state_changed.emit()
            return False
        self._session = session
        self.controller.set_scene_session(session)
        self.state_changed.emit()
        return True

    def shutdown(self) -> None:
        """Release every owned scene lease and close the workspace session lock."""

        if self.controller.get_operation_active():
            raise RuntimeError("cannot shut down scene lifecycle during an active request")
        self._release_workspace()
        self.state_changed.emit()

    def _release_workspace(self) -> None:
        workspace = self._workspace
        session = self._session
        self.controller.reset_workspace_state()
        self.controller.set_scene_session(None)
        self._retry_pending_retirements()
        self._session = None
        self._workspace = None
        if session is not None:
            session.close()
        if workspace is not None:
            self._scan_abandoned(workspace)

    def _retire_lease(self, value: object) -> None:
        if not isinstance(value, SceneLease):
            self._set_cleanup_issue("Scene cleanup received an invalid lease identity.")
            return
        try:
            remove_scene_lease(value)
        except SceneContractError as exc:
            self._pending_retirements[value.path] = value
            self._set_cleanup_issue(f"Scene lease cleanup preserved {value.path}: {exc.message}")
            return
        self._pending_retirements.pop(value.path, None)
        self.state_changed.emit()

    def _retry_pending_retirements(self) -> None:
        for lease in tuple(self._pending_retirements.values()):
            try:
                remove_scene_lease(lease)
            except SceneContractError as exc:
                self._set_cleanup_issue(
                    f"Scene lease cleanup preserved {lease.path}: {exc.message}"
                )
            else:
                self._pending_retirements.pop(lease.path, None)

    def _scan_abandoned(self, workspace: Workspace) -> None:
        try:
            report = cleanup_abandoned_scene_leases(workspace.root)
        except SceneContractError as exc:
            self._set_cleanup_issue(
                f"Abandoned scene leases could not be scanned in {workspace.root}: {exc.message}"
            )
            return
        self._accept_cleanup_report(report)

    def _accept_cleanup_report(self, report: SceneCleanupReport) -> None:
        for path in report.removed:
            self._pending_retirements.pop(path, None)
        preserved = report.preserved
        if preserved:
            reasons = "; ".join(
                f"{entry.path}: {entry.reason}"
                for entry in report.entries
                if entry.action == "preserved"
            )
            self._set_cleanup_issue(f"Scene cleanup conservatively preserved: {reasons}")
        else:
            self.state_changed.emit()

    def _set_cleanup_issue(self, message: str) -> None:
        if message == self._cleanup_issue:
            return
        self._cleanup_issue = message
        self.state_changed.emit()
