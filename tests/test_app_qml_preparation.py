from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QMetaObject,
    QObject,
    QPointF,
    QSettings,
    QTimer,
)
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


def _visible_item(root: QQuickWindow, object_name: str) -> QQuickItem:
    pending = [root.contentItem()]
    matches: list[QQuickItem] = []
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name and candidate.isVisible():
            matches.append(candidate)
        pending.extend(candidate.childItems())
    assert len(matches) == 1
    return matches[0]


def _field_profile(name: str) -> dict[str, object]:
    source = (
        "coordinate"
        if name in {"temperature", "pressure"}
        else "property"
        if name in {"mass_density", "specific_enthalpy"}
        else "categorical"
        if name == "phase"
        else "auxiliary"
    )
    return {
        "name": name,
        "column": name,
        "unit": None,
        "source": source,
        "reference_dependent": name == "specific_enthalpy",
    }


def _open_saved_preparation(runtime: QmlApplicationRuntime) -> None:
    controller = runtime.controller.configuration_controller
    workspace = controller.workspace
    assert workspace is not None
    payload = yaml.safe_load(template_text(cast(Any, "preparation")))
    assert isinstance(payload, dict)
    document = new_document(payload)
    destination = workspace.configs / "qml-plan-preparation.yaml"
    content = document.yaml_bytes
    destination.write_bytes(content)
    document.mark_saved(destination, content)
    assert controller.open_document(document)


def _accept_preparation_eligible_inspection(
    runtime: QmlApplicationRuntime,
    source: Path,
) -> None:
    revision = "a" * 64
    resolved = source.resolve()
    descriptor = {
        "source_path": str(resolved),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "controls": {},
        "tables": [],
    }
    profile = {
        "profile_schema_version": 1,
        "source_path": str(resolved),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "source_identity": {"source_kind": "dataset_run"},
        "completion": {
            "status": "completed",
            "partial": False,
            "included_child_models": [],
            "missing_child_models": [],
        },
        "available_models": ["heos"],
        "declared_models": [],
        "reference_model": "heos",
        "numeric_candidates": [
            _field_profile("temperature"),
            _field_profile("pressure"),
            _field_profile("mass_density"),
            _field_profile("specific_enthalpy"),
        ],
        "target_candidates": [
            _field_profile("temperature"),
            _field_profile("pressure"),
            _field_profile("mass_density"),
            _field_profile("specific_enthalpy"),
        ],
        "categorical_candidates": [_field_profile("phase")],
        "auxiliary_candidates": [
            _field_profile("fluid"),
            _field_profile("backend_model"),
            _field_profile("phase"),
            _field_profile("run_id"),
            _field_profile("case_id"),
        ],
        "observed_category_values": {"phase": ["liquid", "gas"]},
        "derived_features": [
            {
                "name": "specific_volume",
                "status": "ready",
                "available": True,
                "ready_row_count": 10,
                "source_row_count": 10,
                "reason": "",
                "reason_codes": [],
                "missing_dependencies": [],
                "dependencies": ["mass_density"],
                "unit": "m^3/kg",
            }
        ],
        "model_holdout": {
            "available": False,
            "reason": "Model holdout scenarios require a model-sweep source.",
        },
        "reference_context": {
            "compatible": True,
            "compatible_context": {
                "reference_state_policy": "coolprop_DEF",
                "backend": "coolprop",
                "backend_model": "heos",
            },
            "contexts": [],
            "reason_code": "",
            "reason": "",
        },
    }
    inspection = runtime.controller.inspection_controller
    inspection._clear_inspection(source=resolved, state="loading")
    inspection._accept_inspection_payload(
        {
            "source": str(resolved),
            "source_kind": "dataset",
            "revision": revision,
            "summary": {},
            "tables": [],
            "arrays": [],
            "plot_context": None,
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
            "preparation_profile": profile,
        }
    )


