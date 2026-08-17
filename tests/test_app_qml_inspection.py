from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QMetaObject, QObject, QSettings, QTimer
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from carnopy.app.inspection_controller import InspectionController
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _write_dataset(path: Path, rows: int = 150) -> None:
    header = (
        "run_id,case_id,mode,fluid,backend,backend_model,backend_version,phase,valid,"
        "temperature_K,pressure_Pa,mass_density_kg_m3\n"
    )
    body = "".join(
        f"run,{index},property_table,Propane,coolprop,heos,8.0,gas,true,"
        f"{250 + index},101325,{2.0 - index / 1000}\n"
        for index in range(rows)
    )
    path.write_text(header + body, encoding="utf-8")


def _accept_preparation_eligible_inspection(
    controller: InspectionController,
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
        "numeric_candidates": [],
        "target_candidates": [],
        "categorical_candidates": [],
        "auxiliary_candidates": [],
        "observed_category_values": {},
        "derived_features": [],
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
    controller._clear_inspection(source=resolved, state="loading")
    controller._accept_inspection_payload(
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


def _accept_preparation_audit_inspection(
    controller: InspectionController,
    source: Path,
    *,
    audit_recorded: bool = True,
) -> None:
    revision = "b" * 64
    resolved = source.resolve()
    summary: dict[str, object] = {
        "source": str(resolved),
        "status": "completed",
        "row_counts": {"source": 2, "eligible": 2, "excluded": 0},
        "quality": {
            "errors": (["quality flags artifact is unavailable"] if audit_recorded else []),
            "summary": (
                {
                    "status": "completed",
                    "row_counts": {"eligible": 2, "excluded": 0},
                    "matrix_diagnostics": {"status": "not_requested", "fits": []},
                    "baseline_diagnostics": {"status": "not_requested", "fits": []},
                }
                if audit_recorded
                else {}
            ),
        },
    }
    payload: dict[str, object] = {
        "source": str(resolved),
        "source_kind": "preparation",
        "revision": revision,
        "summary": summary,
        "tables": [],
        "arrays": [],
        "plot_context": None,
        "preparation_eligible": False,
        "preparation_ineligible_reason": "",
        "preparation_source_descriptor": None,
        "preparation_profile": None,
    }
    if audit_recorded:
        summary["scenarios"] = {
            "status": "completed",
            "scenario_count": 1,
            "partition_count": 2,
            "scenarios": [
                {
                    "name": "shuffle",
                    "kind": "shuffle",
                    "partition_counts": {"test": 1, "train": 1},
                    "transformations": [],
                }
            ],
        }
        payload["preparation_audit"] = {
            "audit_schema_version": 1,
            "scenario_details": [
                {
                    "name": "shuffle",
                    "state_leakage": {
                        "identity_column": "source_state_hash",
                        "duplicate_state_group_count": 0,
                        "cross_partition_group_count": 0,
                    },
                }
            ],
        }
    controller._clear_inspection(source=resolved, state="loading")
    controller._accept_inspection_payload(payload)


@pytest.fixture
def runtime(
    tmp_path: Path,
    application: QApplication,
) -> QmlApplicationRuntime:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    _write_dataset(workspace.outputs / "standalone.csv")
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        initial_workspace=workspace.root,
        application_arguments=[],
    )
    _wait_until(created, lambda: not created.controller.request_coordinator.is_busy)
    yield created
    _wait_until(created, lambda: not created.controller.request_coordinator.is_busy)
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(6):
        application.processEvents()


def _wait_until(
    runtime: QmlApplicationRuntime,
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = 30_000,
) -> None:
    if predicate():
        _process_events()
        return
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()
    _process_events()
    assert predicate()


def _visible_item(root: QObject, object_name: str) -> QQuickItem:
    matches = [item for item in root.findChildren(QQuickItem, object_name) if item.isVisible()]
    assert len(matches) == 1
    return matches[0]


def _visual_item(root: QQuickItem, object_name: str) -> QQuickItem:
    pending = [root]
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name:
            return candidate
        pending.extend(candidate.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def test_inspect_page_uses_bounded_worker_preview_and_focus_mode(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    controller = runtime.controller.inspection_controller
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 900)
    assert root.setProperty("currentPage", "inspect")
    _process_events()

    page = root.findChild(QObject, "inspectPage")
    assert controller.workspace_sources_model.get_count() == 1
    sources_list = root.findChild(QObject, "inspectionSourcesList")
    assert sources_list is not None
    assert sources_list.property("count") == 1
    assert sources_list.property("height") > 0
    assert sources_list.setProperty("currentIndex", 0)
    _process_events()
    source = sources_list.property("currentItem")
    assert isinstance(source, QQuickItem)
    inspector = _visible_item(root, "inspectionContextInspector")
    assert page is not None
    assert inspector.isVisible()
    assert source.property("enabled") is True
    assert QMetaObject.invokeMethod(source, "click")

    _wait_until(
        runtime,
        lambda: controller.get_state() == "ready" and controller.get_preview_state() == "ready",
    )

    assert root.property("currentPage") == "inspect"
    assert controller.get_source_kind() == "dataset"
    assert controller.get_integrity_label() == "Unrecorded source"
    assert controller.get_selected_table_id() == "dataset"
    assert controller.table_model.rowCount() == 100
    assert controller.table_model.first_row == 1
    assert controller.table_model.last_row == 100
    assert controller.table_model.total_rows == 150

    controller.failure_layer_counts_model.set_rows(
        ({"failureLayer": "state", "count": 1},),
        available=True,
    )
    assert page.setProperty("selectedTab", 3)
    _process_events()
    assert runtime.warning_capture.runtime_warnings == ()
    assert page.setProperty("selectedTab", 1)
    _process_events()

    range_label = root.findChild(QObject, "inspectionTableRange")
    focus = _visible_item(root, "inspectionFocusTableButton")
    assert range_label is not None
    assert range_label.property("text") == "Rows 1\N{EN DASH}100 of 150 · 12 columns"
    assert QMetaObject.invokeMethod(focus, "click")
    _process_events()
    assert page.property("focusTable") is True
    assert focus.property("text") == "Exit Focus Table"

    next_page = _visible_item(root, "inspectionNextPageButton")
    assert next_page.property("enabled") is True
    assert QMetaObject.invokeMethod(next_page, "click")
    _wait_until(runtime, lambda: controller.table_model.page_offset == 100)
    assert controller.table_model.rowCount() == 50
    assert controller.table_model.first_row == 101
    assert controller.table_model.last_row == 150
    assert runtime.warning_capture.runtime_warnings == ()


def test_inspect_page_keeps_workspace_sources_available_in_narrow_mode(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert root.setProperty("width", 768)
    assert root.setProperty("height", 768)
    assert root.setProperty("currentPage", "inspect")
    _process_events()

    compact_selector = _visible_item(root, "inspectionCompactSourceSelector")
    compact_inspect = _visible_item(root, "inspectionCompactInspectButton")
    sources_card = root.findChild(QQuickItem, "inspectionSourcesCard")
    assert compact_selector.property("count") == 1
    assert compact_inspect.property("enabled") is True
    assert sources_card is not None
    assert not sources_card.isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_inspection_facade_normalizes_a_qml_file_url(
    runtime: QmlApplicationRuntime,
) -> None:
    controller = runtime.controller.inspection_controller
    source = Path(str(controller.workspace_sources_model.get(0)["path"]))

    assert runtime.controller.request_inspect_source(source.as_uri())
    _wait_until(
        runtime,
        lambda: controller.get_state() == "ready" and controller.get_preview_state() == "ready",
    )

    assert controller.get_source_path() == str(source)
    assert runtime.warning_capture.runtime_warnings == ()


def test_inspect_page_binds_and_explicitly_clears_a_preparation_source(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    inspection = runtime.controller.inspection_controller
    preparation = runtime.controller.preparation_workflow_controller
    source = Path(str(inspection.workspace_sources_model.get(0)["path"]))
    assert root.setProperty("currentPage", "inspect")
    _accept_preparation_eligible_inspection(inspection, source)
    _process_events()

    bind_button = _visible_item(root, "preparationBindSourceButton")
    assert inspection.get_preparation_eligible()
    assert bind_button.property("text") == "Use for ML Preparation"
    assert bind_button.property("enabled") is True
    assert QMetaObject.invokeMethod(bind_button, "click")
    _process_events()

    assert preparation.get_has_bound_source()
    assert preparation.get_bound_source_path() == str(source.resolve())
    assert preparation.get_inspected_source_matches_binding()
    assert bind_button.property("text") == "Used for ML Preparation"
    assert bind_button.property("enabled") is False

    clear_button = _visible_item(root, "preparationClearSourceButton")
    assert QMetaObject.invokeMethod(clear_button, "click")
    _process_events()
    assert not preparation.get_has_bound_source()

    assert QMetaObject.invokeMethod(bind_button, "click")
    _process_events()
    assert preparation.get_has_bound_source()

    runtime.controller.preparationSourceClearConfirmationRequested.emit()
    _process_events()
    clear_dialog = root.findChild(QObject, "preparationSourceClearDialog")
    assert clear_dialog is not None
    assert clear_dialog.property("opened") is True
    clear_dialog.accept()
    _process_events()

    assert not preparation.get_has_bound_source()
    assert runtime.warning_capture.runtime_warnings == ()


def test_inspect_page_presents_the_accepted_preparation_audit_and_issues(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    inspection = runtime.controller.inspection_controller
    source = runtime.controller.workspace_controller.workspace.outputs / "prepared-audit"
    source.mkdir()
    assert root.setProperty("width", 1440)
    assert root.setProperty("height", 1000)
    assert root.setProperty("currentPage", "inspect")
    _accept_preparation_audit_inspection(inspection, source)
    _process_events()

    page = root.findChild(QObject, "inspectPage")
    assert page is not None
    audit_tab = _visible_item(root, "inspectionPreparationAuditTab")
    assert audit_tab.property("text") == "Preparation Audit"
    assert QMetaObject.invokeMethod(audit_tab, "click")
    _process_events()

    assert page.property("selectedTab") == 4
    audit_view = _visible_item(root, "inspectionPreparationAuditView")
    assert audit_view.property("audit") is inspection.preparation_audit_model
    assert inspection.preparation_quality_errors_model.get_count() == 1
    assert root.findChild(QObject, "preparationAuditScenariosList").property("count") == 1
    assert _visible_item(root, "inspectionPreparationAuditIssuesCard").isVisible()
    audit_pane = _visible_item(root, "inspectionPreparationAuditPane")
    issue = _visual_item(audit_pane, "inspectionPreparationAuditIssue-0")
    assert issue.isVisible()
    assert issue.property("text") == "quality flags artifact is unavailable"

    assert root.setProperty("width", 768)
    _process_events()
    overview_grid = root.findChild(QObject, "preparationAuditOverviewGrid")
    assert overview_grid is not None
    assert overview_grid.property("maximumColumns") == 1

    dataset_source = Path(str(inspection.workspace_sources_model.get(0)["path"]))
    _accept_preparation_eligible_inspection(inspection, dataset_source)
    _process_events()

    assert page.property("selectedTab") == 0
    assert not root.findChild(QQuickItem, "inspectionPreparationAuditTab").isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_inspect_page_keeps_legacy_preparation_audit_unavailability_visible(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    inspection = runtime.controller.inspection_controller
    source = runtime.controller.workspace_controller.workspace.outputs / "legacy-preparation"
    source.mkdir()
    assert root.setProperty("currentPage", "inspect")
    _accept_preparation_audit_inspection(inspection, source, audit_recorded=False)
    _process_events()

    assert not inspection.preparation_audit_model.get_available()
    audit_tab = _visible_item(root, "inspectionPreparationAuditTab")
    assert QMetaObject.invokeMethod(audit_tab, "click")
    _process_events()

    assert _visible_item(root, "preparationAuditStatus").property("label") == "Unavailable"
    issues_card = root.findChild(QQuickItem, "inspectionPreparationAuditIssuesCard")
    assert issues_card is not None
    assert not issues_card.isVisible()
    assert runtime.warning_capture.runtime_warnings == ()
