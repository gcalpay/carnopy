from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QMetaObject, QObject, QSettings, QTimer
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication

from carnopy.app.jobs import JobStore
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace


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


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(6):
        application.processEvents()


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        _process_events()
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(60_000, loop.quit)
    loop.exec()
    _process_events()
    assert not runtime.controller.request_coordinator.is_busy


def _wait_until(
    runtime: QmlApplicationRuntime,
    predicate: Callable[[], bool],
) -> None:
    if predicate():
        _process_events()
        return
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(60_000, loop.quit)
    loop.exec()
    timer.stop()
    _process_events()
    assert predicate()


def _save_saturation_configuration(runtime: QmlApplicationRuntime) -> Path:
    desktop = runtime.controller
    config = desktop.dataset_config_controller
    workspace = config.workspace
    assert workspace is not None
    assert desktop.request_new_dataset("saturation_table")
    assert config.document is not None
    destination = workspace.configs / "run-saturation.yaml"
    destination.write_bytes(config.document.yaml_bytes)
    assert desktop.request_close_configuration(True)
    assert desktop.request_import_dataset(str(destination))
    _wait_for_idle(runtime)
    assert config.document is not None
    assert not config.get_dirty()
    return destination


def _visible_item(root: QObject, object_name: str) -> QQuickItem:
    assert isinstance(root, QQuickWindow)
    matches: list[QQuickItem] = []
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        if item.objectName() == object_name and item.isVisible():
            matches.append(item)
    assert len(matches) == 1
    return matches[0]


def test_run_page_exposes_saved_snapshot_prerequisite_and_responsive_layout(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    runtime.controller.qml_settings.set_inspector_collapsed(False)
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "run")
    _process_events()

    page = root.findChild(QObject, "runPage")
    blocker = _visible_item(root, "runSnapshotBlocker")
    grid = root.findChild(QObject, "runWorkflowGrid")
    inspector = _visible_item(root, "runContextInspector")
    validate = root.findChild(QObject, "runValidateButton")
    generate = root.findChild(QObject, "runGenerateButton")
    assert page is not None
    assert blocker.isVisible()
    assert grid is not None
    assert inspector.isVisible()
    assert validate is not None
    assert generate is not None
    assert validate.property("enabled") is False
    assert generate.property("enabled") is False

    assert grid.property("columnCount") == 2
    assert root.setProperty("width", 768)
    assert root.setProperty("height", 768)
    _process_events()
    assert grid.property("columnCount") == 1
    assert runtime.warning_capture.runtime_warnings == ()


def test_workspace_pages_remain_navigable_before_a_saved_snapshot(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    _process_events()

    run_navigation = _visible_item(root, "nav-run")
    inspect_navigation = _visible_item(root, "nav-inspect")
    visualization_navigation = _visible_item(root, "nav-visualization")
    yaml_navigation = _visible_item(root, "nav-yaml")
    assert run_navigation.isEnabled()
    assert inspect_navigation.isEnabled()
    assert visualization_navigation.isEnabled()
    assert not yaml_navigation.isEnabled()

    _save_saturation_configuration(runtime)
    _process_events()
    assert runtime.controller.execution_controller.get_snapshot_available()
    assert run_navigation.isEnabled()
    assert yaml_navigation.isEnabled()


def test_rapid_dataset_to_run_navigation_retains_the_loaded_dataset_page(
    runtime: QmlApplicationRuntime,
) -> None:
    _save_saturation_configuration(runtime)
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("currentPage", "dataset")
    _process_events()

    dataset_page = root.findChild(QObject, "datasetPage")
    dataset_loader = root.findChild(QObject, "datasetPageLoader")
    assert dataset_page is not None
    assert dataset_loader is not None
    assert dataset_page.property("visible") is True
    assert dataset_loader.property("active") is True

    if "prandtl_number" not in desktop.dataset_draft.selected_property_values():
        assert desktop.dataset_draft.add_property("prandtl_number")
    assert root.setProperty("currentPage", "run")
    _process_events()

    assert dataset_loader.property("active") is True
    assert dataset_loader.property("item") is dataset_page
    assert dataset_page.property("visible") is False
    assert root.findChild(QObject, "runPage") is not None

    assert root.setProperty("currentPage", "dataset")
    _process_events()
    assert dataset_loader.property("item") is dataset_page
    assert dataset_page.property("visible") is True
    assert runtime.warning_capture.runtime_warnings == ()


def test_run_validation_uses_the_facade_and_persists_activity(
    runtime: QmlApplicationRuntime,
) -> None:
    destination = _save_saturation_configuration(runtime)
    desktop = runtime.controller
    execution = desktop.execution_controller
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "run")
    _process_events()

    validate = _visible_item(root, "runValidateButton")
    assert validate.isEnabled()
    assert QMetaObject.invokeMethod(validate, "click")
    _process_events()
    assert root.property("currentPage") == "run"
    assert execution.get_operation() == "validate"
    assert execution.get_state() in {"starting", "running", "succeeded"}

    _wait_for_idle(runtime)

    summary = root.findChild(QObject, "runResultSummary")
    inspector_state = root.findChild(QObject, "runInspectorState")
    assert execution.get_state() == "succeeded"
    assert execution.get_result_configuration_path() == str(destination)
    assert execution.get_result_mode() == "saturation_table"
    assert execution.get_result_projected_rows() > 0
    assert execution.get_activity_record_available()
    assert summary is not None
    assert "Validation accepted" in summary.property("text")
    assert inspector_state is not None
    assert inspector_state.property("text") == "Succeeded"

    workspace = desktop.dataset_config_controller.workspace
    assert workspace is not None
    [record] = JobStore(workspace.private_directory).load()
    assert record.data is not None
    assert record.data["operation"] == "validate"
    assert record.data["status"] == "completed"
    assert runtime.warning_capture.runtime_warnings == ()


