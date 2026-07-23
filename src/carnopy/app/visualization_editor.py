from __future__ import annotations

from typing import cast

from PySide6.QtCore import QModelIndex, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .draft_models import VALUE_ROLE
from .plot_draft import PlotDraft
from .plot_request_dialog import PlotRequestDialog
from .visualization_draft import VisualizationDraft
from .visualization_widgets import ChoiceMappingTable, FluidChoiceList


class _PlotListView(QListView):
    def currentRow(self) -> int:
        return self.currentIndex().row()

    def setCurrentRow(self, row: int) -> None:
        model = self.model()
        index = model.index(row, 0) if model is not None else QModelIndex()
        self.setCurrentIndex(index)


class VisualizationEditor(QWidget):
    """Present the authoritative configured-visualization draft."""

    changed = Signal()

    def __init__(
        self,
        draft: VisualizationDraft | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.draft = draft or VisualizationDraft(self)
        self._syncing = False
        self._last_message = ""

        layout = QVBoxLayout(self)
        self.enabled = QPushButton("Enable Configured Visualization")
        self.enabled.setCheckable(True)
        layout.addWidget(self.enabled)
        shared = QFormLayout()
        self.format = QComboBox()
        self.format.setModel(self.draft.format_choices)
        self.fluids = FluidChoiceList()
        self.filters = ChoiceMappingTable("Shared filter field", "Exact SI value")
        self.display_units = ChoiceMappingTable(
            "Shared field", "Display unit", numeric_values=False
        )
        shared.addRow("Shared format", self.format)
        shared.addRow("Shared fluids", self.fluids)
        shared.addRow("Shared filters", self.filters)
        shared.addRow("Shared display units", self.display_units)
        layout.addLayout(shared)
        layout.addWidget(QLabel("Plot requests (ordered)"))
        plot_name_help = QLabel(
            "Plot names are explicit output identifiers and do not follow the "
            "configuration filename."
        )
        plot_name_help.setWordWrap(True)
        plot_name_help.setAccessibleName("Plot name guidance")
        layout.addWidget(plot_name_help)
        self.plots = _PlotListView()
        self.plots.setModel(self.draft.plot_model)
        layout.addWidget(self.plots, 1)
        actions = QHBoxLayout()
        self.action_buttons: list[QPushButton] = []
        for label, slot in (
            ("Add Plot…", self.add_plot),
            ("Edit Plot…", self.edit_plot),
            ("Remove Plot", self.remove_plot),
            ("Move Up", lambda: self.move_plot(-1)),
            ("Move Down", lambda: self.move_plot(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            self.action_buttons.append(button)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.enabled.toggled.connect(self.draft.set_enabled)
        self.format.currentTextChanged.connect(self.draft.set_format)
        self.fluids.changed.connect(self._fluids_changed)
        self.draft.changed.connect(self._draft_changed)
        self.draft.enabled_changed.connect(self._sync_from_draft)
        self.draft.format_changed.connect(self._sync_from_draft)
        self.draft.active_plot_draft_changed.connect(self._sync_from_draft)
        self.draft.message.connect(self._draft_message)
        for model in (
            self.draft.format_choices,
            self.draft.fluid_choices,
            self.draft.selected_fluids,
            self.draft.filters,
            self.draft.display_units,
        ):
            model.modelReset.connect(self._sync_from_draft)
        self._sync_from_draft()

    def apply_capabilities(self, capabilities: dict[str, object]) -> None:
        self.draft.apply_capabilities(capabilities)
        self._sync_from_draft()

    def set_dataset_context(self, payload: dict[str, object]) -> None:
        self.draft.set_dataset_context(payload)
        self._sync_from_draft()

    def load_visualization(self, value: object) -> None:
        self.draft.load_visualization(value)
        self._sync_from_draft()

    def visualization_payload(self) -> dict[str, object] | None:
        return self.draft.visualization_payload()

    def plot_payloads(self) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], self.draft.plot_payloads())

    def add_plot(self) -> None:
        active = self.draft.begin_add_plot()
        if isinstance(active, PlotDraft):
            self._run_plot_dialog(active)

    def edit_plot(self) -> None:
        active = self.draft.begin_edit_plot(self.plots.currentRow())
        if isinstance(active, PlotDraft):
            self._run_plot_dialog(active)

    def remove_plot(self) -> None:
        row = self.plots.currentRow()
        if self.draft.remove_plot(row):
            self.plots.setCurrentRow(min(row, self.draft.plot_model.rowCount() - 1))

    def move_plot(self, offset: int) -> None:
        row = self.plots.currentRow()
        if self.draft.move_plot(row, offset):
            self.plots.setCurrentRow(row + offset)

    def _run_plot_dialog(self, active: PlotDraft) -> None:
        while True:
            dialog = PlotRequestDialog(active, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.draft.cancel_plot()
                return
            self._last_message = ""
            if self.draft.commit_plot():
                return
            QMessageBox.warning(
                self,
                "Invalid Plot Request",
                self._last_message or active.get_issue() or "The plot request is invalid.",
            )

    def _fluids_changed(self) -> None:
        if self._syncing:
            return
        current = list(self.draft.selected_fluid_values())
        selected = self.fluids.selected_values()
        self._syncing = True
        try:
            for value in current:
                if value not in selected:
                    self.draft.set_fluid_selected(value, False)
            for value in selected:
                if value not in current:
                    self.draft.set_fluid_selected(value, True)
        finally:
            self._syncing = False
        self._sync_from_draft()

    def _draft_changed(self) -> None:
        if not self._syncing:
            self._sync_from_draft()
        self.changed.emit()

    def _draft_message(self, message: str) -> None:
        self._last_message = message

    def _sync_from_draft(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            enabled_blocker = QSignalBlocker(self.enabled)
            format_blocker = QSignalBlocker(self.format)
            fluids_blocker = QSignalBlocker(self.fluids)
            self.enabled.setChecked(self.draft.get_enabled())
            selected_format = self.draft.get_format()
            self.format.setCurrentIndex(self.format.findData(selected_format, role=VALUE_ROLE))
            dataset_fluids = [item.value for item in self.draft.fluid_choices.items]
            selected_fluids = list(self.draft.selected_fluid_values())
            choices = [*dataset_fluids]
            choices.extend(value for value in selected_fluids if value not in choices)
            self.fluids.set_choices(choices, selected_fluids)
            self.filters.bind_draft(self.draft.filters)
            self.display_units.bind_draft(self.draft.display_units)
            self._set_controls_enabled(self.draft.get_enabled())
            del enabled_blocker, format_blocker, fluids_blocker
        finally:
            self._syncing = False

    def _set_controls_enabled(self, enabled: bool) -> None:
        shared_enabled = enabled and not self.draft.get_has_active_plot_edit()
        self.enabled.setEnabled(not self.draft.get_has_active_plot_edit())
        for widget in (
            self.format,
            self.fluids,
            self.filters,
            self.display_units,
            self.plots,
            *self.action_buttons,
        ):
            widget.setEnabled(shared_enabled)
