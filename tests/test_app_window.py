from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from carnopy.app.window import PAGE_TITLES, MainWindow
from carnopy.app.workspace import initialize_workspace


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def settings_for(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_shell_has_six_workspace_gated_pages(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
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
    window.client.shutdown()
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


def test_recents_and_geometry_are_isolated_in_supplied_settings(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    settings_path = tmp_path / "settings.ini"
    workspace = initialize_workspace(tmp_path / "workspace")
    window = MainWindow(settings=settings_for(settings_path), initial_workspace=workspace.root)
    window.resize(900, 600)
    window.client.shutdown()
    window.close()

    settings = settings_for(settings_path)
    assert settings.value("recent_workspaces", [], type=list) == [str(workspace.root)]
    assert settings.contains("window_geometry")
    assert set(settings.allKeys()) == {"recent_workspaces", "window_geometry"}


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


def test_window_uses_one_shared_worker_client(tmp_path: Path, application: QApplication) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))

    assert window.configure_page.client is window.client
    assert window.execution_page.client is window.client
    assert window.inspection_page.client is window.client
    assert window.plot_page.client is window.client
    assert window.jobs_page.client is window.client
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
        scoped.setattr(type(window.client), "is_busy", property(lambda _self: True))
        window._create_workspace()

    assert not target.exists()
    assert "worker request is active" in window.workspace_status.text()
    window.close()


def test_close_during_plot_render_requires_force_stop_and_keeps_open_on_cleanup_error(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    window = MainWindow(settings=settings_for(tmp_path / "settings.ini"))
    window.plot_page._request_id = uuid4()
    stopped: list[bool] = []

    with monkeypatch.context() as scoped:
        scoped.setattr(type(window.client), "is_busy", property(lambda _self: True))
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
    window.plot_page._request_id = None
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
