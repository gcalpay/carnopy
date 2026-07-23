from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_settings import (
    INSPECTOR_COLLAPSED_KEY,
    MAXIMIZED_KEY,
    NORMAL_GEOMETRY_KEY,
    NORMAL_SCREEN_KEY,
    RAIL_COLLAPSED_KEY,
    REDUCED_MOTION_KEY,
    THEME_MODE_KEY,
    WINDOW_STATE_VERSION,
    WINDOW_STATE_VERSION_KEY,
    QmlSettingsController,
    clamp_window_geometry,
)


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def settings_for(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_qml_settings_persist_namespaced_preferences_in_shared_settings(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    settings.setValue("recent_workspaces", ["/tmp/example"])
    controller = QmlSettingsController(settings)

    controller.set_theme_mode("dark")
    controller.set_reduced_motion(True)
    controller.set_rail_collapsed(True)
    controller.set_inspector_collapsed(True)
    controller.remember_normal_screen("rdp-2")
    controller.set_maximized(True)
    settings.sync()

    restored = QmlSettingsController(settings)
    assert restored.get_theme_mode() == "dark"
    assert restored.get_effective_theme() == "dark"
    assert restored.get_reduced_motion()
    assert restored.get_rail_collapsed()
    assert restored.get_inspector_collapsed()
    assert restored.get_normal_screen_name() == "rdp-2"
    assert restored.get_maximized()
    assert settings.value("recent_workspaces", [], type=list) == ["/tmp/example"]
    assert {
        THEME_MODE_KEY,
        REDUCED_MOTION_KEY,
        RAIL_COLLAPSED_KEY,
        INSPECTOR_COLLAPSED_KEY,
        NORMAL_SCREEN_KEY,
        MAXIMIZED_KEY,
        WINDOW_STATE_VERSION_KEY,
    }.issubset(settings.allKeys())


def test_obsolete_window_state_resets_once_without_losing_other_preferences(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "obsolete.ini")
    settings.setValue(THEME_MODE_KEY, "dark")
    settings.setValue("window_geometry", b"widgets-owned-geometry")
    settings.setValue("recent_workspaces", ["/tmp/example"])
    settings.setValue(NORMAL_GEOMETRY_KEY, QRect(2500, 900, 1800, 1200))
    settings.setValue(NORMAL_SCREEN_KEY, "removed-screen")
    settings.setValue(MAXIMIZED_KEY, True)

    controller = QmlSettingsController(settings)

    assert controller.get_theme_mode() == "dark"
    assert controller.get_normal_screen_name() == ""
    assert not controller.get_maximized()
    assert settings.value(WINDOW_STATE_VERSION_KEY) == WINDOW_STATE_VERSION
    assert settings.value(NORMAL_SCREEN_KEY) is None
    assert settings.value("window_geometry") == b"widgets-owned-geometry"
    assert settings.value("recent_workspaces", [], type=list) == ["/tmp/example"]


def test_theme_mode_is_validated_and_system_mode_has_concrete_effective_theme(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    controller = QmlSettingsController(settings_for(tmp_path / "settings.ini"))
    observed_modes: list[str] = []
    controller.themeModeChanged.connect(lambda: observed_modes.append(controller.get_theme_mode()))

    assert controller.get_theme_mode() == "dark"
    assert controller.get_effective_theme() == "dark"
    controller.set_theme_mode("dark")
    controller.set_theme_mode("unsupported")
    controller.set_theme_mode("warm")
    assert controller.get_effective_theme() == "warm"
    controller.set_theme_mode("light")
    controller.set_theme_mode("system")

    assert observed_modes == ["warm", "light", "system"]
    assert controller.get_theme_mode() == "system"
    assert controller.get_effective_theme() in {"light", "dark"}


def test_missing_theme_mode_defaults_to_dark_without_mutating_shared_settings(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "theme-missing.ini")

    controller = QmlSettingsController(settings)

    assert controller.get_theme_mode() == "dark"
    assert controller.get_effective_theme() == "dark"
    assert not settings.contains(THEME_MODE_KEY)


@pytest.mark.parametrize("stored", ["unsupported", 42])
def test_invalid_theme_mode_migrates_to_persisted_dark(
    tmp_path: Path,
    application: QGuiApplication,
    stored: object,
) -> None:
    del application
    settings = settings_for(tmp_path / f"theme-{stored!s}.ini")
    settings.setValue(THEME_MODE_KEY, stored)

    controller = QmlSettingsController(settings)

    assert controller.get_theme_mode() == "dark"
    assert controller.get_effective_theme() == "dark"
    assert settings.value(THEME_MODE_KEY) == "dark"


def test_existing_warm_theme_mode_is_preserved(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "warm.ini")
    settings.setValue(THEME_MODE_KEY, "warm")

    controller = QmlSettingsController(settings)

    assert controller.get_theme_mode() == "warm"
    assert controller.get_effective_theme() == "warm"
    assert settings.value(THEME_MODE_KEY) == "warm"


def test_system_color_scheme_changes_update_only_system_mode(
    tmp_path: Path,
    application: QGuiApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller = QmlSettingsController(settings_for(tmp_path / "settings.ini"))
    original_resolver = controller._resolve_effective_theme
    observed: list[str] = []
    controller.effectiveThemeChanged.connect(
        lambda: observed.append(controller.get_effective_theme())
    )
    controller.set_theme_mode("system")
    observed.clear()
    replacement = "dark" if controller.get_effective_theme() == "light" else "light"
    monkeypatch.setattr(controller, "_resolve_effective_theme", lambda: replacement)

    controller._system_theme_changed(Qt.ColorScheme.Dark)
    assert controller.get_effective_theme() == replacement
    assert observed == [replacement]

    monkeypatch.setattr(controller, "_resolve_effective_theme", original_resolver)
    controller.set_theme_mode("light")
    observed.clear()
    controller._system_theme_changed(Qt.ColorScheme.Dark)
    assert controller.get_effective_theme() == "light"
    assert observed == []


def test_layout_reset_preserves_theme_accessibility_and_unrelated_settings(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    screen = application.primaryScreen().availableGeometry()
    settings = settings_for(tmp_path / "settings.ini")
    settings.setValue("recent_workspaces", ["/tmp/example"])
    controller = QmlSettingsController(settings)
    controller.set_theme_mode("dark")
    controller.set_reduced_motion(True)
    controller.set_rail_collapsed(True)
    controller.set_inspector_collapsed(True)
    controller.remember_normal_screen("rdp-2")
    controller.rememberNormalGeometry(
        screen.x() + 8,
        screen.y() + 8,
        max(1, screen.width() - 16),
        max(1, screen.height() - 16),
    )
    controller.set_maximized(True)

    controller.resetLayout()

    assert controller.get_theme_mode() == "dark"
    assert controller.get_reduced_motion()
    assert not controller.get_rail_collapsed()
    assert not controller.get_inspector_collapsed()
    assert controller.get_normal_screen_name() == ""
    assert not controller.get_maximized()
    assert settings.value("recent_workspaces", [], type=list) == ["/tmp/example"]
    assert THEME_MODE_KEY in settings.allKeys()
    assert REDUCED_MOTION_KEY in settings.allKeys()
    assert RAIL_COLLAPSED_KEY not in settings.allKeys()
    assert INSPECTOR_COLLAPSED_KEY not in settings.allKeys()
    assert NORMAL_GEOMETRY_KEY not in settings.allKeys()
    assert NORMAL_SCREEN_KEY not in settings.allKeys()
    assert MAXIMIZED_KEY not in settings.allKeys()


def test_layout_toggle_slots_change_each_preference_once(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    controller = QmlSettingsController(settings)
    rail_changes: list[bool] = []
    inspector_changes: list[bool] = []
    controller.railCollapsedChanged.connect(
        lambda: rail_changes.append(controller.get_rail_collapsed())
    )
    controller.inspectorCollapsedChanged.connect(
        lambda: inspector_changes.append(controller.get_inspector_collapsed())
    )

    assert controller.toggleRailCollapsed()
    assert controller.toggleInspectorCollapsed()
    assert not controller.toggleRailCollapsed()
    assert not controller.toggleInspectorCollapsed()

    assert rail_changes == [True, False]
    assert inspector_changes == [True, False]
    assert settings.value(RAIL_COLLAPSED_KEY, type=bool) is False
    assert settings.value(INSPECTOR_COLLAPSED_KEY, type=bool) is False


def test_geometry_clamping_uses_logical_screen_bounds() -> None:
    first = QRect(0, 0, 1920, 1080)
    second = QRect(1920, 0, 2560, 1440)

    assert clamp_window_geometry(QRect(2100, 100, 1440, 900), (first, second)) == QRect(
        2100,
        100,
        1440,
        900,
    )
    assert clamp_window_geometry(QRect(4300, 1200, 1200, 900), (first, second)) == QRect(
        3280,
        540,
        1200,
        900,
    )
    assert clamp_window_geometry(QRect(-5000, -5000, 800, 600), (first, second)) == QRect(
        0,
        0,
        800,
        600,
    )
    assert clamp_window_geometry(QRect(0, 0, 5000, 3000), (first, second)) == second
    assert clamp_window_geometry(QRect(), (first, second)) == QRect(240, 90, 1440, 900)


def test_remembered_geometry_is_clamped_and_restored(
    tmp_path: Path,
    application: QGuiApplication,
) -> None:
    screen = application.primaryScreen().availableGeometry()
    settings = settings_for(tmp_path / "settings.ini")
    controller = QmlSettingsController(settings)

    controller.rememberNormalGeometry(
        screen.x() + screen.width() - 20,
        screen.y() + screen.height() - 20,
        min(600, screen.width()),
        min(500, screen.height()),
    )
    saved = controller.get_normal_geometry()
    settings.sync()

    assert screen.contains(saved)
    assert settings.value(NORMAL_GEOMETRY_KEY) == saved
    assert QmlSettingsController(settings).get_normal_geometry() == saved
