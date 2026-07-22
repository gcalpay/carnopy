from __future__ import annotations

import logging
import os
import signal
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from types import FrameType

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QLockFile,
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
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFontDatabase,
    QGuiApplication,
    QPalette,
    QScreen,
    QWindow,
)
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

QML_PALETTE_COLORS: dict[str, dict[str, str]] = {
    "light": {
        "canvas": "#f3f5f4",
        "surface": "#ffffff",
        "surface_raised": "#f8faf9",
        "surface_muted": "#e9efeb",
        "border": "#d3dcd6",
        "border_strong": "#abb9b0",
        "text": "#17211b",
        "text_muted": "#5c6a61",
        "text_subtle": "#7b887f",
        "primary": "#087a50",
        "information": "#2469c7",
        "warning": "#9b6508",
        "danger": "#b33131",
        "highlighted_text": "#ffffff",
    },
    "warm": {
        "canvas": "#f2dfbd",
        "surface": "#fff2d9",
        "surface_raised": "#f9e8ca",
        "surface_muted": "#ead4ae",
        "border": "#d6b67e",
        "border_strong": "#b48d50",
        "text": "#332518",
        "text_muted": "#73583c",
        "text_subtle": "#795a3d",
        "primary": "#0b7650",
        "information": "#486f91",
        "warning": "#ad6500",
        "danger": "#ad4033",
        "highlighted_text": "#ffffff",
    },
    "dark": {
        "canvas": "#0f0f0f",
        "surface": "#141715",
        "surface_raised": "#191d1a",
        "surface_muted": "#202620",
        "border": "#303932",
        "border_strong": "#47534b",
        "text": "#f1f4f2",
        "text_muted": "#aab5ae",
        "text_subtle": "#7f8b83",
        "primary": "#159660",
        "information": "#73a9f5",
        "warning": "#f2b84b",
        "danger": "#ff7777",
        "highlighted_text": "#ffffff",
    },
}


class QmlStartupError(RuntimeError):
    """Raised when the private QML application cannot start cleanly."""


