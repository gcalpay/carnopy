from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
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
from carnopy.app.jobs import JobStore
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
    assert desktop.configuration_controller.parent() is desktop
    assert desktop.configuration_controller.coordinator is desktop.request_coordinator
    assert desktop.configuration_controller.dataset_draft is desktop.dataset_draft
    assert desktop.configuration_controller.visualization_draft is desktop.visualization_draft
    assert desktop.configuration_controller.sweep_draft.parent() is desktop.configuration_controller
    assert (
        desktop.configuration_controller.preparation_draft.parent()
        is desktop.configuration_controller
    )
    assert desktop.execution_controller.parent() is desktop
    assert desktop.execution_controller.coordinator is desktop.request_coordinator
    assert desktop.execution_controller.config_controller is desktop.configuration_controller
    assert desktop.activity_controller.parent() is desktop
    assert desktop.activity_controller.coordinator is desktop.request_coordinator
    assert desktop.sweep_workflow_controller.parent() is desktop
    assert desktop.sweep_workflow_controller.kind == "sweep"
    assert (
        desktop.sweep_workflow_controller.configuration_controller
        is desktop.configuration_controller
    )
    assert desktop.preparation_workflow_controller.parent() is desktop
    assert desktop.preparation_workflow_controller.kind == "preparation"
    assert desktop.preparation_workflow_controller.inspection is desktop.inspection_controller
    assert desktop.configured_plot_results_controller.parent() is desktop
    assert desktop.configured_plot_results_controller.activity is desktop.activity_controller
    assert desktop.session_plot_controller.parent() is desktop
    assert desktop.session_plot_controller.coordinator is desktop.request_coordinator
    assert desktop.session_plot_controller.inspection is desktop.inspection_controller
    assert desktop.workspace_controller.coordinator is desktop.request_coordinator
    assert desktop.client.parent() is desktop
    assert desktop.request_coordinator.parent() is desktop
    assert desktop.workspace_controller.parent() is desktop
    assert desktop.property("workspaceController") is desktop.workspace_controller
    assert desktop.property("qmlSettings") is desktop.qml_settings
    assert desktop.property("datasetDraft") is desktop.dataset_draft
    assert desktop.property("visualizationDraft") is desktop.visualization_draft
    assert desktop.property("configurationController") is desktop.configuration_controller
    assert (
        desktop.configuration_controller.property("sweepDraft")
        is desktop.configuration_controller.sweep_draft
    )
    assert (
        desktop.configuration_controller.property("preparationDraft")
        is desktop.configuration_controller.preparation_draft
    )
    assert not hasattr(desktop, "dataset_config_controller")
    assert desktop.property("datasetConfigController") is None
    assert desktop.property("executionController") is desktop.execution_controller
    assert desktop.property("sweepWorkflowController") is desktop.sweep_workflow_controller
    assert (
        desktop.property("preparationWorkflowController") is desktop.preparation_workflow_controller
    )
    assert desktop.property("activityController") is desktop.activity_controller
    assert (
        desktop.property("configuredPlotResultsController")
        is desktop.configured_plot_results_controller
    )
    assert desktop.property("sessionPlotController") is desktop.session_plot_controller
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
        desktop.configuration_controller,
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


