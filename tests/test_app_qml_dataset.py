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

from carnopy.app.draft_models import VALUE_ROLE
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace
from carnopy.templates import template_text

ROOT = Path(__file__).resolve().parents[1]


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
    for _ in range(4):
        application.processEvents()


def _visual_object_names(root: QQuickWindow) -> set[str]:
    names: set[str] = set()
    pending: list[QQuickItem] = [root.contentItem()]
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        if item.objectName():
            names.add(item.objectName())
    return names


def _visual_item(root: QQuickWindow, object_name: str) -> QQuickItem:
    pending: list[QQuickItem] = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def _click(root: QQuickWindow, item: QQuickItem) -> None:
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, delay=0, pos=point)
    QTest.qWait(150)


def _set_combo_value(combo: QObject, value: str) -> None:
    count = int(combo.property("count"))
    for row in range(count):
        candidate = combo.property("model").index(row, 0).data(VALUE_ROLE)
        if candidate == value:
            combo.setProperty("currentIndex", row)
            return
    raise AssertionError(f"missing combo value: {value}")


def _combo_row(combo: QObject, value: str) -> int:
    count = int(combo.property("count"))
    for row in range(count):
        if combo.property("model").index(row, 0).data(VALUE_ROLE) == value:
            return row
    raise AssertionError(f"missing combo value: {value}")


