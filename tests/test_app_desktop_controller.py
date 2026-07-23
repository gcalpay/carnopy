from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QModelIndex,
    QObject,
    QSettings,
    Qt,
    QUrl,
    Signal,
)

from carnopy.app.desktop_controller import DesktopController
from carnopy.app.draft_models import DraftItem
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import initialize_workspace
from carnopy.app.workspace_controller import (
    MAX_RECENT_WORKSPACES,
    PATH_ROLE,
    RecentWorkspaceModel,
    WorkspaceController,
)


class StubCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False

    def set_busy(self, busy: bool) -> None:
        if busy == self.is_busy:
            return
        self.is_busy = busy
        self.busy_changed.emit(busy)


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def settings_for(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def controller_for(
    settings: QSettings,
) -> tuple[WorkspaceController, StubCoordinator]:
    coordinator = StubCoordinator()
    controller = WorkspaceController(
        cast(DesktopRequestCoordinator, coordinator),
        settings,
    )
    return controller, coordinator


def test_desktop_controller_owns_one_composition_and_preserves_settings_identity(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")

    desktop = DesktopController(settings=settings)

    assert desktop.settings is settings
    assert desktop.qml_settings.settings is settings
    assert desktop.qml_settings.parent() is desktop
    assert desktop.request_coordinator.client is desktop.client
    assert desktop.dataset_draft.parent() is desktop
    assert desktop.visualization_draft.parent() is desktop
    assert desktop.dataset_config_controller.parent() is desktop
    assert desktop.dataset_config_controller.coordinator is desktop.request_coordinator
    assert desktop.dataset_config_controller.dataset_draft is desktop.dataset_draft
    assert desktop.dataset_config_controller.visualization_draft is desktop.visualization_draft
    assert desktop.execution_controller.parent() is desktop
    assert desktop.execution_controller.coordinator is desktop.request_coordinator
    assert desktop.execution_controller.config_controller is desktop.dataset_config_controller
    assert desktop.workspace_controller.coordinator is desktop.request_coordinator
    assert desktop.client.parent() is desktop
    assert desktop.request_coordinator.parent() is desktop
    assert desktop.workspace_controller.parent() is desktop
    assert desktop.property("workspaceController") is desktop.workspace_controller
    assert desktop.property("qmlSettings") is desktop.qml_settings
    assert desktop.property("datasetDraft") is desktop.dataset_draft
    assert desktop.property("visualizationDraft") is desktop.visualization_draft
    assert desktop.property("datasetConfigController") is desktop.dataset_config_controller
    assert desktop.property("executionController") is desktop.execution_controller
    assert (
        desktop.workspace_controller.property("recentWorkspaces")
        is desktop.workspace_controller.recent_model
    )
    assert desktop.shutdown()


def test_desktop_shutdown_is_idle_only_and_idempotent(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    shutdown_calls: list[str] = []
    sync_calls: list[str] = []
    monkeypatch.setattr(
        desktop.request_coordinator,
        "shutdown",
        lambda: shutdown_calls.append("shutdown"),
    )
    monkeypatch.setattr(desktop.settings, "sync", lambda: sync_calls.append("sync"))
    assert desktop.workspace_controller.prepare_create(tmp_path / "pending")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            type(desktop.request_coordinator),
            "is_busy",
            property(lambda _self: True),
        )
        assert not desktop.shutdown()

    assert shutdown_calls == []
    assert sync_calls == []
    assert desktop.workspace_controller.get_pending_operation() == ""
    assert desktop.shutdown()
    assert desktop.shutdown()
    assert shutdown_calls == ["shutdown"]
    assert sync_calls == ["sync"]

    with monkeypatch.context() as scoped:
        scoped.setattr(
            type(desktop.request_coordinator),
            "is_busy",
            property(lambda _self: True),
        )
        assert desktop.shutdown()
    assert shutdown_calls == ["shutdown"]
    assert sync_calls == ["sync"]


def test_qml_shutdown_requires_explicit_dirty_discard_confirmation(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[str] = []
    close_requests: list[str] = []
    desktop.shutdownConfirmationRequested.connect(lambda: confirmations.append("confirm"))
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "needs_discard_confirmation",
        lambda: True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == ["confirm"]
    assert not desktop.confirm_shutdown(False)
    assert close_requests == []
    assert desktop.confirm_shutdown(True)
    assert close_requests == ["close"]
    assert desktop.request_shutdown()


def test_qml_shutdown_refuses_an_active_worker_without_closing(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    close_requests: list[str] = []
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))

    with monkeypatch.context() as scoped:
        scoped.setattr(
            type(desktop.request_coordinator),
            "is_busy",
            property(lambda _self: True),
        )
        assert not desktop.request_shutdown()

    assert close_requests == []
    assert "active worker request" in desktop.get_workspace_error_message()
    assert desktop.shutdown()


def test_configuration_attention_facade_accepts_only_stable_sections(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    attention: list[tuple[str, str, int]] = []
    desktop.attentionRequested.connect(
        lambda section, field, row: attention.append((section, field, row))
    )

    assert desktop.request_configuration_attention("dataset", "dataset.properties", 2)
    assert desktop.request_configuration_attention("visualization", "plot.name", -1)
    assert not desktop.request_configuration_attention("workspace", "dataset.mode", -1)
    assert not desktop.request_configuration_attention("dataset", "plot.name", -1)
    assert attention == [
        ("dataset", "dataset.properties", 2),
        ("visualization", "plot.name", -1),
    ]
    assert desktop.shutdown()


def test_execution_facade_routes_qml_intent_to_the_authoritative_controller(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    calls: list[str] = []
    monkeypatch.setattr(
        desktop.execution_controller,
        "validate",
        lambda: calls.append("validate") or True,
    )
    monkeypatch.setattr(
        desktop.execution_controller,
        "generate",
        lambda: calls.append("generate") or True,
    )
    monkeypatch.setattr(
        desktop.execution_controller,
        "cancel",
        lambda: calls.append("cancel") or True,
    )
    monkeypatch.setattr(
        desktop.execution_controller,
        "force_stop",
        lambda: calls.append("force_stop") or True,
    )

    assert desktop.request_execution_validation()
    assert desktop.request_dataset_generation()
    assert desktop.request_execution_cancel()
    assert desktop.request_execution_force_stop()
    assert calls == ["validate", "generate", "cancel", "force_stop"]
    assert desktop.shutdown()


def test_save_as_facade_converts_qml_file_urls_at_the_composition_boundary(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    destination = tmp_path / "workspace" / "configs" / "dataset.yaml"
    observed: list[str] = []
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "save_path_selected",
        lambda path: observed.append(path) or True,
    )

    assert desktop.request_save_path_selected(QUrl.fromLocalFile(str(destination)).toString())
    assert observed == [str(destination)]
    assert desktop.shutdown()


def test_desktop_workspace_facade_validates_create_name_and_binds_configuration_once(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    activated: list[object] = []
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "set_workspace",
        activated.append,
    )
    parent = tmp_path / "parent"
    parent.mkdir()

    for invalid in ("", ".", "..", "nested/name", "nested\\name"):
        assert not desktop.prepare_create_workspace(str(parent), invalid)
        assert desktop.workspace_controller.get_pending_operation() == ""

    target = parent / "new-workspace"
    assert desktop.prepare_create_workspace(str(parent), target.name)
    assert desktop.get_pending_workspace_path() == str(target.resolve())
    assert not desktop.get_workspace_confirmation_required()
    assert desktop.commit_workspace_operation()

    assert desktop.workspace_controller.workspace is not None
    assert desktop.workspace_controller.workspace.root == target.resolve()
    assert activated == [desktop.workspace_controller.workspace]
    assert desktop.get_workspace_state() == "landing"
    assert desktop.shutdown()


def test_desktop_workspace_facade_requires_initialization_confirmation(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    monkeypatch.setattr(desktop.dataset_config_controller, "set_workspace", lambda _value: None)
    target = tmp_path / "existing"
    target.mkdir()

    assert desktop.prepare_initialize_workspace(str(target))
    assert desktop.get_workspace_confirmation_required()
    assert desktop.get_workspace_confirmation_title() == "Initialize Existing Folder"
    assert not desktop.commit_workspace_operation()
    assert not (target / ".carnopy-gui").exists()
    assert desktop.get_pending_workspace_operation() == "initialize_existing"

    assert desktop.commit_workspace_operation(confirmed=True)
    assert (target / ".carnopy-gui" / "workspace.json").is_file()
    assert desktop.shutdown()


def test_desktop_workspace_facade_rechecks_dirty_confirmation_before_commit(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    monkeypatch.setattr(desktop.dataset_config_controller, "set_workspace", lambda _value: None)
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "needs_discard_confirmation",
        lambda: True,
    )
    target = tmp_path / "replacement"

    assert desktop.prepare_create_workspace_path(str(target))
    assert desktop.get_workspace_confirmation_required()
    assert "unsaved changes" in desktop.get_workspace_confirmation_message()
    assert not desktop.commit_workspace_operation()
    assert desktop.get_pending_workspace_operation() == "create"
    assert not target.exists()

    assert desktop.commit_workspace_operation(confirmed=True)
    assert target.is_dir()
    assert desktop.shutdown()


def test_active_plot_edit_blocks_workspace_preflight_commit_and_shutdown(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    target = tmp_path / "workspace"
    active = QObject()
    preflight_calls: list[object] = []
    with monkeypatch.context() as scoped:
        scoped.setattr(
            desktop.workspace_controller,
            "prepare_create",
            lambda _path: preflight_calls.append(object()) or True,
        )
        scoped.setattr(
            desktop.visualization_draft,
            "get_active_plot_draft",
            lambda: active,
        )

        assert not desktop.prepare_create_workspace_path(str(target))
        assert preflight_calls == []
        assert not desktop.get_can_change_workspace()
        assert "Commit or cancel" in desktop.get_workspace_error_message()
        assert not desktop.shutdown()

    assert desktop.prepare_create_workspace_path(str(target))
    with monkeypatch.context() as scoped:
        scoped.setattr(
            desktop.visualization_draft,
            "get_active_plot_draft",
            lambda: active,
        )
        assert not desktop.commit_workspace_operation()
    assert desktop.get_pending_workspace_operation() == ""
    assert not target.exists()
    assert desktop.shutdown()


def test_active_plot_edit_blocks_all_composition_lifecycle_paths(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    active = QObject()
    calls: list[str] = []
    attention: list[tuple[str, str, int]] = []
    desktop.attentionRequested.connect(
        lambda section, field, row: attention.append((section, field, row))
    )
    monkeypatch.setattr(
        desktop.visualization_draft,
        "get_active_plot_draft",
        lambda: active,
    )
    for name in (
        "new_dataset",
        "import_dataset",
        "request_save",
        "request_save_as",
        "request_validation",
        "reload_source",
        "apply_mode_change",
        "apply_coordinate_change",
    ):
        monkeypatch.setattr(
            desktop.dataset_config_controller,
            name,
            lambda *_args, operation=name: calls.append(operation) or True,
        )

    assert not desktop.request_new_dataset("property_table")
    assert not desktop.request_import_dataset("input.yaml")
    assert not desktop.request_save()
    assert not desktop.request_save_as()
    assert not desktop.request_validate_configuration()
    assert not desktop.request_reload_source()
    assert not desktop.request_close_configuration()
    assert not desktop.request_dataset_mode_change("saturation_table")
    assert not desktop.request_dataset_coordinate_change("pressure")
    assert not desktop.request_visualization_add_plot()
    assert not desktop.request_visualization_edit_plot(0)
    assert not desktop.request_visualization_remove_plot(0)
    assert not desktop.request_visualization_move_plot(0, 1)
    assert not desktop.dataset_config_controller.clear_document(discard_confirmed=True)
    assert not desktop.shutdown()

    assert calls == []
    assert attention
    assert all(item == ("visualization", "visualization.plots", -1) for item in attention)


def test_visualization_facade_accepts_only_the_owned_active_plot_and_mappings(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    draft = desktop.visualization_draft
    draft.apply_capabilities(
        {
            "fluids": [{"name": "Propane", "aliases": []}],
            "visualization": {
                "plot_kinds": ["property_curves"],
                "formats": ["png"],
                "scales": ["linear", "log"],
                "kind_contracts": {
                    "property_curves": {
                        "required": ["property"],
                        "applicable": ["property", "x", "filters", "format"],
                    }
                },
                "fields": [
                    {
                        "name": "temperature",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "filter_allowed": True,
                    },
                    {
                        "name": "mass_density",
                        "kind": "numeric",
                        "axis_allowed": True,
                        "filter_allowed": False,
                    },
                ],
                "display_units": {},
            },
        }
    )
    draft.set_dataset_context(
        {
            "mode": "property_table",
            "fluids": ["Propane"],
            "grid": {"temperature": {}, "pressure": {}},
            "properties": ["mass_density"],
        }
    )
    draft.load_visualization(None)
    draft.set_enabled(True)
    assert desktop.request_visualization_add_plot()
    active = draft.get_active_plot_draft()
    assert active is not None

    desktop.request_plot_field_change(active, "name", "density")
    desktop.request_visualization_mapping_add(active.filters)
    desktop.request_visualization_mapping_value_change(active.filters, 0, "300")
    outsider = QObject()
    desktop.request_plot_field_change(outsider, "name", "ignored")
    desktop.request_visualization_mapping_add(outsider)

    assert active.get_name() == "density"
    assert active.filters.raw_rows() == (("temperature", "300"),)
    assert desktop.request_visualization_cancel_plot()
    assert desktop.shutdown()


def test_dataset_replacement_decisions_are_owned_by_desktop_facade(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    desktop.dataset_draft.mode_choices.replace(
        DraftItem(value=value, display=value, canonical=value)
        for value in ("property_table", "saturation_table")
    )
    desktop.dataset_draft.coordinate_choices.replace(
        DraftItem(value=value, display=value, canonical=value)
        for value in ("temperature", "pressure")
    )
    monkeypatch.setattr(desktop.dataset_draft, "get_mode_name", lambda: "property_table")
    monkeypatch.setattr(desktop.dataset_draft, "get_coordinate_name", lambda: "temperature")
    applied: list[tuple[str, str]] = []
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "apply_mode_change",
        lambda value: applied.append(("mode", value)) or True,
    )
    monkeypatch.setattr(
        desktop.dataset_config_controller,
        "apply_coordinate_change",
        lambda value: applied.append(("coordinate", value)) or True,
    )
    decisions: list[object] = []
    desktop.datasetDecisionRequested.connect(lambda: decisions.append(object()))

    assert desktop.request_dataset_mode_change("saturation_table")
    assert desktop.get_dataset_decision_title() == "Change Dataset Mode"
    assert desktop.commit_dataset_decision(True)
    assert desktop.request_dataset_coordinate_change("pressure")
    assert desktop.get_dataset_decision_title() == "Change Sampling Coordinate"
    assert desktop.commit_dataset_decision(True)

    assert len(decisions) == 2
    assert applied == [("mode", "saturation_table"), ("coordinate", "pressure")]
    assert desktop.shutdown()


def test_prepare_cancel_replace_and_commit_pending_lifecycle(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, _coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert controller.prepare_create(first)
    assert controller.get_pending_operation() == "create"
    assert controller.get_pending_path() == str(first.resolve())
    assert controller.prepare_create(second)
    assert controller.get_pending_path() == str(second.resolve())
    controller.cancel_pending()
    assert controller.get_pending_operation() == ""
    assert controller.get_pending_path() == ""
    assert not first.exists()
    assert not second.exists()

    assert controller.prepare_create(first)
    assert controller.commit_pending()
    assert controller.workspace is not None
    assert controller.workspace.root == first.resolve()
    assert controller.get_pending_operation() == ""
    assert controller.get_available()
    assert controller.get_root_path() == str(first.resolve())


def test_busy_rejection_calls_no_workspace_service(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    calls: list[object] = []
    monkeypatch.setattr(
        "carnopy.app.workspace_controller.preflight_workspace_operation",
        lambda *_args: calls.append(object()),
    )
    coordinator.set_busy(True)

    assert not controller.prepare_create(tmp_path / "workspace")
    assert calls == []
    assert not controller.get_can_change_workspace()
    assert "worker request is active" in controller.get_error_message()

    coordinator.set_busy(False)

    assert controller.get_can_change_workspace()
    assert controller.get_error_message() == ""


def test_worker_idle_does_not_clear_persistent_workspace_error(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    controller.report_error("Persistent workspace failure")

    coordinator.set_busy(True)
    coordinator.set_busy(False)

    assert controller.get_error_message() == "Persistent workspace failure"


def test_commit_rejects_new_busy_state_and_clears_pending_without_mutation(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    controller, coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    target = tmp_path / "workspace"
    calls: list[object] = []
    assert controller.prepare_create(target)
    monkeypatch.setattr(
        "carnopy.app.workspace_controller.commit_workspace_operation",
        lambda *_args: calls.append(object()),
    )
    coordinator.set_busy(True)

    assert not controller.commit_pending()
    assert calls == []
    assert not target.exists()
    assert controller.get_pending_operation() == ""


def test_failed_commit_preserves_active_workspace_recents_and_status_paths(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    controller, _coordinator = controller_for(settings)
    active = initialize_workspace(tmp_path / "active")
    assert controller.prepare_open(active.root)
    assert controller.commit_pending()
    original_recents = controller.recent_model.paths

    raced = tmp_path / "raced"
    assert controller.prepare_create(raced)
    raced.mkdir()
    assert not controller.commit_pending()

    assert controller.workspace == active
    assert controller.get_root_path() == str(active.root)
    assert controller.recent_model.paths == original_recents
    assert "already exists" in controller.get_error_message()
    assert controller.get_pending_operation() == ""


@pytest.mark.parametrize("operation", ["initialize_existing", "open"])
def test_controller_rejects_existing_root_replacement_before_activation(
    tmp_path: Path,
    application: QCoreApplication,
    operation: str,
) -> None:
    del application
    controller, _coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    active = initialize_workspace(tmp_path / "active")
    assert controller.prepare_open(active.root)
    assert controller.commit_pending()
    target = tmp_path / operation
    if operation == "open":
        initialize_workspace(target)
        assert controller.prepare_open(target)
    else:
        target.mkdir()
        assert controller.prepare_initialize_existing(target)
    displaced = tmp_path / f"{operation}-displaced"
    target.rename(displaced)
    if operation == "open":
        initialize_workspace(target)
    else:
        target.mkdir()

    assert not controller.commit_pending()
    assert controller.workspace == active
    assert "changed after confirmation" in controller.get_error_message()


def test_recent_paths_restore_normalize_deduplicate_and_cap(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    raw = [
        str(tmp_path / "first"),
        str(tmp_path / "first" / ".." / "first"),
        *(str(tmp_path / f"workspace-{index}") for index in range(15)),
    ]
    settings.setValue("recent_workspaces", raw)

    controller, _coordinator = controller_for(settings)

    expected = tuple(dict.fromkeys(str(Path(value).resolve()) for value in raw))[
        :MAX_RECENT_WORKSPACES
    ]
    assert controller.recent_model.paths == expected
    assert settings.value("recent_workspaces", [], type=list) == list(expected)


def test_recent_model_roles_and_change_only_reset(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    path = str((tmp_path / "workspace").resolve())
    model = RecentWorkspaceModel([path])
    resets: list[str] = []
    model.modelReset.connect(lambda: resets.append("reset"))
    index = model.index(0, 0, QModelIndex())

    assert model.data(index, int(Qt.ItemDataRole.DisplayRole)) == path
    assert model.data(index, PATH_ROLE) == path
    assert bytes(model.roleNames()[PATH_ROLE]) == b"path"
    assert not model.replace([path])
    assert resets == []
    assert model.replace([str((tmp_path / "other").resolve())])
    assert resets == ["reset"]


def test_failed_stale_recent_open_preserves_row_order(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    settings = settings_for(tmp_path / "settings.ini")
    stale = str((tmp_path / "missing").resolve())
    other = str((tmp_path / "other").resolve())
    settings.setValue("recent_workspaces", [stale, other])
    controller, _coordinator = controller_for(settings)

    assert not controller.prepare_open(stale)
    assert controller.recent_model.paths == (stale, other)
    assert "does not exist" in controller.get_error_message()


def test_workspace_notifications_emit_only_when_values_change(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = controller_for(settings_for(tmp_path / "settings.ini"))
    errors: list[str] = []
    can_change: list[bool] = []
    pending: list[str] = []
    controller.error_message_changed.connect(lambda: errors.append(controller.get_error_message()))
    controller.can_change_workspace_changed.connect(
        lambda: can_change.append(controller.get_can_change_workspace())
    )
    controller.pending_operation_changed.connect(
        lambda: pending.append(controller.get_pending_operation())
    )

    controller.report_error("problem")
    controller.report_error("problem")
    coordinator.set_busy(True)
    coordinator.set_busy(True)
    coordinator.set_busy(False)
    assert controller.prepare_create(tmp_path / "workspace")
    assert controller.prepare_create(tmp_path / "workspace")
    controller.cancel_pending()
    controller.cancel_pending()

    assert errors[0] == "problem"
    assert errors.count("problem") == 1
    assert can_change == [False, True]
    assert pending == ["create", "", "create", ""]


def test_importing_desktop_controllers_does_not_load_scientific_dependencies() -> None:
    code = """
import sys
import carnopy.app.desktop_controller
import carnopy.app.workspace_controller
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline", "carnopy.app.source_inspection",
    "carnopy.app.table_preview", "carnopy.app.plot_rendering",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
