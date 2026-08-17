from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QMetaObject,
    QObject,
    QPointF,
    QSettings,
    Qt,
    QTimer,
)
from PySide6.QtGui import QImage
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


def _wait_until(predicate: Callable[[], bool], *, timeout_ms: int = 5_000) -> None:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout_ms:
            raise AssertionError("condition did not become true before the timeout")
        QTest.qWait(25)
        _process_events()
        elapsed += 25


def _item(root: QQuickWindow, object_name: str) -> QQuickItem:
    pending: list[QQuickItem] = [root.contentItem()]
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name:
            return candidate
        pending.extend(candidate.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def _quick_texts(item: QQuickItem) -> set[str]:
    texts: set[str] = set()
    pending = list(item.childItems())
    while pending:
        child = pending.pop()
        value = child.property("text")
        if isinstance(value, str):
            texts.add(value)
        pending.extend(child.childItems())
    return texts


def _click(root: QQuickWindow, item: QQuickItem) -> None:
    flickable = next(
        (
            candidate
            for object_name in ("visualizationPageFlickable", "sessionPlotPageFlickable")
            if isinstance((candidate := root.findChild(QObject, object_name)), QQuickItem)
            and candidate.isVisible()
        ),
        None,
    )
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


def _click_scene(root: QQuickWindow, item: QQuickItem) -> None:
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, delay=0, pos=point)
    QTest.qWait(120)
    _process_events()


def _session_plot_context(source: Path) -> dict[str, object]:
    return {
        "source": str(source),
        "source_kind": "dataset",
        "revision": "a" * 64,
        "plot_context": {
            "mode": "property_table",
            "fluids": ["Propane"],
            "properties": ["mass_density"],
            "visualization": {
                "plot_kinds": ["property_curves", "xy", "pv"],
                "formats": ["png", "svg", "pdf"],
                "scales": ["linear", "log"],
                "kind_contracts": {
                    "property_curves": {
                        "required": ["property", "x", "format"],
                        "applicable": ["property", "x", "format"],
                    },
                    "xy": {
                        "required": ["x", "y", "format"],
                        "applicable": ["x", "y", "format"],
                    },
                    "pv": {"required": ["format"], "applicable": ["format"]},
                },
                "fields": [
                    {
                        "name": "temperature",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "group_allowed": True,
                        "filter_allowed": True,
                    },
                    {
                        "name": "pressure",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "group_allowed": True,
                        "filter_allowed": True,
                    },
                    {
                        "name": "mass_density",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "group_allowed": False,
                        "filter_allowed": False,
                    },
                    {
                        "name": "specific_volume",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "group_allowed": False,
                        "filter_allowed": False,
                    },
                ],
            },
        },
    }


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


