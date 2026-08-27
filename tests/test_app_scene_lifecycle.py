from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QObject, QSettings, Signal

from carnopy.app.desktop_controller import DesktopController
from carnopy.app.jobs import JobStore
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.scene_contracts import SceneContractError
from carnopy.app.scene_controller import SceneController
from carnopy.app.scene_leases import (
    SceneLease,
    acquire_scene_session,
    create_scene_lease,
)
from carnopy.app.scene_lifecycle import SceneLeaseLifecycle
from carnopy.app.workspace import initialize_workspace


class IdleCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    return existing if isinstance(existing, QCoreApplication) else QCoreApplication([])


def _lifecycle() -> tuple[SceneController, SceneLeaseLifecycle]:
    coordinator = IdleCoordinator()
    controller = SceneController(cast(DesktopRequestCoordinator, coordinator))
    lifecycle = SceneLeaseLifecycle(controller)
    return controller, lifecycle


def _settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_scene_lifecycle_cleans_startup_replacement_and_shutdown_leases(
    application: QCoreApplication,
    tmp_path: Path,
) -> None:
    del application
    first = initialize_workspace(tmp_path / "first")
    second = initialize_workspace(tmp_path / "second")
    abandoned_session = acquire_scene_session(first.root)
    abandoned = create_scene_lease(abandoned_session)
    abandoned_session.close()
    controller, lifecycle = _lifecycle()

    assert lifecycle.set_workspace(first)
    assert not abandoned.path.exists()
    assert lifecycle.session is not None and lifecycle.session.is_active
    assert controller.get_scene_session_available()

    active_first_session = lifecycle.session
    assert active_first_session is not None
    retired = create_scene_lease(active_first_session)
    controller.lease_retirement_requested.emit(retired)
    assert not retired.path.exists()

    replacement_orphan = create_scene_lease(active_first_session)
    first_session = lifecycle.session
    assert lifecycle.set_workspace(second)
    assert first_session is not None and not first_session.is_active
    assert not replacement_orphan.path.exists()
    assert lifecycle.get_workspace_root() == str(second.root)

    active_second_session = lifecycle.session
    assert active_second_session is not None
    shutdown_orphan = create_scene_lease(active_second_session)
    second_session = lifecycle.session
    lifecycle.shutdown()

    assert second_session is not None and not second_session.is_active
    assert not shutdown_orphan.path.exists()
    assert not lifecycle.get_session_available()
    assert not controller.get_scene_session_available()


