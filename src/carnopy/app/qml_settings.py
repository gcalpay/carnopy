from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Property, QObject, QRect, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

THEME_MODE_KEY = "qml/theme/mode"
REDUCED_MOTION_KEY = "qml/accessibility/reduced_motion"
RAIL_COLLAPSED_KEY = "qml/layout/wide_rail_collapsed"
INSPECTOR_COLLAPSED_KEY = "qml/layout/wide_inspector_collapsed"
NORMAL_GEOMETRY_KEY = "qml/window/normal_geometry"
NORMAL_SCREEN_KEY = "qml/window/normal_screen"
MAXIMIZED_KEY = "qml/window/maximized"
WINDOW_STATE_VERSION_KEY = "qml/window/state_version"
WINDOW_STATE_VERSION = 2

THEME_MODES = ("system", "light", "warm", "dark")
DEFAULT_THEME_MODE = "dark"
DEFAULT_WINDOW_WIDTH = 1440
DEFAULT_WINDOW_HEIGHT = 900


def _bool_setting(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _migrate_window_state(settings: QSettings) -> None:
    raw_version = settings.value(WINDOW_STATE_VERSION_KEY, 0)
    try:
        version = int(raw_version) if isinstance(raw_version, (int, str)) else 0
    except (TypeError, ValueError):
        version = 0
    if version == WINDOW_STATE_VERSION:
        return
    for key in (NORMAL_GEOMETRY_KEY, NORMAL_SCREEN_KEY, MAXIMIZED_KEY):
        settings.remove(key)
    settings.setValue(WINDOW_STATE_VERSION_KEY, WINDOW_STATE_VERSION)


def _intersection_area(first: QRect, second: QRect) -> int:
    intersection = first.intersected(second)
    return max(0, intersection.width()) * max(0, intersection.height())


def _centered_default(screen: QRect) -> QRect:
    width = min(DEFAULT_WINDOW_WIDTH, screen.width())
    height = min(DEFAULT_WINDOW_HEIGHT, screen.height())
    return QRect(
        screen.x() + max(0, (screen.width() - width) // 2),
        screen.y() + max(0, (screen.height() - height) // 2),
        width,
        height,
    )


def clamp_window_geometry(requested: QRect, available_screens: Sequence[QRect]) -> QRect:
    """Clamp a normal window rectangle fully inside one current logical screen."""

    screens = tuple(QRect(screen) for screen in available_screens if screen.isValid())
    if not screens:
        screens = (QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT),)
    if not requested.isValid() or requested.width() <= 0 or requested.height() <= 0:
        return _centered_default(screens[0])

    target = max(screens, key=lambda screen: _intersection_area(requested, screen))
    if _intersection_area(requested, target) == 0:
        target = screens[0]

    width = min(requested.width(), target.width())
    height = min(requested.height(), target.height())
    maximum_x = target.x() + target.width() - width
    maximum_y = target.y() + target.height() - height
    x = min(max(requested.x(), target.x()), maximum_x)
    y = min(max(requested.y(), target.y()), maximum_y)
    return QRect(x, y, width, height)


def _available_screen_geometries() -> tuple[QRect, ...]:
    application = QGuiApplication.instance()
    if not isinstance(application, QGuiApplication):
        return ()
    primary = application.primaryScreen()
    screens = tuple(application.screens())
    ordered = (
        (primary, *(screen for screen in screens if screen != primary))
        if primary is not None
        else screens
    )
    return tuple(screen.availableGeometry() for screen in ordered)


class QmlSettingsController(QObject):
    """Own private QML appearance and wide-layout preferences."""

    themeModeChanged = Signal()
    effectiveThemeChanged = Signal()
    reducedMotionChanged = Signal()
    railCollapsedChanged = Signal()
    inspectorCollapsedChanged = Signal()
    normalGeometryChanged = Signal()
    maximizedChanged = Signal()
    layoutReset = Signal()

    def __init__(
        self,
        settings: QSettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        _migrate_window_state(settings)
        theme_is_stored = settings.contains(THEME_MODE_KEY)
        raw_theme = settings.value(THEME_MODE_KEY) if theme_is_stored else None
        self._theme_mode = raw_theme if isinstance(raw_theme, str) else DEFAULT_THEME_MODE
        if self._theme_mode not in THEME_MODES:
            self._theme_mode = DEFAULT_THEME_MODE
        if theme_is_stored and raw_theme != self._theme_mode:
            settings.setValue(THEME_MODE_KEY, self._theme_mode)
        self._reduced_motion = _bool_setting(settings, REDUCED_MOTION_KEY, False)
        self._rail_collapsed = _bool_setting(settings, RAIL_COLLAPSED_KEY, False)
        self._inspector_collapsed = _bool_setting(settings, INSPECTOR_COLLAPSED_KEY, False)
        raw_geometry = settings.value(NORMAL_GEOMETRY_KEY)
        requested = raw_geometry if isinstance(raw_geometry, QRect) else QRect()
        self._normal_geometry = clamp_window_geometry(
            requested,
            _available_screen_geometries(),
        )
        raw_screen = settings.value(NORMAL_SCREEN_KEY, "")
        self._normal_screen_name = raw_screen if isinstance(raw_screen, str) else ""
        self._maximized = _bool_setting(settings, MAXIMIZED_KEY, False)
        self._effective_theme = self._resolve_effective_theme()

        application = QGuiApplication.instance()
        if isinstance(application, QGuiApplication):
            application.styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    def _resolve_effective_theme(self) -> str:
        if self._theme_mode != "system":
            return self._theme_mode
        application = QGuiApplication.instance()
        if not isinstance(application, QGuiApplication):
            return "light"
        scheme = application.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def _system_theme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._theme_mode != "system":
            return
        effective = self._resolve_effective_theme()
        if effective == self._effective_theme:
            return
        self._effective_theme = effective
        self.effectiveThemeChanged.emit()

    def get_theme_mode(self) -> str:
        return self._theme_mode

    def set_theme_mode(self, value: str) -> None:
        if value not in THEME_MODES:
            return
        old_effective = self._effective_theme
        if value == self._theme_mode:
            if not self.settings.contains(THEME_MODE_KEY):
                self.settings.setValue(THEME_MODE_KEY, value)
            return
        self._theme_mode = value
        self._effective_theme = self._resolve_effective_theme()
        self.settings.setValue(THEME_MODE_KEY, value)
        self.themeModeChanged.emit()
        if self._effective_theme != old_effective:
            self.effectiveThemeChanged.emit()

    themeMode = Property(str, get_theme_mode, set_theme_mode, notify=themeModeChanged)

    def get_effective_theme(self) -> str:
        return self._effective_theme

    effectiveTheme = Property(str, get_effective_theme, notify=effectiveThemeChanged)

    def get_reduced_motion(self) -> bool:
        return self._reduced_motion

    def set_reduced_motion(self, value: bool) -> None:
        if value == self._reduced_motion:
            return
        self._reduced_motion = value
        self.settings.setValue(REDUCED_MOTION_KEY, value)
        self.reducedMotionChanged.emit()

    reducedMotion = Property(
        bool,
        get_reduced_motion,
        set_reduced_motion,
        notify=reducedMotionChanged,
    )

    def get_rail_collapsed(self) -> bool:
        return self._rail_collapsed

    def set_rail_collapsed(self, value: bool) -> None:
        if value == self._rail_collapsed:
            return
        self._rail_collapsed = value
        self.settings.setValue(RAIL_COLLAPSED_KEY, value)
        self.railCollapsedChanged.emit()

    railCollapsed = Property(
        bool,
        get_rail_collapsed,
        set_rail_collapsed,
        notify=railCollapsedChanged,
    )

    @Slot(result=bool)
    def toggleRailCollapsed(self) -> bool:
        """Toggle the persisted wide-layout rail preference exactly once."""

        self.set_rail_collapsed(not self._rail_collapsed)
        return self._rail_collapsed

    def get_inspector_collapsed(self) -> bool:
        return self._inspector_collapsed

    def set_inspector_collapsed(self, value: bool) -> None:
        if value == self._inspector_collapsed:
            return
        self._inspector_collapsed = value
        self.settings.setValue(INSPECTOR_COLLAPSED_KEY, value)
        self.inspectorCollapsedChanged.emit()

    inspectorCollapsed = Property(
        bool,
        get_inspector_collapsed,
        set_inspector_collapsed,
        notify=inspectorCollapsedChanged,
    )

    @Slot(result=bool)
    def toggleInspectorCollapsed(self) -> bool:
        """Toggle the persisted wide-layout inspector preference exactly once."""

        self.set_inspector_collapsed(not self._inspector_collapsed)
        return self._inspector_collapsed

    def get_normal_geometry(self) -> QRect:
        return QRect(self._normal_geometry)

    normalGeometry = Property(QRect, get_normal_geometry, notify=normalGeometryChanged)

    def get_normal_screen_name(self) -> str:
        return self._normal_screen_name

    def remember_normal_screen(self, value: str) -> None:
        name = value.strip()
        if name == self._normal_screen_name:
            return
        self._normal_screen_name = name
        if name:
            self.settings.setValue(NORMAL_SCREEN_KEY, name)
        else:
            self.settings.remove(NORMAL_SCREEN_KEY)

    def get_maximized(self) -> bool:
        return self._maximized

    def set_maximized(self, value: bool) -> None:
        if value == self._maximized:
            return
        self._maximized = value
        self.settings.setValue(MAXIMIZED_KEY, value)
        self.maximizedChanged.emit()

    maximized = Property(bool, get_maximized, set_maximized, notify=maximizedChanged)

    @Slot(int, int, int, int)
    def rememberNormalGeometry(self, x: int, y: int, width: int, height: int) -> None:
        geometry = clamp_window_geometry(
            QRect(x, y, width, height),
            _available_screen_geometries(),
        )
        if geometry == self._normal_geometry:
            return
        self._normal_geometry = geometry
        self.settings.setValue(NORMAL_GEOMETRY_KEY, geometry)
        self.normalGeometryChanged.emit()

    @Slot()
    def resetLayout(self) -> None:
        old_rail = self._rail_collapsed
        old_inspector = self._inspector_collapsed
        old_geometry = self._normal_geometry
        old_maximized = self._maximized

        for key in (
            RAIL_COLLAPSED_KEY,
            INSPECTOR_COLLAPSED_KEY,
            NORMAL_GEOMETRY_KEY,
            NORMAL_SCREEN_KEY,
            MAXIMIZED_KEY,
        ):
            self.settings.remove(key)
        self._rail_collapsed = False
        self._inspector_collapsed = False
        self._normal_geometry = clamp_window_geometry(QRect(), _available_screen_geometries())
        self._normal_screen_name = ""
        self._maximized = False

        if old_rail:
            self.railCollapsedChanged.emit()
        if old_inspector:
            self.inspectorCollapsedChanged.emit()
        if old_geometry != self._normal_geometry:
            self.normalGeometryChanged.emit()
        if old_maximized:
            self.maximizedChanged.emit()
        self.layoutReset.emit()
