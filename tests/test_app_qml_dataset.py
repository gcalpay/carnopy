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

from carnopy.app.draft_models import CANONICAL_ROLE
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


def _set_text(field: QObject, value: str) -> None:
    field.setProperty("text", value)
    _process_events()


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
    assert properties_list.property("interactive") is False
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
    root.setHeight(2200)
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


def test_dataset_workbench_uses_ordered_three_and_two_column_layouts(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1920)
    root.setHeight(1080)
    _process_events()

    grid = _visual_item(root, "datasetSamplerGrid")
    first_row = (
        _visual_item(root, "datasetBackendModeCard"),
        _visual_item(root, "datasetFluidsCard"),
        _visual_item(root, "datasetPropertiesCard"),
    )
    second_row = (
        _visual_item(root, "samplerEditor-temperature"),
        _visual_item(root, "samplerEditor-pressure"),
        _visual_item(root, "datasetOutputsCard"),
    )
    assert grid.property("columnCount") == 3
    for row in (first_row, second_row):
        positions = [item.mapToItem(grid, QPointF(0, 0)) for item in row]
        assert (
            max(position.y() for position in positions)
            - min(position.y() for position in positions)
            <= 1
        )
        assert max(item.height() for item in row) - min(item.height() for item in row) <= 1
        assert positions[0].x() < positions[1].x() < positions[2].x()

    root.setWidth(1440)
    root.setHeight(900)
    _process_events()
    assert grid.property("columnCount") == 2
    assert runtime.warning_capture.runtime_warnings == ()


