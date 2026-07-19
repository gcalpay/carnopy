from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QPointF, QSettings, Qt, QTimer
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.fixture
def runtime(tmp_path: Path, application: QApplication) -> QmlApplicationRuntime:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        initial_workspace=workspace.root,
        application_arguments=[],
    )
    _wait_for_idle(created)
    yield created
    _wait_for_idle(created)
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        runtime.application.processEvents()
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    runtime.application.processEvents()
    assert not runtime.controller.request_coordinator.is_busy


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(5):
        application.processEvents()


def _item(root: QQuickWindow, object_name: str) -> QQuickItem:
    pending: list[QQuickItem] = [root.contentItem()]
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name:
            return candidate
        pending.extend(candidate.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def _click(root: QQuickWindow, item: QQuickItem) -> None:
    flickable = root.findChild(QObject, "visualizationPageFlickable")
    if isinstance(flickable, QQuickItem):
        position = item.mapToItem(flickable, QPointF(0, 0))
        viewport_height = float(flickable.property("height"))
        maximum = max(
            0.0,
            float(flickable.property("contentHeight")) - viewport_height,
        )
        desired = min(maximum, max(0.0, position.y() - viewport_height / 3))
        flickable.setProperty("contentY", desired)
        _process_events()
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, delay=0, pos=point)
    QTest.qWait(120)
    _process_events()


def test_qml_visualization_uses_authoritative_temporary_plot_lifecycle(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1200)
    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("currentPage", "visualization")
    _process_events()

    page = root.findChild(QObject, "visualizationPage")
    assert page is not None
    assert page.property("visualizationDraft") is desktop.visualization_draft
    assert root.findChild(QObject, "visualizationPlotList") is not None

    enabled_switch = _item(root, "visualizationEnabledSwitch")
    _click(root, enabled_switch)
    assert desktop.visualization_draft.get_enabled()

    add_button = _item(root, "visualizationAddPlotButton")
    _click(root, add_button)
    active = desktop.visualization_draft.get_active_plot_draft()
    assert active is not None
    assert desktop.get_has_active_plot_edit()
    assert not enabled_switch.isEnabled()
    assert root.findChild(QObject, "activePlotEditor") is not None

    desktop.request_plot_field_change(active, "format", "svg")
    inherit_button = _item(root, "plotFormatInheritButton")
    assert inherit_button.isEnabled()
    _click(root, inherit_button)
    assert active.get_output_format() == ""

    desktop.request_plot_field_change(active, "name", "Invalid Plot Name")
    commit_button = _item(root, "plotCommitButton")
    _click(root, commit_button)

    assert desktop.visualization_draft.get_active_plot_draft() is active
    assert root.property("currentPage") == "visualization"
    focused = root.activeFocusItem()
    assert focused is not None
    assert focused.objectName() == "plotNameField"

    desktop.request_plot_field_change(active, "name", "density-curves")
    _click(root, commit_button)

    assert not desktop.get_has_active_plot_edit()
    assert desktop.visualization_draft.plot_model.rowCount() == 1
    assert desktop.visualization_draft.get_dirty()
    assert runtime.warning_capture.runtime_warnings == ()


def test_active_qml_plot_edit_blocks_replacement_and_cancel_is_non_durable(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert desktop.request_new_dataset("property_table")
    desktop.request_visualization_enabled(True)
    assert desktop.request_visualization_add_plot()
    active = desktop.visualization_draft.get_active_plot_draft()
    assert active is not None
    durable_before = desktop.visualization_draft.raw_state()
    dirty_before = desktop.visualization_draft.get_dirty()

    desktop.request_plot_field_change(active, "name", "temporary-name")
    assert not desktop.request_new_dataset("saturation_table", discard_confirmed=True)
    _process_events()

    assert root.property("currentPage") == "visualization"
    assert desktop.visualization_draft.raw_state() == durable_before
    assert desktop.visualization_draft.get_dirty() == dirty_before
    assert desktop.request_visualization_cancel_plot()
    assert desktop.visualization_draft.raw_state() == durable_before
    assert not desktop.get_has_active_plot_edit()
    assert desktop.request_close_configuration(discard_confirmed=True)
    _process_events()
    assert root.property("currentPage") == "workspace"
    assert runtime.warning_capture.runtime_warnings == ()