def qml_application_palette(mode: str) -> QPalette:
    """Build the Qt fallback-control palette for one effective QML theme."""

    colors = QML_PALETTE_COLORS.get(mode, QML_PALETTE_COLORS["dark"])
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "canvas",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.AlternateBase: "surface_muted",
        QPalette.ColorRole.ToolTipBase: "surface_raised",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface_raised",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.BrightText: "highlighted_text",
        QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.HighlightedText: "highlighted_text",
        QPalette.ColorRole.PlaceholderText: "text_subtle",
        QPalette.ColorRole.Link: "information",
        QPalette.ColorRole.LinkVisited: "information",
        QPalette.ColorRole.Light: "border_strong",
        QPalette.ColorRole.Midlight: "border",
        QPalette.ColorRole.Mid: "border",
        QPalette.ColorRole.Dark: "border_strong",
        QPalette.ColorRole.Shadow: "canvas",
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color_name in roles.items():
            palette.setColor(group, role, QColor(colors[color_name]))
    for role, color_name in roles.items():
        disabled_name = "text_subtle" if color_name in {"text", "highlighted_text"} else color_name
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors[disabled_name]))
    return palette


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
    """Defer native close events to the authoritative composition."""

    close_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._enabled = True
        self._request_pending = False
        self._bypass_next_close = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Close or not isinstance(watched, QWindow):
            return False
        if not isinstance(event, QCloseEvent):
            return False
        if not self._enabled:
            return False
        if self._bypass_next_close:
            self._bypass_next_close = False
            return False
        event.ignore()
        if not self._request_pending:
            self._request_pending = True
            self.close_requested.emit()
        return True

    def complete_request(self) -> None:
        self._request_pending = False

    def allow_next_close(self) -> None:
        self._bypass_next_close = True

    def revoke_bypass(self) -> None:
        self._bypass_next_close = False

    def disable(self) -> None:
        self._enabled = False
        self._request_pending = False
        self._bypass_next_close = False


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
        self._previous_application_palette = QPalette(application.palette())
        self._palette_applied = False
        self.engine = QQmlApplicationEngine()
        self.warning_capture = QmlWarningCapture(self.engine)
        self._close_guard: QmlWindowCloseGuard | None = None
        self._geometry_fit_timer = QTimer(self.engine)
        self._geometry_fit_timer.setSingleShot(True)
        self._geometry_fit_timer.setInterval(100)
        self._close_request_timer = QTimer(self.engine)
        self._close_request_timer.setSingleShot(True)
        self._close_request_timer.setInterval(0)
        self._close_request_timer.timeout.connect(self._process_close_request)
        self._font_ids: list[int] = []
        self._loaded = False
        self._closing = False
        self._closed = False
        self._close_result = False
        self.controller.qml_settings.effectiveThemeChanged.connect(self._apply_application_palette)
        self._apply_application_palette()

    def _apply_application_palette(self) -> None:
        self.application.setPalette(
            qml_application_palette(self.controller.qml_settings.get_effective_theme())
        )
        self._palette_applied = True

    def _complete_geometry_restoration(self, window: QWindow) -> None:
        _fit_window_to_available_screen(
            window,
            self.controller.qml_settings.get_normal_screen_name(),
        )
        window.setProperty("geometryTrackingReady", True)

    def _begin_geometry_restoration(self, window: QWindow) -> None:
        """Place a hidden window before exposing it to the native compositor."""

        _fit_window_to_available_screen(
            window,
            self.controller.qml_settings.get_normal_screen_name(),
        )
        visibility = (
            QWindow.Visibility.Maximized
            if self.controller.qml_settings.get_maximized()
            else QWindow.Visibility.Windowed
        )
        window.setVisibility(visibility)
        window.requestActivate()
        if (
            self.application.platformName() == "offscreen"
            or visibility == QWindow.Visibility.Maximized
        ):
            window.setProperty("geometryTrackingReady", True)
        else:
            self._geometry_fit_timer.start()

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
        if self._closed:
            raise QmlStartupError("a closed QML runtime cannot be loaded again")
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
            self._close_guard = QmlWindowCloseGuard(self.engine)
            self._close_guard.close_requested.connect(self.request_close)
            roots[0].installEventFilter(self._close_guard)
            self._geometry_fit_timer.timeout.connect(
                lambda window=roots[0]: self._complete_geometry_restoration(window)
            )
            self._begin_geometry_restoration(roots[0])
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
            ("datasetNewRequested", self.controller.request_new_dataset),
            ("datasetImportRequested", self.controller.request_import_dataset),
            ("datasetSaveRequested", self.controller.request_save),
            ("datasetSaveAsRequested", self.controller.request_save_as),
            (
                "datasetValidateRequested",
                self.controller.request_validate_configuration,
            ),
            ("datasetSavePathSelected", self.controller.request_save_path_selected),
            ("datasetSavePathCancelled", self.controller.request_cancel_save_path),
            (
                "datasetConfirmReformatRequested",
                self.controller.request_confirm_reformat,
            ),
            ("datasetReloadRequested", self.controller.request_reload_source),
            ("datasetCloseRequested", self.controller.request_close_configuration),
            (
                "configurationAttentionRequested",
                self.controller.request_configuration_attention,
            ),
            ("datasetModelChangeRequested", self.controller.request_dataset_model_change),
            ("datasetFluidAddRequested", self.controller.request_dataset_fluid_add),
            ("datasetFluidMoveRequested", self.controller.request_dataset_fluid_move),
            ("datasetFluidRemoveRequested", self.controller.request_dataset_fluid_remove),
            ("datasetPropertyAddRequested", self.controller.request_dataset_property_add),
            ("datasetPropertyMoveRequested", self.controller.request_dataset_property_move),
            ("datasetPropertyRemoveRequested", self.controller.request_dataset_property_remove),
            (
                "datasetOutputSelectionRequested",
                self.controller.request_dataset_output_selection,
            ),
            (
                "datasetSamplerKindChangeRequested",
                self.controller.request_dataset_sampler_kind_change,
            ),
            (
                "datasetSamplerTextChangeRequested",
                self.controller.request_dataset_sampler_text_change,
            ),
            (
                "datasetSamplerUnitChangeRequested",
                self.controller.request_dataset_sampler_unit_change,
            ),
            ("datasetModeChangeRequested", self.controller.request_dataset_mode_change),
            (
                "datasetCoordinateChangeRequested",
                self.controller.request_dataset_coordinate_change,
            ),
            ("datasetDecisionCommitRequested", self.controller.commit_dataset_decision),
            ("datasetDecisionCancelRequested", self.controller.cancel_dataset_decision),
            ("visualizationEnabledRequested", self.controller.request_visualization_enabled),
            ("visualizationFormatRequested", self.controller.request_visualization_format),
            (
                "visualizationFluidSelectionRequested",
                self.controller.request_visualization_fluid_selection,
            ),
            (
                "visualizationAddPlotRequested",
                self.controller.request_visualization_add_plot,
            ),
            (
                "visualizationEditPlotRequested",
                self.controller.request_visualization_edit_plot,
            ),
            (
                "visualizationCommitPlotRequested",
                self.controller.request_visualization_commit_plot,
            ),
            (
                "visualizationCancelPlotRequested",
                self.controller.request_visualization_cancel_plot,
            ),
            (
                "visualizationRemovePlotRequested",
                self.controller.request_visualization_remove_plot,
            ),
            (
                "visualizationMovePlotRequested",
                self.controller.request_visualization_move_plot,
            ),
            ("plotFieldChangeRequested", self.controller.request_plot_field_change),
            (
                "plotFluidSelectionRequested",
                self.controller.request_plot_fluid_selection,
            ),
            (
                "visualizationMappingAddRequested",
                self.controller.request_visualization_mapping_add,
            ),
            (
                "visualizationMappingFieldChangeRequested",
                self.controller.request_visualization_mapping_field_change,
            ),
            (
                "visualizationMappingValueChangeRequested",
                self.controller.request_visualization_mapping_value_change,
            ),
            (
                "visualizationMappingRemoveRequested",
                self.controller.request_visualization_mapping_remove,
            ),
            (
                "normalGeometryRememberRequested",
                self.controller.qml_settings.rememberNormalGeometry,
            ),
            ("settingsLayoutResetRequested", self.controller.qml_settings.resetLayout),
            ("shutdownConfirmed", self.controller.confirm_shutdown),
        )
        for signal_name, callback in connections:
            signal = getattr(root, signal_name, None)
            if signal is None:
                raise QmlStartupError(f"QML root does not expose {signal_name}")
            signal.connect(callback, Qt.ConnectionType.QueuedConnection)

    def request_close(self) -> None:
        """Schedule one composition-guarded close outside the native event callback."""

        if self._closed or self._closing or self._close_request_timer.isActive():
            return
        self._close_request_timer.start()

    def _process_close_request(self) -> None:
        guard = self._close_guard
        if guard is not None:
            guard.complete_request()
        if self._closed or self._closing:
            return
        if not self.controller.request_shutdown():
            return
        roots = self.engine.rootObjects()
        window = next((root for root in roots if isinstance(root, QWindow)), None)
        if window is None:
            self.application.quit()
            return
        self._remember_window_state(window)
        if guard is not None:
            guard.allow_next_close()
        if not window.close() and guard is not None:
            guard.revoke_bypass()

    def _remember_window_state(self, window: QWindow) -> None:
        settings = self.controller.qml_settings
        screen = window.screen()
        settings.remember_normal_screen("" if screen is None else screen.name())
        settings.set_maximized(window.visibility() == QWindow.Visibility.Maximized)
        if window.visibility() == QWindow.Visibility.Windowed:
            geometry = window.geometry()
            settings.rememberNormalGeometry(
                geometry.x(),
                geometry.y(),
                geometry.width(),
                geometry.height(),
            )
        self.controller.settings.sync()

    def close(self) -> bool:
        if self._closed:
            return self._close_result
        if self._closing:
            return False
        if not self.controller.shutdown():
            return False
        self._closing = True
        self._geometry_fit_timer.stop()
        self._close_request_timer.stop()
        roots = list(self.engine.rootObjects())
        guard = self._close_guard
        if guard is not None:
            guard.disable()
            for root in roots:
                if isinstance(root, QWindow):
                    root.removeEventFilter(guard)
            self._close_guard = None
        for root in roots:
            root.setProperty("visible", False)
            root.deleteLater()
        _drain_deferred_deletes(self.application)
        self.engine.collectGarbage()
        self.engine.deleteLater()
        _drain_deferred_deletes(self.application)
        removal_results = [
            QFontDatabase.removeApplicationFont(font_id) for font_id in reversed(self._font_ids)
        ]
        self._font_ids.clear()
        with suppress(RuntimeError):
            self.controller.qml_settings.effectiveThemeChanged.disconnect(
                self._apply_application_palette
            )
        if self._palette_applied:
            self.application.setPalette(self._previous_application_palette)
            self._palette_applied = False
        self._loaded = False
        self._close_result = all(removal_results)
        self._closed = True
        self._closing = False
        return self._close_result


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


