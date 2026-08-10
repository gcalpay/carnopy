from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_resources import MANDATORY_QML_FILES
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.fixture
def runtime(tmp_path: Path, application: QApplication) -> Iterator[QmlApplicationRuntime]:
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


@pytest.fixture
def sweep_page(runtime: QmlApplicationRuntime) -> Iterator[QQuickItem]:
    desktop = runtime.controller
    assert desktop.configuration_controller.new_sweep()
    _process_events()
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1100)
    component = QQmlComponent(runtime.engine)
    component.loadFromModule("Carnopy", "ModelSweepPage")
    assert component.status() == QQmlComponent.Status.Ready, _component_errors(component)
    created = component.createWithInitialProperties(
        {
            "configController": desktop.configuration_controller,
            "desktopController": desktop,
            "sweepDraft": desktop.configuration_controller.sweep_draft,
            "workflowController": desktop.sweep_workflow_controller,
            "expectedColumns": 3,
            "dialogsEnabled": False,
        }
    )
    assert isinstance(created, QQuickItem), _component_errors(component)
    created.setObjectName("directModelSweepPage")
    created.setParent(root)
    created.setParentItem(root.contentItem())
    created.setWidth(root.width())
    created.setHeight(root.height())
    created.setZ(1000)
    _process_events()
    yield created
    created.setParentItem(None)
    created.deleteLater()
    component.deleteLater()
    _process_events()


def _component_errors(component: QQmlComponent) -> str:
    return "\n".join(error.toString() for error in component.errors())


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
    for _ in range(6):
        application.processEvents()


