from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot

from carnopy.app.activity_controller import ActivityController
from carnopy.app.client import WorkerClient
from carnopy.app.comparison_plot_draft import ComparisonPlotDraft
from carnopy.app.config_controller import ConfigurationController
from carnopy.app.configured_plot_results_controller import ConfiguredPlotResultsController
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.execution_controller import DatasetExecutionController
from carnopy.app.field_ids import VISUALIZATION_PLOTS
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.mapping_draft import MappingDraftModel
from carnopy.app.plot_draft import PlotDraft
from carnopy.app.plot_preview_provider import VerifiedPlotPreviewRegistry
from carnopy.app.qml_settings import QmlSettingsController
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.sampler_draft import SamplerDraft
from carnopy.app.scenario_draft import ScenarioDraft
from carnopy.app.scene_controller import SceneController
from carnopy.app.scene_lifecycle import SceneLeaseLifecycle
from carnopy.app.session_plot_controller import SessionPlotController
from carnopy.app.visualization_draft import VisualizationDraft
from carnopy.app.workflow_controller import (
    PreparationWorkflowController,
    SweepWorkflowController,
)
from carnopy.app.workspace import Workspace
from carnopy.app.workspace_controller import WorkspaceController


class DesktopController(QObject):
    """Compose the process-wide desktop state and worker transport."""

    workspace_state_changed = Signal()
    workspace_feedback_changed = Signal()
    workspace_confirmation_changed = Signal()
    workspaceConfirmationRequested = Signal()
    datasetDecisionRequested = Signal()
    datasetDecisionChanged = Signal()
    configurationDocumentOpened = Signal(str)
    attentionRequested = Signal(str, str, int)
    shutdownConfirmationRequested = Signal()
    transientEditShutdownConfirmationRequested = Signal(str)
    closeWindowRequested = Signal()
    navigationRequested = Signal(str, str)
    activityActionFailed = Signal(str, str)
    busyShutdownConfirmationRequested = Signal(str, str)
    preparationSourceClearConfirmationRequested = Signal()

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings()
        self.qml_settings = QmlSettingsController(self.settings, self)
        self.client = WorkerClient(self)
        self.request_coordinator = DesktopRequestCoordinator(self.client, self)
        self.scene_controller = SceneController(self.request_coordinator, parent=self)
        self.scene_lifecycle = SceneLeaseLifecycle(self.scene_controller, self)
        self.dataset_draft = DatasetDraft(self)
        self.visualization_draft = VisualizationDraft(self)
        self.configuration_controller = ConfigurationController(
            self.request_coordinator,
            self.dataset_draft,
            self.visualization_draft,
            self,
        )
        self.execution_controller = DatasetExecutionController(
            self.request_coordinator,
            self.configuration_controller,
            self,
        )
        self.inspection_controller = InspectionController(
            self.request_coordinator,
            self,
        )
        self.sweep_workflow_controller = SweepWorkflowController(
            self.request_coordinator,
            self,
            configuration_controller=self.configuration_controller,
        )
        self.preparation_workflow_controller = PreparationWorkflowController(
            self.request_coordinator,
            self.inspection_controller,
            self,
            configuration_controller=self.configuration_controller,
        )
        self.preparation_workflow_controller.source_binding_changed.connect(
            self._preparation_source_binding_changed
        )
        self.activity_controller = ActivityController(
            self.request_coordinator,
            self,
        )
        self.plot_preview_registry = VerifiedPlotPreviewRegistry(self)
        self.configured_plot_results_controller = ConfiguredPlotResultsController(
            self.activity_controller,
            self.configuration_controller,
            self.plot_preview_registry,
            self,
        )
        self.session_plot_controller = SessionPlotController(
            self.request_coordinator,
            self.inspection_controller,
            self.plot_preview_registry,
            self,
        )
        self.inspection_controller.set_lifecycle_guard(
            self.session_plot_controller.can_replace_inspection
        )
        self.inspection_controller.inspection_loaded.connect(
            self._pending_explore_inspection_loaded
        )
        self.inspection_controller.inspection_failed.connect(
            self._pending_explore_inspection_failed
        )
        self.execution_controller.activity_record_changed.connect(
            self.activity_controller.refresh_records
        )
        self.execution_controller.state_changed.connect(self._continue_pending_busy_shutdown)
        self.sweep_workflow_controller.state_changed.connect(self._continue_pending_busy_shutdown)
        self.preparation_workflow_controller.state_changed.connect(
            self._continue_pending_busy_shutdown
        )
        self.scene_controller.state_changed.connect(self._continue_pending_busy_shutdown)
        self.scene_lifecycle.state_changed.connect(self._scene_lifecycle_changed)
        self.execution_controller.run_finalized.connect(
            lambda _path: self.inspection_controller.refresh_sources()
        )
        self.sweep_workflow_controller.activity_record_changed.connect(
            self.activity_controller.refresh_records
        )
        self.preparation_workflow_controller.activity_record_changed.connect(
            self.activity_controller.refresh_records
        )
        self.sweep_workflow_controller.output_finalized.connect(
            lambda _path: self.inspection_controller.refresh_sources()
        )
        self.preparation_workflow_controller.output_finalized.connect(
            lambda _path: self.inspection_controller.refresh_sources()
        )
        self.configuration_controller.set_lifecycle_guard(self._guard_configuration_lifecycle)
        self.workspace_controller = WorkspaceController(
            self.request_coordinator,
            self.settings,
            self,
        )
        self.workspace_controller.workspace_changed.connect(self._workspace_activated)
        self.workspace_controller.available_changed.connect(self.workspace_state_changed)
        self.workspace_controller.paths_changed.connect(self.workspace_state_changed)
        self.workspace_controller.status_message_changed.connect(self.workspace_feedback_changed)
        self.workspace_controller.error_message_changed.connect(self.workspace_feedback_changed)
        self.workspace_controller.pending_operation_changed.connect(
            self.workspace_confirmation_changed
        )
        self._configuration_state_revision = 0
        self._pending_busy_shutdown = ""
        self._pending_busy_confirmation_session: object | None = None
        self._pending_busy_shutdown_session: object | None = None
        self._pending_transient_shutdown_context: tuple[tuple[bool, object | None], ...] | None = (
            None
        )
        self._pending_discard_shutdown_context: tuple[object | None, int] | None = None
        self._approved_discard_shutdown_context: tuple[object | None, int] | None = None
        self.configuration_controller.state_changed.connect(self._configuration_state_changed)
        self.configuration_controller.configuration_document_opened.connect(
            self.configurationDocumentOpened
        )
        self.request_coordinator.busy_changed.connect(self._request_state_changed)
        self.visualization_draft.active_plot_draft_changed.connect(self._active_plot_state_changed)
        self.session_plot_controller.active_edit_changed.connect(self._active_plot_state_changed)
        self.session_plot_controller.attention_requested.connect(
            lambda field, row: self.attentionRequested.emit("visualization", field, row)
        )
        self.visualization_draft.plot_commit_rejected.connect(self._plot_commit_rejected)
        self._queued_workspace_request: tuple[str, str, str, bool] | None = None
        self._pending_dataset_decision: tuple[str, str] | None = None
        self._workspace_request_timer = QTimer(self)
        self._workspace_request_timer.setSingleShot(True)
        self._workspace_request_timer.setInterval(0)
        self._workspace_request_timer.timeout.connect(self._run_queued_workspace_request)
        self._shutdown = False
        self._pending_explore_source: Path | None = None
        self._pending_explore_begin_edit = False
        self._pending_explore_action = "Explore this run"

    def get_workspace_controller(self) -> QObject:
        return self.workspace_controller

    workspaceController = Property(QObject, get_workspace_controller, constant=True)

    def get_workspace_available(self) -> bool:
        return self.workspace_controller.get_available()

    workspaceAvailable = Property(
        bool,
        get_workspace_available,
        notify=workspace_state_changed,
    )

    def get_workspace_state(self) -> str:
        if not self.workspace_controller.get_available():
            return "unavailable"
        if self.configuration_controller.get_has_document():
            return "editing"
        if (
            not self.configuration_controller.get_editor_available()
            and self.request_coordinator.is_busy
            and self.request_coordinator.active_owner == "configuration"
        ):
            return "loading"
        return "landing"

    workspaceState = Property(str, get_workspace_state, notify=workspace_state_changed)

    def get_workspace_root_path(self) -> str:
        return self.workspace_controller.get_root_path()

    workspaceRootPath = Property(
        str,
        get_workspace_root_path,
        notify=workspace_state_changed,
    )

    def get_workspace_status_message(self) -> str:
        return self.workspace_controller.get_status_message()

    workspaceStatusMessage = Property(
        str,
        get_workspace_status_message,
        notify=workspace_feedback_changed,
    )

    def get_workspace_error_message(self) -> str:
        return self.workspace_controller.get_error_message()

    workspaceErrorMessage = Property(
        str,
        get_workspace_error_message,
        notify=workspace_feedback_changed,
    )

    def get_can_change_workspace(self) -> bool:
        return (
            self.workspace_controller.get_can_change_workspace()
            and self.visualization_draft.get_active_plot_draft() is None
            and not self.session_plot_controller.get_has_active_edit()
            and not self.get_has_active_sweep_edit()
            and not self.get_has_active_preparation_edit()
        )

    canChangeWorkspace = Property(
        bool,
        get_can_change_workspace,
        notify=workspace_state_changed,
    )

    def get_recent_workspaces(self) -> QObject:
        return self.workspace_controller.recent_model

    recentWorkspaces = Property(QObject, get_recent_workspaces, constant=True)

    def get_pending_workspace_operation(self) -> str:
        return self.workspace_controller.get_pending_operation()

    pendingWorkspaceOperation = Property(
        str,
        get_pending_workspace_operation,
        notify=workspace_confirmation_changed,
    )

    def get_pending_workspace_path(self) -> str:
        return self.workspace_controller.get_pending_path()

    pendingWorkspacePath = Property(
        str,
        get_pending_workspace_path,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_required(self) -> bool:
        operation = self.workspace_controller.get_pending_operation()
        if not operation:
            return False
        if operation == "initialize_existing":
            return True
        workspace = self.workspace_controller.workspace
        if (
            operation == "open"
            and workspace is not None
            and self.workspace_controller.get_pending_path() == str(workspace.root)
        ):
            return False
        return self.configuration_controller.needs_discard_confirmation()

    workspaceConfirmationRequired = Property(
        bool,
        get_workspace_confirmation_required,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_title(self) -> str:
        if self.workspace_controller.get_pending_operation() == "initialize_existing":
            return "Initialize Existing Folder"
        return "Replace Workspace"

    workspaceConfirmationTitle = Property(
        str,
        get_workspace_confirmation_title,
        notify=workspace_confirmation_changed,
    )

    def get_workspace_confirmation_message(self) -> str:
        operation = self.workspace_controller.get_pending_operation()
        path = self.workspace_controller.get_pending_path()
        dirty = self.configuration_controller.needs_discard_confirmation()
        if operation == "initialize_existing":
            message = f"Initialize this existing folder as a Carnopy workspace?\n\n{path}"
            if dirty:
                message += (
                    "\n\nThe current configuration has unsaved changes that will be discarded."
                )
            return message
        if dirty:
            return (
                "The current configuration has unsaved changes. Discard them and "
                f"open this workspace?\n\n{path}"
            )
        return ""

    workspaceConfirmationMessage = Property(
        str,
        get_workspace_confirmation_message,
        notify=workspace_confirmation_changed,
    )

    def get_qml_settings(self) -> QObject:
        return self.qml_settings

    qmlSettings = Property(QObject, get_qml_settings, constant=True)

    def get_dataset_draft(self) -> QObject:
        return self.dataset_draft

    datasetDraft = Property(QObject, get_dataset_draft, constant=True)

    def get_visualization_draft(self) -> QObject:
        return self.visualization_draft

    visualizationDraft = Property(QObject, get_visualization_draft, constant=True)

    def get_has_active_plot_edit(self) -> bool:
        return self.visualization_draft.get_has_active_plot_edit()

    hasActivePlotEdit = Property(
        bool,
        get_has_active_plot_edit,
        notify=workspace_state_changed,
    )

    hasConfiguredPlotEdit = Property(
        bool,
        get_has_active_plot_edit,
        notify=workspace_state_changed,
    )

    def get_has_session_plot_edit(self) -> bool:
        return self.session_plot_controller.get_has_active_edit()

    hasSessionPlotEdit = Property(
        bool,
        get_has_session_plot_edit,
        notify=workspace_state_changed,
    )

    def get_has_active_sweep_edit(self) -> bool:
        return self.configuration_controller.sweep_draft.get_has_active_comparison_edit()

    hasActiveSweepEdit = Property(
        bool,
        get_has_active_sweep_edit,
        notify=workspace_state_changed,
    )

    def get_has_active_preparation_edit(self) -> bool:
        return self.configuration_controller.preparation_draft.get_has_active_scenario_edit()

    hasActivePreparationEdit = Property(
        bool,
        get_has_active_preparation_edit,
        notify=workspace_state_changed,
    )

    def get_has_any_transient_edit(self) -> bool:
        return (
            self.get_has_active_plot_edit()
            or self.get_has_session_plot_edit()
            or self.get_has_active_sweep_edit()
            or self.get_has_active_preparation_edit()
        )

    hasAnyTransientEdit = Property(
        bool,
        get_has_any_transient_edit,
        notify=workspace_state_changed,
    )

    def get_configuration_controller(self) -> QObject:
        return self.configuration_controller

    configurationController = Property(
        QObject,
        get_configuration_controller,
        constant=True,
    )

    def get_execution_controller(self) -> QObject:
        return self.execution_controller

    executionController = Property(
        QObject,
        get_execution_controller,
        constant=True,
    )

    def get_scene_controller(self) -> QObject:
        return self.scene_controller

    sceneController = Property(
        QObject,
        get_scene_controller,
        constant=True,
    )

    def get_scene_cleanup_issue(self) -> str:
        return self.scene_lifecycle.get_cleanup_issue()

    sceneCleanupIssue = Property(
        str,
        get_scene_cleanup_issue,
        notify=workspace_feedback_changed,
    )

    def get_sweep_workflow_controller(self) -> QObject:
        return self.sweep_workflow_controller

    sweepWorkflowController = Property(
        QObject,
        get_sweep_workflow_controller,
        constant=True,
    )

    def get_preparation_workflow_controller(self) -> QObject:
        return self.preparation_workflow_controller

    preparationWorkflowController = Property(
        QObject,
        get_preparation_workflow_controller,
        constant=True,
    )

    def get_inspection_controller(self) -> QObject:
        return self.inspection_controller

    inspectionController = Property(
        QObject,
        get_inspection_controller,
        constant=True,
    )

    def get_activity_controller(self) -> QObject:
        return self.activity_controller

    activityController = Property(
        QObject,
        get_activity_controller,
        constant=True,
    )

    def get_configured_plot_results_controller(self) -> QObject:
        return self.configured_plot_results_controller

    configuredPlotResultsController = Property(
        QObject,
        get_configured_plot_results_controller,
        constant=True,
    )

    def get_session_plot_controller(self) -> QObject:
        return self.session_plot_controller

    sessionPlotController = Property(
        QObject,
        get_session_plot_controller,
        constant=True,
    )

    def get_dataset_decision_title(self) -> str:
        decision = self._pending_dataset_decision
        if decision is None:
            return ""
        return "Change Dataset Mode" if decision[0] == "mode" else "Change Sampling Coordinate"

    datasetDecisionTitle = Property(
        str,
        get_dataset_decision_title,
        notify=datasetDecisionRequested,
    )

    def get_dataset_decision_message(self) -> str:
        decision = self._pending_dataset_decision
        if decision is None:
            return ""
        if decision[0] == "mode":
            return (
                "Changing dataset mode resets the sampling grid and removes configured "
                "visualization requests. Shared model, fluids, properties, and output formats "
                "are preserved."
            )
        return (
            "Changing the independent coordinate replaces that coordinate's sampler. "
            "Other compatible dataset selections are retained."
        )

    datasetDecisionMessage = Property(
        str,
        get_dataset_decision_message,
        notify=datasetDecisionRequested,
    )

    @Slot(str, bool, result=bool, name="requestNewDataset")
    def request_new_dataset(self, mode: str, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("New Dataset"):
            return False
        return self.configuration_controller.new_dataset(mode, discard_confirmed)

    @Slot(bool, result=bool, name="requestNewSweep")
    def request_new_sweep(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("New Model Sweep"):
            return False
        return self.configuration_controller.new_sweep(discard_confirmed)

    @Slot(bool, result=bool, name="requestNewPreparation")
    def request_new_preparation(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("New ML Preparation"):
            return False
        return self.configuration_controller.new_preparation(discard_confirmed)

    @Slot(str, bool, result=bool, name="requestImportConfiguration")
    def request_import_configuration(
        self,
        path: str,
        discard_confirmed: bool = False,
    ) -> bool:
        if not self._guard_idle_configuration_action("Open Configuration"):
            return False
        return self.configuration_controller.import_configuration(
            _local_path(path),
            discard_confirmed,
        )

    @Slot(str, bool, result=bool, name="requestImportDataset")
    def request_import_dataset(self, path: str, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("Import"):
            return False
        return self.configuration_controller.import_dataset(
            _local_path(path),
            discard_confirmed,
        )

    @Slot(bool, result=bool, name="requestSave")
    def request_save(self, allow_reformat: bool = False) -> bool:
        if not self._guard_idle_configuration_action("Save"):
            return False
        return self.configuration_controller.request_save(allow_reformat)

    @Slot(bool, result=bool, name="requestSaveAs")
    def request_save_as(self, allow_reformat: bool = False) -> bool:
        if not self._guard_idle_configuration_action("Save As"):
            return False
        return self.configuration_controller.request_save_as(allow_reformat)

    @Slot(result=bool, name="requestValidateConfiguration")
    def request_validate_configuration(self) -> bool:
        if not self._guard_idle_configuration_action("Validation"):
            return False
        return self.configuration_controller.request_validation()

    @Slot(result=bool, name="requestExecutionValidation")
    def request_execution_validation(self) -> bool:
        if not self._guard_idle_configuration_action("Dataset validation"):
            return False
        return self.execution_controller.validate()

    @Slot(result=bool, name="requestDatasetGeneration")
    def request_dataset_generation(self) -> bool:
        if not self._guard_idle_configuration_action("Dataset generation"):
            return False
        return self.execution_controller.generate()

    @Slot(result=bool, name="requestExecutionCancel")
    def request_execution_cancel(self) -> bool:
        return self.execution_controller.cancel()

    @Slot(result=bool, name="requestExecutionForceStop")
    def request_execution_force_stop(self) -> bool:
        return self.execution_controller.force_stop()

    @Slot(str, result=bool, name="requestWorkflowPlan")
    def request_workflow_plan(self, workflow: str) -> bool:
        controller = self._workflow_controller(workflow)
        if controller is None or not self._guard_idle_configuration_action(
            f"{_workflow_label(workflow)} planning"
        ):
            return False
        return controller.plan()

    @Slot(str, result=bool, name="requestWorkflowExecute")
    def request_workflow_execute(self, workflow: str) -> bool:
        controller = self._workflow_controller(workflow)
        if controller is None or not self._guard_idle_configuration_action(
            f"{_workflow_label(workflow)} execution"
        ):
            return False
        return controller.execute()

    @Slot(str, result=bool, name="requestWorkflowCancel")
    def request_workflow_cancel(self, workflow: str) -> bool:
        controller = self._workflow_controller(workflow)
        return False if controller is None else controller.cancel()

    @Slot(str, result=bool, name="requestWorkflowForceStop")
    def request_workflow_force_stop(self, workflow: str) -> bool:
        controller = self._workflow_controller(workflow)
        return False if controller is None else controller.force_stop()

    @Slot(str, result=bool, name="requestWorkflowInspectResult")
    def request_workflow_inspect_result(self, workflow: str) -> bool:
        controller = self._workflow_controller(workflow)
        output = "" if controller is None else controller.get_result_output_directory()
        if not output:
            self.activityActionFailed.emit(
                "Inspect Result",
                "Complete this workflow successfully before inspecting its finalized output.",
            )
            return False
        return self._inspect_run(output, navigate=True)

    @Slot(str, result=bool, name="requestInspectSource")
    def request_inspect_source(self, source: str) -> bool:
        return self.inspection_controller.inspect_source(_local_path(source))

    @Slot(result=bool, name="requestRefreshInspection")
    def request_refresh_inspection(self) -> bool:
        return self.inspection_controller.refresh_inspection()

    @Slot(result=bool, name="requestBindInspectedPreparationSource")
    def request_bind_inspected_preparation_source(self) -> bool:
        return self.preparation_workflow_controller.bind_inspected_source()

    @Slot(bool, result=bool, name="requestClearPreparationSource")
    def request_clear_preparation_source(self, confirmed: bool = False) -> bool:
        controller = self.preparation_workflow_controller
        if controller.get_has_bound_source() and controller.get_plan_current() and not confirmed:
            self.preparationSourceClearConfirmationRequested.emit()
            return False
        return controller.clear_bound_source()

    @Slot(name="requestRefreshInspectionSources")
    def request_refresh_inspection_sources(self) -> None:
        self.inspection_controller.refresh_sources()

    @Slot(str, result=bool, name="requestInspectionTable")
    def request_inspection_table(self, table_id: str) -> bool:
        return self.inspection_controller.select_table(table_id)

    @Slot(int, result=bool, name="requestInspectionPreviewPage")
    def request_inspection_preview_page(self, page_offset: int) -> bool:
        return self.inspection_controller.request_preview_page(page_offset)

    @Slot(name="requestMoreInspectionSources")
    def request_more_inspection_sources(self) -> None:
        self.inspection_controller.reveal_more_sources()

    @Slot(result=bool, name="requestExecutionInspectRun")
    def request_execution_inspect_run(self) -> bool:
        if (
            self.execution_controller.get_operation() != "generate"
            or self.execution_controller.get_state() != "succeeded"
        ):
            self.activityActionFailed.emit(
                "Inspect Run",
                "Generate a dataset successfully before inspecting its output.",
            )
            return False
        return self._inspect_run(
            self.execution_controller.get_result_output_directory(),
            navigate=True,
        )

    @Slot(result=bool, name="requestExecutionViewPlots")
    def request_execution_view_plots(self) -> bool:
        if (
            self.execution_controller.get_operation() != "generate"
            or self.execution_controller.get_state() != "succeeded"
        ):
            self.activityActionFailed.emit(
                "View Plots",
                "Generate a dataset successfully before opening its plot results.",
            )
            return False
        return self._view_configured_generation(self.execution_controller.get_result_request_id())

    @Slot(result=bool, name="requestExecutionCreatePlot")
    def request_execution_create_plot(self) -> bool:
        if (
            self.execution_controller.get_operation() != "generate"
            or self.execution_controller.get_state() != "succeeded"
        ):
            self.activityActionFailed.emit(
                "Create plot from this run",
                "Generate a dataset successfully before creating a plot from its output.",
            )
            return False
        return self._inspect_for_exploration(
            self.execution_controller.get_result_output_directory(),
            begin_edit=True,
            action="Create plot from this run",
        )

    @Slot(result=bool, name="requestInspectionExplore")
    def request_inspection_explore(self) -> bool:
        if not self.inspection_controller.get_can_explore_plots():
            self.activityActionFailed.emit(
                "Explore inspected data",
                self.inspection_controller.get_issue()
                or "Inspect a compatible generated dataset before opening session plotting.",
            )
            return False
        self.navigationRequested.emit("visualization", "explore")
        return True

    @Slot(result=bool, name="requestConfiguredPlotExploreRun")
    def request_configured_plot_explore_run(self) -> bool:
        controller = self.configured_plot_results_controller
        if not controller.get_can_explore_run():
            self.activityActionFailed.emit(
                "Explore this run",
                "Select a successful generated run with a recorded output directory.",
            )
            return False
        return self._inspect_for_exploration(
            controller.get_selected_output_directory(),
            begin_edit=True,
            action="Create plot from this run",
        )

    @Slot(result=bool, name="requestActivityInspectRun")
    def request_activity_inspect_run(self) -> bool:
        summary = self.activity_controller.get_selected_record_summary()
        source = summary.get("outputDirectory")
        if not self.activity_controller.get_can_inspect_run() or not isinstance(source, str):
            self.activityActionFailed.emit(
                "Inspect Run",
                "Select a completed generation record with a recorded output directory.",
            )
            return False
        return self._inspect_run(source, navigate=True)

    @Slot(result=bool, name="requestActivityViewPlots")
    def request_activity_view_plots(self) -> bool:
        record_id = self.activity_controller.get_selected_record_id()
        if not self.activity_controller.get_can_view_plots() or not record_id:
            self.activityActionFailed.emit(
                "View Plots",
                "Select a completed generation record with a recorded output directory.",
            )
            return False
        return self._view_configured_generation(record_id)

    @Slot(result=bool, name="requestActivityRecordRemoval")
    def request_activity_record_removal(self) -> bool:
        return self.activity_controller.remove_selected_record()

    @Slot(result=bool, name="requestActivityRecoveryRemoval")
    def request_activity_recovery_removal(self) -> bool:
        return self.activity_controller.remove_selected_recovery()

    @Slot(str, result=bool, name="requestSavePathSelected")
    def request_save_path_selected(self, path: str) -> bool:
        if not self._guard_idle_configuration_action("Save As"):
            self.configuration_controller.cancel_save_path()
            return False
        return self.configuration_controller.save_path_selected(_local_path(path))

    @Slot(name="requestCancelSavePath")
    def request_cancel_save_path(self) -> None:
        self.configuration_controller.cancel_save_path()

    @Slot(str, name="requestConfirmReformat")
    def request_confirm_reformat(self, action: str) -> None:
        if self._guard_idle_configuration_action("Save"):
            self.configuration_controller.confirm_reformat(action)

    @Slot(bool, result=bool, name="requestReloadSource")
    def request_reload_source(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("Reload"):
            return False
        return self.configuration_controller.reload_source(discard_confirmed)

    @Slot(bool, result=bool, name="requestCloseConfiguration")
    def request_close_configuration(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_idle_configuration_action("Close Configuration"):
            return False
        return self.configuration_controller.clear_document(discard_confirmed)

    @Slot(str, str, int, result=bool, name="requestConfigurationAttention")
    def request_configuration_attention(self, section: str, field: str, row: int) -> bool:
        if section not in {"dataset", "sweep", "preparation", "visualization"}:
            return False
        if not field.startswith(f"{section}.") and not (
            section == "visualization" and field.startswith("plot.")
        ):
            return False
        self.attentionRequested.emit(section, field, row)
        return True

    @Slot(str, result=bool, name="requestDatasetModeChange")
    def request_dataset_mode_change(self, mode: str) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_configuration_lifecycle(
            "dataset mode change"
        ):
            return False
        if mode == self.dataset_draft.get_mode_name():
            return False
        if mode not in self.dataset_draft.mode_choices.values:
            return False
        self._pending_dataset_decision = ("mode", mode)
        self.datasetDecisionRequested.emit()
        return True

    @Slot(str, result=bool, name="requestDatasetCoordinateChange")
    def request_dataset_coordinate_change(self, axis: str) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_configuration_lifecycle(
            "dataset coordinate change"
        ):
            return False
        if axis == self.dataset_draft.get_coordinate_name():
            return False
        if axis not in self.dataset_draft.coordinate_choices.values:
            return False
        self._pending_dataset_decision = ("coordinate", axis)
        self.datasetDecisionRequested.emit()
        return True

    @Slot(bool, result=bool, name="commitDatasetDecision")
    def commit_dataset_decision(self, confirmed: bool) -> bool:
        decision = self._pending_dataset_decision
        if decision is None:
            return False
        if (
            not confirmed
            or not self._can_edit_dataset_document()
            or not self._guard_configuration_lifecycle("dataset replacement")
        ):
            self._pending_dataset_decision = None
            self.datasetDecisionChanged.emit()
            return False
        self._pending_dataset_decision = None
        operation, value = decision
        if operation == "mode":
            changed = self.configuration_controller.apply_mode_change(value)
        else:
            changed = self.configuration_controller.apply_coordinate_change(value)
        self.datasetDecisionChanged.emit()
        return changed

    @Slot(name="cancelDatasetDecision")
    def cancel_dataset_decision(self) -> None:
        self._pending_dataset_decision = None
        self.datasetDecisionChanged.emit()

    @Slot(str, name="requestDatasetModelChange")
    def request_dataset_model_change(self, model: str) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.set_model_name(model)

    @Slot(str, bool, name="requestDatasetFluidSelection")
    def request_dataset_fluid_selection(self, value: str, selected: bool) -> None:
        if not self._can_edit_dataset_document():
            return
        if selected:
            self.dataset_draft.add_fluid(value)
        else:
            self.dataset_draft.remove_fluid_value(value)

    @Slot(int, int, name="requestDatasetFluidMove")
    def request_dataset_fluid_move(self, row: int, offset: int) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.move_fluid(row, offset)

    @Slot(int, name="requestDatasetFluidRemove")
    def request_dataset_fluid_remove(self, row: int) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.remove_fluid(row)

    @Slot(str, bool, name="requestDatasetPropertySelection")
    def request_dataset_property_selection(self, value: str, selected: bool) -> None:
        if not self._can_edit_dataset_document():
            return
        if selected:
            self.dataset_draft.add_property(value)
        else:
            self.dataset_draft.remove_property_value(value)

    @Slot(int, int, name="requestDatasetPropertyMove")
    def request_dataset_property_move(self, row: int, offset: int) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.move_property(row, offset)

    @Slot(int, name="requestDatasetPropertyRemove")
    def request_dataset_property_remove(self, row: int) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.remove_property(row)

    @Slot(str, bool, name="requestDatasetOutputSelection")
    def request_dataset_output_selection(self, output_format: str, selected: bool) -> None:
        if self._can_edit_dataset_document():
            self.dataset_draft.set_output_selected(output_format, selected)

    @Slot(QObject, str, name="requestDatasetSamplerKindChange")
    def request_dataset_sampler_kind_change(self, candidate: QObject, kind: str) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None and self._can_edit_dataset_document():
            sampler.set_kind(kind)

    @Slot(QObject, str, str, name="requestDatasetSamplerTextChange")
    def request_dataset_sampler_text_change(
        self,
        candidate: QObject,
        field: str,
        text: str,
    ) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None and self._can_edit_dataset_document():
            sampler.set_text(field, text)

    @Slot(QObject, str, name="requestDatasetSamplerUnitChange")
    def request_dataset_sampler_unit_change(self, candidate: QObject, unit: str) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None and self._can_edit_dataset_document():
            sampler.requestUnitChange(unit)

    @Slot(str, bool, name="requestSweepModelSelection")
    def request_sweep_model_selection(self, model: str, selected: bool) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.set_model_selected(model, selected)

    @Slot(str, name="requestSweepReferenceModel")
    def request_sweep_reference_model(self, model: str) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.set_reference_model(model)

    @Slot(str, bool, name="requestSweepModeChange")
    def request_sweep_mode_change(self, mode: str, confirmed: bool) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.apply_mode_change(mode, confirmed)

    @Slot(str, bool, name="requestSweepCoordinateChange")
    def request_sweep_coordinate_change(self, axis: str, confirmed: bool) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.apply_coordinate_change(axis, confirmed)

    @Slot(str, bool, name="requestSweepFluidSelection")
    def request_sweep_fluid_selection(self, value: str, selected: bool) -> None:
        if not self._can_edit_sweep_document():
            return
        draft = self.configuration_controller.sweep_draft.dataset_draft
        if selected:
            draft.add_fluid(value)
        else:
            draft.remove_fluid_value(value)

    @Slot(int, int, name="requestSweepFluidMove")
    def request_sweep_fluid_move(self, row: int, offset: int) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.dataset_draft.move_fluid(row, offset)

    @Slot(int, name="requestSweepFluidRemove")
    def request_sweep_fluid_remove(self, row: int) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.dataset_draft.remove_fluid(row)

    @Slot(str, bool, name="requestSweepPropertySelection")
    def request_sweep_property_selection(self, value: str, selected: bool) -> None:
        if not self._can_edit_sweep_document():
            return
        draft = self.configuration_controller.sweep_draft.dataset_draft
        if selected:
            draft.add_property(value)
        else:
            draft.remove_property_value(value)

    @Slot(int, int, name="requestSweepPropertyMove")
    def request_sweep_property_move(self, row: int, offset: int) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.dataset_draft.move_property(row, offset)

    @Slot(int, name="requestSweepPropertyRemove")
    def request_sweep_property_remove(self, row: int) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.dataset_draft.remove_property(row)

    @Slot(str, bool, name="requestSweepOutputSelection")
    def request_sweep_output_selection(self, output_format: str, selected: bool) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.dataset_draft.set_output_selected(
                output_format,
                selected,
            )

    @Slot(QObject, str, name="requestSweepSamplerKindChange")
    def request_sweep_sampler_kind_change(self, candidate: QObject, kind: str) -> None:
        sampler = self._owned_sweep_sampler(candidate)
        if sampler is not None and self._can_edit_sweep_document():
            sampler.set_kind(kind)

    @Slot(QObject, str, str, name="requestSweepSamplerTextChange")
    def request_sweep_sampler_text_change(
        self,
        candidate: QObject,
        field: str,
        text: str,
    ) -> None:
        sampler = self._owned_sweep_sampler(candidate)
        if sampler is not None and self._can_edit_sweep_document():
            sampler.set_text(field, text)

    @Slot(QObject, str, name="requestSweepSamplerUnitChange")
    def request_sweep_sampler_unit_change(self, candidate: QObject, unit: str) -> None:
        sampler = self._owned_sweep_sampler(candidate)
        if sampler is not None and self._can_edit_sweep_document():
            sampler.requestUnitChange(unit)

    @Slot(str, name="requestSweepComparisonFormat")
    def request_sweep_comparison_format(self, output_format: str) -> None:
        if self._can_edit_sweep_document():
            self.configuration_controller.sweep_draft.set_comparison_format(output_format)

    @Slot(result=bool, name="requestSweepAddComparison")
    def request_sweep_add_comparison(self) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.begin_add_comparison()
        )

    @Slot(int, result=bool, name="requestSweepEditComparison")
    def request_sweep_edit_comparison(self, row: int) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.begin_edit_comparison(row)
        )

    @Slot(result=bool, name="requestSweepCommitComparison")
    def request_sweep_commit_comparison(self) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.commit_comparison()
        )

    @Slot(result=bool, name="requestSweepCancelComparison")
    def request_sweep_cancel_comparison(self) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.cancel_comparison()
        )

    @Slot(int, result=bool, name="requestSweepRemoveComparison")
    def request_sweep_remove_comparison(self, row: int) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.remove_comparison(row)
        )

    @Slot(int, int, result=bool, name="requestSweepMoveComparison")
    def request_sweep_move_comparison(self, source: int, destination: int) -> bool:
        return self._can_edit_sweep_document() and (
            self.configuration_controller.sweep_draft.move_comparison(source, destination)
        )

    @Slot(QObject, str, str, name="requestSweepComparisonFieldChange")
    def request_sweep_comparison_field_change(
        self,
        candidate: QObject,
        field: str,
        value: str,
    ) -> None:
        draft = self._owned_sweep_comparison(candidate)
        if draft is None or not self._can_edit_sweep_document():
            return
        setters = {
            "name": draft.set_name,
            "kind": draft.set_kind,
            "fluid": draft.set_fluid,
            "property": draft.set_property_name,
            "x": draft.set_x_field,
            "group_by": draft.set_group_by,
            "delta_metric": draft.set_delta_metric,
            "value_scale": draft.set_value_scale,
            "format": draft.set_output_format,
        }
        setter = setters.get(field)
        if setter is not None:
            setter(value)

    @Slot(QObject, bool, name="requestSweepComparisonExplicitModels")
    def request_sweep_comparison_explicit_models(
        self,
        candidate: QObject,
        enabled: bool,
    ) -> None:
        draft = self._owned_sweep_comparison(candidate)
        if draft is not None and self._can_edit_sweep_document():
            draft.set_explicit_models(enabled)

    @Slot(QObject, str, bool, name="requestSweepComparisonModelSelection")
    def request_sweep_comparison_model_selection(
        self,
        candidate: QObject,
        model: str,
        selected: bool,
    ) -> None:
        draft = self._owned_sweep_comparison(candidate)
        if draft is not None and self._can_edit_sweep_document():
            draft.set_model_selected(model, selected)

    @Slot(QObject, name="requestSweepComparisonFilterAdd")
    def request_sweep_comparison_filter_add(self, candidate: QObject) -> None:
        mapping = self._owned_sweep_comparison_mapping(candidate)
        if mapping is not None and self._can_edit_sweep_document():
            mapping.add_row()

    @Slot(QObject, int, str, name="requestSweepComparisonFilterFieldChange")
    def request_sweep_comparison_filter_field_change(
        self,
        candidate: QObject,
        row: int,
        field: str,
    ) -> None:
        mapping = self._owned_sweep_comparison_mapping(candidate)
        if mapping is not None and self._can_edit_sweep_document():
            mapping.set_field(row, field)

    @Slot(QObject, int, str, name="requestSweepComparisonFilterValueChange")
    def request_sweep_comparison_filter_value_change(
        self,
        candidate: QObject,
        row: int,
        value: str,
    ) -> None:
        mapping = self._owned_sweep_comparison_mapping(candidate)
        if mapping is not None and self._can_edit_sweep_document():
            mapping.set_raw_value(row, value)

    @Slot(QObject, int, name="requestSweepComparisonFilterRemove")
    def request_sweep_comparison_filter_remove(self, candidate: QObject, row: int) -> None:
        mapping = self._owned_sweep_comparison_mapping(candidate)
        if mapping is not None and self._can_edit_sweep_document():
            mapping.remove_row(row)

    @Slot(str, str, bool, name="requestPreparationRoleSelection")
    def request_preparation_role_selection(
        self,
        role: str,
        value: str,
        selected: bool,
    ) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_role_selected(
                role,
                value,
                selected,
            )

    @Slot(str, bool, name="requestPreparationCategoricalSelection")
    def request_preparation_categorical_selection(self, field: str, selected: bool) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_categorical_selected(
                field,
                selected,
            )

    @Slot(str, str, bool, name="requestPreparationCategoryMode")
    def request_preparation_category_mode(
        self,
        field: str,
        mode: str,
        discard_confirmed: bool,
    ) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_category_mode(
                field,
                mode,
                discard_confirmed,
            )

    @Slot(str, str, name="requestPreparationExplicitCategories")
    def request_preparation_explicit_categories(self, field: str, values: str) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_explicit_categories(
                field,
                values,
            )

    @Slot(str, bool, name="requestPreparationBooleanField")
    def request_preparation_boolean_field(self, field: str, value: bool) -> None:
        if not self._can_edit_preparation_document():
            return
        draft = self.configuration_controller.preparation_draft
        setter = {
            "allow_partial_sweep": draft.set_allow_partial_sweep,
            "array_outputs": draft.set_array_outputs_enabled,
            "include_auxiliary": draft.set_include_auxiliary,
            "matrix_diagnostics": draft.set_matrix_enabled,
            "baseline_diagnostics": draft.set_baseline_enabled,
        }.get(field)
        if setter is not None:
            setter(value)

    @Slot(str, str, name="requestPreparationTextField")
    def request_preparation_text_field(self, field: str, value: str) -> None:
        if not self._can_edit_preparation_document():
            return
        draft = self.configuration_controller.preparation_draft
        setter = {
            "array_dtype": draft.set_array_dtype,
            "correlation_threshold": draft.set_correlation_threshold,
            "near_constant_relative_spread": draft.set_near_constant_spread,
            "baseline_random_seed": draft.set_baseline_seed,
            "ridge_alpha": draft.set_ridge_alpha,
            "histogram_max_iterations": draft.set_histogram_iterations,
        }.get(field)
        if setter is not None:
            setter(value)

    @Slot(str, bool, name="requestPreparationArrayFormatSelection")
    def request_preparation_array_format_selection(
        self,
        value: str,
        selected: bool,
    ) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_array_format_selected(
                value,
                selected,
            )

    @Slot(str, bool, name="requestPreparationBaselineModelSelection")
    def request_preparation_baseline_model_selection(
        self,
        value: str,
        selected: bool,
    ) -> None:
        if self._can_edit_preparation_document():
            self.configuration_controller.preparation_draft.set_baseline_model_selected(
                value,
                selected,
            )

    @Slot(result=bool, name="requestPreparationAddScenario")
    def request_preparation_add_scenario(self) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.begin_add_scenario()
        )

    @Slot(int, result=bool, name="requestPreparationEditScenario")
    def request_preparation_edit_scenario(self, row: int) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.begin_edit_scenario(row)
        )

    @Slot(result=bool, name="requestPreparationCommitScenario")
    def request_preparation_commit_scenario(self) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.commit_scenario()
        )

    @Slot(result=bool, name="requestPreparationCancelScenario")
    def request_preparation_cancel_scenario(self) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.cancel_scenario()
        )

    @Slot(int, result=bool, name="requestPreparationRemoveScenario")
    def request_preparation_remove_scenario(self, row: int) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.remove_scenario(row)
        )

    @Slot(int, int, result=bool, name="requestPreparationMoveScenario")
    def request_preparation_move_scenario(self, source: int, destination: int) -> bool:
        return self._can_edit_preparation_document() and (
            self.configuration_controller.preparation_draft.move_scenario(source, destination)
        )

    @Slot(QObject, str, str, name="requestPreparationScenarioFieldChange")
    def request_preparation_scenario_field_change(
        self,
        candidate: QObject,
        field: str,
        value: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is None or not self._can_edit_preparation_document():
            return
        setter = {
            "name": draft.set_name,
            "seed": draft.set_seed_text,
            "field": draft.set_field,
            "remainder": draft.set_remainder,
        }.get(field)
        if setter is not None:
            setter(value)

    @Slot(QObject, str, bool, name="requestPreparationScenarioKindChange")
    def request_preparation_scenario_kind_change(
        self,
        candidate: QObject,
        kind: str,
        confirmed: bool,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.apply_kind_change(kind, confirmed)

    @Slot(QObject, str, str, name="requestPreparationScenarioPartition")
    def request_preparation_scenario_partition(
        self,
        candidate: QObject,
        partition: str,
        ratio: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_partition(partition, ratio)

    @Slot(QObject, str, name="requestPreparationScenarioRemovePartition")
    def request_preparation_scenario_remove_partition(
        self,
        candidate: QObject,
        partition: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.remove_partition(partition)

    @Slot(QObject, str, str, name="requestPreparationScenarioCategoricalHoldout")
    def request_preparation_scenario_categorical_holdout(
        self,
        candidate: QObject,
        partition: str,
        values: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_categorical_holdout(partition, values)

    @Slot(QObject, str, str, str, name="requestPreparationScenarioRangeHoldout")
    def request_preparation_scenario_range_holdout(
        self,
        candidate: QObject,
        partition: str,
        minimum: str,
        maximum: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_range_holdout(partition, minimum, maximum)

    @Slot(QObject, str, str, str, str, name="requestPreparationScenarioCoordinateHoldout")
    def request_preparation_scenario_coordinate_holdout(
        self,
        candidate: QObject,
        partition: str,
        field: str,
        minimum: str,
        maximum: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_coordinate_holdout(partition, field, minimum, maximum)

    @Slot(QObject, str, name="requestPreparationScenarioRemoveHoldout")
    def request_preparation_scenario_remove_holdout(
        self,
        candidate: QObject,
        partition: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.remove_holdout(partition)

    @Slot(QObject, str, name="requestPreparationScenarioStrata")
    def request_preparation_scenario_strata(
        self,
        candidate: QObject,
        fields: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_strata_categorical(fields)

    @Slot(QObject, str, str, name="requestPreparationScenarioNumericBins")
    def request_preparation_scenario_numeric_bins(
        self,
        candidate: QObject,
        field: str,
        boundaries: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.set_numeric_bins(field, boundaries)

    @Slot(QObject, str, name="requestPreparationScenarioRemoveNumericBins")
    def request_preparation_scenario_remove_numeric_bins(
        self,
        candidate: QObject,
        field: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.remove_numeric_bins(field)

    @Slot(QObject, str, str, name="requestPreparationScenarioTransformationAdd")
    def request_preparation_scenario_transformation_add(
        self,
        candidate: QObject,
        field: str,
        methods: str,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.add_transformation(field, methods)

    @Slot(QObject, int, name="requestPreparationScenarioTransformationRemove")
    def request_preparation_scenario_transformation_remove(
        self,
        candidate: QObject,
        row: int,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.remove_transformation(row)

    @Slot(QObject, int, int, name="requestPreparationScenarioTransformationMove")
    def request_preparation_scenario_transformation_move(
        self,
        candidate: QObject,
        source: int,
        destination: int,
    ) -> None:
        draft = self._owned_preparation_scenario(candidate)
        if draft is not None and self._can_edit_preparation_document():
            draft.move_transformation(source, destination)

    @Slot(bool, name="requestVisualizationEnabled")
    def request_visualization_enabled(self, enabled: bool) -> None:
        if self._can_edit_dataset_document() and self._guard_active_plot_edit(
            "visualization enable or disable"
        ):
            self.visualization_draft.set_enabled(enabled)

    @Slot(str, name="requestVisualizationFormat")
    def request_visualization_format(self, output_format: str) -> None:
        if self._can_edit_dataset_document() and self._guard_active_plot_edit(
            "shared visualization format change"
        ):
            self.visualization_draft.set_format(output_format)

    @Slot(str, bool, name="requestVisualizationFluidSelection")
    def request_visualization_fluid_selection(self, value: str, selected: bool) -> None:
        if self._can_edit_dataset_document() and self._guard_active_plot_edit(
            "shared visualization fluid change"
        ):
            self.visualization_draft.set_fluid_selected(value, selected)

    @Slot(result=bool, name="requestVisualizationAddPlot")
    def request_visualization_add_plot(self) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_active_plot_edit(
            "starting another plot edit"
        ):
            return False
        return self.visualization_draft.begin_add_plot() is not None

    @Slot(int, result=bool, name="requestVisualizationEditPlot")
    def request_visualization_edit_plot(self, row: int) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_active_plot_edit(
            "starting another plot edit"
        ):
            return False
        return self.visualization_draft.begin_edit_plot(row) is not None

    @Slot(int, result=bool, name="requestConfiguredPlotSessionEdit")
    def request_configured_plot_session_edit(self, row: int) -> bool:
        payload = self.visualization_draft.resolved_plot_payload(row)
        if payload is None:
            return False
        started = self.session_plot_controller.begin_edit_from_request(payload)
        if started:
            self.navigationRequested.emit("visualization", "explore")
        return started

    @Slot(result=bool, name="requestVisualizationCommitPlot")
    def request_visualization_commit_plot(self) -> bool:
        return self._can_edit_dataset_document() and self.visualization_draft.commit_plot()

    @Slot(result=bool, name="requestVisualizationCancelPlot")
    def request_visualization_cancel_plot(self) -> bool:
        return self._can_edit_dataset_document() and self.visualization_draft.cancel_plot()

    @Slot(int, result=bool, name="requestVisualizationRemovePlot")
    def request_visualization_remove_plot(self, row: int) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_active_plot_edit(
            "plot removal"
        ):
            return False
        return self.visualization_draft.remove_plot(row)

    @Slot(int, int, result=bool, name="requestVisualizationMovePlot")
    def request_visualization_move_plot(self, row: int, offset: int) -> bool:
        if not self._can_edit_dataset_document() or not self._guard_active_plot_edit(
            "plot movement"
        ):
            return False
        return self.visualization_draft.move_plot(row, offset)

    @Slot(str, result=bool, name="requestConfiguredPlotGeneration")
    def request_configured_plot_generation(self, request_id: str) -> bool:
        return self.configured_plot_results_controller.select_generation(request_id)

    @Slot(int, result=bool, name="requestConfiguredPlotOutcome")
    def request_configured_plot_outcome(self, index: int) -> bool:
        return self.configured_plot_results_controller.select_outcome(index)

    @Slot(str, result=bool, name="requestConfiguredPlotExport")
    def request_configured_plot_export(self, destination: str) -> bool:
        return self.configured_plot_results_controller.export_selected(_local_path(destination))

    @Slot(result=bool, name="requestConfiguredPlotOpenPdf")
    def request_configured_plot_open_pdf(self) -> bool:
        return self.configured_plot_results_controller.open_selected_pdf()

    @Slot(str, result=bool, name="requestSessionPlotBeginEdit")
    def request_session_plot_begin_edit(self, output_format: str) -> bool:
        return self.session_plot_controller.begin_edit(output_format)

    @Slot(result=bool, name="requestSessionPlotCancelEdit")
    def request_session_plot_cancel_edit(self) -> bool:
        return self.session_plot_controller.cancel_edit()

    @Slot(result=bool, name="requestSessionPlotRender")
    def request_session_plot_render(self) -> bool:
        return self.session_plot_controller.render()

    @Slot(result=bool, name="requestSessionPlotForceStop")
    def request_session_plot_force_stop(self) -> bool:
        return self.session_plot_controller.force_stop()

    @Slot(str, result=bool, name="requestSessionPlotExport")
    def request_session_plot_export(self, destination: str) -> bool:
        return self.session_plot_controller.export_result(_local_path(destination))

    @Slot(result=bool, name="requestSessionPlotOpenPdf")
    def request_session_plot_open_pdf(self) -> bool:
        return self.session_plot_controller.open_result_pdf()

    @Slot(QObject, str, str, name="requestPlotFieldChange")
    def request_plot_field_change(self, candidate: QObject, field: str, value: str) -> None:
        draft = self._owned_active_plot(candidate)
        if draft is None:
            return
        setters = {
            "name": draft.set_name,
            "kind": draft.set_kind,
            "property": draft.set_property_name,
            "x": draft.set_x_field,
            "y": draft.set_y_field,
            "group_by": draft.set_group_by,
            "value_scale": draft.set_value_scale,
            "color_scale": draft.set_color_scale,
            "x_scale": draft.set_x_scale,
            "y_scale": draft.set_y_scale,
            "format": draft.set_output_format,
        }
        setter = setters.get(field)
        if setter is not None:
            setter(value)

    @Slot(QObject, str, bool, name="requestPlotFluidSelection")
    def request_plot_fluid_selection(
        self,
        candidate: QObject,
        value: str,
        selected: bool,
    ) -> None:
        draft = self._owned_active_plot(candidate)
        if draft is not None:
            draft.set_fluid_selected(value, selected)

    @Slot(QObject, name="requestVisualizationMappingAdd")
    def request_visualization_mapping_add(self, candidate: QObject) -> None:
        mapping = self._owned_visualization_mapping(candidate)
        if mapping is not None:
            mapping.add_row()

    @Slot(QObject, int, str, name="requestVisualizationMappingFieldChange")
    def request_visualization_mapping_field_change(
        self,
        candidate: QObject,
        row: int,
        field: str,
    ) -> None:
        mapping = self._owned_visualization_mapping(candidate)
        if mapping is not None:
            mapping.set_field(row, field)

    @Slot(QObject, int, str, name="requestVisualizationMappingValueChange")
    def request_visualization_mapping_value_change(
        self,
        candidate: QObject,
        row: int,
        value: str,
    ) -> None:
        mapping = self._owned_visualization_mapping(candidate)
        if mapping is not None:
            mapping.set_raw_value(row, value)

    @Slot(QObject, int, name="requestVisualizationMappingRemove")
    def request_visualization_mapping_remove(self, candidate: QObject, row: int) -> None:
        mapping = self._owned_visualization_mapping(candidate)
        if mapping is not None:
            mapping.remove_row(row)

    def _owned_dataset_sampler(self, candidate: QObject) -> SamplerDraft | None:
        return next(
            (sampler for sampler in self.dataset_draft.samplers.drafts if sampler is candidate),
            None,
        )

    def _can_edit_dataset_document(self) -> bool:
        return self._can_edit_document("dataset", "Dataset")

    def _can_edit_sweep_document(self) -> bool:
        return self._can_edit_document("model_sweep", "Model Sweep")

    def _can_edit_preparation_document(self) -> bool:
        return self._can_edit_document("preparation", "ML Preparation")

    def _can_edit_document(self, document_kind: str, label: str) -> bool:
        if self.configuration_controller.get_document_kind() != document_kind:
            return False
        if self.configuration_controller.get_can_edit():
            return True
        self.workspace_controller.report_error(
            f"Wait for the active worker request before editing the {label} configuration."
        )
        return False

    def _owned_sweep_sampler(self, candidate: QObject) -> SamplerDraft | None:
        samplers = self.configuration_controller.sweep_draft.dataset_draft.samplers.drafts
        return next((sampler for sampler in samplers if sampler is candidate), None)

    def _owned_sweep_comparison(
        self,
        candidate: QObject,
    ) -> ComparisonPlotDraft | None:
        active = self.configuration_controller.sweep_draft.get_active_comparison_draft()
        return active if isinstance(active, ComparisonPlotDraft) and active is candidate else None

    def _owned_sweep_comparison_mapping(
        self,
        candidate: QObject,
    ) -> MappingDraftModel | None:
        active = self.configuration_controller.sweep_draft.get_active_comparison_draft()
        if not isinstance(active, ComparisonPlotDraft):
            return None
        if candidate is not active.filters:
            return None
        return candidate if isinstance(candidate, MappingDraftModel) else None

    def _owned_preparation_scenario(self, candidate: QObject) -> ScenarioDraft | None:
        active = self.configuration_controller.preparation_draft.get_active_scenario_draft()
        return active if isinstance(active, ScenarioDraft) and active is candidate else None

    def _owned_active_plot(self, candidate: QObject) -> PlotDraft | None:
        configured = self.visualization_draft.get_active_plot_draft()
        if isinstance(configured, PlotDraft) and configured is candidate:
            return configured if self._can_edit_dataset_document() else None
        session = self.session_plot_controller.get_active_plot_draft()
        if not isinstance(session, PlotDraft) or session is not candidate:
            return None
        if not self.session_plot_controller.get_is_rendering():
            return session
        self.workspace_controller.report_error(
            "Wait for the active plot worker before editing the session plot."
        )
        return None

    def _owned_visualization_mapping(
        self,
        candidate: QObject,
    ) -> MappingDraftModel | None:
        shared = (
            self.visualization_draft.filters,
            self.visualization_draft.display_units,
        )
        if candidate in shared:
            if not self._can_edit_dataset_document():
                return None
            if not self._guard_active_plot_edit("shared visualization mapping change"):
                return None
            return candidate if isinstance(candidate, MappingDraftModel) else None
        for active in (
            self.visualization_draft.get_active_plot_draft(),
            self.session_plot_controller.get_active_plot_draft(),
        ):
            if not isinstance(active, PlotDraft):
                continue
            mappings = (active.filters, active.series, active.display_units)
            if not isinstance(candidate, MappingDraftModel) or candidate not in mappings:
                continue
            return candidate if self._owned_active_plot(active) is active else None
        return None

    @Slot(str, str, result=bool, name="prepareCreateWorkspace")
    def prepare_create_workspace(self, parent_path: str, child_name: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        parent = _local_path(parent_path)
        name = child_name.strip()
        if not parent:
            self.workspace_controller.report_error("Choose a parent folder first.")
            return False
        if not _valid_workspace_child_name(name):
            self.workspace_controller.report_error(
                "Enter one new folder name without path separators."
            )
            return False
        return self.workspace_controller.prepare_create(Path(parent) / name)

    @Slot(str, result=bool, name="prepareCreateWorkspacePath")
    def prepare_create_workspace_path(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_create(_local_path(path))

    @Slot(str, result=bool, name="prepareInitializeWorkspace")
    def prepare_initialize_workspace(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_initialize_existing(_local_path(path))

    @Slot(str, result=bool, name="prepareOpenWorkspace")
    def prepare_open_workspace(self, path: str) -> bool:
        if not self._guard_workspace_change(before_commit=False):
            return False
        return self.workspace_controller.prepare_open(_local_path(path))

    @Slot(bool, result=bool, name="commitWorkspaceOperation")
    def commit_workspace_operation(self, confirmed: bool = False) -> bool:
        if not self._guard_workspace_change(before_commit=True):
            return False
        if self.get_workspace_confirmation_required() and not confirmed:
            self.workspace_controller.report_error(
                "Confirm the pending workspace operation before continuing."
            )
            return False
        return self.workspace_controller.commit_pending()

    @Slot(name="cancelWorkspaceOperation")
    def cancel_workspace_operation(self) -> None:
        self.workspace_controller.cancel_pending()

    @Slot(str, str, name="requestCreateWorkspace")
    def request_create_workspace(self, parent_path: str, child_name: str) -> None:
        self._queue_workspace_request("create", parent_path, child_name)

    @Slot(str, name="requestCreateWorkspacePath")
    def request_create_workspace_path(self, path: str) -> None:
        self._queue_workspace_request("create_path", path)

    @Slot(str, name="requestInitializeWorkspace")
    def request_initialize_workspace(self, path: str) -> None:
        self._queue_workspace_request("initialize", path)

    @Slot(str, name="requestOpenWorkspace")
    def request_open_workspace(self, path: str) -> None:
        self._queue_workspace_request("open", path)

    @Slot(bool, name="requestCommitWorkspaceOperation")
    def request_commit_workspace_operation(self, confirmed: bool = False) -> None:
        self._queue_workspace_request("commit", "", confirmed=confirmed)

    @Slot(name="requestCancelWorkspaceOperation")
    def request_cancel_workspace_operation(self) -> None:
        self._queue_workspace_request("cancel", "")

    def shutdown(self) -> bool:
        if self._shutdown:
            return True
        if not self._guard_configuration_lifecycle("closing Carnopy"):
            return False
        if not self._guard_session_plot_edit("closing Carnopy"):
            return False
        self.workspace_controller.cancel_pending()
        if self.request_coordinator.is_busy:
            return False
        self._workspace_request_timer.stop()
        self._queued_workspace_request = None
        self.scene_lifecycle.shutdown()
        self.request_coordinator.shutdown()
        self.settings.sync()
        self._shutdown = True
        return True

    @Slot(result=bool, name="requestShutdown")
    def request_shutdown(self) -> bool:
        if self._shutdown:
            return True
        active_session = self.request_coordinator.active_session
        if active_session is not None:
            if (
                self._pending_busy_shutdown
                and active_session is self._pending_busy_shutdown_session
            ):
                self.workspace_controller.report_error(
                    "Carnopy will close after the active worker request finishes safely."
                )
                return False
            self._clear_pending_shutdown_decisions()
            if bool(getattr(active_session, "termination_protected", False)):
                self._pending_busy_shutdown = "protected_finalization"
                self._pending_busy_shutdown_session = active_session
                self.workspace_controller.report_error(
                    "Finalizing safely. Carnopy will close after the worker finishes and "
                    "the remaining close checks pass."
                )
                return False
            self._pending_busy_confirmation_session = active_session
            if (
                active_session.owner == "execution"
                and active_session.request_type == "generate_dataset"
            ):
                self.busyShutdownConfirmationRequested.emit(
                    "cancel_generation",
                    "Dataset generation is active. Cancel it cooperatively and close "
                    "Carnopy after the worker and activity record finish safely?",
                )
            elif active_session.owner == "sweep" and active_session.request_type == "execute_sweep":
                self.busyShutdownConfirmationRequested.emit(
                    "cancel_sweep",
                    "Model Sweep execution is active. Cancel it cooperatively and close "
                    "Carnopy after the worker and activity record finish safely?",
                )
            elif (
                active_session.owner == "preparation"
                and active_session.request_type == "execute_preparation"
            ):
                self.busyShutdownConfirmationRequested.emit(
                    "cancel_preparation",
                    "ML Preparation execution is active. Cancel it cooperatively and close "
                    "Carnopy after the worker and activity record finish safely?",
                )
            elif (
                active_session.owner == "plot"
                and active_session.request_type == "render_plot"
                and self.session_plot_controller.get_can_force_stop()
            ):
                self.busyShutdownConfirmationRequested.emit(
                    "force_stop_plot",
                    "A session plot render is active. Force-stop it and close Carnopy only "
                    "after its owned staging cleanup succeeds?",
                )
            elif active_session.owner == "scene" and active_session.request_type in {
                "profile_scene",
                "build_scene",
            }:
                self.busyShutdownConfirmationRequested.emit(
                    "cancel_scene",
                    "Scene preparation is active. Cancel it cooperatively and, only if "
                    "needed after the safety delay, force-stop it before closing Carnopy?",
                )
            else:
                self._pending_busy_confirmation_session = None
                self.workspace_controller.report_error(
                    "Wait for the active worker request to finish before closing Carnopy."
                )
            return False
        if self.request_coordinator.is_busy:
            self._pending_busy_confirmation_session = None
            self.workspace_controller.report_error(
                "Wait for the active worker request to finish before closing Carnopy."
            )
            return False
        if self.get_has_any_transient_edit():
            self._pending_busy_confirmation_session = None
            self._approved_discard_shutdown_context = None
            self._pending_discard_shutdown_context = None
            self._pending_transient_shutdown_context = self._transient_shutdown_context()
            edit_names = []
            if self.get_has_active_plot_edit():
                edit_names.append("configured plot")
            if self.get_has_session_plot_edit():
                edit_names.append("session plot")
            if self.get_has_active_sweep_edit():
                edit_names.append("Sweep comparison")
            if self.get_has_active_preparation_edit():
                edit_names.append("Preparation scenario")
            description = " and ".join(edit_names)
            self.transientEditShutdownConfirmationRequested.emit(
                f"A {description} edit is still open. Cancel the edit and close Carnopy?"
            )
            return False
        self._pending_transient_shutdown_context = None
        if self.configuration_controller.needs_discard_confirmation():
            context = self._discard_shutdown_context()
            if not self._same_discard_shutdown_context(
                self._approved_discard_shutdown_context,
                context,
            ):
                self._approved_discard_shutdown_context = None
                self._pending_discard_shutdown_context = context
                self.shutdownConfirmationRequested.emit()
                return False
        self._pending_discard_shutdown_context = None
        self._approved_discard_shutdown_context = None
        return self.shutdown()

    @Slot(bool, result=bool, name="confirmBusyShutdown")
    def confirm_busy_shutdown(self, confirmed: bool) -> bool:
        if not confirmed:
            self._clear_pending_busy_shutdown()
            return False
        session = self.request_coordinator.active_session
        if session is None or session is not self._pending_busy_confirmation_session:
            self._clear_pending_busy_shutdown()
            self.workspace_controller.report_error(
                "The active worker request changed. Close Carnopy again to review it."
            )
            return False
        self._pending_busy_confirmation_session = None
        self._pending_busy_shutdown_session = session
        if session.owner == "execution" and session.request_type == "generate_dataset":
            self._pending_busy_shutdown = "generation_waiting"
            self._continue_pending_busy_shutdown()
            return True
        if session.owner == "sweep" and session.request_type == "execute_sweep":
            self._pending_busy_shutdown = "sweep_waiting"
            self._continue_pending_busy_shutdown()
            return True
        if session.owner == "preparation" and session.request_type == "execute_preparation":
            self._pending_busy_shutdown = "preparation_waiting"
            self._continue_pending_busy_shutdown()
            return True
        if session.owner == "plot" and session.request_type == "render_plot":
            if not self.session_plot_controller.force_stop():
                self._clear_pending_busy_shutdown()
                self.workspace_controller.report_error(
                    "The plot worker cannot be force-stopped safely yet."
                )
                return False
            self._pending_busy_shutdown = "plot"
            return True
        if session.owner == "scene" and session.request_type in {
            "profile_scene",
            "build_scene",
        }:
            self._pending_busy_shutdown = "scene_waiting"
            self._continue_pending_busy_shutdown()
            return True
        self._clear_pending_busy_shutdown()
        return False

    @Slot(bool, result=bool, name="confirmTransientEditShutdown")
    def confirm_transient_edit_shutdown(self, discard_confirmed: bool) -> bool:
        if not discard_confirmed:
            self._pending_transient_shutdown_context = None
            return False
        if self.request_coordinator.is_busy:
            self._pending_transient_shutdown_context = None
            self.workspace_controller.report_error(
                "Wait for the active worker request to finish before closing Carnopy."
            )
            return False
        context = self._pending_transient_shutdown_context
        if not self._same_transient_shutdown_context(
            context,
            self._transient_shutdown_context(),
        ):
            self._pending_transient_shutdown_context = None
            self.workspace_controller.report_error(
                "The unfinished edits changed. Close Carnopy again to review them."
            )
            return False
        self._pending_transient_shutdown_context = None
        if self.get_has_active_plot_edit() and not self.visualization_draft.cancel_plot():
            return False
        if self.get_has_session_plot_edit() and not self.session_plot_controller.cancel_edit():
            return False
        if (
            self.get_has_active_sweep_edit()
            and not self.configuration_controller.sweep_draft.cancel_comparison()
        ):
            return False
        if (
            self.get_has_active_preparation_edit()
            and not self.configuration_controller.preparation_draft.cancel_scenario()
        ):
            return False
        self._continue_guarded_shutdown()
        return True

    @Slot(bool, result=bool, name="confirmShutdown")
    def confirm_shutdown(self, discard_confirmed: bool) -> bool:
        if not discard_confirmed:
            self._pending_discard_shutdown_context = None
            self._approved_discard_shutdown_context = None
            return False
        context = self._pending_discard_shutdown_context
        if not self._same_discard_shutdown_context(context, self._discard_shutdown_context()):
            self._pending_discard_shutdown_context = None
            self._approved_discard_shutdown_context = None
            self.workspace_controller.report_error(
                "The open configuration changed. Close Carnopy again to review it."
            )
            return False
        if not self._guard_configuration_lifecycle("closing Carnopy"):
            return False
        if not self._guard_session_plot_edit("closing Carnopy"):
            return False
        if self.request_coordinator.is_busy:
            self.workspace_controller.report_error(
                "Wait for the active worker request to finish before closing Carnopy."
            )
            return False
        self._pending_discard_shutdown_context = None
        self._approved_discard_shutdown_context = context
        return self._continue_guarded_shutdown()

    def _workspace_activated(self, value: object) -> None:
        self._clear_pending_explore()
        workspace = value if isinstance(value, Workspace) else None
        self.scene_lifecycle.set_workspace(workspace)
        self.configuration_controller.set_workspace(value)
        self.execution_controller.set_workspace(workspace)
        self.session_plot_controller.set_workspace(workspace)
        self.inspection_controller.set_workspace(workspace)
        self.sweep_workflow_controller.set_workspace(workspace)
        self.preparation_workflow_controller.set_workspace(workspace)
        self.activity_controller.set_workspace(workspace)
        self.configured_plot_results_controller.set_workspace(workspace)
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _configuration_state_changed(self) -> None:
        self._configuration_state_revision += 1
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _preparation_source_binding_changed(self) -> None:
        snapshot = self.preparation_workflow_controller.bound_source_snapshot()
        profile = None if snapshot is None else snapshot[3]
        self.configuration_controller.preparation_draft.apply_source_profile(profile)

    def _request_state_changed(self, busy: bool) -> None:
        self.workspace_state_changed.emit()
        if not busy:
            self._pending_busy_confirmation_session = None
        if not busy and self._pending_busy_shutdown:
            QTimer.singleShot(0, self._complete_busy_shutdown)

    def _scene_lifecycle_changed(self) -> None:
        issue = self.scene_lifecycle.get_cleanup_issue()
        if issue:
            self.workspace_controller.report_error(issue)
        self.workspace_feedback_changed.emit()

    def _continue_pending_busy_shutdown(self) -> None:
        mode = self._pending_busy_shutdown
        if mode not in {
            "generation_waiting",
            "sweep_waiting",
            "preparation_waiting",
            "scene_waiting",
            "scene_cancelling",
        }:
            return
        session = self.request_coordinator.active_session
        if session is None:
            return
        if session is not self._pending_busy_shutdown_session:
            self._clear_pending_busy_shutdown()
            self.workspace_controller.report_error(
                "Another worker request started. Close Carnopy again to review it."
            )
            return
        if mode == "generation_waiting":
            if (
                session.owner != "execution"
                or session.request_type != "generate_dataset"
                or not self.execution_controller.get_can_cancel()
            ):
                return
            self._pending_busy_shutdown = "generation"
            if not self.execution_controller.cancel():
                self._pending_busy_shutdown = mode
            return
        if mode == "sweep_waiting":
            if (
                session.owner != "sweep"
                or session.request_type != "execute_sweep"
                or not self.sweep_workflow_controller.get_cancellation_available()
            ):
                return
            self._pending_busy_shutdown = "sweep"
            if not self.sweep_workflow_controller.cancel():
                self._pending_busy_shutdown = mode
            return
        if mode == "scene_waiting":
            if self.scene_controller.get_protected_finalization():
                self._pending_busy_shutdown = "protected_finalization"
                return
            if not self.scene_controller.get_cancellation_available():
                return
            self._pending_busy_shutdown = "scene_cancelling"
            if not self.scene_controller.cancel():
                self._pending_busy_shutdown = mode
            return
        if mode == "scene_cancelling":
            if self.scene_controller.get_protected_finalization():
                return
            if not self.scene_controller.get_force_stop_available():
                return
            self._pending_busy_shutdown = "scene"
            if not self.scene_controller.force_stop():
                self._pending_busy_shutdown = mode
            return
        if (
            session.owner != "preparation"
            or session.request_type != "execute_preparation"
            or not self.preparation_workflow_controller.get_cancellation_available()
        ):
            return
        self._pending_busy_shutdown = "preparation"
        if not self.preparation_workflow_controller.cancel():
            self._pending_busy_shutdown = mode

    def _complete_busy_shutdown(self) -> None:
        mode = self._pending_busy_shutdown
        if not mode:
            return
        active_session = self.request_coordinator.active_session
        if active_session is self._pending_busy_shutdown_session:
            return
        if self.request_coordinator.is_busy:
            self._clear_pending_busy_shutdown()
            self.workspace_controller.report_error(
                "Another worker request started. Close Carnopy again to review it."
            )
            return
        self._clear_pending_busy_shutdown()
        if mode == "plot":
            cleanup_issue = self.session_plot_controller.get_cleanup_issue()
            if cleanup_issue:
                message = f"Plot staging cleanup failed; Carnopy remains open: {cleanup_issue}"
                self.workspace_controller.report_error(message)
                self.activityActionFailed.emit("Close Carnopy", message)
                return
            if (
                self.session_plot_controller.get_has_active_edit()
                and not self.session_plot_controller.cancel_edit()
            ):
                self.workspace_controller.report_error(
                    "The stopped session plot edit could not be cancelled safely."
                )
                return
        self._continue_guarded_shutdown()

    def _continue_guarded_shutdown(self) -> bool:
        if not self.request_shutdown():
            return False
        self.closeWindowRequested.emit()
        return True

    def _clear_pending_busy_shutdown(self) -> None:
        self._pending_busy_shutdown = ""
        self._pending_busy_confirmation_session = None
        self._pending_busy_shutdown_session = None

    def _clear_pending_shutdown_decisions(self) -> None:
        self._pending_transient_shutdown_context = None
        self._pending_discard_shutdown_context = None
        self._approved_discard_shutdown_context = None
        self._pending_busy_shutdown = ""
        self._pending_busy_shutdown_session = None
        self._pending_busy_confirmation_session = None

    def _transient_shutdown_context(
        self,
    ) -> tuple[tuple[bool, object | None], ...]:
        return (
            (
                self.get_has_active_plot_edit(),
                self.visualization_draft.get_active_plot_draft(),
            ),
            (
                self.get_has_session_plot_edit(),
                self.session_plot_controller.get_active_plot_draft(),
            ),
            (
                self.get_has_active_sweep_edit(),
                self.configuration_controller.sweep_draft.get_active_comparison_draft(),
            ),
            (
                self.get_has_active_preparation_edit(),
                self.configuration_controller.preparation_draft.get_active_scenario_draft(),
            ),
        )

    @staticmethod
    def _same_transient_shutdown_context(
        expected: tuple[tuple[bool, object | None], ...] | None,
        current: tuple[tuple[bool, object | None], ...],
    ) -> bool:
        if expected is None or len(expected) != len(current):
            return False
        return all(
            expected_active == current_active and expected_draft is current_draft
            for (expected_active, expected_draft), (current_active, current_draft) in zip(
                expected,
                current,
                strict=True,
            )
        )

    def _discard_shutdown_context(self) -> tuple[object | None, int]:
        return (
            self.configuration_controller.document,
            self._configuration_state_revision,
        )

    @staticmethod
    def _same_discard_shutdown_context(
        expected: tuple[object | None, int] | None,
        current: tuple[object | None, int],
    ) -> bool:
        return expected is not None and expected[0] is current[0] and expected[1] == current[1]

    def _active_plot_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _guard_workspace_change(self, *, before_commit: bool) -> bool:
        if self._guard_configuration_lifecycle(
            "replacing the workspace"
        ) and self._guard_session_plot_edit("replacing the workspace"):
            return True
        if before_commit:
            self.workspace_controller.cancel_pending()
        return False

    def _guard_idle_configuration_action(self, operation: str) -> bool:
        if not self._guard_configuration_lifecycle(operation):
            return False
        if not self.request_coordinator.is_busy:
            return True
        self.workspace_controller.report_error(
            f"Wait for the active worker request before {operation}."
        )
        return False

    def _guard_configuration_lifecycle(self, operation: str = "this operation") -> bool:
        if not self._guard_active_plot_edit(operation) or not self._guard_workflow_nested_edit(
            operation
        ):
            return False
        if operation != "New ML Preparation" or not self.configuration_controller.get_can_create():
            return True
        if self.preparation_workflow_controller.get_has_bound_source():
            return True
        message = (
            "Inspect an eligible Dataset or Model Sweep and choose "
            "Use for ML Preparation before creating a Preparation configuration."
        )
        self.activityActionFailed.emit("New ML Preparation", message)
        self.navigationRequested.emit("inspect", "preparation-source")
        return False

    def _guard_active_plot_edit(self, operation: str = "this operation") -> bool:
        if self.visualization_draft.get_active_plot_draft() is None:
            return True
        message = f"Commit or cancel the active plot edit before {operation}."
        self.visualization_draft.message.emit(message)
        self.workspace_controller.report_error(message)
        self.attentionRequested.emit(
            "visualization",
            VISUALIZATION_PLOTS,
            -1,
        )
        return False

    def _guard_workflow_nested_edit(self, operation: str = "this operation") -> bool:
        sweep = self.configuration_controller.sweep_draft
        if sweep.get_has_active_comparison_edit():
            message = f"Commit or cancel the active Sweep comparison edit before {operation}."
            sweep.message.emit(message)
            self.workspace_controller.report_error(message)
            self.attentionRequested.emit(
                "sweep",
                sweep.get_first_invalid_field(),
                sweep.get_first_invalid_row(),
            )
            return False
        preparation = self.configuration_controller.preparation_draft
        if preparation.get_has_active_scenario_edit():
            message = f"Commit or cancel the active Preparation scenario edit before {operation}."
            preparation.message.emit(message)
            self.workspace_controller.report_error(message)
            self.attentionRequested.emit(
                "preparation",
                preparation.get_first_invalid_field(),
                preparation.get_first_invalid_row(),
            )
            return False
        return True

    def _guard_session_plot_edit(self, operation: str = "this operation") -> bool:
        if self.session_plot_controller.can_replace_inspection(operation):
            return True
        self.workspace_controller.report_error(self.session_plot_controller.get_issue())
        return False

    def _plot_commit_rejected(self, field: str, row: int, _message: str) -> None:
        self.attentionRequested.emit("visualization", field, row)

    def _workflow_controller(
        self,
        workflow: str,
    ) -> SweepWorkflowController | PreparationWorkflowController | None:
        if workflow in {"sweep", "model_sweep"}:
            return self.sweep_workflow_controller
        if workflow == "preparation":
            return self.preparation_workflow_controller
        return None

    def _inspect_run(self, source: str, *, navigate: bool) -> bool:
        if not source:
            self.activityActionFailed.emit(
                "Inspect Run",
                "The selected generation record has no output directory.",
            )
            return False
        if not self.inspection_controller.inspect_source(source):
            self.activityActionFailed.emit(
                "Inspect Run",
                self.inspection_controller.get_issue()
                or "The selected run could not be submitted for inspection.",
            )
            return False
        if navigate:
            self.navigationRequested.emit("inspect", "")
        return True

    def _view_configured_generation(self, record_id: str) -> bool:
        if not record_id:
            self.activityActionFailed.emit(
                "View Plots",
                "The selected generation has no persisted request identity.",
            )
            return False
        if not self.configured_plot_results_controller.select_generation(record_id):
            self.activityActionFailed.emit(
                "View Plots",
                self.configured_plot_results_controller.get_issue()
                or "The selected plot evidence could not be opened.",
            )
            return False
        self.navigationRequested.emit("visualization", "configured")
        return True

    def _inspect_for_exploration(
        self,
        source: str,
        *,
        begin_edit: bool = False,
        action: str = "Explore this run",
    ) -> bool:
        if self._pending_explore_source is not None:
            self.activityActionFailed.emit(
                action,
                "Another dataset is already being prepared for plotting.",
            )
            return False
        if not source:
            self.activityActionFailed.emit(
                action,
                "The selected generation has no recorded output directory.",
            )
            return False
        resolved = Path(source).expanduser().resolve()
        self._pending_explore_source = resolved
        self._pending_explore_begin_edit = begin_edit
        self._pending_explore_action = action
        if self.inspection_controller.inspect_source(str(resolved)):
            return True
        self._clear_pending_explore()
        self.activityActionFailed.emit(
            action,
            self.inspection_controller.get_issue()
            or "The selected run could not be submitted for inspection.",
        )
        return False

    def _pending_explore_inspection_loaded(self, value: object) -> None:
        pending = self._pending_explore_source
        if pending is None or not isinstance(value, Path) or value.resolve() != pending:
            return
        QTimer.singleShot(0, self._complete_pending_explore)

    def _complete_pending_explore(self) -> None:
        pending = self._pending_explore_source
        if pending is None:
            return
        action = self._pending_explore_action
        begin_edit = self._pending_explore_begin_edit
        if self.request_coordinator.is_busy:
            self._clear_pending_explore()
            self.activityActionFailed.emit(
                action,
                "The inspected dataset could not be opened while another operation is active.",
            )
            return
        inspected_source = self.session_plot_controller.get_source_path()
        if not inspected_source or Path(inspected_source).resolve() != pending:
            self._clear_pending_explore()
            self.activityActionFailed.emit(
                action,
                "The completed inspection no longer matches the selected generated output.",
            )
            return
        if begin_edit and not self.session_plot_controller.begin_edit("png"):
            message = (
                self.session_plot_controller.get_issue()
                or "A compatible plot editor could not be opened for this dataset."
            )
            self._clear_pending_explore()
            self.activityActionFailed.emit(action, message)
            return
        self._clear_pending_explore()
        self.navigationRequested.emit("visualization", "explore")

    def _pending_explore_inspection_failed(self, value: object, message: str) -> None:
        pending = self._pending_explore_source
        if pending is None or not isinstance(value, Path) or value.resolve() != pending:
            return
        action = self._pending_explore_action
        self._clear_pending_explore()
        self.activityActionFailed.emit(action, message)

    def _clear_pending_explore(self) -> None:
        self._pending_explore_source = None
        self._pending_explore_begin_edit = False
        self._pending_explore_action = "Explore this run"

    def _queue_workspace_request(
        self,
        operation: str,
        path: str,
        detail: str = "",
        *,
        confirmed: bool = False,
    ) -> None:
        if self._queued_workspace_request is not None:
            return
        self._queued_workspace_request = (operation, path, detail, confirmed)
        self._workspace_request_timer.start()

    def _run_queued_workspace_request(self) -> None:
        request, self._queued_workspace_request = self._queued_workspace_request, None
        if request is None:
            return
        operation, path, detail, confirmed = request
        if operation == "cancel":
            self.cancel_workspace_operation()
            return
        if operation == "commit":
            self.commit_workspace_operation(confirmed)
            return
        if operation == "create":
            prepared = self.prepare_create_workspace(path, detail)
        elif operation == "create_path":
            prepared = self.prepare_create_workspace_path(path)
        elif operation == "initialize":
            prepared = self.prepare_initialize_workspace(path)
        else:
            prepared = self.prepare_open_workspace(path)
        if not prepared:
            return
        if self.get_workspace_confirmation_required():
            self.workspaceConfirmationRequested.emit()
            return
        self.commit_workspace_operation()


def _local_path(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("file:"):
        return candidate
    return QUrl(candidate).toLocalFile()


def _workflow_label(workflow: str) -> str:
    return "Model Sweep" if workflow in {"sweep", "model_sweep"} else "ML Preparation"


def _valid_workspace_child_name(value: str) -> bool:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        return False
    return not Path(value).is_absolute() and Path(value).name == value
