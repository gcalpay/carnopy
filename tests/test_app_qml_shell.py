from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QAbstractItemModel, QCoreApplication, QObject, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime

ROOT = Path(__file__).resolve().parents[1]

NAVIGATION_ORDER = (
    "Workspace",
    "Dataset",
    "Visualization",
    "YAML Preview",
    "Run",
    "Inspect",
    "Activity and Recovery",
    "Model Sweeps",
    "ML Preparation",
    "3D",
)


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.fixture
def runtime(
    tmp_path: Path,
    application: QApplication,
) -> QmlApplicationRuntime:
    del application
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    yield created
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(3):
        application.processEvents()


def _set_size(root: QObject, width: int, height: int) -> None:
    assert root.setProperty("width", width)
    assert root.setProperty("height", height)
    _process_events()


def _role(model: QAbstractItemModel, name: bytes) -> int:
    return next(role for role, role_name in model.roleNames().items() if role_name == name)


def test_shell_uses_exact_navigation_order_and_disables_future_workflows(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    models = root.findChildren(QAbstractItemModel, "primaryNavigationModel")
    assert models
    model = models[0]
    title_role = _role(model, b"title")
    available_role = _role(model, b"available")

    assert (
        tuple(model.data(model.index(row, 0), title_role) for row in range(model.rowCount()))
        == NAVIGATION_ORDER
    )
    assert tuple(
        model.data(model.index(row, 0), available_role) for row in range(model.rowCount())
    ) == (True, False, False, False, False, False, False, False, False, False)

    nav_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/NavRail.qml").read_text(
        encoding="utf-8"
    )
    assert "activeFocusOnTab: available" in nav_source
    assert "enabled: available" in nav_source
    assert root.property("hasFake3dViewport") is False


