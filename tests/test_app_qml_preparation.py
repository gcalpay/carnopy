from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication

from carnopy.app.config_document import new_document
from carnopy.app.qml_resources import MANDATORY_QML_FILES
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.scenario_draft import ScenarioDraft
from carnopy.app.workspace import initialize_workspace
from carnopy.templates import template_text

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
def scenario_editor(runtime: QmlApplicationRuntime) -> Iterator[QQuickItem]:
    desktop = runtime.controller
    draft = ScenarioDraft(
        field_choices=("temperature", "pressure", "fluid", "phase"),
        parent=desktop,
    )

    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1200)
    root.setHeight(1200)
    component = QQmlComponent(runtime.engine)
    component.loadFromModule("Carnopy", "PreparationScenarioEditor")
    assert component.status() == QQmlComponent.Status.Ready, _component_errors(component)
    created = component.createWithInitialProperties(
        {
            "desktopController": desktop,
            "dialogsEnabled": False,
            "draft": draft,
            "locked": False,
        }
    )
    assert isinstance(created, QQuickItem), _component_errors(component)
    created.setParent(root)
    created.setParentItem(root.contentItem())
    created.setWidth(900)
    created.setZ(1000)
    _process_events()
    yield created


@pytest.fixture
def preparation_page(runtime: QmlApplicationRuntime) -> Iterator[QQuickItem]:
    desktop = runtime.controller
    payload = yaml.safe_load(template_text(cast(Any, "preparation")))
    assert isinstance(payload, dict)
    assert desktop.configuration_controller.open_document(new_document(payload))

    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1200)
    component = QQmlComponent(runtime.engine)
    component.loadFromModule("Carnopy", "PreparationPage")
    assert component.status() == QQmlComponent.Status.Ready, _component_errors(component)
    created = component.createWithInitialProperties(
        {
            "configController": desktop.configuration_controller,
            "desktopController": desktop,
            "dialogsEnabled": False,
            "expectedColumns": 3,
            "inspectionController": desktop.inspection_controller,
            "preparationDraft": desktop.configuration_controller.preparation_draft,
            "workflowController": desktop.preparation_workflow_controller,
        }
    )
    assert isinstance(created, QQuickItem), _component_errors(component)
    created.setObjectName("directPreparationPage")
    created.setParent(root)
    created.setParentItem(root.contentItem())
    created.setWidth(root.width())
    created.setHeight(root.height())
    created.setZ(1000)
    _process_events()
    yield created


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


def test_scenario_editor_binds_the_complete_temporary_surface(
    runtime: QmlApplicationRuntime,
    scenario_editor: QQuickItem,
) -> None:
    active = scenario_editor.property("draft")
    assert isinstance(active, ScenarioDraft)

    expected = {
        "preparationScenarioEditor",
        "preparationScenarioEditorIssue",
        "preparationScenarioBasicsGrid",
        "preparationScenarioName",
        "preparationScenarioKind",
        "preparationScenarioSeed",
        "preparationScenarioField",
        "preparationScenarioRemainder",
        "preparationScenarioPartitionsCard",
        "preparationScenarioPartitions",
        "preparationScenarioHoldoutsCard",
        "preparationScenarioHoldouts",
        "preparationScenarioStratificationCard",
        "preparationScenarioStrataFields",
        "preparationScenarioNumericBins",
        "preparationScenarioTransformationsCard",
        "preparationScenarioTransformations",
        "preparationScenarioCancelButton",
        "preparationScenarioCommitButton",
    }
    assert expected <= _visual_names(scenario_editor)
    assert scenario_editor.property("draft") is active
    assert _item(scenario_editor, "preparationScenarioCommitButton").property("enabled")
    assert not _item(scenario_editor, "preparationScenarioPartitionsCard").isVisible()
    assert not _item(scenario_editor, "preparationScenarioHoldoutsCard").isVisible()
    assert not _item(scenario_editor, "preparationScenarioStratificationCard").isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_scenario_editor_projects_all_kind_specific_sections_without_warnings(
    runtime: QmlApplicationRuntime,
    scenario_editor: QQuickItem,
) -> None:
    active = scenario_editor.property("draft")
    assert isinstance(active, ScenarioDraft)
    cases = (
        ("shuffle", True, False, False),
        ("stratified_hash", True, False, True),
        ("coordinate_block", False, True, False),
        ("range_holdout", False, True, False),
        ("leave_fluid_out", False, True, False),
        ("phase_holdout", False, True, False),
        ("model_holdout", False, True, False),
        ("unsplit", False, False, False),
    )
    for kind, partitions, holdouts, strata in cases:
        active.apply_kind_change(kind, True)
        _process_events()
        assert active.get_kind() == kind
        assert _item(scenario_editor, "preparationScenarioPartitionsCard").isVisible() is partitions
        assert _item(scenario_editor, "preparationScenarioHoldoutsCard").isVisible() is holdouts
        assert _item(scenario_editor, "preparationScenarioStratificationCard").isVisible() is strata

    assert runtime.warning_capture.runtime_warnings == ()