def test_dataset_survives_live_appearance_and_width_changes_without_warnings(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    _process_events()

    root.setWidth(1920)
    runtime.controller.qml_settings.set_theme_mode("warm")
    _process_events()
    root.setWidth(1440)
    runtime.controller.qml_settings.set_theme_mode("dark")
    _process_events()

    assert root.property("cardColumnCount") == 2
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


def test_searchable_dataset_selectors_apply_changes_immediately(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()

    _click(root, _visual_item(root, "datasetFluidsOpenButton"))
    fluid_popup = root.findChild(QObject, "datasetFluidsPopover")
    fluid_search = root.findChild(QObject, "datasetFluidsSearchField")
    fluid_list = root.findChild(QObject, "datasetFluidsChoiceList")
    assert fluid_popup is not None
    assert fluid_search is not None
    assert fluid_list is not None
    assert fluid_popup.property("opened") is True
    _set_text(fluid_search, "CYCLOPENTANE")
    assert fluid_list.property("count") >= 1
    _click(root, _visual_item(root, "datasetFluidsChoiceItem-0"))
    _process_events()

    _click(root, _visual_item(root, "datasetFluidsDoneButton"))
    _click(root, _visual_item(root, "datasetPropertiesOpenButton"))
    property_popup = root.findChild(QObject, "datasetPropertiesPopover")
    property_search = root.findChild(QObject, "datasetPropertiesSearchField")
    property_list = root.findChild(QObject, "datasetPropertiesChoiceList")
    assert property_popup is not None
    assert property_search is not None
    assert property_list is not None
    _set_text(property_search, "PRANDTL")
    assert property_list.property("count") == 1
    _click(root, _visual_item(root, "datasetPropertiesChoiceItem-0"))
    _process_events()

    draft = runtime.controller.dataset_draft
    assert any(
        draft.selected_fluids.index(row, 0).data(CANONICAL_ROLE) == "Cyclopentane"
        for row in range(draft.selected_fluids.rowCount())
    )
    assert "prandtl_number" in draft.selected_property_values()
    assert _visual_item(root, "datasetFluidsCard").property("meta") == "3 selected"
    assert _visual_item(root, "datasetPropertiesCard").property("meta") == "7 selected"
    assert runtime.warning_capture.runtime_warnings == ()


def test_selector_closure_paths_restore_focus_and_keep_immediate_changes(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()
    opener = _visual_item(root, "datasetFluidsOpenButton")
    popup = root.findChild(QObject, "datasetFluidsPopover")
    assert popup is not None

    _click(root, opener)
    assert popup.property("opened") is True
    _click(root, _visual_item(root, "datasetFluidsDoneButton"))
    assert popup.property("opened") is False
    assert opener.property("activeFocus") is True

    _click(root, opener)
    QTest.keyClick(root, Qt.Key.Key_Escape)
    _process_events()
    assert popup.property("opened") is False
    assert opener.property("activeFocus") is True

    _click(root, opener)
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=QPointF(8, 8).toPoint())
    _process_events()
    assert popup.property("opened") is False
    assert opener.property("activeFocus") is True
    assert runtime.warning_capture.runtime_warnings == ()


def test_selector_keyboard_selection_and_incompatible_recovery(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()
    draft = runtime.controller.dataset_draft

    _click(root, _visual_item(root, "datasetPropertiesOpenButton"))
    search = root.findChild(QObject, "datasetPropertiesSearchField")
    assert search is not None
    _set_text(search, "prandtl")
    QTest.keyClick(root, Qt.Key.Key_Down)
    QTest.keyClick(root, Qt.Key.Key_Space)
    _process_events()
    assert "prandtl_number" in draft.selected_property_values()

    QTest.keyClick(root, Qt.Key.Key_Escape)
    assert draft.add_property("surface_tension")
    draft.set_model_name("pr")
    _process_events()
    _click(root, _visual_item(root, "datasetPropertiesOpenButton"))
    _set_text(search, "surface tension")
    incompatible = _visual_item(root, "datasetPropertiesChoiceItem-0")
    assert incompatible.property("enabled") is True
    _click(root, incompatible)
    _process_events()
    assert "surface_tension" not in draft.selected_property_values()
    assert runtime.warning_capture.runtime_warnings == ()


def test_selector_summaries_are_bounded_and_overflow_preserves_order(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    assert runtime.controller.request_new_dataset("property_table")
    root.setWidth(1440)
    root.setHeight(2200)
    _process_events()
    draft = runtime.controller.dataset_draft

    assert draft.add_property("prandtl_number")
    _process_events()
    more = _visual_item(root, "datasetPropertiesMoreButton")
    assert more.property("visible") is True
    assert more.property("text") == "+1 more"
    _click(root, more)
    popup = root.findChild(QObject, "datasetPropertiesPopover")
    assert popup is not None
    assert popup.property("opened") is True
    _click(root, _visual_item(root, "datasetPropertiesDoneButton"))

    before = draft.selected_property_values()
    actions = _visual_item(root, "datasetPropertiesSelectedActions-1")
    _click(root, actions)
    _click(root, _visual_item(root, "datasetPropertiesMoveUp-1"))
    _process_events()
    assert draft.selected_property_values() == (before[1], before[0], *before[2:])

    _click(root, _visual_item(root, "datasetPropertiesSelectedActions-0"))
    _click(root, _visual_item(root, "datasetPropertiesRemove-0"))
    _process_events()
    assert before[1] not in draft.selected_property_values()
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
    assert "datasetDraft.removeFluid" not in dataset_source
    assert "datasetDraft.removeProperty" not in dataset_source
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


def test_searchable_selectors_use_bounded_non_nested_lists() -> None:
    dataset_source = (ROOT / "src/carnopy/app/qml/Carnopy/pages/DatasetPage.qml").read_text(
        encoding="utf-8"
    )
    selector_source = (
        ROOT / "src/carnopy/app/qml/Carnopy/components/SearchableChoiceList.qml"
    ).read_text(encoding="utf-8")

    assert dataset_source.count("SearchableChoiceList {") == 2
    assert "summaryLimit: 4" in dataset_source
    assert "summaryLimit: 6" in dataset_source
    assert "ScrollView" not in selector_source
    assert "interactive: false" in selector_source
    assert "Popup.CloseOnEscape | Popup.CloseOnPressOutside" in selector_source
    assert "Math.min(320, Math.max(88, contentHeight))" in selector_source


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

    assert "color: Theme.text" in combo_source
    assert "rowDelegate.highlighted || rowDelegate.hovered ? Theme.hover" in combo_source
    assert dataset_source.count("AppComboBox {") == 3
    assert sampler_source.count("AppComboBox {") == 2
    assert choice_source.count("AppComboBox {") == 1
