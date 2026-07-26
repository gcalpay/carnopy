from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot

from carnopy.app.activity_controller import ActivityController
from carnopy.app.client import WorkerClient
from carnopy.app.config_controller import DatasetConfigController
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.execution_controller import DatasetExecutionController
from carnopy.app.field_ids import VISUALIZATION_PLOTS
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.mapping_draft import MappingDraftModel
from carnopy.app.plot_draft import PlotDraft
from carnopy.app.qml_settings import QmlSettingsController
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.sampler_draft import SamplerDraft
from carnopy.app.visualization_draft import VisualizationDraft
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
    datasetDocumentOpened = Signal()
    attentionRequested = Signal(str, str, int)
    shutdownConfirmationRequested = Signal()
    closeWindowRequested = Signal()

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
        self.dataset_draft = DatasetDraft(self)
        self.visualization_draft = VisualizationDraft(self)
        self.dataset_config_controller = DatasetConfigController(
            self.request_coordinator,
            self.dataset_draft,
            self.visualization_draft,
            self,
        )
        self.execution_controller = DatasetExecutionController(
            self.request_coordinator,
            self.dataset_config_controller,
            self,
        )
        self.inspection_controller = InspectionController(
            self.request_coordinator,
            self,
        )
        self.activity_controller = ActivityController(
            self.request_coordinator,
            self,
        )
        self.execution_controller.activity_record_changed.connect(
            self.activity_controller.refresh_records
        )
        self.execution_controller.run_finalized.connect(
            lambda _path: self.inspection_controller.refresh_sources()
        )
        self.dataset_config_controller.set_lifecycle_guard(self._guard_active_plot_edit)
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
        self.dataset_config_controller.state_changed.connect(self._configuration_state_changed)
        self.dataset_config_controller.document_opened.connect(self.datasetDocumentOpened)
        self.request_coordinator.busy_changed.connect(self._request_state_changed)
        self.visualization_draft.active_plot_draft_changed.connect(self._active_plot_state_changed)
        self.visualization_draft.plot_commit_rejected.connect(self._plot_commit_rejected)
        self._queued_workspace_request: tuple[str, str, str, bool] | None = None
        self._pending_dataset_decision: tuple[str, str] | None = None
        self._workspace_request_timer = QTimer(self)
        self._workspace_request_timer.setSingleShot(True)
        self._workspace_request_timer.setInterval(0)
        self._workspace_request_timer.timeout.connect(self._run_queued_workspace_request)
        self._shutdown = False
        self._shutdown_discard_confirmed = False

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
        if self.dataset_config_controller.get_has_document():
            return "editing"
        if (
            not self.dataset_config_controller.get_editor_available()
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
        return self.dataset_config_controller.needs_discard_confirmation()

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
        dirty = self.dataset_config_controller.needs_discard_confirmation()
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

    def get_dataset_config_controller(self) -> QObject:
        return self.dataset_config_controller

    datasetConfigController = Property(
        QObject,
        get_dataset_config_controller,
        constant=True,
    )

    def get_execution_controller(self) -> QObject:
        return self.execution_controller

    executionController = Property(
        QObject,
        get_execution_controller,
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
        if not self._guard_active_plot_edit("New Dataset"):
            return False
        return self.dataset_config_controller.new_dataset(mode, discard_confirmed)

    @Slot(str, bool, result=bool, name="requestImportDataset")
    def request_import_dataset(self, path: str, discard_confirmed: bool = False) -> bool:
        if not self._guard_active_plot_edit("Import"):
            return False
        return self.dataset_config_controller.import_dataset(
            _local_path(path),
            discard_confirmed,
        )

    @Slot(bool, result=bool, name="requestSave")
    def request_save(self, allow_reformat: bool = False) -> bool:
        if not self._guard_active_plot_edit("Save"):
            return False
        return self.dataset_config_controller.request_save(allow_reformat)

    @Slot(bool, result=bool, name="requestSaveAs")
    def request_save_as(self, allow_reformat: bool = False) -> bool:
        if not self._guard_active_plot_edit("Save As"):
            return False
        return self.dataset_config_controller.request_save_as(allow_reformat)

    @Slot(result=bool, name="requestValidateConfiguration")
    def request_validate_configuration(self) -> bool:
        if not self._guard_active_plot_edit("Validation"):
            return False
        return self.dataset_config_controller.request_validation()

    @Slot(result=bool, name="requestExecutionValidation")
    def request_execution_validation(self) -> bool:
        return self.execution_controller.validate()

    @Slot(result=bool, name="requestDatasetGeneration")
    def request_dataset_generation(self) -> bool:
        return self.execution_controller.generate()

    @Slot(result=bool, name="requestExecutionCancel")
    def request_execution_cancel(self) -> bool:
        return self.execution_controller.cancel()

    @Slot(result=bool, name="requestExecutionForceStop")
    def request_execution_force_stop(self) -> bool:
        return self.execution_controller.force_stop()

    @Slot(str, result=bool, name="requestInspectSource")
    def request_inspect_source(self, source: str) -> bool:
        return self.inspection_controller.inspect_source(_local_path(source))

    @Slot(result=bool, name="requestRefreshInspection")
    def request_refresh_inspection(self) -> bool:
        return self.inspection_controller.refresh_inspection()

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

    @Slot(str, result=bool, name="requestSavePathSelected")
    def request_save_path_selected(self, path: str) -> bool:
        if not self._guard_active_plot_edit("Save As"):
            return False
        return self.dataset_config_controller.save_path_selected(_local_path(path))

    @Slot(name="requestCancelSavePath")
    def request_cancel_save_path(self) -> None:
        self.dataset_config_controller.cancel_save_path()

    @Slot(str, name="requestConfirmReformat")
    def request_confirm_reformat(self, action: str) -> None:
        if self._guard_active_plot_edit("Save"):
            self.dataset_config_controller.confirm_reformat(action)

    @Slot(bool, result=bool, name="requestReloadSource")
    def request_reload_source(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_active_plot_edit("Reload"):
            return False
        return self.dataset_config_controller.reload_source(discard_confirmed)

    @Slot(bool, result=bool, name="requestCloseConfiguration")
    def request_close_configuration(self, discard_confirmed: bool = False) -> bool:
        if not self._guard_active_plot_edit("Close Configuration"):
            return False
        return self.dataset_config_controller.clear_document(discard_confirmed)

    @Slot(str, str, int, result=bool, name="requestConfigurationAttention")
    def request_configuration_attention(self, section: str, field: str, row: int) -> bool:
        if section not in {"dataset", "visualization"}:
            return False
        if not field.startswith(f"{section}.") and not (
            section == "visualization" and field.startswith("plot.")
        ):
            return False
        self.attentionRequested.emit(section, field, row)
        return True

    @Slot(str, result=bool, name="requestDatasetModeChange")
    def request_dataset_mode_change(self, mode: str) -> bool:
        if not self._guard_active_plot_edit("dataset mode change"):
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
        if not self._guard_active_plot_edit("dataset coordinate change"):
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
        if not confirmed or not self._guard_active_plot_edit("dataset replacement"):
            self._pending_dataset_decision = None
            self.datasetDecisionChanged.emit()
            return False
        self._pending_dataset_decision = None
        operation, value = decision
        if operation == "mode":
            changed = self.dataset_config_controller.apply_mode_change(value)
        else:
            changed = self.dataset_config_controller.apply_coordinate_change(value)
        self.datasetDecisionChanged.emit()
        return changed

    @Slot(name="cancelDatasetDecision")
    def cancel_dataset_decision(self) -> None:
        self._pending_dataset_decision = None
        self.datasetDecisionChanged.emit()

    @Slot(str, name="requestDatasetModelChange")
    def request_dataset_model_change(self, model: str) -> None:
        self.dataset_draft.set_model_name(model)

    @Slot(str, bool, name="requestDatasetFluidSelection")
    def request_dataset_fluid_selection(self, value: str, selected: bool) -> None:
        if selected:
            self.dataset_draft.add_fluid(value)
        else:
            self.dataset_draft.remove_fluid_value(value)

    @Slot(int, int, name="requestDatasetFluidMove")
    def request_dataset_fluid_move(self, row: int, offset: int) -> None:
        self.dataset_draft.move_fluid(row, offset)

    @Slot(int, name="requestDatasetFluidRemove")
    def request_dataset_fluid_remove(self, row: int) -> None:
        self.dataset_draft.remove_fluid(row)

    @Slot(str, bool, name="requestDatasetPropertySelection")
    def request_dataset_property_selection(self, value: str, selected: bool) -> None:
        if selected:
            self.dataset_draft.add_property(value)
        else:
            self.dataset_draft.remove_property_value(value)

    @Slot(int, int, name="requestDatasetPropertyMove")
    def request_dataset_property_move(self, row: int, offset: int) -> None:
        self.dataset_draft.move_property(row, offset)

    @Slot(int, name="requestDatasetPropertyRemove")
    def request_dataset_property_remove(self, row: int) -> None:
        self.dataset_draft.remove_property(row)

    @Slot(str, bool, name="requestDatasetOutputSelection")
    def request_dataset_output_selection(self, output_format: str, selected: bool) -> None:
        self.dataset_draft.set_output_selected(output_format, selected)

    @Slot(QObject, str, name="requestDatasetSamplerKindChange")
    def request_dataset_sampler_kind_change(self, candidate: QObject, kind: str) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None:
            sampler.set_kind(kind)

    @Slot(QObject, str, str, name="requestDatasetSamplerTextChange")
    def request_dataset_sampler_text_change(
        self,
        candidate: QObject,
        field: str,
        text: str,
    ) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None:
            sampler.set_text(field, text)

    @Slot(QObject, str, name="requestDatasetSamplerUnitChange")
    def request_dataset_sampler_unit_change(self, candidate: QObject, unit: str) -> None:
        sampler = self._owned_dataset_sampler(candidate)
        if sampler is not None:
            sampler.requestUnitChange(unit)

    @Slot(bool, name="requestVisualizationEnabled")
    def request_visualization_enabled(self, enabled: bool) -> None:
        if self._guard_active_plot_edit("visualization enable or disable"):
            self.visualization_draft.set_enabled(enabled)

    @Slot(str, name="requestVisualizationFormat")
    def request_visualization_format(self, output_format: str) -> None:
        if self._guard_active_plot_edit("shared visualization format change"):
            self.visualization_draft.set_format(output_format)

    @Slot(str, bool, name="requestVisualizationFluidSelection")
    def request_visualization_fluid_selection(self, value: str, selected: bool) -> None:
        if self._guard_active_plot_edit("shared visualization fluid change"):
            self.visualization_draft.set_fluid_selected(value, selected)

    @Slot(result=bool, name="requestVisualizationAddPlot")
    def request_visualization_add_plot(self) -> bool:
        if not self._guard_active_plot_edit("starting another plot edit"):
            return False
        return self.visualization_draft.begin_add_plot() is not None

    @Slot(int, result=bool, name="requestVisualizationEditPlot")
    def request_visualization_edit_plot(self, row: int) -> bool:
        if not self._guard_active_plot_edit("starting another plot edit"):
            return False
        return self.visualization_draft.begin_edit_plot(row) is not None

    @Slot(result=bool, name="requestVisualizationCommitPlot")
    def request_visualization_commit_plot(self) -> bool:
        return self.visualization_draft.commit_plot()

    @Slot(result=bool, name="requestVisualizationCancelPlot")
    def request_visualization_cancel_plot(self) -> bool:
        return self.visualization_draft.cancel_plot()

    @Slot(int, result=bool, name="requestVisualizationRemovePlot")
    def request_visualization_remove_plot(self, row: int) -> bool:
        if not self._guard_active_plot_edit("plot removal"):
            return False
        return self.visualization_draft.remove_plot(row)

    @Slot(int, int, result=bool, name="requestVisualizationMovePlot")
    def request_visualization_move_plot(self, row: int, offset: int) -> bool:
        if not self._guard_active_plot_edit("plot movement"):
            return False
        return self.visualization_draft.move_plot(row, offset)

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

    def _owned_active_plot(self, candidate: QObject) -> PlotDraft | None:
        active = self.visualization_draft.get_active_plot_draft()
        return active if isinstance(active, PlotDraft) and active is candidate else None

    def _owned_visualization_mapping(
        self,
        candidate: QObject,
    ) -> MappingDraftModel | None:
        shared = (
            self.visualization_draft.filters,
            self.visualization_draft.display_units,
        )
        if candidate in shared:
            if not self._guard_active_plot_edit("shared visualization mapping change"):
                return None
            return candidate if isinstance(candidate, MappingDraftModel) else None
        active = self.visualization_draft.get_active_plot_draft()
        if not isinstance(active, PlotDraft):
            return None
        mappings = (active.filters, active.series, active.display_units)
        if isinstance(candidate, MappingDraftModel) and candidate in mappings:
            return candidate
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
        if not self._guard_active_plot_edit("closing Carnopy"):
            return False
        self.workspace_controller.cancel_pending()
        if self.request_coordinator.is_busy:
            return False
        self._workspace_request_timer.stop()
        self._queued_workspace_request = None
        self.request_coordinator.shutdown()
        self.settings.sync()
        self._shutdown = True
        return True

    @Slot(result=bool, name="requestShutdown")
    def request_shutdown(self) -> bool:
        if not self._guard_active_plot_edit("closing Carnopy"):
            return False
        if self.request_coordinator.is_busy:
            self.workspace_controller.report_error(
                "Wait for the active worker request to finish before closing Carnopy."
            )
            return False
        if (
            self.dataset_config_controller.needs_discard_confirmation()
            and not self._shutdown_discard_confirmed
        ):
            self.shutdownConfirmationRequested.emit()
            return False
        self._shutdown_discard_confirmed = False
        return self.shutdown()

    @Slot(bool, result=bool, name="confirmShutdown")
    def confirm_shutdown(self, discard_confirmed: bool) -> bool:
        if not discard_confirmed:
            self._shutdown_discard_confirmed = False
            return False
        if not self._guard_active_plot_edit("closing Carnopy"):
            return False
        if self.request_coordinator.is_busy:
            self.workspace_controller.report_error(
                "Wait for the active worker request to finish before closing Carnopy."
            )
            return False
        self._shutdown_discard_confirmed = True
        self.closeWindowRequested.emit()
        return True

    def _workspace_activated(self, value: object) -> None:
        self.dataset_config_controller.set_workspace(value)
        self.execution_controller.set_workspace(value if isinstance(value, Workspace) else None)
        self.inspection_controller.set_workspace(value if isinstance(value, Workspace) else None)
        self.activity_controller.set_workspace(value if isinstance(value, Workspace) else None)
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _configuration_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _request_state_changed(self, _busy: bool) -> None:
        self.workspace_state_changed.emit()

    def _active_plot_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        self.workspace_confirmation_changed.emit()

    def _guard_workspace_change(self, *, before_commit: bool) -> bool:
        if self._guard_active_plot_edit():
            return True
        if before_commit:
            self.workspace_controller.cancel_pending()
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

    def _plot_commit_rejected(self, field: str, row: int, _message: str) -> None:
        self.attentionRequested.emit("visualization", field, row)

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


def _valid_workspace_child_name(value: str) -> bool:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        return False
    return not Path(value).is_absolute() and Path(value).name == value