def _acquire_instance_lock() -> QLockFile:
    user_suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    lock_path = Path(tempfile.gettempdir()) / f"carnopy-qml-desktop{user_suffix}.lock"
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise QmlStartupError(
            "another Carnopy QML application is already running; close it before starting "
            "a second instance"
        )
    return lock


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
    application = _application()
    apply_application_identity(application)
    instance_lock = _acquire_instance_lock()
    try:
        if smoke_test:
            with tempfile.TemporaryDirectory(prefix="carnopy-qml-smoke-") as directory:
                settings = QSettings(
                    str(Path(directory) / "settings.ini"),
                    QSettings.Format.IniFormat,
                )
                runtime = create_qml_runtime(
                    initial_workspace=initial_workspace,
                    settings=settings,
                )
                _exercise_installed_qml_smoke(runtime)
                QTimer.singleShot(0, runtime.application.quit)
                result = _execute_qml_event_loop(runtime)
                if not runtime.close():
                    raise QmlStartupError(
                        "the QML runtime could not shut down while a request was active"
                    )
                return result
        runtime = create_qml_runtime(initial_workspace=initial_workspace)
        result = _execute_qml_event_loop(runtime)
        if not runtime.close():
            raise QmlStartupError("the QML runtime could not shut down while a request was active")
        return result
    finally:
        instance_lock.unlock()


