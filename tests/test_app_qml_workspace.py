from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QEventLoop,
    QObject,
    QPointF,
    QSettings,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace
from carnopy.app.workspace_controller import RECENT_WORKSPACES_KEY

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
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        application_arguments=[],
    )
    yield created
    _wait_for_idle(created)
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(3):
        application.processEvents()


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    runtime.application.processEvents()
    assert not runtime.controller.request_coordinator.is_busy


def _method_names(value: QObject) -> set[str]:
    meta = value.metaObject()
    return {
        bytes(meta.method(index).name()).decode("utf-8")
        for index in range(meta.methodOffset(), meta.methodCount())
    }


def _visual_items(root: QQuickWindow) -> tuple[QQuickItem, ...]:
    found: list[QQuickItem] = []
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        found.append(item)
        pending.extend(item.childItems())
    return tuple(found)


def _visual_item(root: QQuickWindow, object_name: str, *, text: str = "") -> QQuickItem:
    matches = [item for item in _visual_items(root) if item.objectName() == object_name]
    if text:
        matches = [item for item in matches if item.property("text") == text]
    assert len(matches) == 1
    return matches[0]


def _click(root: QQuickWindow, item: QQuickItem) -> None:
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, delay=0, pos=point)
    QTest.qWait(150)


def test_workspace_page_starts_unavailable_and_uses_only_composition_facade(
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    page = root.findChild(QObject, "workspacePage")

    assert page is not None
    assert root.property("desktopController") is runtime.controller
    assert runtime.controller.get_workspace_state() == "unavailable"
    assert page.property("workspaceState") == "unavailable"
    assert root.findChild(QObject, "createWorkspaceButton") is not None
    assert root.findChild(QObject, "initializeWorkspaceButton") is not None
    assert root.findChild(QObject, "openWorkspaceButton") is not None
    assert root.findChild(QObject, "workspaceConfirmationDialog") is not None

    source = (ROOT / "src/carnopy/app/qml/Carnopy/pages/WorkspacePage.qml").read_text(
        encoding="utf-8"
    )
    assert "signal createWorkspaceRequested" in source
    assert "signal initializeWorkspaceRequested" in source
    assert "signal openWorkspaceRequested" in source
    assert "desktopController.prepareCreateWorkspace" not in source
    assert "desktopController.prepareInitializeWorkspace" not in source
    assert "desktopController.prepareOpenWorkspace" not in source
    assert "workspaceController." not in source
    assert "FolderDialog" in source
    assert "existing ordinary folder that is not yet a Carnopy workspace" in source
    assert "already created or initialized by Carnopy" in source

    assert "prepare_create" not in _method_names(runtime.controller.workspace_controller)
    assert "prepare_open" not in _method_names(runtime.controller.workspace_controller)
    assert "commit_pending" not in _method_names(runtime.controller.workspace_controller)
    assert "set_workspace" not in _method_names(runtime.controller.configuration_controller)

    initialize_dialog = root.findChild(QObject, "initializeFolderDialog")
    open_dialog = root.findChild(QObject, "openFolderDialog")
    assert initialize_dialog is not None
    assert open_dialog is not None
    assert initialize_dialog.property("title") == "Choose an existing folder to initialize"
    assert open_dialog.property("title") == "Choose an initialized Carnopy workspace"


def test_create_click_opens_one_parented_folder_dialog_before_name_dialog(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    create = _visual_item(root, "createWorkspaceButton")
    folder_dialog = root.findChild(QObject, "createParentFolderDialog")
    name_dialog = root.findChild(QObject, "createWorkspaceDialog")
    assert folder_dialog is not None
    assert name_dialog is not None

    _click(root, create)

    assert folder_dialog.property("visible") is True
    assert folder_dialog.property("parentWindow") is root
    assert name_dialog.property("opened") is False
    folder_dialog.setProperty("selectedFolder", QUrl.fromLocalFile(str(tmp_path)))
    folder_dialog.accept()
    QTest.qWait(100)
    assert name_dialog.property("opened") is True
    assert name_dialog.property("parentPath") == QUrl.fromLocalFile(str(tmp_path)).toString()
    name_dialog.close()
    _process_events()
    assert runtime.engine.rootObjects() == [root]


def test_recent_workspace_delegate_queues_facade_without_invalidating_itself(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    first = initialize_workspace(tmp_path / "first")
    second = initialize_workspace(tmp_path / "second")
    settings = QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)
    settings.setValue(RECENT_WORKSPACES_KEY, [str(first.root), str(second.root)])
    created = create_qml_runtime(settings=settings, application_arguments=[])
    try:
        root = created.engine.rootObjects()[0]
        assert isinstance(root, QQuickWindow)
        root.setWidth(1440)
        root.setHeight(900)
        _process_events()
        recent = _visual_item(root, "recentWorkspaceButton", text=str(second.root))

        _click(root, recent)
        _wait_for_idle(created)
        _process_events()

        assert created.engine.rootObjects() == [root]
        assert created.controller.get_workspace_root_path() == str(second.root)
        assert created.controller.workspace_controller.recent_model.paths[0] == str(second.root)
        assert created.warning_capture.runtime_warnings == ()
    finally:
        _wait_for_idle(created)
        assert created.close()


def test_qml_facade_creates_workspace_from_parent_and_refreshes_bound_state(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    target = parent / "scientific-workspace"

    assert runtime.controller.prepare_create_workspace(str(parent), target.name)
    assert not runtime.controller.get_workspace_confirmation_required()
    assert runtime.controller.commit_workspace_operation()
    assert target.is_dir()
    assert (target / ".carnopy-gui" / "workspace.json").is_file()

    _wait_for_idle(runtime)
    _process_events()
    root = runtime.engine.rootObjects()[0]
    page = root.findChild(QObject, "workspacePage")
    recent = runtime.controller.get_recent_workspaces()
    assert isinstance(recent, QAbstractItemModel)
    assert page is not None
    assert runtime.controller.get_workspace_state() == "landing"
    assert page.property("workspaceState") == "landing"
    assert runtime.controller.get_workspace_root_path() == str(target.resolve())
    assert recent.rowCount() == 1
    assert root.findChild(QObject, "newDatasetModeGrid") is not None
    assert runtime.warning_capture.runtime_warnings == ()


def test_qml_facade_refuses_unconfirmed_initialization_without_writing(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    note = target / "note.txt"
    note.write_text("unchanged", encoding="utf-8")

    assert runtime.controller.prepare_initialize_workspace(str(target))
    assert runtime.controller.get_workspace_confirmation_required()
    assert runtime.controller.get_pending_workspace_operation() == "initialize_existing"
    assert not runtime.controller.commit_workspace_operation()
    assert runtime.controller.get_pending_workspace_operation() == "initialize_existing"
    assert note.read_text(encoding="utf-8") == "unchanged"
    assert not (target / ".carnopy-gui").exists()

    runtime.controller.cancel_workspace_operation()
    assert runtime.controller.get_pending_workspace_operation() == ""
    assert not (target / ".carnopy-gui").exists()


def test_queued_initialize_request_opens_and_cancels_confirmation_dialog(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    root = runtime.engine.rootObjects()[0]
    confirmation = root.findChild(QObject, "workspaceConfirmationDialog")
    assert confirmation is not None

    root.workspaceInitializeRequested.emit(str(target))
    QTest.qWait(100)

    assert runtime.controller.get_pending_workspace_operation() == "initialize_existing"
    assert confirmation.property("opened") is True
    confirmation.reject()
    QTest.qWait(100)
    assert runtime.controller.get_pending_workspace_operation() == ""
    assert not (target / ".carnopy-gui").exists()


def test_initialize_folder_acceptance_waits_for_native_dialog_to_hide(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    initialize = _visual_item(root, "initializeWorkspaceButton")
    folder_dialog = root.findChild(QObject, "initializeFolderDialog")
    confirmation = root.findChild(QObject, "workspaceConfirmationDialog")
    assert folder_dialog is not None
    assert confirmation is not None
    visible_when_requested: list[bool] = []
    root.workspaceInitializeRequested.connect(
        lambda _path: visible_when_requested.append(bool(folder_dialog.property("visible")))
    )

    _click(root, initialize)

    assert folder_dialog.property("visible") is True
    assert folder_dialog.property("parentWindow") is root
    folder_dialog.setProperty("selectedFolder", QUrl.fromLocalFile(str(target)))
    folder_dialog.accept()
    QTest.qWait(150)

    assert folder_dialog.property("visible") is False
    assert visible_when_requested == [False]
    assert runtime.controller.get_pending_workspace_operation() == "initialize_existing"
    assert confirmation.property("opened") is True
    confirmation.accept()
    QTest.qWait(100)
    _wait_for_idle(runtime)
    _process_events()
    assert runtime.controller.get_pending_workspace_operation() == ""
    assert (target / ".carnopy-gui" / "workspace.json").is_file()
    assert runtime.controller.get_workspace_root_path() == str(target.resolve())
    assert runtime.engine.rootObjects() == [root]


def test_open_folder_acceptance_waits_for_native_dialog_to_hide(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    target = initialize_workspace(tmp_path / "existing")
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    open_button = _visual_item(root, "openWorkspaceButton")
    folder_dialog = root.findChild(QObject, "openFolderDialog")
    assert folder_dialog is not None
    visible_when_requested: list[bool] = []
    root.workspaceOpenRequested.connect(
        lambda _path: visible_when_requested.append(bool(folder_dialog.property("visible")))
    )

    _click(root, open_button)

    assert folder_dialog.property("visible") is True
    assert folder_dialog.property("parentWindow") is root
    folder_dialog.setProperty("selectedFolder", QUrl.fromLocalFile(str(target.root)))
    folder_dialog.accept()
    QTest.qWait(150)
    _wait_for_idle(runtime)
    _process_events()

    assert folder_dialog.property("visible") is False
    assert visible_when_requested == [False]
    assert runtime.controller.get_workspace_root_path() == str(target.root)
    assert runtime.engine.rootObjects() == [root]


def test_import_dialog_starts_in_active_workspace_configs_folder(
    tmp_path: Path,
    runtime: QmlApplicationRuntime,
) -> None:
    workspace = initialize_workspace(tmp_path / "existing")
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)

    root.workspaceOpenRequested.emit(str(workspace.root))
    QTest.qWait(100)
    _wait_for_idle(runtime)
    _process_events()
    root.setWidth(1440)
    root.setHeight(1600)
    _process_events()

    import_button = _visual_item(root, "importDatasetButton")
    import_dialog = root.findChild(QObject, "importConfigurationDialog")
    assert import_dialog is not None

    _click(root, import_button)

    current_folder = import_dialog.property("currentFolder")
    assert isinstance(current_folder, QUrl)
    assert Path(current_folder.toLocalFile()) == workspace.configs
    assert import_dialog.property("visible") is True
    import_dialog.reject()
    _process_events()
    assert runtime.warning_capture.runtime_warnings == ()