def test_qml_shutdown_cancels_generation_then_closes_after_safe_completion(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[tuple[str, str]] = []
    cancellations: list[str] = []
    close_requests: list[str] = []
    desktop.busyShutdownConfirmationRequested.connect(
        lambda mode, message: confirmations.append((mode, message))
    )
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    desktop.request_coordinator._active_session = SimpleNamespace(
        owner="execution",
        request_type="generate_dataset",
    )
    monkeypatch.setattr(desktop.execution_controller, "get_can_cancel", lambda: True)
    monkeypatch.setattr(
        desktop.execution_controller,
        "cancel",
        lambda: cancellations.append("cancel") or True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == [
        (
            "cancel_generation",
            "Dataset generation is active. Cancel it cooperatively and close Carnopy "
            "after the worker and activity record finish safely?",
        )
    ]
    assert not desktop.confirm_busy_shutdown(False)
    assert cancellations == []

    assert not desktop.request_shutdown()
    assert desktop.confirm_busy_shutdown(True)
    assert cancellations == ["cancel"]
    desktop.request_coordinator._active_session = None
    desktop._complete_busy_shutdown()

    assert close_requests == ["close"]


def test_qml_shutdown_cancels_sweep_then_closes_after_safe_completion(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[tuple[str, str]] = []
    cancellations: list[str] = []
    close_requests: list[str] = []
    desktop.busyShutdownConfirmationRequested.connect(
        lambda mode, message: confirmations.append((mode, message))
    )
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    desktop.request_coordinator._active_session = SimpleNamespace(
        owner="sweep",
        request_type="execute_sweep",
    )
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "get_cancellation_available",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "cancel",
        lambda: cancellations.append("cancel") or True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == [
        (
            "cancel_sweep",
            "Model Sweep execution is active. Cancel it cooperatively and close Carnopy "
            "after the worker and activity record finish safely?",
        )
    ]
    assert desktop.confirm_busy_shutdown(True)
    assert cancellations == ["cancel"]
    desktop.request_coordinator._active_session = None
    desktop._complete_busy_shutdown()

    assert close_requests == ["close"]


def test_plot_cleanup_failure_aborts_pending_busy_shutdown(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[tuple[str, str]] = []
    close_requests: list[str] = []
    desktop.busyShutdownConfirmationRequested.connect(
        lambda mode, message: confirmations.append((mode, message))
    )
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    desktop.request_coordinator._active_session = SimpleNamespace(
        owner="plot",
        request_type="render_plot",
    )
    monkeypatch.setattr(desktop.session_plot_controller, "get_can_force_stop", lambda: True)
    monkeypatch.setattr(desktop.session_plot_controller, "force_stop", lambda: True)

    assert not desktop.request_shutdown()
    assert confirmations[0][0] == "force_stop_plot"
    assert desktop.confirm_busy_shutdown(True)
    desktop.request_coordinator._active_session = None
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "get_cleanup_issue",
        lambda: "owned staging cleanup failed",
    )
    desktop._complete_busy_shutdown()

    assert close_requests == []
    assert "cleanup failed" in desktop.get_workspace_error_message()
    assert desktop.shutdown()


def test_qml_shutdown_explicitly_cancels_transient_plot_edits_before_close(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[str] = []
    close_requests: list[str] = []
    cancellations: list[str] = []
    desktop.transientEditShutdownConfirmationRequested.connect(confirmations.append)
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    monkeypatch.setattr(desktop, "get_has_active_plot_edit", lambda: False)
    monkeypatch.setattr(desktop, "get_has_session_plot_edit", lambda: True)
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "cancel_edit",
        lambda: cancellations.append("session") or True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == [
        "A session plot edit is still open. Cancel the edit and close Carnopy?"
    ]
    assert not desktop.confirm_transient_edit_shutdown(False)
    assert cancellations == []
    assert close_requests == []
    assert desktop.confirm_transient_edit_shutdown(True)
    assert cancellations == ["session"]
    assert close_requests == ["close"]


def test_qml_shutdown_explicitly_cancels_a_transient_sweep_edit_before_close(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[str] = []
    close_requests: list[str] = []
    cancellations: list[str] = []
    desktop.transientEditShutdownConfirmationRequested.connect(confirmations.append)
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    monkeypatch.setattr(desktop, "get_has_active_sweep_edit", lambda: True)
    monkeypatch.setattr(
        desktop.configuration_controller.sweep_draft,
        "cancel_comparison",
        lambda: cancellations.append("comparison") or True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == [
        "A Sweep comparison edit is still open. Cancel the edit and close Carnopy?"
    ]
    assert not desktop.confirm_transient_edit_shutdown(False)
    assert cancellations == []
    assert close_requests == []
    assert desktop.confirm_transient_edit_shutdown(True)
    assert cancellations == ["comparison"]
    assert close_requests == ["close"]


def test_qml_shutdown_explicitly_cancels_a_transient_preparation_edit_before_close(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    confirmations: list[str] = []
    close_requests: list[str] = []
    cancellations: list[str] = []
    desktop.transientEditShutdownConfirmationRequested.connect(confirmations.append)
    desktop.closeWindowRequested.connect(lambda: close_requests.append("close"))
    monkeypatch.setattr(desktop, "get_has_active_preparation_edit", lambda: True)
    monkeypatch.setattr(
        desktop.configuration_controller.preparation_draft,
        "cancel_scenario",
        lambda: cancellations.append("scenario") or True,
    )

    assert not desktop.request_shutdown()
    assert confirmations == [
        "A Preparation scenario edit is still open. Cancel the edit and close Carnopy?"
    ]
    assert not desktop.confirm_transient_edit_shutdown(False)
    assert cancellations == []
    assert close_requests == []
    assert desktop.confirm_transient_edit_shutdown(True)
    assert cancellations == ["scenario"]
    assert close_requests == ["close"]


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
    assert desktop.request_configuration_attention("sweep", "sweep.backend.reference_model", -1)
    assert desktop.request_configuration_attention(
        "preparation",
        "preparation.scenario.active.name",
        -1,
    )
    assert desktop.request_configuration_attention("visualization", "plot.name", -1)
    assert not desktop.request_configuration_attention("workspace", "dataset.mode", -1)
    assert not desktop.request_configuration_attention("dataset", "plot.name", -1)
    assert attention == [
        ("dataset", "dataset.properties", 2),
        ("sweep", "sweep.backend.reference_model", -1),
        ("preparation", "preparation.scenario.active.name", -1),
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


def test_sweep_workflow_facade_routes_only_the_integrated_workflow(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    calls: list[str] = []
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "plan",
        lambda: calls.append("plan") or True,
    )
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "execute",
        lambda: calls.append("execute") or True,
    )
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "cancel",
        lambda: calls.append("cancel") or True,
    )
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "force_stop",
        lambda: calls.append("force_stop") or True,
    )

    assert desktop.request_workflow_plan("sweep")
    assert desktop.request_workflow_execute("model_sweep")
    assert desktop.request_workflow_cancel("sweep")
    assert desktop.request_workflow_force_stop("model_sweep")
    assert not desktop.request_workflow_plan("preparation")
    assert not desktop.request_workflow_execute("unknown")
    assert calls == ["plan", "execute", "cancel", "force_stop"]
    assert desktop.shutdown()


def test_sweep_creation_and_generic_open_facade_use_global_configuration_lifecycle(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        desktop.configuration_controller,
        "new_sweep",
        lambda confirmed: calls.append(("new_sweep", confirmed)) or True,
    )
    monkeypatch.setattr(
        desktop.configuration_controller,
        "import_configuration",
        lambda path, confirmed: calls.append(("open", path, confirmed)) or True,
    )
    source = tmp_path / "sweep.yaml"

    assert desktop.request_new_sweep(True)
    assert desktop.request_import_configuration(QUrl.fromLocalFile(str(source)).toString(), True)
    assert calls == [
        ("new_sweep", True),
        ("open", str(source), True),
    ]
    assert desktop.shutdown()


def test_sweep_editor_facade_enforces_document_and_worker_edit_guards(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    selections: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        desktop.configuration_controller.sweep_draft,
        "set_model_selected",
        lambda model, selected: selections.append((model, selected)) or True,
    )
    monkeypatch.setattr(
        desktop.configuration_controller,
        "get_document_kind",
        lambda: "dataset",
    )
    monkeypatch.setattr(desktop.configuration_controller, "get_can_edit", lambda: True)

    desktop.request_sweep_model_selection("pr", True)
    assert selections == []

    monkeypatch.setattr(
        desktop.configuration_controller,
        "get_document_kind",
        lambda: "model_sweep",
    )
    desktop.request_sweep_model_selection("pr", True)
    assert selections == [("pr", True)]

    monkeypatch.setattr(desktop.configuration_controller, "get_can_edit", lambda: False)
    desktop.request_sweep_model_selection("srk", True)
    assert selections == [("pr", True)]
    assert "active worker request" in desktop.get_workspace_error_message()
    assert desktop.shutdown()


def test_sweep_result_handoff_inspects_the_exact_finalized_output(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    output = tmp_path / "workspace" / "outputs" / "sweep-run"
    inspected: list[str] = []
    navigation: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []
    desktop.navigationRequested.connect(lambda page, detail: navigation.append((page, detail)))
    desktop.activityActionFailed.connect(lambda title, message: failures.append((title, message)))
    monkeypatch.setattr(
        desktop.sweep_workflow_controller,
        "get_result_output_directory",
        lambda: str(output),
    )
    monkeypatch.setattr(
        desktop.inspection_controller,
        "inspect_source",
        lambda value: inspected.append(str(value)) or True,
    )

    assert desktop.request_workflow_inspect_result("sweep")
    assert inspected == [str(output)]
    assert navigation == [("inspect", "")]
    assert failures == []

    assert not desktop.request_workflow_inspect_result("preparation")
    assert failures == [
        (
            "Inspect Result",
            "Complete this workflow successfully before inspecting its finalized output.",
        )
    ]
    assert desktop.shutdown()


def test_preparation_source_facade_requires_confirmation_for_a_current_plan(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    controller = desktop.preparation_workflow_controller
    calls: list[str] = []
    confirmations: list[str] = []
    desktop.preparationSourceClearConfirmationRequested.connect(
        lambda: confirmations.append("clear")
    )
    monkeypatch.setattr(
        controller,
        "bind_inspected_source",
        lambda: calls.append("bind") or True,
    )
    monkeypatch.setattr(controller, "get_has_bound_source", lambda: True)
    monkeypatch.setattr(controller, "get_plan_current", lambda: True)
    monkeypatch.setattr(
        controller,
        "clear_bound_source",
        lambda: calls.append("clear") or True,
    )

    assert desktop.request_bind_inspected_preparation_source()
    assert not desktop.request_clear_preparation_source()
    assert confirmations == ["clear"]
    assert calls == ["bind"]

    assert desktop.request_clear_preparation_source(confirmed=True)
    assert calls == ["bind", "clear"]

    monkeypatch.setattr(controller, "get_plan_current", lambda: False)
    assert desktop.request_clear_preparation_source()
    assert calls == ["bind", "clear", "clear"]
    assert confirmations == ["clear"]
    assert desktop.shutdown()


def test_bound_preparation_profile_is_the_only_profile_applied_to_the_draft(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    source = tmp_path / "workspace" / "outputs" / "dataset-run"
    profile = {"source_kind": "dataset_run", "inspection_revision": "a" * 64}
    applied: list[object] = []
    monkeypatch.setattr(
        desktop.preparation_workflow_controller,
        "bound_source_snapshot",
        lambda: (source, "a" * 64, {"source_path": str(source)}, profile),
    )
    monkeypatch.setattr(
        desktop.configuration_controller.preparation_draft,
        "apply_source_profile",
        applied.append,
    )

    desktop._preparation_source_binding_changed()
    assert applied == [profile]

    monkeypatch.setattr(
        desktop.preparation_workflow_controller,
        "bound_source_snapshot",
        lambda: None,
    )
    desktop._preparation_source_binding_changed()
    assert applied == [profile, None]
    assert desktop.shutdown()


def test_execution_record_changes_refresh_the_shared_activity_projection(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    workspace = initialize_workspace(tmp_path / "workspace")
    desktop.activity_controller.set_workspace(workspace)
    assert desktop.activity_controller.records_model.get_count() == 0
    JobStore(workspace.private_directory).start(
        request_id="00000000-0000-0000-0000-000000000020",
        operation="validate",
        config_relative_path="configs/dataset.yaml",
        yaml_snapshot="schema_version: 2\n",
        config_sha256="a" * 64,
    )

    desktop.execution_controller.activity_record_changed.emit()

    assert desktop.activity_controller.records_model.get_count() == 1
    assert desktop.activity_controller.records_model.rows()[0]["state"] == "interrupted"
    assert desktop.shutdown()


def test_activity_cross_page_actions_use_exact_selected_record_identity(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    source = str((tmp_path / "workspace" / "outputs" / "run-id").resolve())
    inspected: list[str] = []
    selected: list[str] = []
    navigation: list[tuple[str, str]] = []
    desktop.navigationRequested.connect(lambda page, detail: navigation.append((page, detail)))
    monkeypatch.setattr(
        desktop.activity_controller,
        "get_selected_record_summary",
        lambda: {"outputDirectory": source},
    )
    monkeypatch.setattr(
        desktop.activity_controller,
        "get_selected_record_id",
        lambda: "request-id",
    )
    monkeypatch.setattr(
        desktop.activity_controller,
        "get_can_inspect_run",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.activity_controller,
        "get_can_view_plots",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.inspection_controller,
        "inspect_source",
        lambda value: inspected.append(value) or True,
    )
    monkeypatch.setattr(
        desktop.configured_plot_results_controller,
        "select_generation",
        lambda value: selected.append(value) or True,
    )
    monkeypatch.setattr(desktop.execution_controller, "get_operation", lambda: "generate")
    monkeypatch.setattr(desktop.execution_controller, "get_state", lambda: "succeeded")
    monkeypatch.setattr(
        desktop.execution_controller,
        "get_result_output_directory",
        lambda: source,
    )
    monkeypatch.setattr(
        desktop.execution_controller,
        "get_result_request_id",
        lambda: "request-id",
    )
    monkeypatch.setattr(
        desktop.inspection_controller,
        "get_can_explore_plots",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.configured_plot_results_controller,
        "get_can_explore_run",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.configured_plot_results_controller,
        "get_selected_output_directory",
        lambda: source,
    )

    assert desktop.request_activity_inspect_run()
    assert desktop.request_activity_view_plots()
    assert desktop.request_execution_inspect_run()
    assert desktop.request_execution_view_plots()
    assert desktop.request_inspection_explore()
    assert desktop.request_configured_plot_explore_run()
    desktop.inspection_controller.inspection_loaded.emit(Path(source))

    assert inspected == [source, source, source]
    assert selected == ["request-id", "request-id"]
    assert navigation == [
        ("inspect", ""),
        ("visualization", "configured"),
        ("inspect", ""),
        ("visualization", "configured"),
        ("visualization", "explore"),
        ("visualization", "explore"),
    ]
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
        desktop.configuration_controller,
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
        desktop.configuration_controller,
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
    monkeypatch.setattr(desktop.configuration_controller, "set_workspace", lambda _value: None)
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
    monkeypatch.setattr(desktop.configuration_controller, "set_workspace", lambda _value: None)
    monkeypatch.setattr(
        desktop.configuration_controller,
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
        "new_sweep",
        "import_dataset",
        "import_configuration",
        "request_save",
        "request_save_as",
        "request_validation",
        "reload_source",
        "apply_mode_change",
        "apply_coordinate_change",
    ):
        monkeypatch.setattr(
            desktop.configuration_controller,
            name,
            lambda *_args, operation=name: calls.append(operation) or True,
        )

    assert not desktop.request_new_dataset("property_table")
    assert not desktop.request_new_sweep()
    assert not desktop.request_import_dataset("input.yaml")
    assert not desktop.request_import_configuration("input.yaml")
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
    assert not desktop.configuration_controller.clear_document(discard_confirmed=True)
    assert not desktop.shutdown()

    assert calls == []
    assert attention
    assert all(item == ("visualization", "visualization.plots", -1) for item in attention)


def test_active_preparation_edit_blocks_workspace_and_configuration_lifecycle(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    preparation = desktop.configuration_controller.preparation_draft
    calls: list[str] = []
    attention: list[tuple[str, str, int]] = []
    desktop.attentionRequested.connect(
        lambda section, field, row: attention.append((section, field, row))
    )
    monkeypatch.setattr(preparation, "get_has_active_scenario_edit", lambda: True)
    monkeypatch.setattr(
        preparation,
        "get_first_invalid_field",
        lambda: "preparation.scenario.active.name",
    )
    monkeypatch.setattr(preparation, "get_first_invalid_row", lambda: -1)
    for name in (
        "new_dataset",
        "new_sweep",
        "import_dataset",
        "import_configuration",
        "request_save",
        "request_save_as",
        "request_validation",
        "reload_source",
    ):
        monkeypatch.setattr(
            desktop.configuration_controller,
            name,
            lambda *_args, operation=name: calls.append(operation) or True,
        )
    preflight_calls: list[str] = []
    monkeypatch.setattr(
        desktop.workspace_controller,
        "prepare_create",
        lambda _path: preflight_calls.append("workspace") or True,
    )

    assert desktop.get_has_active_preparation_edit()
    assert desktop.get_has_any_transient_edit()
    assert not desktop.get_can_change_workspace()
    assert not desktop.prepare_create_workspace_path(str(tmp_path / "workspace"))
    assert not desktop.request_new_dataset("property_table")
    assert not desktop.request_new_sweep()
    assert not desktop.request_import_dataset("input.yaml")
    assert not desktop.request_import_configuration("input.yaml")
    assert not desktop.request_save()
    assert not desktop.request_save_as()
    assert not desktop.request_validate_configuration()
    assert not desktop.request_reload_source()
    assert not desktop.request_close_configuration()
    assert not desktop.shutdown()

    assert calls == []
    assert preflight_calls == []
    assert attention
    assert all(
        item == ("preparation", "preparation.scenario.active.name", -1) for item in attention
    )
    assert "Preparation scenario" in desktop.get_workspace_error_message()
    monkeypatch.setattr(preparation, "get_has_active_scenario_edit", lambda: False)
    assert desktop.shutdown()


def test_session_plot_edit_guards_replacement_but_not_configuration_save(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    desktop = DesktopController(settings=settings_for(tmp_path / "settings.ini"))
    calls: list[str] = []
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "get_has_active_edit",
        lambda: True,
    )
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "can_replace_inspection",
        lambda operation: calls.append(operation) or False,
    )
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "get_issue",
        lambda: "Render or cancel the session plot edit.",
    )
    save_calls: list[str] = []
    monkeypatch.setattr(
        desktop.configuration_controller,
        "request_save",
        lambda *_args: save_calls.append("save") or True,
    )

    assert not desktop.get_can_change_workspace()
    assert not desktop.prepare_create_workspace_path(str(tmp_path / "workspace"))
    assert not desktop.shutdown()
    assert desktop.request_save()
    assert save_calls == ["save"]
    assert calls == ["replacing the workspace", "closing Carnopy"]
    monkeypatch.setattr(
        desktop.session_plot_controller,
        "can_replace_inspection",
        lambda _operation: True,
    )
    assert desktop.shutdown()


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
        desktop.configuration_controller,
        "apply_mode_change",
        lambda value: applied.append(("mode", value)) or True,
    )
    monkeypatch.setattr(
        desktop.configuration_controller,
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
    "carnopy.visualization.configuration", "carnopy.visualization.models",
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
