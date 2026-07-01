from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
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