def test_shared_visualization_columns_remain_inside_the_page(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    desktop.qml_settings.set_inspector_collapsed(True)
    root.setWidth(1440)
    root.setHeight(1000)
    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("currentPage", "visualization")
    _process_events()

    grid = _item(root, "visualizationSharedSettingsGrid")
    primary = _item(root, "visualizationSharedPrimaryColumn")
    mappings = _item(root, "visualizationSharedMappingsColumn")
    assert grid.property("columns") == 2
    assert abs(primary.width() - mappings.width()) <= 1
    for column in (primary, mappings):
        position = column.mapToItem(grid, QPointF(0, 0))
        assert position.x() >= 0
        assert position.x() + column.width() <= grid.width() + 1

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
    assert root.property("currentPage") == "visualization"
    assert runtime.warning_capture.runtime_warnings == ()


def test_visualization_tabs_do_not_render_and_session_edit_is_explicit(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert desktop.request_new_dataset("property_table")
    source = desktop.workspace_controller.workspace.outputs / "inspected.parquet"
    source.write_bytes(b"source")
    desktop.session_plot_controller._inspection_changed(_session_plot_context(source))
    assert root.setProperty("currentPage", "visualization")
    _process_events()

    page = root.findChild(QObject, "visualizationPage")
    assert page is not None
    assert (
        page.property("configuredResultsController") is desktop.configured_plot_results_controller
    )
    assert page.property("sessionPlotController") is desktop.session_plot_controller
    assert not desktop.request_coordinator.is_busy

    explore_tab = _item(root, "exploreInspectedDataTab")
    _click(root, explore_tab)
    assert not desktop.request_coordinator.is_busy
    assert not desktop.session_plot_controller.get_has_active_edit()

    begin_button = _item(root, "sessionPlotBeginButton")
    assert begin_button.isEnabled()
    _click(root, begin_button)
    assert desktop.session_plot_controller.get_has_active_edit()
    active_draft = desktop.session_plot_controller.get_active_plot_draft()
    assert active_draft is not None
    assert active_draft.property("kind") == ""
    assert not desktop.session_plot_controller.get_can_render()
    assert not desktop.request_coordinator.is_busy
    assert root.findChild(QObject, "sessionPlotEditor") is not None

    cancel_button = _item(root, "plotCancelButton")
    assert cancel_button.isVisible()
    _click(root, cancel_button)
    assert not desktop.session_plot_controller.get_has_active_edit()
    assert not desktop.request_coordinator.is_busy
    assert runtime.warning_capture.runtime_warnings == ()


def test_configured_plot_edit_round_trips_and_can_seed_session_without_rendering(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1000)
    assert desktop.request_new_dataset("property_table")
    desktop.request_visualization_enabled(True)
    assert desktop.request_visualization_add_plot()
    configured = desktop.visualization_draft.get_active_plot_draft()
    assert configured is not None
    desktop.request_plot_field_change(configured, "name", "configured-density")
    desktop.request_plot_field_change(configured, "kind", "property_curves")
    desktop.request_plot_field_change(configured, "property", "mass_density")
    desktop.request_plot_field_change(configured, "x", "temperature")
    assert desktop.request_visualization_commit_plot()

    source = desktop.workspace_controller.workspace.outputs / "inspected.parquet"
    source.write_bytes(b"source")
    desktop.session_plot_controller._inspection_changed(_session_plot_context(source))
    assert root.setProperty("currentPage", "visualization")
    _process_events()

    edit_button = _item(root, "visualizationEditPlot-0")
    _click(root, edit_button)
    edited = desktop.visualization_draft.get_active_plot_draft()
    assert edited is not None
    assert edited.property("kind") == "property_curves"
    assert edited.property("propertyName") == "mass_density"
    assert edited.property("xField") == "temperature"
    kind_texts = _quick_texts(_item(root, "plotKindBox"))
    property_texts = _quick_texts(_item(root, "plotPropertyBox"))
    assert desktop.request_visualization_cancel_plot()
    _process_events()
    assert "Property curves" in kind_texts
    assert "mass_density" in property_texts

    explore_button = _item(root, "visualizationUsePlot-0")
    assert explore_button.isEnabled()
    _click(root, explore_button)
    _wait_until(desktop.session_plot_controller.get_has_active_edit)
    session = desktop.session_plot_controller.get_active_plot_draft()
    assert session is not None
    assert session.property("name") == "configured-density"
    assert session.property("kind") == "property_curves"
    assert session.property("propertyName") == "mass_density"
    assert session.property("xField") == "temperature"
    assert not desktop.request_coordinator.is_busy
    assert _item(root, "exploreInspectedDataTab").property("checked")
    assert desktop.session_plot_controller.cancel_edit()
    assert runtime.warning_capture.runtime_warnings == ()


def test_historical_visualization_stays_open_without_a_configuration(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert not desktop.configuration_controller.get_has_document()
    source = desktop.workspace_controller.workspace.outputs / "historical.parquet"
    source.write_bytes(b"source")
    desktop.session_plot_controller._inspection_changed(_session_plot_context(source))
    assert root.setProperty("currentPage", "visualization")
    _process_events()

    desktop.workspace_state_changed.emit()
    desktop.request_coordinator.busy_changed.emit(True)
    _process_events()

    assert root.property("currentPage") == "visualization"
    assert _item(root, "nav-visualization").isEnabled()
    assert _item(root, "sessionPlotBeginButton").isEnabled()
    assert runtime.warning_capture.runtime_warnings == ()


def test_configured_result_columns_share_top_alignment_and_list_height(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    desktop.qml_settings.set_rail_collapsed(True)
    desktop.qml_settings.set_inspector_collapsed(True)
    root.setWidth(1920)
    root.setHeight(1080)
    assert root.setProperty("currentPage", "visualization")

    controller = desktop.configured_plot_results_controller
    controller.records_model.set_rows(
        (
            {
                "requestId": "request-1",
                "runId": "run-1",
                "createdAtUtc": "2026-07-29T10:00:00Z",
                "configurationPath": "configs/demo.yaml",
                "configurationSha256": "a" * 64,
                "visualizationStatus": "completed",
                "hasRecordedVisualization": True,
            },
        ),
        available=True,
    )
    controller.outcomes_model.set_rows(
        (
            {
                "index": index,
                "name": f"plot-{index}",
                "kind": "xy",
                "status": "completed",
                "format": "png",
                "previewAvailable": True,
                "openExternally": False,
                "validSampleCount": 10,
                "excludedSampleCount": 0,
                "issue": "",
            }
            for index in range(4)
        ),
        available=True,
    )
    _process_events()

    grid = _item(root, "configuredResultsGrid")
    generation_column = _item(root, "configuredGenerationColumn")
    outcome_column = _item(root, "configuredOutcomeColumn")
    preview_column = _item(root, "configuredPreviewColumn")
    generation_list = _item(root, "configuredPlotGenerationList")
    outcome_list = _item(root, "configuredPlotOutcomeList")

    assert grid.property("columns") == 3
    column_tops = {
        round(column.mapToItem(grid, QPointF(0, 0)).y())
        for column in (generation_column, outcome_column, preview_column)
    }
    assert len(column_tops) == 1
    assert generation_list.height() == pytest.approx(outcome_list.height(), abs=1)
    assert generation_list.height() == pytest.approx(176, abs=1)
    assert runtime.warning_capture.runtime_warnings == ()


def test_plot_focus_mode_distinguishes_fit_from_native_size(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(900)
    assert root.setProperty("currentPage", "visualization")

    workspace = desktop.workspace_controller.workspace
    image_path = workspace.figures / "focus-mode-test.png"
    image = QImage(2400, 1200, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    assert image.save(str(image_path), "PNG")
    token = desktop.plot_preview_registry.issue(
        workspace_identity=str(workspace.root),
        figures_root=workspace.figures,
        image_path=image_path,
        image_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
        image_format="png",
        verification_revision="focus-mode-test",
    )

    view = _item(root, "configuredVerifiedPlotView")
    view.setProperty("canPreview", True)
    view.setProperty("previewSource", desktop.plot_preview_registry.url(token))
    view.setVisible(True)
    _process_events()
    assert QMetaObject.invokeMethod(view, "openFocusMode", Qt.ConnectionType.DirectConnection)
    _process_events()

    viewport = _item(root, "plotFocusModeViewport")
    focus_image = _item(root, "plotFocusModeImage")
    _wait_until(lambda: focus_image.property("implicitWidth") == 2400)
    assert focus_image.width() <= viewport.width() + 1
    assert focus_image.height() <= viewport.height() + 1

    _click_scene(root, _item(root, "plotFocusActualSizeButton"))
    assert focus_image.width() == pytest.approx(2400, abs=1)
    assert focus_image.height() == pytest.approx(1200, abs=1)
    assert focus_image.width() > viewport.width()

    _click_scene(root, _item(root, "plotFocusFitButton"))
    assert focus_image.width() <= viewport.width() + 1
    assert focus_image.height() <= viewport.height() + 1
    assert focus_image.x() >= 0
    assert focus_image.y() >= 0
    _click_scene(root, _item(root, "plotFocusModeCloseButton"))
    assert runtime.warning_capture.runtime_warnings == ()
