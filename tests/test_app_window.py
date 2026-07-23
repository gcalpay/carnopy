from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QAbstractListModel, QEventLoop, QModelIndex, QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QListView, QMessageBox

from carnopy.app.desktop_controller import DesktopController
from carnopy.app.qml_settings import WINDOW_STATE_VERSION_KEY
from carnopy.app.window import PAGE_TITLES, MainWindow
from carnopy.app.workspace import initialize_workspace
from carnopy.app.workspace_controller import PATH_ROLE

INVALID_MODEL_INDEX = QModelIndex()


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def settings_for(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def wait_for_idle(application: QApplication, window: MainWindow) -> None:
    if not window.coordinator.is_busy:
        return
    loop = QEventLoop()
    window.coordinator.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    application.processEvents()
    assert not window.coordinator.is_busy


def test_shell_has_six_workspace_gated_pages(
    tmp_path: Path,
    application: QApplication,
) -> None:
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))

    assert window.navigation.count() == 6
    assert tuple(window.navigation.item(index).text() for index in range(6)) == PAGE_TITLES
    for index in range(1, 6):
        assert not (window.navigation.item(index).flags() & Qt.ItemFlag.ItemIsEnabled)
        assert not window.pages.widget(index).isEnabled()

    workspace = initialize_workspace(tmp_path / "workspace")
    window.workspace_path.setText(str(workspace.root))
    window._open_selected_workspace()

    assert window.workspace == workspace
    for index in range(1, 6):
        assert window.navigation.item(index).flags() & Qt.ItemFlag.ItemIsEnabled
        assert window.pages.widget(index).isEnabled()
    wait_for_idle(application, window)
    window.close()


def test_uninitialized_startup_path_is_preselected_but_not_created(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    root = tmp_path / "not-initialized"

    window = MainWindow(
        settings=settings_for(tmp_path / "settings.ini"),
        initial_workspace=root,
    )

    assert window.workspace is None
    assert window.workspace_path.text() == str(root.resolve())
    assert not root.exists()
    assert "does not exist" in window.workspace_status.text()
    window.close()


def test_recents_are_isolated_in_supplied_settings(
    tmp_path: Path,
    application: QApplication,
) -> None:
    settings_path = tmp_path / "settings.ini"
    workspace = initialize_workspace(tmp_path / "workspace")
    window = MainWindow(settings=settings_for(settings_path), initial_workspace=workspace.root)
    window.resize(900, 600)
    wait_for_idle(application, window)
    window.close()

    settings = settings_for(settings_path)
    assert settings.value("recent_workspaces", [], type=list) == [str(workspace.root)]
    assert set(settings.allKeys()) == {"recent_workspaces", WINDOW_STATE_VERSION_KEY}


def test_stale_window_geometry_is_ignored(
    tmp_path: Path,
    application: QApplication,
) -> None:
    settings = settings_for(tmp_path / "settings.ini")
    stale = MainWindow(settings=settings)
    stale.move(-100_000, -100_000)
    settings.setValue("window_geometry", stale.saveGeometry())
    stale.coordinator.shutdown()
    stale.close()

    window = MainWindow(settings=settings)
    window.center_on_primary_screen()
    primary = application.primaryScreen()
    assert primary is not None
    assert primary.availableGeometry().intersects(window.frameGeometry())
    window.coordinator.shutdown()
    window.close()


def test_window_can_show_and_close_offscreen(
    tmp_path: Path,
    application: QApplication,
) -> None:
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    window.show()
    application.processEvents()
    assert window.isVisible()
    window.close()
    application.processEvents()
    assert not window.isVisible()


def test_window_uses_one_shared_request_coordinator(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))

    assert window.desktop_controller.client is window.client
    assert window.desktop_controller.workspace_controller is window.workspace_controller
    assert window.dataset_config_controller is window.desktop_controller.dataset_config_controller
    assert window.coordinator.client is window.client
    assert window.configure_page.controller is window.dataset_config_controller
    assert window.configure_page.desktop_controller is window.desktop_controller
    assert window.configure_page.coordinator is window.coordinator
    assert window.configure_page.dataset_draft is window.desktop_controller.dataset_draft
    assert (
        window.configure_page.visualization_draft is window.desktop_controller.visualization_draft
    )
    assert (
        window.configure_page.visualization.draft is window.desktop_controller.visualization_draft
    )
    assert window.execution_page.coordinator is window.coordinator
    assert window.inspection_page.coordinator is window.coordinator
    assert window.plot_page.coordinator is window.coordinator
    window.close()


