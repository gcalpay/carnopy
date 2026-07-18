from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.config_widgets import SamplerEditor
from carnopy.app.dataset_draft import DatasetDraft
from carnopy.app.draft_models import (
    COMPATIBLE_ROLE,
    VALUE_ROLE,
    DraftListModel,
)


class CompatibilityDelegate(QStyledItemDelegate):
    """Preserve explicit incompatible-row styling in the Widgets view."""

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().initStyleOption(option, index)
        if index.data(COMPATIBLE_ROLE) is False:
            option.palette.setColor(QPalette.ColorRole.Text, QColor("#a33a00"))


class DraftListView(QListView):
    """Keep the former row-selection convenience on a model-backed view."""

    def currentRow(self) -> int:
        return self.currentIndex().row()

    def setCurrentRow(self, row: int) -> None:
        model = self.model()
        if model is None or not 0 <= row < model.rowCount():
            self.setCurrentIndex(QModelIndex())
            return
        self.setCurrentIndex(model.index(row, 0))


class DatasetConfigForm(QWidget):
    """Present controller-owned dataset fields without owning draft state."""

    changed = Signal()
    mode_change_requested = Signal(str)
    coordinate_change_requested = Signal(str)
    message = Signal(str)

    def __init__(
        self,
        draft: DatasetDraft,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.draft = draft
        self._sampler_editors: dict[str, SamplerEditor] = {}

        body = QWidget()
        body_layout = QVBoxLayout(body)
        form = QFormLayout()
        self.model = QComboBox()
        self.model.setModel(draft.model_choices)
        self.model.setAccessibleName("Thermodynamic model")
        self.mode = QComboBox()
        self.mode.setModel(draft.mode_choices)
        self.mode.setAccessibleName("Dataset mode")
        form.addRow("Model", self.model)
        form.addRow("Mode", self.mode)
        body_layout.addLayout(form)

        body_layout.addWidget(QLabel("Fluids (ordered)"))
        fluid_entry = QHBoxLayout()
        self.fluid_input = QComboBox()
        self.fluid_input.setModel(draft.fluid_choices)
        self.fluid_input.setEditable(True)
        self.fluid_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.fluid_input.setAccessibleName("Fluid or alias")
        completer = self.fluid_input.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.fluid_feedback = QLabel()
        self.fluid_feedback.setAccessibleName("Canonical fluid name")
        add_fluid = QPushButton("Add Fluid")
        add_fluid.clicked.connect(self._add_fluid)
        fluid_entry.addWidget(self.fluid_input, 1)
        fluid_entry.addWidget(add_fluid)
        body_layout.addLayout(fluid_entry)
        body_layout.addWidget(self.fluid_feedback)
        self.fluids = DraftListView()
        self.fluids.setModel(draft.selected_fluids)
        self.fluids.setAccessibleName("Selected fluids")
        body_layout.addWidget(self.fluids)
        body_layout.addLayout(self._list_actions(self.fluids, "fluid"))

        body_layout.addWidget(QLabel("Sampling grid"))
        coordinate_form = QFormLayout()
        self.coordinate = QComboBox()
        self.coordinate.setModel(draft.coordinate_choices)
        self.coordinate.setAccessibleName("Independent saturation coordinate")
        self.coordinate_label = QLabel("Independent coordinate")
        self.coordinate_label.setBuddy(self.coordinate)
        coordinate_form.addRow(self.coordinate_label, self.coordinate)
        body_layout.addLayout(coordinate_form)
        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self.grid_container)

        body_layout.addWidget(QLabel("Properties (ordered)"))
        property_entry = QHBoxLayout()
        self.property_input = QComboBox()
        self.property_input.setModel(draft.property_choices)
        self.property_input.view().setItemDelegate(CompatibilityDelegate(self.property_input))
        self.property_input.setAccessibleName("Available property")
        add_property = QPushButton("Add Property")
        add_property.clicked.connect(self._add_property)
        property_entry.addWidget(self.property_input, 1)
        property_entry.addWidget(add_property)
        body_layout.addLayout(property_entry)
        self.properties = DraftListView()
        self.properties.setModel(draft.selected_properties)
        self.properties.setItemDelegate(CompatibilityDelegate(self.properties))
        self.properties.setAccessibleName("Selected properties")
        body_layout.addWidget(self.properties)
        body_layout.addLayout(self._list_actions(self.properties, "property"))
        self.reference_advisory = QLabel()
        self.reference_advisory.setWordWrap(True)
        self.reference_advisory.setAccessibleName("Reference-state advisory")
        body_layout.addWidget(self.reference_advisory)

        body_layout.addWidget(QLabel("Dataset outputs"))
        output_row = QHBoxLayout()
        self.csv_output = QCheckBox("CSV")
        self.parquet_output = QCheckBox("Parquet")
        output_row.addWidget(self.csv_output)
        output_row.addWidget(self.parquet_output)
        output_row.addStretch(1)
        body_layout.addLayout(output_row)
        body_layout.addStretch(1)

        self.model.activated.connect(self._model_requested)
        self.mode.activated.connect(self._mode_requested)
        self.coordinate.activated.connect(self._coordinate_requested)
        self.fluid_input.currentTextChanged.connect(self._fluid_text_changed)
        self.csv_output.toggled.connect(lambda selected: draft.set_output_selected("csv", selected))
        self.parquet_output.toggled.connect(
            lambda selected: draft.set_output_selected("parquet", selected)
        )
        draft.changed.connect(self._sync_from_draft)
        draft.changed.connect(self.changed)
        draft.mode_change_requested.connect(self.mode_change_requested)
        draft.message.connect(self.message)
        draft.samplers.modelReset.connect(self._rebuild_samplers)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self._sync_from_draft()

    @property
    def model_name(self) -> str:
        return self.draft.get_model_name()

    @property
    def mode_name(self) -> str:
        return self.draft.get_mode_name()

    def apply_capabilities(self, payload: dict[str, Any]) -> None:
        self.draft.apply_capabilities(payload)
        self._sync_from_draft()

    def load_payload(self, payload: dict[str, Any]) -> None:
        self.draft.load_payload(payload)

    def clear(self) -> None:
        self.draft.clear()

    def selected_properties(self) -> list[str]:
        return list(self.draft.selected_property_values())

    def unsupported_selected_properties(self) -> list[str]:
        return list(self.draft.unsupported_properties())

    def move_selected(self, widget: DraftListView, offset: int) -> None:
        row = widget.currentRow()
        if widget is self.fluids:
            moved = self.draft.move_fluid(row, offset)
        else:
            moved = self.draft.move_property(row, offset)
        if moved:
            widget.setCurrentRow(row + offset)

    @staticmethod
    def list_values(widget: DraftListView) -> list[str]:
        model = widget.model()
        if not isinstance(model, DraftListModel):
            return []
        return list(model.values)

    def sync_from_draft(self) -> None:
        self._sync_from_draft()

    def _list_actions(self, widget: DraftListView, noun: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        remove = QPushButton(f"Remove {noun.title()}")
        up = QPushButton("Move Up")
        down = QPushButton("Move Down")
        remove.clicked.connect(lambda: self._remove_selected(widget))
        up.clicked.connect(lambda: self.move_selected(widget, -1))
        down.clicked.connect(lambda: self.move_selected(widget, 1))
        layout.addWidget(remove)
        layout.addWidget(up)
        layout.addWidget(down)
        layout.addStretch(1)
        return layout

    def _sync_from_draft(self) -> None:
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.model,
                self.mode,
                self.coordinate,
                self.csv_output,
                self.parquet_output,
            )
        ]
        self.model.setCurrentIndex(
            self.model.findData(self.draft.get_model_name(), role=VALUE_ROLE)
        )
        self.mode.setCurrentIndex(self.mode.findData(self.draft.get_mode_name(), role=VALUE_ROLE))
        self.coordinate.setCurrentIndex(
            self.coordinate.findData(self.draft.get_coordinate_name(), role=VALUE_ROLE)
        )
        self.csv_output.setChecked(self.draft.output_selected("csv"))
        self.parquet_output.setChecked(self.draft.output_selected("parquet"))
        visible = self.draft.get_mode_name() != "property_table"
        self.coordinate.setVisible(visible)
        self.coordinate_label.setVisible(visible)
        self.reference_advisory.setText(self.draft.get_reference_advisory())
        self._fluid_text_changed(self.fluid_input.currentText())
        del blockers

    def _rebuild_samplers(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._sampler_editors = {}
        for sampler in self.draft.samplers.drafts:
            editor = SamplerEditor(sampler)
            self.grid_layout.addWidget(editor)
            self._sampler_editors[sampler.get_axis()] = editor

    def _mode_requested(self, index: int) -> None:
        value = self.mode.itemData(index, VALUE_ROLE)
        if isinstance(value, str):
            self.draft.request_mode_change(value)

    def _coordinate_requested(self, index: int) -> None:
        value = self.coordinate.itemData(index, VALUE_ROLE)
        if isinstance(value, str) and value != self.draft.get_coordinate_name():
            self.coordinate_change_requested.emit(value)

    def _model_requested(self, index: int) -> None:
        value = self.model.itemData(index, VALUE_ROLE)
        if isinstance(value, str):
            self.draft.set_model_name(value)

    def _add_fluid(self) -> None:
        self.draft.add_fluid(self.fluid_input.currentText())

    def _fluid_text_changed(self, text: str) -> None:
        requested = text.strip()
        canonical = next(
            (
                str(item.canonical)
                for item in self.draft.fluid_choices.items
                if item.value.casefold() == requested.casefold()
            ),
            "",
        )
        self.fluid_feedback.setText(
            f"Canonical fluid: {canonical}" if canonical else "Choose a known fluid or alias."
        )

    def _add_property(self) -> None:
        value = self.property_input.currentData(VALUE_ROLE)
        if isinstance(value, str):
            self.draft.add_property(value)

    def _remove_selected(self, widget: DraftListView) -> None:
        row = widget.currentRow()
        if widget is self.fluids:
            self.draft.remove_fluid(row)
        else:
            self.draft.remove_property(row)