def _execute_qml_event_loop(runtime: QmlApplicationRuntime) -> int:
    """Run Qt while routing SIGINT through the same deferred close guard."""

    previous_handler = signal.getsignal(signal.SIGINT)
    heartbeat = QTimer(runtime.engine)
    heartbeat.setInterval(100)
    heartbeat.timeout.connect(lambda: None)

    def request_guarded_close(_signum: int, _frame: FrameType | None) -> None:
        runtime.request_close()

    signal.signal(signal.SIGINT, request_guarded_close)
    heartbeat.start()
    try:
        return runtime.application.exec()
    finally:
        heartbeat.stop()
        signal.signal(signal.SIGINT, previous_handler)


def _exercise_installed_qml_smoke(runtime: QmlApplicationRuntime) -> None:
    roots = runtime.engine.rootObjects()
    if len(roots) != 1:
        raise QmlStartupError("installed QML smoke lost its root object")
    root = roots[0]
    if root.property("configController") is not runtime.controller.dataset_config_controller:
        raise QmlStartupError("installed QML smoke did not bind the configuration controller")
    if not root.setProperty("width", 1024) or not root.setProperty("height", 768):
        raise QmlStartupError("installed QML smoke could not resize the workbench")
    if not root.setProperty("currentPage", "yaml"):
        raise QmlStartupError("installed QML smoke could not select the YAML page")
    runtime.controller.qml_settings.set_reduced_motion(True)
    runtime.application.processEvents()
    if root.property("shellMode") != "compact" or root.property("motionDuration") != 0:
        raise QmlStartupError("installed QML smoke did not apply responsive controller state")
    if root.findChild(QObject, "yamlPreviewPage") is None:
        raise QmlStartupError("installed QML smoke did not instantiate the YAML page")
    if runtime.controller.dataset_config_controller.get_yaml_available():
        raise QmlStartupError("installed QML smoke unexpectedly exposed YAML without a document")
    if runtime.warning_capture.runtime_warnings:
        details = "\n".join(runtime.warning_capture.runtime_warnings)
        raise QmlStartupError(f"installed QML smoke emitted runtime warnings:\n{details}")