def _item(root: QQuickItem, object_name: str) -> QQuickItem:
    pending = [root]
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name:
            return candidate
        pending.extend(candidate.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def _visual_names(root: QQuickItem) -> set[str]:
    names: set[str] = set()
    pending = [root]
    while pending:
        candidate = pending.pop()
        if candidate.objectName():
            names.add(candidate.objectName())
        pending.extend(candidate.childItems())
    return names


def test_hidden_model_sweep_page_binds_complete_authoritative_surface(
    runtime: QmlApplicationRuntime,
    sweep_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.sweep_draft

    assert sweep_page.property("configController") is desktop.configuration_controller
    assert sweep_page.property("desktopController") is desktop
    assert sweep_page.property("sweepDraft") is draft
    assert sweep_page.property("workflowController") is desktop.sweep_workflow_controller
    assert sweep_page.property("locked") is False
    assert draft.dataset_draft.samplers.rowCount() == 2
    assert _item(sweep_page, "modelSweepPageFlickable").property("pixelAligned") is True
    assert _item(sweep_page, "modelSweepDefinitionGrid").property("maximumColumns") == 3

    expected = {
        "modelSweepModelsCard",
        "modelSweepReferenceModel",
        "modelSweepMode",
        "modelSweepFluids",
        "modelSweepProperties",
        "samplerEditor-temperature",
        "samplerEditor-pressure",
        "modelSweepOutputsCard",
        "modelSweepComparisonsCard",
        "sweepWorkflowRunPanel",
        "sweepPlanButton",
        "sweepExecuteButton",
        "sweepInspectResultButton",
        "sweepPlanBlocker-0",
    }
    names = _visual_names(sweep_page)
    assert expected <= names, sorted(name for name in names if "ampler" in name)
    assert "HEOS" in _item(sweep_page, "modelSweepModel-heos").property("text")
    assert not _item(sweep_page, "sweepPlanButton").property("enabled")
    assert not _item(sweep_page, "sweepExecuteButton").property("enabled")
    assert "save" in _item(sweep_page, "sweepPlanBlocker-0").property("text").casefold()
    assert runtime.warning_capture.runtime_warnings == ()


def test_model_sweep_page_routes_edits_and_commits_one_temporary_comparison(
    runtime: QmlApplicationRuntime,
    sweep_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.sweep_draft
    selected_before = draft.get_selected_models()
    desktop.request_sweep_model_selection("srk", False)
    _process_events()
    assert draft.get_selected_models() == [value for value in selected_before if value != "srk"]
    assert desktop.configuration_controller.get_dirty()

    assert desktop.request_sweep_add_comparison()
    _process_events()
    assert draft.get_has_active_comparison_edit()
    editor = _item(sweep_page, "comparisonPlotEditor")
    assert _item(editor, "comparisonPlotName").property("enabled")
    assert _item(editor, "comparisonPlotKind") is not None
    assert _item(editor, "comparisonPlotFluid") is not None
    assert _item(editor, "comparisonPlotProperty") is not None
    assert _item(editor, "comparisonPlotX") is not None
    assert _item(editor, "comparisonPlotFilters") is not None

    active = draft.get_active_comparison_draft()
    assert active is not None
    desktop.request_sweep_comparison_field_change(active, "name", "density-comparison")
    _process_events()
    commit = _item(editor, "comparisonPlotCommitButton")
    assert commit.property("enabled")
    assert desktop.request_sweep_commit_comparison()
    _process_events()

    assert not draft.get_has_active_comparison_edit()
    assert draft.comparison_plots_model.rowCount() == 1
    assert "Property comparison" in draft.comparison_plots_model.items[0].display
    assert _item(sweep_page, "modelSweepComparisonList").property("count") == 1
    assert runtime.warning_capture.runtime_warnings == ()


def test_model_sweep_focus_and_responsive_state_remain_warning_free(
    runtime: QmlApplicationRuntime,
    sweep_page: QQuickItem,
) -> None:
    reference = _item(sweep_page, "modelSweepReferenceModel")
    sweep_page.setProperty("attentionField", "sweep.backend.reference_model")
    sweep_page.setProperty("attentionSerial", 1)
    _process_events()
    assert reference.property("activeFocus") is True

    sweep_page.setWidth(720)
    sweep_page.setProperty("expectedColumns", 1)
    _process_events()
    assert _item(sweep_page, "modelSweepDefinitionGrid").property("maximumColumns") == 1
    sweep_page.setWidth(1440)
    sweep_page.setProperty("expectedColumns", 3)
    _process_events()
    assert _item(sweep_page, "modelSweepDefinitionGrid").property("maximumColumns") == 3
    assert runtime.warning_capture.runtime_warnings == ()


def test_sweep_qml_resources_and_controller_boundary_are_explicit() -> None:
    qml_root = ROOT / "src/carnopy/app/qml/Carnopy"
    page_source = (qml_root / "pages/ModelSweepPage.qml").read_text(encoding="utf-8")
    editor_source = (qml_root / "components/ComparisonPlotEditor.qml").read_text(encoding="utf-8")
    qmldir = (qml_root / "qmldir").read_text(encoding="utf-8")

    assert "ModelSweepPage 1.0 pages/ModelSweepPage.qml" in qmldir
    assert "ComparisonPlotEditor 1.0 components/ComparisonPlotEditor.qml" in qmldir
    assert "WorkflowRunPanel 1.0 components/WorkflowRunPanel.qml" in qmldir
    assert "qml/Carnopy/pages/ModelSweepPage.qml" in MANDATORY_QML_FILES
    assert "qml/Carnopy/components/ComparisonPlotEditor.qml" in MANDATORY_QML_FILES
    assert "qml/Carnopy/components/WorkflowRunPanel.qml" in MANDATORY_QML_FILES
    assert "requestSweep" in page_source
    assert "requestWorkflow" in page_source
    assert "requestSweep" in editor_source
    assert 'Accessible.name: qsTr("Sweep reference model")' in page_source
    assert 'Accessible.name: qsTr("Committed comparison plots")' in page_source
    assert 'Accessible.name: qsTr("Comparison plot name")' in editor_source
    assert 'Accessible.name: qsTr("Comparison delta metric")' in editor_source
    assert ".setModelSelected(" not in page_source
    assert ".setReferenceModel(" not in page_source
    assert ".beginAddComparison(" not in page_source
    assert ".commitComparison(" not in page_source
    assert ".setName(" not in editor_source
    assert "yaml" not in editor_source.casefold()