def test_shell_breakpoints_adapt_rail_inspector_and_card_columns_without_mutating_preferences(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings
    settings.set_reduced_motion(True)
    settings.set_rail_collapsed(False)
    settings.set_inspector_collapsed(False)

    for width, height, mode in (
        (768, 768, "narrow"),
        (799, 900, "narrow"),
        (800, 900, "compact"),
        (1024, 768, "compact"),
        (1279, 900, "compact"),
        (1280, 900, "wide"),
        (1440, 900, "wide"),
        (1920, 1080, "wide"),
        (2560, 1440, "wide"),
        (3840, 2160, "wide"),
    ):
        _set_size(root, width, height)
        assert root.property("shellMode") == mode
        assert 1 <= root.property("cardColumnCount") <= 3

    _set_size(root, 1440, 900)
    assert root.property("railEffectiveCollapsed") is False
    assert root.property("inspectorWideVisible") is True
    assert root.property("cardColumnCount") == 2

    _set_size(root, 1024, 768)
    assert root.property("railEffectiveCollapsed") is True
    assert root.property("inspectorWideVisible") is False
    assert not settings.get_rail_collapsed()
    assert not settings.get_inspector_collapsed()

    overview = root.findChild(QObject, "workspaceOverviewGrid")
    assert overview is not None
    assert overview.property("columnCount") == root.property("cardColumnCount")
    assert runtime.warning_capture.runtime_warnings == ()


def test_context_inspector_has_two_way_controls_in_the_main_shell(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings
    settings.set_inspector_collapsed(False)
    _set_size(root, 1440, 900)

    command_bar = root.findChild(QObject, "documentCommandBar")
    inspector = root.findChild(QObject, "persistentContextInspector")
    assert command_bar is not None
    assert inspector is not None
    assert command_bar.property("showInspectorButton") is False
    assert command_bar.property("inspectorOpen") is True
    assert inspector.property("visible") is True
    assert inspector.property("closeButtonVisible") is True
    assert inspector.findChild(QObject, "inspectorCloseButton") is not None

    inspector.closeRequested.emit()
    _process_events()
    assert settings.get_inspector_collapsed()
    assert command_bar.property("showInspectorButton") is True
    assert command_bar.property("inspectorOpen") is False
    assert inspector.property("visible") is False

    command_bar.inspectorToggleRequested.emit()
    _process_events()
    assert not settings.get_inspector_collapsed()
    assert command_bar.property("showInspectorButton") is False
    assert command_bar.property("inspectorOpen") is True
    assert inspector.property("visible") is True
    assert runtime.warning_capture.runtime_warnings == ()


def test_context_inspector_close_button_is_fixed_above_scrollable_content(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings
    settings.set_inspector_collapsed(False)
    _set_size(root, 1440, 900)
    inspector = root.findChild(QObject, "persistentContextInspector")
    assert inspector is not None
    close_button = inspector.findChild(QObject, "inspectorCloseButton")
    assert close_button is not None

    ancestor = close_button.parent()
    while ancestor is not None and ancestor is not inspector:
        assert "Flickable" not in ancestor.metaObject().className()
        ancestor = ancestor.parent()
    assert runtime.warning_capture.runtime_warnings == ()


def test_context_inspector_workspace_card_title_is_page_independent(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings
    settings.set_inspector_collapsed(False)
    _set_size(root, 1440, 900)
    inspector = root.findChild(QObject, "persistentContextInspector")
    assert inspector is not None

    assert root.setProperty("currentPage", "settings")
    _process_events()
    assert inspector.property("visible") is True
    assert inspector.metaObject().indexOfProperty("pageTitle") == -1

    source = (ROOT / "src/carnopy/app/qml/Carnopy/components/ContextInspector.qml").read_text(
        encoding="utf-8"
    )
    assert 'title: qsTr("Workspace")' in source
    assert runtime.warning_capture.runtime_warnings == ()


def test_theme_motion_and_local_pages_bind_to_one_settings_controller(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings

    settings.set_theme_mode("dark")
    settings.set_reduced_motion(True)
    _process_events()
    assert root.property("effectiveTheme") == "dark"
    assert root.property("motionDuration") == 0

    assert root.setProperty("currentPage", "settings")
    _process_events()
    settings_page = root.findChild(QObject, "settingsPage")
    assert settings_page is not None
    assert settings_page.property("qmlSettings") is settings

    settings.set_theme_mode("light")
    settings.set_reduced_motion(False)
    assert root.setProperty("currentPage", "help")
    _process_events()
    assert root.property("effectiveTheme") == "light"
    assert root.property("motionDuration") > 0
    assert root.findChild(QObject, "helpPage") is not None
    assert runtime.warning_capture.runtime_warnings == ()


def test_dark_theme_basic_control_labels_use_carnopy_palette(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings
    settings.set_theme_mode("dark")
    assert root.setProperty("currentPage", "settings")
    _process_events()

    for object_name in (
        "reducedMotionSwitch",
        "railPreferenceSwitch",
        "inspectorPreferenceSwitch",
    ):
        control = root.findChild(QObject, object_name)
        assert control is not None
        content = control.property("contentItem")
        assert isinstance(content, QObject)
        assert content.property("color") == QColor("#f0f5f8")

    assert runtime.warning_capture.runtime_warnings == ()


def test_logical_breakpoints_do_not_depend_on_native_scale_factor() -> None:
    code = """
import sys
from pathlib import Path
from PySide6.QtCore import QSettings
from carnopy.app.qml_runtime import create_qml_runtime

root_dir = Path(sys.argv[1])
runtime = create_qml_runtime(
    settings=QSettings(str(root_dir / "settings.ini"), QSettings.Format.IniFormat),
    application_arguments=[],
)
root = runtime.engine.rootObjects()[0]
for width, expected in ((768, "narrow"), (1024, "compact"), (1280, "wide")):
    root.setProperty("width", width)
    runtime.application.processEvents()
    if root.property("shellMode") != expected:
        raise SystemExit(f"{width}: {root.property('shellMode')} != {expected}")
if not runtime.close():
    raise SystemExit("runtime did not close")
"""
    for scale in ("1", "1.5", "2"):
        environment = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QT_SCALE_FACTOR": scale,
        }
        completed = subprocess.run(
            [sys.executable, "-c", code, str(ROOT / "prerelease")],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_public_launchers_still_resolve_to_widgets() -> None:
    from carnopy.app import launcher

    assert launcher.main.__module__ == "carnopy.app.launcher"
    assert launcher.main_gui.__module__ == "carnopy.app.launcher"
    source = (ROOT / "src/carnopy/app/launcher.py").read_text(encoding="utf-8")
    assert "from carnopy.app.window import run_application" in source
    assert "qml_runtime" not in source


def test_shell_imports_remain_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.qml_settings
import carnopy.app.qml_runtime
for name in ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib"):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