def test_window_accepts_injected_composition_root_but_not_two_settings_sources(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    window = MainWindow(desktop_controller=desktop)

    assert window.desktop_controller is desktop
    assert window.settings is desktop.settings
    assert window.recent_workspaces.model() is desktop.workspace_controller.recent_model

    with pytest.raises(ValueError, match="either desktop_controller or settings"):
        MainWindow(
            desktop_controller=desktop,
            settings=settings_for(tmp_path / "other.ini"),
        )
    window.close()


def test_workspace_changes_are_blocked_before_side_effects_while_worker_is_busy(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    target = tmp_path / "must-not-exist"
    window.workspace_path.setText(str(target))

    with monkeypatch.context() as scoped:
        scoped.setattr(type(window.coordinator), "is_busy", property(lambda _self: True))
        window._create_workspace()

    assert not target.exists()
    assert "worker request is active" in window.workspace_status.text()
    window.close()


def test_dirty_draft_cancellation_happens_before_workspace_mutation(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    window = MainWindow(settings=settings)
    target = tmp_path / "must-remain-absent"
    window.workspace_path.setText(str(target))
    monkeypatch.setattr(window.configure_page, "confirm_discard", lambda: False)

    window._create_workspace()

    assert not target.exists()
    assert window.workspace is None
    assert window.workspace_controller.get_pending_operation() == ""
    assert window.workspace_controller.recent_model.paths == ()
    assert settings.value("recent_workspaces", [], type=list) == []
    window.close()


def test_initialization_confirmation_cancellation_is_non_writing(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    target = tmp_path / "existing"
    target.mkdir()
    note = target / "note.txt"
    note.write_text("unchanged", encoding="utf-8")
    window.workspace_path.setText(str(target))
    monkeypatch.setattr(window.configure_page, "confirm_discard", lambda: True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    window._initialize_existing_workspace()

    assert note.read_text(encoding="utf-8") == "unchanged"
    assert not (target / ".carnopy-gui").exists()
    assert window.workspace is None
    assert window.workspace_controller.get_pending_operation() == ""
    window.close()


def test_opening_active_workspace_skips_discard_and_page_reset(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    window = MainWindow(
        settings=settings_for(tmp_path / "settings.ini"),
        initial_workspace=workspace.root,
    )
    wait_for_idle(application, window)
    propagated: list[str] = []
    monkeypatch.setattr(
        window.dataset_config_controller,
        "set_workspace",
        lambda _workspace: propagated.append("configuration"),
    )
    for name, page in (
        ("execution", window.execution_page),
        ("inspection", window.inspection_page),
        ("plot", window.plot_page),
        ("jobs", window.jobs_page),
        ("sources", window.sources_panel),
    ):
        monkeypatch.setattr(
            page,
            "set_workspace",
            lambda _workspace, name=name: propagated.append(name),
        )
    with monkeypatch.context() as scoped:
        scoped.setattr(
            window.configure_page,
            "confirm_discard",
            lambda: pytest.fail("active workspace must not ask for discard"),
        )
        window._open_selected_workspace()

    assert window.workspace == workspace
    assert propagated == []
    window.close()


class _RoleTrackingModel(QAbstractListModel):
    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self.roles: list[int] = []

    def rowCount(self, _parent: QModelIndex = INVALID_MODEL_INDEX) -> int:
        return 1

    def data(
        self,
        index: QModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid():
            return None
        self.roles.append(role)
        if role == PATH_ROLE:
            return self.path
        if role == int(Qt.ItemDataRole.DisplayRole):
            return "display-only"
        return None


def test_recent_activation_uses_path_role(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    path = str((tmp_path / "canonical-workspace").resolve())
    model = _RoleTrackingModel(path)
    window.recent_workspaces.setModel(model)
    prepared: list[str | Path] = []
    monkeypatch.setattr(
        window.workspace_controller,
        "prepare_open",
        lambda value: prepared.append(value) or False,
    )

    window._open_recent_workspace(model.index(0, 0))

    assert isinstance(window.recent_workspaces, QListView)
    assert prepared == [path]
    assert PATH_ROLE in model.roles
    assert window.workspace_path.text() == path
    window.close()


def test_successful_activation_propagates_once_to_every_workspace_page(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    propagated: list[str] = []
    monkeypatch.setattr(
        window.dataset_config_controller,
        "set_workspace",
        lambda _workspace: propagated.append("configuration"),
    )
    for name, page in (
        ("execution", window.execution_page),
        ("inspection", window.inspection_page),
        ("plot", window.plot_page),
        ("jobs", window.jobs_page),
        ("sources", window.sources_panel),
    ):
        monkeypatch.setattr(
            page,
            "set_workspace",
            lambda _workspace, name=name: propagated.append(name),
        )
    target = tmp_path / "workspace"
    window.workspace_path.setText(str(target))

    window._create_workspace()

    assert window.workspace is not None
    assert window.workspace.root == target.resolve()
    assert propagated == [
        "configuration",
        "execution",
        "inspection",
        "plot",
        "jobs",
        "sources",
    ]
    window.close()


def test_failed_open_preserves_active_workspace_and_page_state(
    tmp_path: Path,
    application: QApplication,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    window = MainWindow(
        settings=settings_for(tmp_path / "settings.ini"),
        initial_workspace=workspace.root,
    )
    wait_for_idle(application, window)
    prior_config_workspace = window.configure_page.workspace
    missing = tmp_path / "missing"
    window.workspace_path.setText(str(missing))

    window._open_selected_workspace()

    assert window.workspace == workspace
    assert window.configure_page.workspace is prior_config_workspace
    assert window.workspace_path.text() == str(missing)
    assert "does not exist" in window.workspace_status.text()
    window.close()


def test_close_during_plot_render_requires_force_stop_and_keeps_open_on_cleanup_error(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    stopped: list[bool] = []

    with monkeypatch.context() as scoped:
        scoped.setattr(type(window.coordinator), "is_busy", property(lambda _self: True))
        scoped.setattr(type(window.coordinator), "active_owner", property(lambda _self: "plot"))
        scoped.setattr(window, "_confirm_force_stop_and_close", lambda: True)
        scoped.setattr(
            window.plot_page,
            "force_stop",
            lambda *, confirm: stopped.append(confirm) or True,
        )
        event = QCloseEvent()
        window.closeEvent(event)

    assert not event.isAccepted()
    assert stopped == [False]
    assert window._close_after_plot_stop

    window._plot_render_finished({"cleanup_error": "simulated cleanup failure"})

    assert not window._close_after_plot_stop
    assert window.navigation.currentRow() == 4
    assert "cleanup failed" in window.workspace_status.text()
    window.close()


def test_importing_gui_window_does_not_load_scientific_dependencies() -> None:
    code = """
import sys
import carnopy.app.window
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.app.source_inspection",
    "carnopy.app.table_preview",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
