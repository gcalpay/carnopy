from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtGui import QFontDatabase
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
        self._font_ids: list[int] = []
        self._loaded = False

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
        self._loaded = True
        return roots[0]

    def close(self) -> bool:
        for root in self.engine.rootObjects():
            root.setProperty("visible", False)
            root.deleteLater()
        self.engine.collectGarbage()
        self.engine.deleteLater()
        closed = self.controller.shutdown()
        self.application.processEvents()
        return closed


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
