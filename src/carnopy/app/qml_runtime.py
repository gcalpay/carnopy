from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMargins,
    QObject,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QFontDatabase, QGuiApplication, QScreen, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlError
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from carnopy.app.application_identity import apply_application_identity
from carnopy.app.desktop_controller import DesktopController
from carnopy.app.qml_resources import (
    MANDATORY_FONT_FILES,
    QML_MODULE,
    QML_TYPE,
    PackagedResourceError,
    packaged_path,
    qml_import_path,
    verify_packaged_resources,
)

LOGGER = logging.getLogger(__name__)

EXPECTED_FONT_FAMILIES = {
    "resources/fonts/IBMPlexSans-Regular.ttf": "IBM Plex Sans",
    "resources/fonts/IBMPlexSans-Medium.ttf": "IBM Plex Sans",
    "resources/fonts/IBMPlexSans-SemiBold.ttf": "IBM Plex Sans",
    "resources/fonts/IBMPlexMono-Regular.ttf": "IBM Plex Mono",
    "resources/fonts/IBMPlexMono-Medium.ttf": "IBM Plex Mono",
}


class QmlStartupError(RuntimeError):
    """Raised when the private QML application cannot start cleanly."""


def fitted_window_frame(
    client_size: QSize,
    frame_margins: QMargins,
    frame_position: QPoint,
    available_geometry: QRect,
) -> tuple[QSize, QPoint]:
    """Fit one decorated window inside one logical screen's available geometry."""

    horizontal_frame = max(0, frame_margins.left()) + max(0, frame_margins.right())
    vertical_frame = max(0, frame_margins.top()) + max(0, frame_margins.bottom())
    width = min(max(1, client_size.width()), max(1, available_geometry.width() - horizontal_frame))
    height = min(
        max(1, client_size.height()),
        max(1, available_geometry.height() - vertical_frame),
    )
    frame_width = width + horizontal_frame
    frame_height = height + vertical_frame
    maximum_x = available_geometry.x() + max(0, available_geometry.width() - frame_width)
    maximum_y = available_geometry.y() + max(0, available_geometry.height() - frame_height)
    x = min(max(frame_position.x(), available_geometry.x()), maximum_x)
    y = min(max(frame_position.y(), available_geometry.y()), maximum_y)
    return QSize(width, height), QPoint(x, y)


def _fit_window_to_available_screen(
    window: QWindow,
    preferred_screen_name: str = "",
) -> QScreen | None:
    application = QGuiApplication.instance()
    if not isinstance(application, QGuiApplication):
        return None
    frame = window.frameGeometry()
    screens = tuple(application.screens())
    if not screens:
        return None

    def intersection_area(screen: QScreen) -> int:
        geometry = screen.availableGeometry()
        intersection = frame.intersected(geometry)
        return max(0, intersection.width()) * max(0, intersection.height())

    preferred = next(
        (screen for screen in screens if screen.name() == preferred_screen_name),
        None,
    )
    if preferred is not None:
        screen = preferred
    else:
        screen = max(screens, key=intersection_area)
        if intersection_area(screen) == 0 and window.screen() is not None:
            screen = window.screen()
    frame_margins = window.frameMargins()
    client_size, frame_position = fitted_window_frame(
        window.size(),
        frame_margins,
        window.framePosition(),
        screen.availableGeometry(),
    )
    if client_size != window.size():
        window.resize(client_size)
    client_position = QPoint(
        frame_position.x() + max(0, frame_margins.left()),
        frame_position.y() + max(0, frame_margins.top()),
    )
    if client_position != window.position():
        window.setPosition(client_position)
    return screen


