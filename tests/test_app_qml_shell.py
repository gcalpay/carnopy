from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QEventLoop,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    QSettings,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace

ROOT = Path(__file__).resolve().parents[1]

NAVIGATION_ORDER = (
    "Workspace",
    "Dataset",
    "YAML Preview",
    "Run",
    "Inspect",
    "Visualization",
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


def _visual_items(root: QQuickWindow, object_name: str) -> tuple[QQuickItem, ...]:
    matches: list[QQuickItem] = []
    pending: list[QQuickItem] = [root.contentItem()]
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        if item.objectName() == object_name:
            matches.append(item)
    return tuple(matches)


def _visible_item(root: QQuickWindow, object_name: str) -> QQuickItem:
    matches = tuple(item for item in _visual_items(root, object_name) if item.isVisible())
    assert len(matches) == 1
    return matches[0]


def _activate(item: QQuickItem) -> None:
    assert QMetaObject.invokeMethod(item, "click")
    _process_events()


def _mouse_click(root: QQuickWindow, item: QQuickItem) -> None:
    center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(center.x()), round(center.y())),
    )
    _process_events()


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        _process_events()
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    _process_events()
    assert not runtime.controller.request_coordinator.is_busy


def test_shell_uses_exact_navigation_order_and_enables_only_integrated_workflows(
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
    ) == (True, True, True, True, True, True, True, True, False, False)
    nav_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/NavRail.qml").read_text(
        encoding="utf-8"
    )
    assert "activeFocusOnTab: effectivelyAvailable" in nav_source
    assert "enabled: effectivelyAvailable" in nav_source
    assert 'pageKey !== "dataset"' in nav_source
    assert "root.datasetAvailable" in nav_source
    assert 'pageKey !== "visualization"' in nav_source
    assert "root.visualizationAvailable" in nav_source
    assert 'pageKey !== "yaml"' in nav_source
    assert "root.yamlAvailable" in nav_source
    assert '!== "run"' in nav_source
    assert "root.runAvailable" in nav_source
    assert 'pageKey !== "inspect"' in nav_source
    assert "root.inspectAvailable" in nav_source
    assert '!== "activity"' in nav_source
    assert "root.activityAvailable" in nav_source
    assert 'pageKey !== "sweeps"' in nav_source
    assert "root.sweepsAvailable" in nav_source
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
    _set_size(root, 1440, 900)
    card_heights = {
        _visible_item(root, object_name).height()
        for object_name in (
            "createWorkspaceCard",
            "initializeWorkspaceCard",
            "openWorkspaceCard",
        )
    }
    assert len(card_heights) == 1
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