def test_shell_requires_a_bound_source_then_enables_the_preparation_surface(
    runtime: QmlApplicationRuntime,
    tmp_path: Path,
) -> None:
    desktop = runtime.controller
    controller = desktop.configuration_controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1200)
    _process_events()

    workspace_page = root.findChild(QObject, "workspacePage")
    preparation_button = _visible_item(root, "newPreparationButton")
    preparation_navigation = _visible_item(root, "nav-preparation")
    assert workspace_page is not None
    assert preparation_button.property("text") == "Choose source in Inspect"
    assert preparation_button.property("enabled") is True
    assert preparation_navigation.property("enabled") is True

    assert QMetaObject.invokeMethod(preparation_button, "click")
    _process_events()
    assert root.property("currentPage") == "inspect"
    assert not controller.get_has_document()

    source = tmp_path / "workspace" / "outputs" / "eligible-source"
    source.mkdir()
    _accept_preparation_eligible_inspection(runtime, source)
    _process_events()
    bind_button = _visible_item(root, "preparationBindSourceButton")
    assert bind_button.width() > 36
    assert bind_button.property("text") == "Use for ML Preparation"
    assert QMetaObject.invokeMethod(bind_button, "click")
    _process_events()
    assert desktop.preparation_workflow_controller.get_has_bound_source()
    assert not bind_button.isVisible()
    assert _visible_item(root, "preparationClearSourceButton").width() > 36
    assert _visible_item(root, "preparationContinueButton").width() > 36

    assert desktop.request_new_dataset("property_table")
    assert root.setProperty("currentPage", "workspace")
    _process_events()
    preparation_button = _visible_item(root, "newPreparationButton")
    assert preparation_button.property("text") == "New ML Preparation"
    assert QMetaObject.invokeMethod(preparation_button, "click")
    _process_events()

    discard_dialog = root.findChild(QObject, "configurationDiscardDialog")
    assert discard_dialog is not None
    assert discard_dialog.property("opened") is True
    assert controller.get_document_kind() == "dataset"
    discard_dialog.accept()
    _process_events()

    page = root.findChild(QObject, "preparationPage")
    command_bar = root.findChild(QObject, "documentCommandBar")
    inspector = _visible_item(root, "preparationWorkflowContextInspector")
    assert page is not None
    assert command_bar is not None
    assert controller.get_document_kind() == "preparation"
    assert root.property("currentPage") == "preparation"
    assert page.property("visible") is True
    assert page.property("documentActive") is True
    assert page.property("preparationDraft") is controller.preparation_draft
    assert page.property("workflowController") is desktop.preparation_workflow_controller
    assert command_bar.property("pageTitle") == "ML Preparation"
    assert command_bar.property("statusLabel") == "Unsaved Preparation"
    assert inspector.property("visible") is True

    change_source = _visible_item(root, "preparationChangeSource")
    assert QMetaObject.invokeMethod(change_source, "click")
    _process_events()
    assert root.property("currentPage") == "inspect"
    assert desktop.preparation_workflow_controller.get_bound_source_path() == str(source.resolve())
    assert runtime.warning_capture.runtime_warnings == ()