class QmlWindowCloseGuard(QObject):
    """Route QML window shutdown through the authoritative composition."""

    def __init__(self, controller: DesktopController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Close or not isinstance(watched, QWindow):
            return False
        if not isinstance(event, QCloseEvent):
            return False
        if not self._controller.request_shutdown():
            event.ignore()
            return True
        settings = self._controller.qml_settings
        screen = watched.screen()
        settings.remember_normal_screen("" if screen is None else screen.name())
        settings.set_maximized(watched.visibility() == QWindow.Visibility.Maximized)
        if watched.visibility() == QWindow.Visibility.Windowed:
            geometry = watched.geometry()
            settings.rememberNormalGeometry(
                geometry.x(),
                geometry.y(),
                geometry.width(),
                geometry.height(),
            )
        self._controller.settings.sync()
        return False


class QmlWarningCapture(QObject):
    runtime_warning = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._loading = True
        self._startup_warnings: list[str] = []
        self._runtime_warnings: list[str] = []

    def record(self, warnings: list[QQmlError]) -> None:
        for warning in warnings:
            message = warning.toString()
            if self._loading:
                self._startup_warnings.append(message)
            else:
                self._runtime_warnings.append(message)
                LOGGER.warning("QML runtime warning: %s", message)
                self.runtime_warning.emit(message)

    def finish_startup(self) -> None:
        self._loading = False

    @property
    def startup_warnings(self) -> tuple[str, ...]:
        return tuple(self._startup_warnings)

    @property
    def runtime_warnings(self) -> tuple[str, ...]:
        return tuple(self._runtime_warnings)


class QmlApplicationRuntime:
    """Own the private Stage 2 QML engine and its authoritative controllers."""

    def __init__(
        self,
        application: QApplication,
        settings: QSettings,
        controller: DesktopController,
        *,
        initial_workspace: Path | None = None,
    ) -> None:
        self.application = application
        self.settings = settings
        self.controller = controller
        self.initial_workspace = initial_workspace
        self.engine = QQmlApplicationEngine()
        self.warning_capture = QmlWarningCapture(self.engine)
        self._close_guard: QmlWindowCloseGuard | None = None
        self._geometry_fit_timer = QTimer(self.engine)
        self._geometry_fit_timer.setSingleShot(True)
        self._geometry_fit_timer.setInterval(100)
        self._font_ids: list[int] = []
        self._loaded = False

    def _complete_geometry_restoration(self, window: QWindow) -> None:
        _fit_window_to_available_screen(
            window,
            self.controller.qml_settings.get_normal_screen_name(),
        )
        window.setProperty("geometryTrackingReady", True)

    def _register_fonts(self) -> None:
        for relative_path in MANDATORY_FONT_FILES:
            font_id = QFontDatabase.addApplicationFont(str(packaged_path(relative_path)))
            if font_id < 0:
                raise QmlStartupError(f"could not register mandatory font: {relative_path}")
            families = QFontDatabase.applicationFontFamilies(font_id)
            expected = EXPECTED_FONT_FAMILIES[relative_path]
            if expected not in families:
                raise QmlStartupError(
                    f"mandatory font {relative_path} did not register {expected!r}: {families!r}"
                )
            self._font_ids.append(font_id)

    def load(self) -> QObject:
        if self._loaded:
            roots = self.engine.rootObjects()
            if len(roots) != 1:
                raise QmlStartupError(
                    "the loaded QML runtime no longer has exactly one root object"
                )
            return roots[0]
        try:
            verify_packaged_resources()
        except PackagedResourceError as exc:
            raise QmlStartupError(str(exc)) from exc
        self._register_fonts()
        self.engine.addImportPath(str(qml_import_path()))
        self.engine.warnings.connect(self.warning_capture.record)
        self.engine.setInitialProperties(
            {
                "desktopController": self.controller,
                "qmlSettings": self.controller.qml_settings,
                "startupWorkspace": (
                    "" if self.initial_workspace is None else str(self.initial_workspace)
                ),
            }
        )
        self.engine.loadFromModule(QML_MODULE, QML_TYPE)
        self.application.processEvents()
        self.warning_capture.finish_startup()
        roots = self.engine.rootObjects()
        if self.warning_capture.startup_warnings:
            details = "\n".join(self.warning_capture.startup_warnings)
            raise QmlStartupError(f"QML emitted warnings during startup:\n{details}")
        if len(roots) != 1:
            raise QmlStartupError(f"QML created {len(roots)} root objects; expected exactly one")
        self._connect_qml_facade(roots[0])
        if isinstance(roots[0], QWindow):
            self._close_guard = QmlWindowCloseGuard(self.controller, self.engine)
            roots[0].installEventFilter(self._close_guard)
            roots[0].requestActivate()
            self._geometry_fit_timer.timeout.connect(
                lambda window=roots[0]: self._complete_geometry_restoration(window)
            )
            if self.application.platformName() == "offscreen":
                self._complete_geometry_restoration(roots[0])
            else:
                self._geometry_fit_timer.start()
        self._loaded = True
        return roots[0]

    def _connect_qml_facade(self, root: QObject) -> None:
        connections = (
            ("workspaceCreateRequested", self.controller.request_create_workspace),
            ("workspaceCreatePathRequested", self.controller.request_create_workspace_path),
            ("workspaceInitializeRequested", self.controller.request_initialize_workspace),
            ("workspaceOpenRequested", self.controller.request_open_workspace),
            ("workspaceCommitRequested", self.controller.request_commit_workspace_operation),
            ("workspaceCancelRequested", self.controller.request_cancel_workspace_operation),
            (
                "normalGeometryRememberRequested",
                self.controller.qml_settings.rememberNormalGeometry,
            ),
            ("settingsLayoutResetRequested", self.controller.qml_settings.resetLayout),
        )
        for signal_name, callback in connections:
            signal = getattr(root, signal_name, None)
            if signal is None:
                raise QmlStartupError(f"QML root does not expose {signal_name}")
            signal.connect(callback, Qt.ConnectionType.QueuedConnection)

    def close(self) -> bool:
        self._geometry_fit_timer.stop()
        for root in self.engine.rootObjects():
            root.setProperty("visible", False)
            root.deleteLater()
        _drain_deferred_deletes(self.application)
        self.engine.collectGarbage()
        self.engine.deleteLater()
        _drain_deferred_deletes(self.application)
        closed = self.controller.shutdown()
        removal_results = [
            QFontDatabase.removeApplicationFont(font_id) for font_id in reversed(self._font_ids)
        ]
        self._font_ids.clear()
        return closed and all(removal_results)


def _drain_deferred_deletes(application: QApplication) -> None:
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def _application(arguments: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is None:
        existing = QApplication(list(arguments) if arguments is not None else sys.argv)
    if not isinstance(existing, QApplication):
        raise QmlStartupError("a non-GUI Qt application already exists")
    return existing


def create_qml_runtime(
    *,
    initial_workspace: Path | None = None,
    settings: QSettings | None = None,
    application_arguments: Sequence[str] | None = None,
) -> QmlApplicationRuntime:
    application = _application(application_arguments)
    apply_application_identity(application)
    QQuickStyle.setStyle("Basic")
    selected_settings = settings if settings is not None else QSettings()
    controller = DesktopController(settings=selected_settings, parent=application)
    runtime = QmlApplicationRuntime(
        application,
        selected_settings,
        controller,
        initial_workspace=initial_workspace,
    )
    try:
        runtime.load()
        if initial_workspace is not None:
            if not controller.prepare_open_workspace(str(initial_workspace)):
                raise QmlStartupError(controller.get_workspace_error_message())
            if not controller.commit_workspace_operation():
                raise QmlStartupError(controller.get_workspace_error_message())
    except Exception:
        runtime.close()
        raise
    return runtime


def run_qml_application(
    initial_workspace: Path | None = None,
    *,
    smoke_test: bool = False,
) -> int:
    runtime = create_qml_runtime(initial_workspace=initial_workspace)
    if smoke_test:
        QTimer.singleShot(0, runtime.application.quit)
    result = runtime.application.exec()
    if not runtime.close():
        raise QmlStartupError("the QML runtime could not shut down while a request was active")
    return result
