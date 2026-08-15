from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QMargins,
    QObject,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QPalette, QScreen, QWindow
from PySide6.QtQml import QQmlError
from PySide6.QtWidgets import QApplication

import carnopy.app.qml_runtime as qml_runtime_module
from carnopy.app.application_identity import APPLICATION_NAME, ORGANIZATION_NAME
from carnopy.app.qml_resources import (
    MANDATORY_ICON_FILES,
    MANDATORY_QML_FILES,
    MANIFEST_PATH,
    manifest_records,
    packaged_path,
    verify_packaged_resources,
)
from carnopy.app.qml_runtime import (
    QmlStartupError,
    QmlWarningCapture,
    _acquire_instance_lock,
    _configure_quick_style,
    create_qml_runtime,
    fitted_window_frame,
    screen_name_for_frame,
    screen_name_for_window_state,
)
from carnopy.app.qml_settings import (
    NORMAL_SCREEN_KEY,
    WINDOW_STATE_VERSION,
    WINDOW_STATE_VERSION_KEY,
)
from carnopy.app.workspace import initialize_workspace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    return application


def test_packaged_resource_manifest_matches_every_installed_byte() -> None:
    records = verify_packaged_resources()
    assert records == manifest_records()
    assert {record.owner for record in records} == {"Carnopy", "IBM Plex", "Lucide"}
    assert len({record.packaged_path for record in records}) == len(records)
    assert len(records) == 31

    manifest = json.loads(packaged_path(MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["branding"]["sha256"] == (
        "7c01f9c7f8fe12f98acc2063396a9af615a5a6eba30e995e4f86bc4fd8155fcc"
    )
    projects = {project["name"]: project for project in manifest["third_party_projects"]}
    assert projects["IBM Plex"]["revision"] == "2f9ba1b25957d958db71a849e85d72e3ecfb845a"
    assert projects["IBM Plex"]["license_expression"] == "OFL-1.1"
    assert projects["Lucide"]["revision"] == ("1.24.0 (b5b5d95933790a311aa6b7ed232fc8469934acdf)")
    assert projects["Lucide"]["license_expression"] == "ISC AND MIT"
    first_party_paths = {
        f"resources/{entry['packaged_path']}" for entry in manifest["first_party_resources"]
    }
    assert first_party_paths == {
        "resources/icons/appearance-dark.svg",
        "resources/icons/appearance-light.svg",
        "resources/icons/appearance-warm.svg",
    }
    assert {
        f"resources/{record.packaged_path}"
        for record in records
        if record.owner == "Lucide" and record.packaged_path.startswith("icons/")
    } == set(MANDATORY_ICON_FILES) - first_party_paths
    assert all(packaged_path(path).is_file() for path in MANDATORY_QML_FILES)


def test_private_qml_runtime_loads_one_warning_free_root(
    application: QApplication,
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = initialize_workspace(tmp_path / "workspace")
    runtime = create_qml_runtime(
        settings=settings,
        initial_workspace=workspace.root,
        application_arguments=[],
    )
    roots = runtime.engine.rootObjects()
    assert len(roots) == 1
    root = roots[0]
    assert root.objectName() == "carnopyQmlRoot"
    assert root.property("runtimeReady") is True
    assert root.property("desktopController") is runtime.controller
    assert root.property("qmlSettings") is runtime.controller.qml_settings
    assert runtime.plot_image_provider.registry is runtime.controller.plot_preview_registry
    assert root.property("geometryTrackingReady") is True
    assert root.property("startupWorkspace") == str(workspace.root)
    assert runtime.controller.workspace_controller.workspace == workspace
    assert runtime.warning_capture.startup_warnings == ()
    assert runtime.warning_capture.runtime_warnings == ()
    assert QCoreApplication.organizationName() == ORGANIZATION_NAME
    assert QCoreApplication.applicationName() == APPLICATION_NAME
    if runtime.controller.request_coordinator.is_busy:
        loop = QEventLoop()
        runtime.controller.request_coordinator.busy_changed.connect(
            lambda busy: None if busy else loop.quit()
        )
        QTimer.singleShot(15_000, loop.quit)
        loop.exec()
    assert not runtime.controller.request_coordinator.is_busy
    assert runtime.close()
    assert runtime._font_ids == []
    application.processEvents()


def test_qml_quick_style_is_not_reset_after_basic_controls_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_names = iter(("Fusion", "Basic"))
    set_calls: list[str] = []
    monkeypatch.setattr(qml_runtime_module.QQuickStyle, "name", lambda: next(observed_names))
    monkeypatch.setattr(qml_runtime_module.QQuickStyle, "setStyle", set_calls.append)

    _configure_quick_style()
    _configure_quick_style()

    assert set_calls == ["Basic"]


def test_qml_runtime_applies_each_theme_palette_immediately_and_restores_it(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = QPalette(application.palette())
    settings = QSettings(str(tmp_path / "palette.ini"), QSettings.Format.IniFormat)
    real_engine = qml_runtime_module.QQmlApplicationEngine
    engine_creation_highlights: list[QColor] = []

    def create_engine() -> object:
        engine_creation_highlights.append(application.palette().color(QPalette.ColorRole.Highlight))
        return real_engine()

    monkeypatch.setattr(qml_runtime_module, "QQmlApplicationEngine", create_engine)
    runtime = create_qml_runtime(settings=settings, application_arguments=[])
    controller = runtime.controller.qml_settings
    root = runtime.engine.rootObjects()[0]

    assert controller.get_theme_mode() == "dark"
    assert engine_creation_highlights == [QColor("#159660")]
    assert application.palette().color(QPalette.ColorRole.Window) == QColor("#0f0f0f")
    assert root.property("color") == QColor("#0f0f0f")

    controller.set_theme_mode("warm")
    assert application.palette().color(QPalette.ColorRole.Window) == QColor("#e7bd69")
    assert application.palette().color(QPalette.ColorRole.Highlight) == QColor("#0b7650")
    assert application.palette().color(QPalette.ColorRole.HighlightedText) == QColor("#ffffff")
    assert root.property("color") == QColor("#e7bd69")

    controller.set_theme_mode("light")
    assert application.palette().color(QPalette.ColorRole.Window) == QColor("#f3f5f4")
    assert root.property("color") == QColor("#f3f5f4")

    controller.set_theme_mode("system")
    replacement = "dark" if controller.get_effective_theme() == "light" else "light"
    monkeypatch.setattr(controller, "_resolve_effective_theme", lambda: replacement)
    controller._system_theme_changed(Qt.ColorScheme.Dark)
    expected_canvas = "#0f0f0f" if replacement == "dark" else "#f3f5f4"
    assert application.palette().color(QPalette.ColorRole.Window) == QColor(expected_canvas)
    assert root.property("color") == QColor(expected_canvas)

    assert runtime.close()
    assert application.palette() == previous
    assert runtime._font_ids == []
    application.processEvents()


def test_decorated_window_frame_is_fitted_inside_available_screen() -> None:
    client_size, frame_position = fitted_window_frame(
        QSize(1440, 900),
        QMargins(8, 30, 8, 8),
        QPoint(100, 100),
        QRect(0, 0, 1366, 768),
    )
    assert client_size == QSize(1350, 730)
    assert frame_position == QPoint(0, 0)

    client_size, frame_position = fitted_window_frame(
        QSize(1200, 900),
        QMargins(8, 30, 8, 8),
        QPoint(4300, 1200),
        QRect(1920, 0, 2560, 1440),
    )
    assert client_size == QSize(1200, 900)
    assert frame_position == QPoint(3264, 502)


def test_persisting_native_geometry_does_not_reposition_the_running_window(
    application: QApplication,
    tmp_path: Path,
) -> None:
    runtime = create_qml_runtime(
        settings=QSettings(str(tmp_path / "geometry.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    root = runtime.engine.rootObjects()[0]
    original = (
        root.property("x"),
        root.property("y"),
        root.property("width"),
        root.property("height"),
    )

    runtime.controller.qml_settings.rememberNormalGeometry(20, 30, 700, 650)
    application.processEvents()

    assert (
        root.property("x"),
        root.property("y"),
        root.property("width"),
        root.property("height"),
    ) == original
    assert runtime.close()


def test_maximized_window_is_placed_while_hidden_before_being_shown(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "maximized.ini"), QSettings.Format.IniFormat)
    settings.setValue(WINDOW_STATE_VERSION_KEY, WINDOW_STATE_VERSION)
    settings.setValue("qml/window/maximized", True)
    observed_visibility: list[QWindow.Visibility] = []

    from carnopy.app import qml_runtime

    original_fit = qml_runtime._fit_window_to_available_screen

    def record_fit(window: QWindow, preferred_screen_name: str = "") -> QScreen | None:
        observed_visibility.append(window.visibility())
        return original_fit(window, preferred_screen_name)

    monkeypatch.setattr(qml_runtime, "_fit_window_to_available_screen", record_fit)
    runtime = create_qml_runtime(
        settings=settings,
        application_arguments=[],
    )
    root = runtime.engine.rootObjects()[0]

    assert observed_visibility == [QWindow.Visibility.Hidden]
    assert root.property("visibility") == QWindow.Visibility.Maximized
    assert root.property("geometryTrackingReady") is True
    assert runtime.close()


def test_closing_screen_uses_window_frame_instead_of_stale_qt_screen() -> None:
    screens = (
        ("main", QRect(0, 0, 1920, 1080)),
        ("secondary", QRect(1920, 0, 1280, 1024)),
    )

    assert (
        screen_name_for_frame(
            QRect(1920, 0, 1280, 1024),
            screens,
            fallback_name="main",
        )
        == "secondary"
    )
    assert (
        screen_name_for_window_state(
            QRect(1920, 0, 1280, 1024),
            QRect(142, 116, 1440, 884),
            True,
            screens,
            fallback_name="secondary",
        )
        == "main"
    )
    assert (
        screen_name_for_window_state(
            QRect(1920, 0, 1280, 1024),
            QRect(142, 116, 1440, 884),
            False,
            screens,
            fallback_name="secondary",
        )
        == "secondary"
    )
    assert (
        screen_name_for_frame(
            QRect(0, 0, 1920, 1080),
            screens,
            fallback_name="secondary",
        )
        == "main"
    )
    assert (
        screen_name_for_frame(
            QRect(5000, 5000, 800, 600),
            screens,
            fallback_name="secondary",
        )
        == "secondary"
    )


def test_qml_instance_lock_rejects_overlapping_launches(
    application: QApplication,
) -> None:
    del application
    first = _acquire_instance_lock()
    try:
        with pytest.raises(QmlStartupError, match="already running"):
            _acquire_instance_lock()
    finally:
        first.unlock()

    replacement = _acquire_instance_lock()
    replacement.unlock()


def test_qml_instance_lock_reclaims_dead_process_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(qml_runtime_module.tempfile, "gettempdir", lambda: str(tmp_path))
    lock_path = tmp_path / f"carnopy-qml-desktop-{os.getuid()}.lock"
    lock_path.write_text("999999\npython\nGCA\n\n", encoding="utf-8")
    os.utime(lock_path, (1, 1))

    lock = _acquire_instance_lock()
    try:
        assert lock.isLocked()
    finally:
        lock.unlock()


def test_qml_close_event_uses_composition_guard(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = create_qml_runtime(
        settings=QSettings(str(tmp_path / "close.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    root = runtime.engine.rootObjects()[0]
    calls: list[object] = []
    monkeypatch.setattr(
        runtime.controller,
        "request_shutdown",
        lambda: calls.append(object()) or False,
    )

    root.close()
    assert calls == []
    assert root.property("visible") is True
    application.processEvents()

    assert len(calls) == 1
    assert root.property("visible") is True
    assert runtime.close()


def test_qml_close_approval_uses_one_bypass_then_restores_the_guard(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = create_qml_runtime(
        settings=QSettings(str(tmp_path / "bypass.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    root = runtime.engine.rootObjects()[0]
    outcomes = iter((True, False))
    calls: list[object] = []
    monkeypatch.setattr(
        runtime.controller,
        "request_shutdown",
        lambda: calls.append(object()) or next(outcomes),
    )

    root.close()
    application.processEvents()
    assert len(calls) == 1
    assert root.property("visible") is False

    root.setProperty("visible", True)
    application.processEvents()
    root.close()
    application.processEvents()
    assert len(calls) == 2
    assert root.property("visible") is True
    assert runtime.close()


def test_qml_close_offers_an_explicit_transient_edit_decision(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = create_qml_runtime(
        settings=QSettings(str(tmp_path / "transient-close.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    root = runtime.engine.rootObjects()[0]
    active = {"session": True}
    monkeypatch.setattr(runtime.controller, "get_has_active_plot_edit", lambda: False)
    monkeypatch.setattr(
        runtime.controller,
        "get_has_session_plot_edit",
        lambda: active["session"],
    )
    monkeypatch.setattr(
        runtime.controller.session_plot_controller,
        "cancel_edit",
        lambda: active.update(session=False) is None,
    )

    root.close()
    application.processEvents()

    dialog = root.findChild(QObject, "transientEditShutdownDialog")
    assert dialog is not None
    assert dialog.property("opened") is True
    assert "session plot edit" in dialog.property("bodyText")

    assert runtime.controller.confirm_transient_edit_shutdown(True)
    application.processEvents()
    application.processEvents()
    assert root.property("visible") is False
    assert runtime.close()


def test_qml_runtime_teardown_is_idempotent_and_removes_the_close_filter(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = create_qml_runtime(
        settings=QSettings(str(tmp_path / "teardown.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    calls: list[str] = []
    monkeypatch.setattr(
        runtime.controller,
        "shutdown",
        lambda: calls.append("shutdown") or True,
    )

    assert runtime.close()
    assert runtime.close()
    assert calls == ["shutdown"]
    assert runtime._close_guard is None
    assert runtime._font_ids == []
    with pytest.raises(QmlStartupError, match="closed QML runtime"):
        runtime.load()
    application.processEvents()


def test_qml_close_records_the_last_used_monitor(
    application: QApplication,
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "monitor.ini"), QSettings.Format.IniFormat)
    runtime = create_qml_runtime(settings=settings, application_arguments=[])
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QWindow)
    screen = root.screen()
    assert screen is not None

    root.close()
    application.processEvents()
    settings.sync()

    assert runtime.controller.qml_settings.get_normal_screen_name() == screen.name()
    if screen.name():
        assert settings.value(NORMAL_SCREEN_KEY) == screen.name()
    else:
        assert NORMAL_SCREEN_KEY not in settings.allKeys()
    assert runtime.close()


def test_qml_warning_capture_distinguishes_startup_and_later_warnings(
    application: QApplication,
) -> None:
    capture = QmlWarningCapture()
    emitted: list[str] = []
    capture.runtime_warning.connect(emitted.append)
    startup = QQmlError()
    startup.setDescription("startup binding warning")
    capture.record([startup])
    capture.finish_startup()
    runtime = QQmlError()
    runtime.setDescription("later binding warning")
    capture.record([runtime])
    application.processEvents()

    assert capture.startup_warnings == ("<Unknown File>: startup binding warning",)
    assert capture.runtime_warnings == ("<Unknown File>: later binding warning",)
    assert emitted == ["<Unknown File>: later binding warning"]


def test_qml_resource_and_runtime_imports_remain_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.qml_resources
if "PySide6" in sys.modules:
    raise SystemExit("resource lookup imported Qt")
import carnopy.app.qml_runtime
for name in ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib"):
    if name in sys.modules:
        raise SystemExit(f"QML runtime imported scientific dependency: {name}")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_module_qml_launcher_smoke_exits_cleanly() -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-m", "carnopy.app.qml_launcher", "--smoke-test"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_module_qml_launcher_workspace_smoke_waits_for_startup_request(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "carnopy.app.qml_launcher",
            "--workspace",
            str(workspace.root),
            "--smoke-test",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_guarded_sigint_closes_without_python_override_traceback(tmp_path: Path) -> None:
    code = """
import os
import signal
import sys
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer
from carnopy.app.qml_runtime import (
    _execute_qml_event_loop,
    create_qml_runtime,
)

settings_path = Path(sys.argv[1]) / "sigint.ini"
runtime = create_qml_runtime(
    settings=QSettings(str(settings_path), QSettings.Format.IniFormat),
    application_arguments=[],
)
QTimer.singleShot(0, lambda: os.kill(os.getpid(), signal.SIGINT))
result = _execute_qml_event_loop(runtime)
if not runtime.close():
    raise SystemExit("runtime did not close")
raise SystemExit(result)
"""
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    completed = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Error calling Python override" not in completed.stderr
    assert "KeyboardInterrupt" not in completed.stderr
    assert completed.stderr == ""


def test_qml_sources_pass_non_writing_qt_tooling() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_qml.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == "QML checks passed for 46 file(s).\n"