def test_scene_lifecycle_preserves_live_foreign_lease_and_reports_reason(
    application: QCoreApplication,
    tmp_path: Path,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    foreign_session = acquire_scene_session(workspace.root)
    foreign = create_scene_lease(foreign_session)
    _controller, lifecycle = _lifecycle()
    try:
        assert lifecycle.set_workspace(workspace)
        assert foreign.path.is_dir()
        assert "conservatively preserved" in lifecycle.get_cleanup_issue()
        assert "lock is held" in lifecycle.get_cleanup_issue()
    finally:
        lifecycle.shutdown()
        foreign_session.close()

    retry_controller, retry = _lifecycle()
    del retry_controller
    assert retry.set_workspace(workspace)
    assert not foreign.path.exists()
    retry.shutdown()


def test_startup_cleanup_removes_abandoned_and_preserves_real_process_lease(
    application: QCoreApplication,
    tmp_path: Path,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    abandoned_session = acquire_scene_session(workspace.root)
    abandoned = create_scene_lease(abandoned_session)
    abandoned_session.close()
    script = """
import json
import os
import sys
from pathlib import Path
from carnopy.app.scene_leases import acquire_scene_session, create_scene_lease

session = acquire_scene_session(Path(sys.argv[1]))
lease = create_scene_lease(session)
print(json.dumps({"path": str(lease.path)}), flush=True)
sys.stdin.readline()
os._exit(0)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(workspace.root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    controller, lifecycle = _lifecycle()
    del controller
    retry: SceneLeaseLifecycle | None = None
    try:
        child = json.loads(process.stdout.readline())
        live_path = Path(child["path"])

        assert lifecycle.set_workspace(workspace)
        assert not abandoned.path.exists()
        assert live_path.is_dir()
        assert "conservatively preserved" in lifecycle.get_cleanup_issue()
        assert "lock is held" in lifecycle.get_cleanup_issue()
        lifecycle.shutdown()

        process.stdin.write("release\n")
        process.stdin.flush()
        return_code = process.wait(timeout=10)
        assert return_code == 0, process.stderr.read() if process.stderr is not None else ""

        retry_controller, retry = _lifecycle()
        del retry_controller
        assert retry.set_workspace(workspace)
        assert not live_path.exists()
    finally:
        lifecycle.shutdown()
        if retry is not None:
            retry.shutdown()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_scene_lifecycle_cleanup_failure_is_preserved_and_retried(
    application: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    controller, lifecycle = _lifecycle()
    assert lifecycle.set_workspace(workspace)
    active_session = lifecycle.session
    assert active_session is not None
    lease = create_scene_lease(active_session)

    def fail_cleanup(_lease: SceneLease) -> None:
        raise SceneContractError("scene_cleanup_failed", "injected cleanup failure")

    with monkeypatch.context() as scoped:
        scoped.setattr("carnopy.app.scene_lifecycle.remove_scene_lease", fail_cleanup)
        controller.lease_retirement_requested.emit(lease)

    assert lease.path.is_dir()
    assert "injected cleanup failure" in lifecycle.get_cleanup_issue()

    lifecycle.shutdown()

    assert not lease.path.exists()


def test_desktop_composes_scene_lifecycle_without_activity_records(
    application: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=_settings(tmp_path / "settings.ini"))
    monkeypatch.setattr(desktop.configuration_controller, "set_workspace", lambda _value: None)
    parent = tmp_path / "parent"
    parent.mkdir()
    target = parent / "workspace"

    assert desktop.prepare_create_workspace(str(parent), target.name)
    assert desktop.commit_workspace_operation()
    workspace = desktop.workspace_controller.workspace
    assert workspace is not None

    assert desktop.scene_controller.parent() is desktop
    assert desktop.scene_controller.coordinator is desktop.request_coordinator
    assert desktop.scene_lifecycle.parent() is desktop
    assert desktop.scene_lifecycle.controller is desktop.scene_controller
    assert desktop.property("sceneController") is desktop.scene_controller
    assert desktop.scene_lifecycle.get_workspace_root() == str(workspace.root)
    assert desktop.scene_lifecycle.get_session_available()
    assert JobStore(workspace.private_directory).load() == []

    session = desktop.scene_lifecycle.session
    assert desktop.shutdown()
    assert session is not None and not session.is_active
    assert JobStore(workspace.private_directory).load() == []


@pytest.mark.parametrize("request_type", ["build_scene", "resolve_scene_pick"])
def test_scene_busy_shutdown_cancels_then_uses_delayed_safe_force_stop(
    application: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_type: str,
) -> None:
    del application
    desktop = DesktopController(settings=_settings(tmp_path / "settings.ini"))
    confirmations: list[tuple[str, str]] = []
    actions: list[str] = []
    closes: list[str] = []
    session = type(
        "SceneSessionStub",
        (),
        {
            "owner": "scene",
            "request_type": request_type,
            "termination_protected": False,
        },
    )()
    desktop.request_coordinator._active_session = session
    desktop.busyShutdownConfirmationRequested.connect(
        lambda mode, message: confirmations.append((mode, message))
    )
    desktop.closeWindowRequested.connect(lambda: closes.append("close"))
    availability = {"cancel": True, "force": False, "protected": False}
    monkeypatch.setattr(
        desktop.scene_controller,
        "get_cancellation_available",
        lambda: availability["cancel"],
    )
    monkeypatch.setattr(
        desktop.scene_controller,
        "get_force_stop_available",
        lambda: availability["force"],
    )
    monkeypatch.setattr(
        desktop.scene_controller,
        "get_protected_finalization",
        lambda: availability["protected"],
    )

    def cancel_scene() -> bool:
        actions.append("cancel")
        availability["cancel"] = False
        return True

    def force_stop_scene() -> bool:
        actions.append("force")
        return True

    monkeypatch.setattr(desktop.scene_controller, "cancel", cancel_scene)
    monkeypatch.setattr(desktop.scene_controller, "force_stop", force_stop_scene)

    assert not desktop.request_shutdown()
    assert confirmations[0][0] == "cancel_scene"
    assert "safety delay" in confirmations[0][1]
    assert desktop.confirm_busy_shutdown(True)
    assert actions == ["cancel"]
    assert desktop._pending_busy_shutdown == "scene_cancelling"

    availability.update(force=True, protected=True)
    desktop._continue_pending_busy_shutdown()
    assert actions == ["cancel"]
    assert desktop._pending_busy_shutdown == "scene_cancelling"

    availability["protected"] = False
    desktop._continue_pending_busy_shutdown()
    assert actions == ["cancel", "force"]
    assert desktop._pending_busy_shutdown == "scene"

    desktop.request_coordinator._active_session = None
    desktop._complete_busy_shutdown()
    assert closes == ["close"]