def test_new_mode_card_opens_real_dataset_page_bound_to_authoritative_draft(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    desktop = runtime.controller

    root.setWidth(1440)
    root.setHeight(1200)
    _process_events()
    _click(root, _visual_item(root, "newDatasetButton-property_table"))
    _process_events()

    page = root.findChild(QObject, "datasetPage")
    assert page is not None
    assert root.property("currentPage") == "dataset"
    assert page.property("datasetDraft") is desktop.dataset_draft
    assert page.property("desktopController") is desktop
    assert root.findChild(QObject, "datasetModelChoice") is not None
    assert root.findChild(QObject, "datasetModeChoice") is not None
    assert root.findChild(QObject, "datasetSamplerGrid") is not None
    page_flickable = root.findChild(QObject, "datasetPageFlickable")
    fluids_list = root.findChild(QObject, "datasetFluidsSelectedList")
    properties_list = root.findChild(QObject, "datasetPropertiesSelectedList")
    assert page_flickable is not None
    assert page_flickable.property("pixelAligned") is True
    assert fluids_list is not None
    assert properties_list is not None
    assert fluids_list.property("interactive") is False
    assert properties_list.property("interactive") is True
    assert properties_list.property("contentHeight") > properties_list.property("height")
    names = _visual_object_names(root)
    assert "samplerEditor-temperature" in names
    assert "samplerEditor-pressure" in names
    assert desktop.dataset_config_controller.get_has_document()
    assert desktop.dataset_draft.get_locally_valid()
    assert runtime.warning_capture.runtime_warnings == ()


def test_dataset_local_mutations_flow_through_existing_models(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    assert desktop.request_new_dataset("property_table")
    _process_events()
    draft = desktop.dataset_draft

    assert draft.add_fluid("Cyclopentane")
    added_row = len(draft.selected_fluid_values()) - 1
    assert draft.move_fluid(added_row, -1)
    assert draft.set_output_selected("csv", False)
    pressure = draft.sampler("pressure")
    assert pressure is not None
    assert pressure.requestUnitChange("kPa")
    _process_events()

    assert "Cyclopentane" in draft.selected_fluid_values()
    assert draft.output_selected("csv") is False
    assert pressure.get_unit() == "kPa"
    assert desktop.dataset_config_controller.get_locally_valid()
    assert runtime.warning_capture.runtime_warnings == ()


def test_default_dataset_renders_exact_sampler_and_row_projections(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()

    assert _visual_item(root, "samplerPointCount-temperature").property("text") == "101 points"
    assert _visual_item(root, "samplerPointCount-pressure").property("text") == "41 points"
    assert _visual_item(root, "datasetGridCombinationsPerFluid").property("text") == (
        "4,141 grid combinations per fluid"
    )
    assert _visual_item(root, "datasetProjectedRowsPerFluid").property("text") == (
        "4,141 projected rows per fluid"
    )
    assert _visual_item(root, "datasetProjectedRows").property("text") == (
        "8,282 projected rows across selected fluids"
    )
    assert runtime.warning_capture.runtime_warnings == ()


def test_property_symbols_use_trusted_markup_and_complete_accessible_names(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    draft = runtime.controller.dataset_draft
    while draft.selected_property_values():
        assert draft.remove_property(len(draft.selected_property_values()) - 1)
    assert draft.add_property("critical_temperature")
    _process_events()

    symbol = _visual_item(root, "propertySymbol-critical_temperature")
    assert symbol.property("symbolMarkup") == "T<sub>c</sub>"
    assert symbol.property("text") == "T<sub>c</sub>"
    assert symbol.property("accessibleName") == "Critical temperature"
    assert runtime.warning_capture.runtime_warnings == ()


def test_dataset_choice_buttons_mutate_through_actual_qml_clicks(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()

    fluid_choice = root.findChild(QObject, "datasetFluidsChoiceBox")
    fluid_add = _visual_item(root, "datasetFluidsAddButton")
    assert fluid_choice is not None
    _set_combo_value(fluid_choice, "Cyclopentane")
    _click(root, fluid_add)
    _process_events()

    property_choice = root.findChild(QObject, "datasetPropertiesChoiceBox")
    property_add = _visual_item(root, "datasetPropertiesAddButton")
    assert property_choice is not None
    property_row = _combo_row(property_choice, "prandtl_number")
    _click(root, property_choice)
    _process_events()
    _click(root, _visual_item(root, f"datasetPropertiesChoiceItem-{property_row}"))
    _process_events()
    assert property_choice.property("currentValue") == "prandtl_number"
    _click(root, property_add)
    _process_events()

    draft = runtime.controller.dataset_draft
    assert "Cyclopentane" in draft.selected_fluid_values()
    assert "prandtl_number" in draft.selected_property_values()
    assert runtime.warning_capture.runtime_warnings == ()


def test_sampler_qml_mutations_update_the_authoritative_draft(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert runtime.controller.request_new_dataset("property_table")
    _process_events()

    kind_choice = _visual_item(root, "samplerKind-pressure")
    unit_choice = _visual_item(root, "samplerUnit-pressure")

    pressure = runtime.controller.dataset_draft.sampler("pressure")
    assert pressure is not None
    target_row = next(
        row
        for row in range(int(unit_choice.property("count")))
        if unit_choice.property("model")[row] == "kPa"
    )
    unit_choice.setProperty("currentIndex", target_row)
    unit_choice.activated.emit(target_row)
    _process_events()
    assert pressure.get_unit() == "kPa"

    kind_choice.setProperty("currentIndex", 0)
    kind_choice.activated.emit(0)
    _process_events()
    assert pressure.get_kind() == "explicit"

    values_field = _visual_item(root, "samplerField-pressure-values")
    values_field.setProperty("text", "100, 200")
    values_field.textEdited.emit()
    _process_events()
    assert pressure.text("values") == "100, 200"
    assert pressure.get_valid()
    assert runtime.warning_capture.runtime_warnings == ()


def test_mode_and_coordinate_replacements_use_composition_decision_facade(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert desktop.request_new_dataset("property_table")
    _process_events()

    assert desktop.request_dataset_mode_change("vapor_mass_fraction_table")
    _process_events()
    dialog = root.findChild(QObject, "datasetDecisionDialog")
    assert dialog is not None
    assert dialog.property("opened") is True
    assert desktop.dataset_draft.get_mode_name() == "property_table"
    assert desktop.commit_dataset_decision(True)
    _process_events()
    assert desktop.dataset_draft.get_mode_name() == "vapor_mass_fraction_table"

    assert desktop.request_dataset_coordinate_change("pressure")
    assert desktop.dataset_draft.get_coordinate_name() == "temperature"
    assert desktop.commit_dataset_decision(True)
    _process_events()
    assert desktop.dataset_draft.get_coordinate_name() == "pressure"
    assert desktop.dataset_draft.sampler("temperature") is None
    pressure = desktop.dataset_draft.sampler("pressure")
    assert pressure is not None
    assert pressure.raw_state() == (
        "pressure",
        "explicit",
        "Pa",
        (("values", "101325"),),
    )
    assert runtime.warning_capture.runtime_warnings == ()


def test_worker_authoritative_import_opens_dataset_page(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    source = tmp_path / "external.yaml"
    source.write_text(template_text("saturation_table"), encoding="utf-8")
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]

    assert desktop.request_import_dataset(str(source))
    _wait_for_idle(runtime)
    _process_events()

    assert desktop.dataset_draft.get_mode_name() == "saturation_table"
    assert desktop.dataset_config_controller.document is not None
    assert desktop.dataset_config_controller.document.imported
    assert root.property("currentPage") == "dataset"
    assert runtime.warning_capture.runtime_warnings == ()


def test_structured_invalid_field_is_projected_without_parsing_issue_text(
    runtime: QmlApplicationRuntime,
) -> None:
    desktop = runtime.controller
    root = runtime.engine.rootObjects()[0]
    assert desktop.request_new_dataset("property_table")
    _process_events()
    pressure = desktop.dataset_draft.sampler("pressure")
    assert pressure is not None

    active_field = pressure.get_active_fields()[0]
    pressure.set_text(active_field, "")
    _process_events()
    issue = root.findChild(QObject, "datasetBlockingIssue")

    assert issue is not None
    assert issue.property("field") == f"dataset.grid.pressure.{active_field}"
    assert issue.property("issue") == desktop.dataset_draft.get_issue()


def test_qml_uses_child_drafts_only_for_local_edits() -> None:
    dataset_source = (ROOT / "src/carnopy/app/qml/Carnopy/pages/DatasetPage.qml").read_text(
        encoding="utf-8"
    )
    workspace_source = (ROOT / "src/carnopy/app/qml/Carnopy/pages/WorkspacePage.qml").read_text(
        encoding="utf-8"
    )
    sampler_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/SamplerEditor.qml").read_text(
        encoding="utf-8"
    )

    assert "datasetDraft.applyModeChange" not in dataset_source
    assert "datasetDraft.setCoordinate" not in dataset_source
    assert "datasetConfigController.newDataset" not in workspace_source
    assert "datasetConfigController.importDataset" not in workspace_source
    assert "datasetDraft.addFluid" not in dataset_source
    assert "datasetDraft.addProperty" not in dataset_source
    assert "datasetDraft.setModelName" not in dataset_source
    assert "datasetDraft.setOutputSelected" not in dataset_source
    assert "signal modeChangeRequested" in dataset_source
    assert "signal coordinateChangeRequested" in dataset_source
    assert "signal newDatasetRequested" in workspace_source
    assert "signal importDatasetRequested" in workspace_source
    assert "unitChangeRequested" in sampler_source
    assert "draft.unit =" not in sampler_source
    assert "draft.kind =" not in sampler_source
    assert "draft.setText" not in sampler_source


def test_dataset_selectors_share_readable_hover_styling() -> None:
    combo_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/AppComboBox.qml").read_text(
        encoding="utf-8"
    )
    dataset_source = (ROOT / "src/carnopy/app/qml/Carnopy/pages/DatasetPage.qml").read_text(
        encoding="utf-8"
    )
    sampler_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/SamplerEditor.qml").read_text(
        encoding="utf-8"
    )
    choice_source = (ROOT / "src/carnopy/app/qml/Carnopy/components/ChoiceList.qml").read_text(
        encoding="utf-8"
    )

    assert "rowDelegate.highlighted || rowDelegate.hovered ? Theme.highlightedText" in combo_source
    assert "rowDelegate.highlighted || rowDelegate.hovered ? Theme.primary" in combo_source
    assert dataset_source.count("AppComboBox {") == 3
    assert sampler_source.count("AppComboBox {") == 2
    assert choice_source.count("AppComboBox {") == 1