def test_shell_queues_mutations_from_the_visible_preparation_page(
    runtime: QmlApplicationRuntime,
    tmp_path: Path,
) -> None:
    desktop = runtime.controller
    controller = desktop.configuration_controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.setWidth(1440)
    root.setHeight(1200)

    source = tmp_path / "workspace" / "outputs" / "eligible-source"
    source.mkdir()
    _accept_preparation_eligible_inspection(runtime, source)
    assert root.setProperty("currentPage", "inspect")
    _process_events()
    assert QMetaObject.invokeMethod(_visible_item(root, "preparationBindSourceButton"), "click")
    _process_events()

    continue_button = _visible_item(root, "preparationContinueButton")
    assert QMetaObject.invokeMethod(continue_button, "click")
    _process_events()
    assert root.property("currentPage") == "preparation"
    assert not controller.get_has_document()

    create_button = _visible_item(root, "preparationCreateDocumentButton")
    assert QMetaObject.invokeMethod(create_button, "click")
    _process_events()
    assert controller.get_document_kind() == "preparation"

    page = root.findChild(QQuickItem, "preparationPage")
    assert page is not None
    add_button = _item(page, "preparationAddScenario")
    assert QMetaObject.invokeMethod(add_button, "click")
    _process_events()
    active = controller.preparation_draft.get_active_scenario_draft()
    assert isinstance(active, ScenarioDraft)

    editor = _item(page, "preparationScenarioEditor")
    name_field = _item(editor, "preparationScenarioName")
    assert name_field.setProperty("text", "queued-scenario")
    assert QMetaObject.invokeMethod(name_field, "editingFinished")
    _process_events()
    assert active.get_name() == "queued-scenario"

    commit_button = _item(editor, "preparationScenarioCommitButton")
    assert QMetaObject.invokeMethod(commit_button, "click")
    _process_events()
    assert not controller.preparation_draft.get_has_active_scenario_edit()
    assert controller.preparation_draft.scenarios_model.rowCount() == 1

    edit_button = _item(page, "preparationScenarioEdit-0")
    assert edit_button.width() > 36
    assert QMetaObject.invokeMethod(edit_button, "click")
    _process_events()
    assert controller.preparation_draft.get_has_active_scenario_edit()

    editor = _item(page, "preparationScenarioEditor")
    assert QMetaObject.invokeMethod(_item(editor, "preparationScenarioCancelButton"), "click")
    _process_events()
    assert not controller.preparation_draft.get_has_active_scenario_edit()

    matrix_check = _item(page, "preparationMatrixDiagnostics")
    matrix_settings = _item(page, "preparationMatrixSettingsGrid")
    assert not controller.preparation_draft.get_matrix_enabled()
    assert not matrix_settings.isVisible()
    assert QMetaObject.invokeMethod(matrix_check, "click")
    _process_events()
    assert controller.preparation_draft.get_matrix_enabled()
    assert matrix_settings.isVisible()
    assert QMetaObject.invokeMethod(matrix_check, "click")
    _process_events()
    assert not controller.preparation_draft.get_matrix_enabled()
    assert not matrix_settings.isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_shell_queues_an_enabled_preparation_plan_click(
    runtime: QmlApplicationRuntime,
    tmp_path: Path,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    source = tmp_path / "workspace" / "outputs" / "eligible-plan-source"
    source.mkdir()
    _accept_preparation_eligible_inspection(runtime, source)
    assert desktop.request_bind_inspected_preparation_source()
    _open_saved_preparation(runtime)
    assert root.setProperty("currentPage", "preparation")
    _process_events()

    requested: list[str] = []
    root.workflowPlanRequested.connect(requested.append)
    plan_button = _visible_item(root, "preparationPlanButton")
    assert plan_button.property("enabled") is True

    assert QMetaObject.invokeMethod(plan_button, "click")
    assert requested == ["preparation"]
    assert not desktop.request_coordinator.is_busy

    _process_events()
    assert desktop.preparation_workflow_controller.get_workflow_operation() == "plan"
    _wait_for_idle(runtime)
    assert runtime.warning_capture.runtime_warnings == ()


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
    assert "scenarioFieldChangeRequested" in source
    assert "scenarioTransformationAddRequested" in source
    assert "desktopController.requestPreparationScenario" not in source
    assert 'Accessible.name: qsTr("Scenario name")' in source
    assert 'Accessible.name: qsTr("Scenario partitions")' in source
    assert 'Accessible.name: qsTr("Scenario transformations")' in source
    assert ".setName(" not in source
    assert ".setPartition(" not in source
    assert ".addTransformation(" not in source
    assert "yaml" not in source.casefold()


def test_preparation_page_binds_the_complete_authoritative_editor(
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


def test_preparation_quality_fields_remain_labeled_and_cards_stay_top_aligned(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    draft = runtime.controller.configuration_controller.preparation_draft
    grid = _item(preparation_page, "preparationOutputQualityGrid")
    outputs = _item(preparation_page, "preparationOutputsCard")
    quality = _item(preparation_page, "preparationQualityCard")
    assert grid.property("columnCount") == 2

    initial_tops = (
        outputs.mapToItem(grid, QPointF(0, 0)).y(),
        quality.mapToItem(grid, QPointF(0, 0)).y(),
    )
    assert initial_tops[0] == pytest.approx(initial_tops[1], abs=1)

    draft.apply_capabilities(
        {
            "workflows": {
                "preparation": {
                    "baseline_diagnostics": {"available": True, "guidance": ""},
                    "safetensors": {"available": False, "guidance": ""},
                }
            }
        }
    )
    assert draft.set_matrix_enabled(True)
    assert draft.set_baseline_enabled(True)
    _process_events()

    expected_labels = {
        "preparationCorrelationThresholdLabel": "Correlation threshold (absolute r)",
        "preparationNearConstantSpreadLabel": "Near-constant relative spread",
        "preparationBaselineSeedLabel": "Baseline random seed",
        "preparationRidgeAlphaLabel": "Ridge alpha",
        "preparationHistogramIterationsLabel": "Histogram maximum iterations",
    }
    for object_name, text in expected_labels.items():
        label = _item(preparation_page, object_name)
        assert label.isVisible()
        assert label.property("text") == text

    expanded_tops = (
        outputs.mapToItem(grid, QPointF(0, 0)).y(),
        quality.mapToItem(grid, QPointF(0, 0)).y(),
    )
    assert expanded_tops[0] == pytest.approx(expanded_tops[1], abs=1)
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_page_keeps_app_only_optional_features_explicitly_unavailable(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    draft = desktop.configuration_controller.preparation_draft
    draft.apply_capabilities(
        {
            "preparation": {
                "safetensors": {
                    "available": False,
                    "guidance": 'Install the optional dependency with: pip install "carnopy[ml]"',
                },
                "baseline_diagnostics": {
                    "available": False,
                    "guidance": (
                        'Install the optional dependency with: pip install "carnopy[analysis]"'
                    ),
                },
            }
        }
    )
    desktop.request_preparation_boolean_field("array_outputs", True)
    assert draft.get_array_outputs_enabled()
    _process_events()

    safetensors = _item(preparation_page, "preparationArrayFormat-safetensors")
    baseline = _item(preparation_page, "preparationBaselineDiagnostics")
    guidance = _item(preparation_page, "preparationBaselineDependencyGuidance")
    assert safetensors.property("enabled") is False
    safetensors_choice = next(
        item for item in draft.array_format_choices.items if item.value == "safetensors"
    )
    assert "carnopy[ml]" in safetensors_choice.issue
    assert baseline.property("enabled") is False
    assert "carnopy[analysis]" in guidance.property("text")
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


def test_preparation_page_releases_closed_scenario_editor_layout(
    runtime: QmlApplicationRuntime,
    preparation_page: QQuickItem,
) -> None:
    desktop = runtime.controller
    loader = _item(preparation_page, "preparationActiveScenarioEditor")
    output_grid = _item(preparation_page, "preparationOutputQualityGrid")

    for width, height in ((1920, 1000), (1600, 800), (1366, 768)):
        preparation_page.setWidth(width)
        preparation_page.setHeight(height)
        _process_events()
        initial_output_y = output_grid.mapToItem(preparation_page, QPointF(0, 0)).y()

        assert desktop.request_preparation_add_scenario()
        _process_events()
        open_output_y = output_grid.mapToItem(preparation_page, QPointF(0, 0)).y()
        assert open_output_y > initial_output_y

        assert desktop.request_preparation_cancel_scenario()
        _process_events()
        closed_output_y = output_grid.mapToItem(preparation_page, QPointF(0, 0)).y()
        assert loader.property("active") is False
        assert loader.height() == pytest.approx(0, abs=1)
        assert closed_output_y < open_output_y

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
    assert "booleanFieldRequested" in source
    assert "roleSelectionRequested" in source
    assert "workflowPlanRequested" in source
    assert "workflowExecuteRequested" in source
    assert "workflowCancelRequested" in source
    assert "workflowForceStopRequested" in source
    assert "workflowInspectResultRequested" in source
    assert "desktopController.requestWorkflow" not in source
    assert 'Accessible.name: qsTr("Committed Preparation scenarios")' in source
    assert 'Accessible.name: qsTr("Enable matrix diagnostics")' in source
    assert ".setRoleSelected(" not in source
    assert ".beginAddScenario(" not in source
    assert ".commitScenario(" not in source
    assert "desktopController.requestPreparation" not in source
    assert "desktopController.requestBindInspectedPreparationSource" not in source
    assert "desktopController.requestClearPreparationSource" not in source
    assert "desktopController.requestPreparationScenario" not in source
    assert "PreparationAuditView" not in source
    assert "TextArea" not in source
    main_source = (qml_root / "Main.qml").read_text(encoding="utf-8")
    assert 'currentPage === "preparation"' in main_source
    assert "PreparationPage" in main_source