def test_run_generation_stays_on_page_and_retains_saved_baseline_identity(
    runtime: QmlApplicationRuntime,
) -> None:
    destination = _save_saturation_configuration(runtime)
    desktop = runtime.controller
    execution = desktop.execution_controller
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "run")
    _process_events()

    generate = _visible_item(root, "runGenerateButton")
    assert generate.isEnabled()
    assert QMetaObject.invokeMethod(generate, "click")
    _process_events()
    assert root.property("currentPage") == "run"
    assert execution.get_operation() == "generate"

    _wait_for_idle(runtime)

    assert execution.get_state() == "succeeded"
    assert execution.get_result_configuration_path() == str(destination)
    assert execution.get_result_row_count() > 0
    output_directory = Path(execution.get_result_output_directory())
    assert output_directory.is_dir()
    assert execution.get_result_matches_current_saved_baseline()
    inspect_run = _visible_item(root, "runInspectButton")
    view_plots = _visible_item(root, "runViewPlotsButton")
    assert inspect_run.isEnabled()
    assert view_plots.isEnabled()

    assert QMetaObject.invokeMethod(view_plots, "click")
    _process_events()
    assert root.property("currentPage") == "visualization"
    configured = desktop.configured_plot_results_controller
    assert configured.get_selected_record_id() == execution.get_result_request_id()
    assert configured.get_state() == "incomplete"
    assert not desktop.request_coordinator.is_busy

    explore_run = _visible_item(root, "configuredExploreRunButton")
    assert explore_run.isEnabled()
    assert QMetaObject.invokeMethod(explore_run, "click")
    tabs = root.findChild(QObject, "visualizationViewTabs")
    assert tabs is not None
    _wait_until(
        runtime,
        lambda: (
            root.property("currentPage") == "visualization"
            and tabs.property("currentIndex") == 1
            and desktop.inspection_controller.get_state() == "ready"
            and desktop.inspection_controller.get_preview_state() == "ready"
            and not desktop.request_coordinator.is_busy
        ),
    )
    assert desktop.inspection_controller.get_source_path() == str(output_directory)
    assert desktop.session_plot_controller.get_source_path() == str(output_directory)

    assert root.setProperty("currentPage", "run")
    _process_events()
    inspect_run = _visible_item(root, "runInspectButton")
    assert QMetaObject.invokeMethod(inspect_run, "click")
    _process_events()
    assert root.property("currentPage") == "inspect"
    _wait_until(
        runtime,
        lambda: (
            desktop.inspection_controller.get_state() == "ready"
            and desktop.inspection_controller.get_preview_state() == "ready"
            and not desktop.request_coordinator.is_busy
        ),
    )

    explore_inspected = _visible_item(root, "inspectionExploreButton")
    assert explore_inspected.isEnabled()
    assert QMetaObject.invokeMethod(explore_inspected, "click")
    _process_events()
    assert root.property("currentPage") == "visualization"
    assert tabs.property("currentIndex") == 1
    assert not desktop.request_coordinator.is_busy

    desktop.dataset_draft.set_output_selected("csv", False)
    _process_events()
    assert execution.get_current_draft_dirty()
    assert execution.get_result_matches_current_saved_baseline()
    assert (
        execution.get_result_relation_issue()
        == "Generated from the current saved configuration; unsaved draft changes now exist."
    )
    relation = root.findChild(QObject, "runResultRelationBadge")
    issue = root.findChild(QObject, "runResultRelationIssue")
    assert relation is not None
    assert relation.property("label") == "Current saved baseline"
    assert issue is not None
    assert "unsaved draft changes" in issue.property("text")
    assert runtime.warning_capture.runtime_warnings == ()
