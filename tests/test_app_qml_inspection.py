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

    range_label = root.findChild(QObject, "inspectionTableRange")
    focus = _visible_item(root, "inspectionFocusTableButton")
    assert range_label is not None
    assert range_label.property("text") == "Rows 1\N{EN DASH}100 of 150"
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
