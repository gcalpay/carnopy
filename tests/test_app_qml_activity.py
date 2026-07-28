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
def runtime(tmp_path: Path, application: QApplication) -> QmlApplicationRuntime:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    request_id = "00000000-0000-0000-0000-000000000091"
    store = JobStore(workspace.private_directory)
    record = store.start(
        request_id=request_id,
        operation="generate",
        config_relative_path="configs/dataset.yaml",
        yaml_snapshot="schema_version: 2\n",
        config_sha256="a" * 64,
    )
    store.finish(
        record,
        {
            "request_id": request_id,
            "request_type": "generate_dataset",
            "terminal_event": {
                "type": "result",
                "payload": {
                    "run_id": "run-id",
                    "run_status": "completed",
                    "output_directory": str(workspace.outputs / "run-id"),
                    "row_count": 10,
                    "valid_row_count": 9,
                    "invalid_row_count": 1,
                    "visualization": {
                        "status": "not_requested",
                    },
                },
            },
            "stderr": "",
            "exit_code": 0,
            "exit_status": "normal",
            "force_stopped": False,
        },
    )
    candidate = workspace.outputs / ".20260728T120000Z_property_1a2b3c4d.staging"
    candidate.mkdir()
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        initial_workspace=workspace.root,
        application_arguments=[],
    )
    if created.controller.request_coordinator.is_busy:
        loop = QEventLoop()
        created.controller.request_coordinator.busy_changed.connect(
            lambda busy: None if busy else loop.quit()
        )
        QTimer.singleShot(15_000, loop.quit)
        loop.exec()
    assert not created.controller.request_coordinator.is_busy
    yield created
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(8):
        application.processEvents()


def _visible_item(root: QObject, object_name: str) -> QQuickItem:
    matches = [item for item in root.findChildren(QQuickItem, object_name) if item.isVisible()]
    assert len(matches) == 1
    return matches[0]


def test_activity_page_projects_records_details_and_diagnostics(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert not runtime.controller.request_coordinator.is_busy
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "activity")
    _process_events()

    controller = runtime.controller.activity_controller
    page = root.findChild(QObject, "activityPage")
    records = _visible_item(root, "activityRecordsList")
    inspector = _visible_item(root, "activityContextInspector")
    assert page is not None
    assert records.property("count") == 1
    assert inspector.isVisible()
    assert not runtime.controller.request_coordinator.is_busy

    [row] = controller.records_model.rows()
    assert controller.select_record(str(row["recordId"]))
    _process_events()

    assert controller.get_selected_record_state() == "completed"
    assert controller.get_can_inspect_run()
    assert not controller.get_can_view_plots()
    assert page.setProperty("diagnosticExpanded", True)
    _process_events()
    diagnostic = _visible_item(root, "activityDiagnosticText")
    assert '"request_id"' in diagnostic.property("text")


def test_recovery_tab_selects_exact_paths_before_confirmation(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "activity")
    _process_events()
    assert not runtime.controller.request_coordinator.is_busy
    tabs = root.findChild(QObject, "activityTabs")
    assert tabs is not None
    assert tabs.setProperty("currentIndex", 1)
    _process_events()

    controller = runtime.controller.activity_controller
    assert controller.set_recovery_selected(0, True)
    _process_events()
    assert controller.get_selected_recovery_count() == 1
    [selected_path] = controller.get_selected_recovery_paths()
    assert selected_path.endswith(".staging")

    remove = _visible_item(root, "recoveryRemoveButton")
    assert QMetaObject.invokeMethod(remove, "click")
    _process_events()
    dialog = root.findChild(QObject, "removeRecoveryDialog")
    assert dialog is not None
    assert dialog.property("visible") is True
    assert selected_path in dialog.property("bodyText")
    assert Path(selected_path).is_dir()
