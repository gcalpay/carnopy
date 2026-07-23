from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QMetaObject, QObject, QSettings, QTimer
from PySide6.QtQuick import QQuickItem
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
    matches = [item for item in root.findChildren(QQuickItem, object_name) if item.isVisible()]
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


def test_run_validation_uses_the_facade_and_persists_activity(
    runtime: QmlApplicationRuntime,
) -> None:
    destination = _save_saturation_configuration(runtime)
    desktop = runtime.controller
    execution = desktop.execution_controller
    root = runtime.engine.rootObjects()[0]
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
    assert not inspect_run.isEnabled()
    assert not view_plots.isEnabled()

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