def test_scenario_editor_nested_models_focus_and_responsive_layout_are_authoritative(
    runtime: QmlApplicationRuntime,
    scenario_editor: QQuickItem,
) -> None:
    active = scenario_editor.property("draft")
    assert isinstance(active, ScenarioDraft)
    active.apply_kind_change("stratified_hash", True)
    active.set_strata_categorical("fluid, phase")
    active.set_numeric_bins("temperature", "250, 300")
    active.add_transformation("pressure", "log10, standard")
    _process_events()

    assert active.get_strata_categorical_text() == "fluid, phase"
    assert active.numeric_bin_rows.get_count() == 1
    assert active.transformation_rows.get_count() == 1
    assert _item(scenario_editor, "preparationScenarioNumericBins").property("count") == 1
    assert _item(scenario_editor, "preparationScenarioTransformations").property("count") == 1

    scenario_editor.setProperty("attentionField", "preparation.scenario.active.seed")
    scenario_editor.setProperty("attentionSerial", 1)
    _process_events()
    assert _item(scenario_editor, "preparationScenarioSeed").property("activeFocus") is True

    assert _item(scenario_editor, "preparationScenarioBasicsGrid").property("columns") == 2
    scenario_editor.setWidth(600)
    _process_events()
    assert _item(scenario_editor, "preparationScenarioBasicsGrid").property("columns") == 1
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_scenario_qml_resource_and_controller_boundary_are_explicit() -> None:
    qml_root = ROOT / "src/carnopy/app/qml/Carnopy"
    source = (qml_root / "components/PreparationScenarioEditor.qml").read_text(encoding="utf-8")
    qmldir = (qml_root / "qmldir").read_text(encoding="utf-8")

    assert "PreparationScenarioEditor 1.0 components/PreparationScenarioEditor.qml" in qmldir
    assert "qml/Carnopy/components/PreparationScenarioEditor.qml" in MANDATORY_QML_FILES
    assert "requestPreparationScenario" in source
    assert 'Accessible.name: qsTr("Scenario name")' in source
    assert 'Accessible.name: qsTr("Scenario partitions")' in source
    assert 'Accessible.name: qsTr("Scenario transformations")' in source
    assert ".setName(" not in source
    assert ".setPartition(" not in source
    assert ".addTransformation(" not in source
    assert "yaml" not in source.casefold()


