from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QSettings, QTimer
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication

from carnopy.app.config_document import new_document
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace
from carnopy.templates import template_text


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


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(6):
        application.processEvents()


def test_global_shell_routes_sweep_documents_to_the_structured_editor(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    payload = yaml.safe_load(template_text("model_sweep"))

    assert runtime.controller.configuration_controller.open_document(new_document(payload))
    _process_events()

    assert runtime.controller.configuration_controller.get_document_kind() == "model_sweep"
    assert root.property("currentPage") == "sweeps"
    assert root.findChild(QObject, "modelSweepPage") is not None


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        _process_events()
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    _process_events()
    assert not runtime.controller.request_coordinator.is_busy


def test_yaml_page_projects_only_current_authoritative_document(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("currentPage", "yaml")
    _process_events()

    controller = desktop.configuration_controller
    page = root.findChild(QObject, "yamlPreviewPage")
    viewer = root.findChild(QObject, "yamlLineNumberedText")
    source = root.findChild(QObject, "yamlSourceText")
    assert page is not None
    assert viewer is not None
    assert source is not None
    assert page.property("configController") is controller
    assert controller.get_yaml_available()
    assert source.property("text") == controller.get_yaml_preview()
    assert "schema_version: 2" in source.property("text")
    assert viewer.findNext("backend") is True
    assert source.property("selectedText").lower() == "backend"


def test_inspector_distinguishes_workspace_readiness_from_document_state(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    configuration_state = root.findChild(QObject, "inspectorConfigurationState")
    validation_state = root.findChild(QObject, "inspectorWorkerValidationState")
    assert configuration_state is not None
    assert validation_state is not None
    assert configuration_state.property("text") == "Not loaded"
    assert validation_state.property("text") == "Not available"

    assert desktop.request_new_dataset("property_table")
    _process_events()
    assert configuration_state.property("text") == "Unsaved"
    assert validation_state.property("text") == "Not run"


def test_inspector_runs_one_revision_bound_standalone_validation(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    controller = desktop.configuration_controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    _process_events()

    buttons = root.findChildren(QObject, "inspectorValidateButton")
    visible_buttons = [button for button in buttons if button.property("visible")]
    state = root.findChild(QObject, "inspectorWorkerValidationState")
    assert len(visible_buttons) == 1
    assert state is not None
    button = visible_buttons[0]
    assert button.property("enabled") is True

    button.clicked.emit()
    _process_events()
    assert controller.get_worker_validation_state() == "running"
    assert state.property("text") == "Running"
    assert button.property("enabled") is False

    _wait_for_idle(runtime)
    assert controller.get_worker_validation_state() == "valid"
    assert state.property("text") == "Valid"
    assert button.property("enabled") is True


def test_inspector_validation_is_blocked_by_local_invalidity(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    controller = desktop.configuration_controller
    root = runtime.engine.rootObjects()[0]
    assert desktop.request_new_dataset("property_table")
    controller.dataset_draft.set_output_selected("csv", False)
    controller.dataset_draft.set_output_selected("parquet", False)
    _process_events()

    button = root.findChild(QObject, "inspectorValidateButton")
    state = root.findChild(QObject, "inspectorWorkerValidationState")
    assert button is not None
    assert state is not None
    assert controller.get_worker_validation_state() == "blocked"
    assert state.property("text") == "Blocked"
    assert button.property("enabled") is False


def test_invalid_yaml_state_is_empty_and_routes_by_structured_field(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("currentPage", "yaml")
    desktop.dataset_draft.set_output_selected("csv", False)
    desktop.dataset_draft.set_output_selected("parquet", False)
    _process_events()

    controller = desktop.configuration_controller
    banner = root.findChild(QObject, "yamlBlockingBanner")
    assert banner is not None
    assert not controller.get_yaml_available()
    assert controller.get_yaml_preview() == ""
    assert controller.get_blocking_section() == "dataset"
    assert controller.get_blocking_field() == "dataset.outputs.dataset_formats"
    assert banner.property("visible") is True

    banner.actionRequested.emit(
        controller.get_blocking_section(),
        controller.get_blocking_field(),
        controller.get_blocking_row(),
    )
    _process_events()

    assert root.property("currentPage") == "dataset"
    focused = root.activeFocusItem()
    assert focused is not None
    assert focused.objectName() == "datasetOutput-csv"


def test_typed_operation_feedback_is_persistent_until_success_or_dismissal(
    runtime: QmlApplicationRuntime,
) -> None:
    controller = runtime.controller.configuration_controller
    root = runtime.engine.rootObjects()[0]
    feedback = root.findChild(QObject, "operationFeedback")
    toast = root.findChild(QObject, "toastHost")
    assert feedback is not None
    assert toast is not None

    controller.operationFailed.emit(
        "save",
        "Validation Failed",
        "The worker rejected the exact YAML.",
        [{"path": "grid.pressure", "code": "value_error", "message": "invalid grid"}],
    )
    _process_events()

    assert feedback.property("visible") is True
    assert feedback.property("operation") == "save"
    assert feedback.property("title") == "Validation Failed"
    assert feedback.property("message") == "The worker rejected the exact YAML."

    controller.saveSucceeded.emit("/workspace/configs/dataset.yaml")
    _process_events()
    assert feedback.property("visible") is False
    assert "Saved validated configuration" in toast.property("message")


def test_dirty_close_configuration_uses_qml_decision_and_facade(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert desktop.request_new_dataset("property_table")
    _process_events()
    command_bar = root.findChild(QObject, "documentCommandBar")
    dialog = root.findChild(QObject, "configurationDiscardDialog")
    assert command_bar is not None
    assert dialog is not None
    assert desktop.configuration_controller.get_dirty()

    command_bar.closeConfigurationRequested.emit()
    _process_events()
    assert dialog.property("opened") is True
    assert desktop.configuration_controller.get_has_document()

    dialog.accept()
    _process_events()
    assert not desktop.configuration_controller.get_has_document()
    assert root.property("currentPage") == "dataset"


def test_qml_save_command_keeps_worker_validation_and_reformat_authoritative(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    controller = desktop.configuration_controller
    root = runtime.engine.rootObjects()[0]
    workspace = controller.workspace
    assert workspace is not None
    assert desktop.request_new_dataset("property_table")
    assert controller.document is not None
    source = workspace.configs / "imported.yaml"
    source.write_bytes(controller.document.yaml_bytes)
    assert desktop.request_close_configuration(True)

    assert desktop.request_import_dataset(str(source))
    _wait_for_idle(runtime)
    assert controller.document is not None
    assert controller.document.imported
    controller.dataset_draft.set_output_selected("csv", False)
    expected = controller.document.yaml_bytes
    assert controller.get_dirty()

    command_bar = root.findChild(QObject, "documentCommandBar")
    reformat_dialog = root.findChild(QObject, "reformatConfirmationDialog")
    toast = root.findChild(QObject, "toastHost")
    assert command_bar is not None
    assert reformat_dialog is not None
    assert toast is not None
    command_bar.saveRequested.emit()
    _process_events()
    assert reformat_dialog.property("opened") is True

    reformat_dialog.accept()
    _process_events()
    _wait_for_idle(runtime)
    assert source.read_bytes() == expected
    assert not controller.get_dirty()
    assert "Saved validated configuration" in toast.property("message")