def test_wide_shell_actions_respond_once_to_first_click_and_keyboard(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    settings = runtime.controller.qml_settings
    settings.set_reduced_motion(True)
    settings.set_rail_collapsed(False)
    settings.set_inspector_collapsed(False)
    _set_size(root, 1440, 900)
    rail_changes: list[bool] = []
    inspector_changes: list[bool] = []
    settings.railCollapsedChanged.connect(
        lambda: rail_changes.append(settings.get_rail_collapsed())
    )
    settings.inspectorCollapsedChanged.connect(
        lambda: inspector_changes.append(settings.get_inspector_collapsed())
    )

    rail_button = _visible_item(root, "railCollapseButton")
    _activate(rail_button)
    assert settings.get_rail_collapsed()
    assert rail_changes == [True]
    _activate(rail_button)
    assert not settings.get_rail_collapsed()
    assert rail_changes == [True, False]

    inspector_close = _visible_item(root, "inspectorCloseButton")
    _activate(inspector_close)
    assert settings.get_inspector_collapsed()
    assert inspector_changes == [True]
    inspector_open = _visible_item(root, "inspectorToggleButton")
    _activate(inspector_open)
    assert not settings.get_inspector_collapsed()
    assert inspector_changes == [True, False]

    QTest.keyClick(root, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    _process_events()
    assert settings.get_rail_collapsed()
    assert rail_changes == [True, False, True]
    QTest.keyClick(root, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    _process_events()
    assert settings.get_inspector_collapsed()
    assert inspector_changes == [True, False, True]
    assert runtime.warning_capture.runtime_warnings == ()


def test_wide_shell_pointer_toggles_remain_immediate_during_capability_loading(
    runtime: QmlApplicationRuntime,
    tmp_path: Path,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    desktop = runtime.controller
    settings = desktop.qml_settings
    settings.set_reduced_motion(False)
    settings.set_rail_collapsed(False)
    settings.set_inspector_collapsed(False)
    _set_size(root, 1440, 900)

    workspace = initialize_workspace(tmp_path / "capability-loading-workspace")
    assert desktop.prepare_open_workspace(str(workspace.root))
    assert desktop.commit_workspace_operation()
    assert desktop.request_coordinator.is_busy
    assert desktop.get_workspace_state() == "loading"
    loading_banner = root.findChild(QQuickItem, "capabilityLoadingBanner")
    loading_title = root.findChild(QQuickItem, "capabilityLoadingTitle")
    loading_detail = root.findChild(QQuickItem, "capabilityLoadingDetail")
    assert loading_banner is not None
    assert loading_title is not None
    assert loading_detail is not None
    assert loading_banner.isVisible()
    assert loading_title.property("text") == "Preparing local CoolProp capabilities"
    assert "Importing the installed CoolProp package" in loading_detail.property("text")
    assert "No network service is contacted" in loading_detail.property("text")
    try:
        _mouse_click(root, _visible_item(root, "railCollapseButton"))
        assert settings.get_rail_collapsed()
        _mouse_click(root, _visible_item(root, "railCollapseButton"))
        assert not settings.get_rail_collapsed()

        inspector_close = _visible_item(root, "inspectorCloseButton")
        pointer_events: list[str] = []
        inspector_close.clicked.connect(lambda: pointer_events.append("clicked"))
        _mouse_click(root, inspector_close)
        assert pointer_events == ["clicked"]
        assert settings.get_inspector_collapsed()
        _mouse_click(root, _visible_item(root, "inspectorToggleButton"))
        assert not settings.get_inspector_collapsed()
    finally:
        _wait_for_idle(runtime)
    assert not loading_banner.isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_breakpoint_changes_close_transient_drawers_and_preserve_wide_preferences(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    settings = runtime.controller.qml_settings
    settings.set_reduced_motion(True)
    settings.set_rail_collapsed(False)
    settings.set_inspector_collapsed(False)

    _set_size(root, 768, 768)
    _activate(_visible_item(root, "railMenuButton"))
    assert root.property("navigationDrawerOpen") is True
    _set_size(root, 1024, 768)
    QTest.qWait(300)
    _process_events()
    assert root.property("navigationDrawerOpen") is False
    assert not settings.get_rail_collapsed()
    assert not settings.get_inspector_collapsed()
    focused = root.activeFocusItem()
    assert focused is not None
    assert focused.objectName() == "nav-workspace"

    _activate(_visible_item(root, "inspectorToggleButton"))
    assert root.property("inspectorDrawerOpen") is True
    _set_size(root, 1440, 900)
    QTest.qWait(300)
    _process_events()
    assert root.property("inspectorDrawerOpen") is False
    assert root.property("inspectorWideVisible") is True
    assert not settings.get_rail_collapsed()
    assert not settings.get_inspector_collapsed()
    focused = root.activeFocusItem()
    assert focused is not None
    assert focused.objectName() == "inspectorCloseButton"
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


def test_header_appearance_controls_follow_docked_and_responsive_layouts(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    settings = runtime.controller.qml_settings
    settings.set_inspector_collapsed(False)
    settings.set_theme_mode("system")
    _set_size(root, 1440, 900)

    docked = root.findChild(QQuickItem, "dockedAppearanceSelector")
    command = root.findChild(QQuickItem, "commandAppearanceSelector")
    inspector = root.findChild(QQuickItem, "persistentContextInspector")
    assert docked is not None
    assert command is not None
    assert inspector is not None
    assert docked.isVisible()
    assert not command.isVisible()
    assert docked.mapToScene(QPointF(0, 0)).x() == inspector.mapToScene(QPointF(0, 0)).x()
    assert _visible_item(root, "appearanceLightButton").isVisible()
    assert _visible_item(root, "appearanceWarmButton").isVisible()
    assert _visible_item(root, "appearanceDarkButton").isVisible()
    assert _visible_item(root, "appearanceAutoMarker").isVisible()

    _mouse_click(root, _visible_item(root, "appearanceWarmButton"))
    assert settings.get_theme_mode() == "warm"
    assert settings.get_effective_theme() == "warm"
    assert not tuple(
        item for item in _visual_items(root, "appearanceAutoMarker") if item.isVisible()
    )

    settings.set_inspector_collapsed(True)
    _process_events()
    assert not docked.isVisible()
    assert command.isVisible()
    _mouse_click(root, _visible_item(root, "appearanceLightButton"))
    assert settings.get_theme_mode() == "light"

    _set_size(root, 768, 768)
    assert _visible_item(root, "appearanceMenuButton").isVisible()
    assert not tuple(
        item
        for name in (
            "appearanceLightButton",
            "appearanceWarmButton",
            "appearanceDarkButton",
        )
        for item in _visual_items(root, name)
        if item.isVisible()
    )
    _activate(_visible_item(root, "appearanceMenuButton"))
    _activate(_visible_item(root, "appearanceDarkMenuItem"))
    assert settings.get_theme_mode() == "dark"
    assert runtime.warning_capture.runtime_warnings == ()


def test_document_commands_use_labels_wide_and_overflow_narrow(
    runtime: QmlApplicationRuntime,
    tmp_path: Path,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    _set_size(root, 1440, 900)

    new_button = _visible_item(root, "commandNewButton")
    import_button = _visible_item(root, "commandImportButton")
    overflow = root.findChild(QQuickItem, "commandOverflowButton")
    assert new_button.property("text") == "New"
    assert import_button.property("text") == "Import"
    assert overflow is not None
    assert not overflow.isVisible()

    workspace = initialize_workspace(tmp_path / "document-command-workspace")
    assert runtime.controller.prepare_open_workspace(str(workspace.root))
    assert runtime.controller.commit_workspace_operation()
    _wait_for_idle(runtime)
    assert runtime.controller.request_new_dataset("property_table")
    _process_events()
    _set_size(root, 768, 768)
    assert not new_button.isVisible()
    assert not import_button.isVisible()
    assert overflow.isVisible()
    assert _visible_item(root, "commandSaveButton").isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_settings_exposes_system_light_warm_and_dark_modes(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("currentPage", "settings")
    _process_events()

    expected = {
        "systemThemeButton": "System",
        "lightThemeButton": "Light",
        "warmThemeButton": "Warm",
        "darkThemeButton": "Dark",
    }
    for object_name, label in expected.items():
        button = root.findChild(QObject, object_name)
        assert button is not None
        assert button.property("text") == label

    assert runtime.warning_capture.runtime_warnings == ()


def test_page_scrolling_avoids_layout_animation_and_reports_motion_mode(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    settings = runtime.controller.qml_settings

    workspace_flickable = root.findChild(QObject, "workspacePageFlickable")
    assert workspace_flickable is not None
    assert workspace_flickable.property("pixelAligned") is True

    assert root.setProperty("currentPage", "settings")
    _process_events()
    settings_flickable = root.findChild(QObject, "settingsPageFlickable")
    motion_card = root.findChild(QObject, "motionPreferenceCard")
    assert settings_flickable is not None
    assert settings_flickable.property("pixelAligned") is True
    assert motion_card is not None

    settings.set_reduced_motion(False)
    _process_events()
    assert "Standard motion is active" in motion_card.property("subtitle")
    settings.set_reduced_motion(True)
    _process_events()
    assert "Reduced motion is active" in motion_card.property("subtitle")

    navigation_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/NavRail.qml").read_text(
        encoding="utf-8"
    )
    assert "Behavior on implicitWidth" not in navigation_source
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
        assert content.property("color") == QColor("#f1f4f2")

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


def test_public_launchers_resolve_directly_to_qml() -> None:
    from carnopy.app import qml_launcher

    assert qml_launcher.main_app.__module__ == "carnopy.app.qml_launcher"
    assert qml_launcher.main_gui.__module__ == "carnopy.app.qml_launcher"
    source = (ROOT / "src/carnopy/app/qml_launcher.py").read_text(encoding="utf-8")
    assert "from carnopy.app.qml_runtime import QmlStartupError, run_qml_application" in source
    assert "carnopy.app.window" not in source


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