def test_hidden_preparation_page_binds_the_complete_authoritative_editor(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.preparation_draft

    assert preparation_page.property("configController") is desktop.configuration_controller
    assert preparation_page.property("desktopController") is desktop
    assert preparation_page.property("inspectionController") is desktop.inspection_controller
    assert preparation_page.property("preparationDraft") is draft
    assert (
        preparation_page.property("workflowController") is desktop.preparation_workflow_controller
    )
    assert preparation_page.property("documentActive") is True
    assert preparation_page.property("locked") is False

    expected = {
        "preparationPageFlickable",
        "preparationLocalState",
        "preparationBoundSourceCard",
        "preparationBoundSourceState",
        "preparationRolesGrid",
        "preparationNumericFeaturesCard",
        "preparationDerivedFeaturesCard",
        "preparationTargetsCard",
        "preparationAuxiliaryCard",
        "preparationCategoricalCard",
        "preparationScenariosCard",
        "preparationAllowPartialSweep",
        "preparationAddScenario",
        "preparationScenarioList",
        "preparationOutputQualityGrid",
        "preparationOutputsCard",
        "preparationArrayOutputs",
        "preparationQualityCard",
        "preparationMatrixDiagnostics",
        "preparationBaselineDiagnostics",
        "preparationBaselineDependencyGuidance",
        "preparationWorkflowRunPanel",
        "preparationPlanButton",
        "preparationExecuteButton",
    }
    names = _visual_names(preparation_page)
    assert expected <= names
    assert _item(preparation_page, "preparationRolesGrid").property("maximumColumns") == 3
    assert _item(preparation_page, "preparationOutputQualityGrid").property("maximumColumns") == 2
    assert _item(preparation_page, "preparationNumeric-temperature").property("checked")
    assert _item(preparation_page, "preparationTarget-specific_enthalpy").property("checked")
    assert _item(preparation_page, "preparationCategorical-phase").property("checked")
    assert not _item(preparation_page, "preparationPlanButton").property("enabled")
    assert not _item(preparation_page, "preparationExecuteButton").property("enabled")
    guidance = _item(preparation_page, "preparationBaselineDependencyGuidance").property("text")
    assert bool(guidance) is (not draft.get_baseline_available())
    if guidance:
        assert "carnopy[analysis]" in guidance
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_page_restores_one_python_owned_scenario_editor(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.preparation_draft

    assert desktop.request_preparation_add_scenario()
    _process_events()
    assert draft.get_has_active_scenario_edit()
    editor = _item(preparation_page, "preparationScenarioEditor")
    active = draft.get_active_scenario_draft()
    assert isinstance(active, ScenarioDraft)
    assert editor.property("draft") is active
    desktop.request_preparation_scenario_field_change(active, "name", "complete-source")
    _process_events()
    assert _item(editor, "preparationScenarioCommitButton").property("enabled")
    assert desktop.request_preparation_commit_scenario()
    _process_events()

    assert not draft.get_has_active_scenario_edit()
    assert draft.scenarios_model.rowCount() == 1
    assert draft.scenarios_model.rows()[0]["name"] == "complete-source"
    assert _item(preparation_page, "preparationScenarioList").property("count") == 1
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_page_focus_and_responsive_state_remain_warning_free(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.preparation_draft

    preparation_page.setProperty("attentionField", "preparation.outputs")
    preparation_page.setProperty("attentionSerial", 1)
    _process_events()
    assert _item(preparation_page, "preparationOutputsCard").property("activeFocus") is True

    assert desktop.request_preparation_add_scenario()
    _process_events()
    active = draft.get_active_scenario_draft()
    assert isinstance(active, ScenarioDraft)
    preparation_page.setProperty("attentionField", "preparation.scenario.active.name")
    preparation_page.setProperty("attentionSerial", 2)
    _process_events()
    assert _item(preparation_page, "preparationScenarioName").property("activeFocus") is True

    preparation_page.setWidth(720)
    preparation_page.setProperty("expectedColumns", 1)
    _process_events()
    assert _item(preparation_page, "preparationRolesGrid").property("maximumColumns") == 1
    assert _item(preparation_page, "preparationOutputQualityGrid").property("maximumColumns") == 1
    assert desktop.request_preparation_cancel_scenario()
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_page_qml_resource_and_controller_boundary_are_explicit() -> None:
    qml_root = ROOT / "src/carnopy/app/qml/Carnopy"
    source = (qml_root / "pages/PreparationPage.qml").read_text(encoding="utf-8")
    qmldir = (qml_root / "qmldir").read_text(encoding="utf-8")

    assert "PreparationPage 1.0 pages/PreparationPage.qml" in qmldir
    assert "qml/Carnopy/pages/PreparationPage.qml" in MANDATORY_QML_FILES
    assert "requestPreparation" in source
    assert "requestWorkflow" in source
    assert 'Accessible.name: qsTr("Committed Preparation scenarios")' in source
    assert 'Accessible.name: qsTr("Enable matrix diagnostics")' in source
    assert ".setRoleSelected(" not in source
    assert ".beginAddScenario(" not in source
    assert ".commitScenario(" not in source
    assert "PreparationAuditView" not in source
    assert "TextArea" not in source
