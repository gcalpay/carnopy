from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from carnopy.app.config_document import serialize_dataset_config
from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.field_ids import (
    PLOT_FILTERS,
    PLOT_NAME,
    VISUALIZATION_DISPLAY_UNITS,
    VISUALIZATION_ENABLED,
    VISUALIZATION_FILTERS,
    VISUALIZATION_FLUIDS,
    VISUALIZATION_FORMAT,
    VISUALIZATION_PLOTS,
)
from carnopy.app.mapping_draft import MappingDraftModel
from carnopy.app.plot_draft import PlotDraft

DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole)
NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 70
KIND_ROLE = NAME_ROLE + 1
COMPATIBLE_ROLE = NAME_ROLE + 2
ISSUE_ROLE = NAME_ROLE + 3
INVALID_INDEX = QModelIndex()


@dataclass(frozen=True)
class VisualizationPlotItem:
    payload: dict[str, Any]
    issue: str = ""


@dataclass(frozen=True)
class _VisualizationIssue:
    field: str
    row: int
    message: str


class VisualizationPlotModel(QAbstractListModel):
    """Expose ordered configured-plot snapshots without owning plot editors."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: tuple[VisualizationPlotItem, ...] = ()

    def replace(
        self,
        payloads: Iterable[Mapping[str, object]],
        issues: Iterable[str],
    ) -> bool:
        updated = tuple(
            VisualizationPlotItem(copy.deepcopy(dict(payload)), str(issue))
            for payload, issue in zip(payloads, issues, strict=True)
        )
        if updated == self._items:
            return False
        self.beginResetModel()
        self._items = updated
        self.endResetModel()
        return True

    def payload(self, row: int) -> dict[str, Any] | None:
        if not 0 <= row < len(self._items):
            return None
        return copy.deepcopy(self._items[row].payload)

    def payloads(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item.payload) for item in self._items]

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._items)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = DISPLAY_ROLE,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        name = str(item.payload.get("name", ""))
        kind = str(item.payload.get("kind", ""))
        values: dict[int, object] = {
            DISPLAY_ROLE: f"{name or '<unnamed>'} — {kind or '<unknown>'}",
            NAME_ROLE: name,
            KIND_ROLE: kind,
            COMPATIBLE_ROLE: not item.issue,
            ISSUE_ROLE: item.issue,
            int(Qt.ItemDataRole.ToolTipRole): item.issue,
        }
        return values.get(role)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            DISPLAY_ROLE: QByteArray(b"display"),
            NAME_ROLE: QByteArray(b"name"),
            KIND_ROLE: QByteArray(b"kind"),
            COMPATIBLE_ROLE: QByteArray(b"compatible"),
            ISSUE_ROLE: QByteArray(b"issue"),
        }


class VisualizationDraft(QObject):
    """Own QML-ready editable state for configured dataset visualization."""

    changed = Signal()
    enabled_changed = Signal()
    format_changed = Signal()
    validity_changed = Signal()
    dirty_changed = Signal()
    active_plot_draft_changed = Signal()
    plot_commit_rejected = Signal(str, int, str)
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.format_choices = DraftListModel(self)
        self.fluid_choices = DraftListModel(self)
        self.selected_fluids = DraftListModel(self)
        self.filters = MappingDraftModel(self, mutation_guard=self._shared_mutation_allowed)
        self.display_units = MappingDraftModel(
            self,
            numeric_values=False,
            mutation_guard=self._shared_mutation_allowed,
        )
        self.plot_model = VisualizationPlotModel(self)
        self._capabilities: dict[str, Any] | None = None
        self._dataset_payload: dict[str, Any] = {}
        self._loaded = False
        self._enabled = False
        self._format = ""
        self._fluids: tuple[str, ...] = ()
        self._plots: tuple[dict[str, Any], ...] = ()
        self._baseline_yaml: bytes | None = None
        self._baseline_raw: tuple[object, ...] | None = None
        self._valid = False
        self._issue = "No dataset configuration is open."
        self._first_invalid_field = VISUALIZATION_ENABLED
        self._first_invalid_row = -1
        self._dirty = False
        self._active_plot_draft: PlotDraft | None = None
        self._active_plot_row: int | None = None
        self._loading = False
        self.filters.changed.connect(self._mapping_changed)
        self.display_units.changed.connect(self._mapping_changed)

    def get_enabled(self) -> bool:
        return self._enabled

    @Slot(bool)
    def set_enabled(self, value: bool) -> None:
        enabled = bool(value)
        if self._loading or not self._loaded or enabled == self._enabled:
            return
        if not self._shared_mutation_allowed():
            return
        previous = self._observable_state()
        self._enabled = enabled
        self._state_changed(previous=previous)

    enabled = Property(bool, get_enabled, set_enabled, notify=enabled_changed)

    def get_format(self) -> str:
        return self._format

    @Slot(str)
    def set_format(self, value: str) -> None:
        if self._loading or not self._loaded or value == self._format:
            return
        if not self._shared_mutation_allowed():
            return
        previous = self._observable_state()
        self._format = value
        self._state_changed(previous=previous)

    format = Property(str, get_format, set_format, notify=format_changed)

    def get_locally_valid(self) -> bool:
        return self._valid

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        return self._issue

    issue = Property(str, get_issue, notify=validity_changed)

    def get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, get_dirty, notify=dirty_changed)

    def get_active_plot_draft(self) -> QObject | None:
        return self._active_plot_draft

    activePlotDraft = Property(
        QObject,
        get_active_plot_draft,
        notify=active_plot_draft_changed,
    )

    def get_has_active_plot_edit(self) -> bool:
        return self._active_plot_draft is not None

    hasActivePlotEdit = Property(
        bool,
        get_has_active_plot_edit,
        notify=active_plot_draft_changed,
    )

    def get_first_invalid_field(self) -> str:
        return self._first_invalid_field

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        return self._first_invalid_row

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def _constant_model(self, model: QObject) -> QObject:
        return model

    formatChoices = Property(
        QObject,
        lambda self: self._constant_model(self.format_choices),
        constant=True,
    )
    fluidChoices = Property(
        QObject,
        lambda self: self._constant_model(self.fluid_choices),
        constant=True,
    )
    selectedFluids = Property(
        QObject,
        lambda self: self._constant_model(self.selected_fluids),
        constant=True,
    )
    filterRows = Property(
        QObject,
        lambda self: self._constant_model(self.filters),
        constant=True,
    )
    displayUnitRows = Property(
        QObject,
        lambda self: self._constant_model(self.display_units),
        constant=True,
    )
    plots = Property(
        QObject,
        lambda self: self._constant_model(self.plot_model),
        constant=True,
    )

    def apply_capabilities(self, payload: Mapping[str, object]) -> None:
        previous = self._observable_state()
        self._loading = True
        try:
            self._capabilities = copy.deepcopy(dict(payload))
            if self._active_plot_draft is not None:
                self._active_plot_draft.refresh_context(payload, self._dataset_payload)
            self._refresh_models()
            self._refresh_derived()
        finally:
            self._loading = False
        self._emit_observable_changes(previous)

    def set_dataset_context(self, payload: Mapping[str, object]) -> None:
        previous = self._observable_state()
        self._loading = True
        try:
            self._dataset_payload = copy.deepcopy(dict(payload))
            if self._active_plot_draft is not None and self._capabilities is not None:
                self._active_plot_draft.refresh_context(self._capabilities, payload)
            self._refresh_models()
            self._refresh_derived()
        finally:
            self._loading = False
        self._emit_observable_changes(previous)

    def load_visualization(self, value: object) -> None:
        previous = self._observable_state()
        self._discard_active_plot()
        visualization = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else None
        self._loading = True
        try:
            self._loaded = True
            self._enabled = visualization is not None
            self._format = (
                str(visualization.get("format", "png"))
                if visualization is not None
                else self._default_format()
            )
            self._fluids = (
                _string_tuple(visualization.get("fluids")) if visualization is not None else ()
            )
            self.filters.load_mapping(
                _mapping(visualization.get("filters")) if visualization is not None else {}
            )
            self.display_units.load_mapping(
                _mapping(visualization.get("display_units")) if visualization is not None else {}
            )
            plots = visualization.get("plots") if visualization is not None else None
            self._plots = tuple(
                copy.deepcopy(dict(plot))
                for plot in (plots if isinstance(plots, (list, tuple)) else ())
                if isinstance(plot, Mapping)
            )
            self._refresh_models()
            self._refresh_derived()
            self._baseline_yaml = _visualization_bytes(visualization)
            self._baseline_raw = self.raw_state()
            self._refresh_derived()
        finally:
            self._loading = False
        self._emit_observable_changes(previous)
        self.changed.emit()

    def clear(self) -> None:
        previous = self._observable_state()
        self._discard_active_plot()
        self._loading = True
        try:
            self._loaded = False
            self._dataset_payload = {}
            self._enabled = False
            self._format = ""
            self._fluids = ()
            self.filters.load_mapping({})
            self.display_units.load_mapping({})
            self._plots = ()
            self._baseline_yaml = None
            self._baseline_raw = None
            self._refresh_models()
            self._refresh_derived()
        finally:
            self._loading = False
        self._emit_observable_changes(previous)
        self.changed.emit()

    def reset_for_mode_change(self) -> None:
        if not self._loaded:
            return
        previous = self._observable_state()
        self._discard_active_plot()
        self._loading = True
        try:
            self._enabled = False
            self._format = self._default_format()
            self._fluids = ()
            self.filters.load_mapping({})
            self.display_units.load_mapping({})
            self._plots = ()
            self._refresh_models()
            self._refresh_derived()
        finally:
            self._loading = False
        self._emit_observable_changes(previous)
        self.changed.emit()

    def mark_baseline(self) -> None:
        if not self._valid:
            raise ValueError("cannot mark an invalid visualization draft as saved")
        previous = self._observable_state()
        self._baseline_yaml = self._canonical_bytes()
        self._baseline_raw = self.raw_state()
        self._refresh_derived()
        self._emit_observable_changes(previous)

    def visualization_payload(self) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        issue = self._validation_issue()
        if issue:
            raise ValueError(issue)
        payload: dict[str, Any] = {
            "format": self._format,
            "plots": [copy.deepcopy(plot) for plot in self._plots],
        }
        if self._fluids:
            payload["fluids"] = list(self._fluids)
        filters = self.filters.mapping()
        if filters:
            payload["filters"] = filters
        display_units = self.display_units.mapping()
        if display_units:
            payload["display_units"] = display_units
        return payload

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._loaded,
            self._enabled,
            self._format,
            self._fluids,
            self.filters.raw_rows(),
            self.display_units.raw_rows(),
            tuple(_freeze(plot) for plot in self._plots),
        )

    @Slot(str, bool, result=bool)
    def set_fluid_selected(self, value: str, selected: bool) -> bool:
        if self._loading or not self._loaded:
            return False
        canonical = self._canonical_fluid(value)
        selected_canonical = self._canonical_fluid_values(self._fluids)
        if selected:
            if canonical in selected_canonical:
                return False
            updated = (*self._fluids, value)
        else:
            updated = tuple(
                fluid for fluid in self._fluids if self._canonical_fluid(fluid) != canonical
            )
            if updated == self._fluids:
                return False
        if not self._shared_mutation_allowed():
            return False
        self._fluids = updated
        self._state_changed()
        return True

    def selected_fluid_values(self) -> tuple[str, ...]:
        return self._fluids

    def format_values(self) -> tuple[str, ...]:
        return self.format_choices.values

    def plot_payloads(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(plot) for plot in self._plots]

    def resolved_plot_payload(self, row: int) -> dict[str, Any] | None:
        """Return one configured plot with its inherited defaults applied."""

        if not self._enabled or not 0 <= row < len(self._plots):
            return None
        return self._effective_plot(self._plots[row])

    @Slot(result=QObject)
    def begin_add_plot(self) -> QObject | None:
        if not self._can_begin_plot_edit():
            return None
        assert self._capabilities is not None
        draft = PlotDraft(self._capabilities, self._dataset_payload, parent=self)
        self._set_active_plot(draft, None)
        return draft

    @Slot(int, result=QObject)
    def begin_edit_plot(self, row: int) -> QObject | None:
        if not self._can_begin_plot_edit():
            return None
        if not 0 <= row < len(self._plots):
            self.message.emit("Choose a configured plot to edit.")
            return None
        assert self._capabilities is not None
        draft = PlotDraft(
            self._capabilities,
            self._dataset_payload,
            self._plots[row],
            self,
        )
        self._set_active_plot(draft, row)
        return draft

    @Slot(result=bool)
    def commit_plot(self) -> bool:
        draft = self._active_plot_draft
        if draft is None:
            return False
        try:
            payload = draft.payload()
        except ValueError as exc:
            self.plot_commit_rejected.emit(
                draft.get_first_invalid_field(),
                draft.get_first_invalid_row(),
                str(exc),
            )
            self.message.emit(str(exc))
            return False
        updated = list(self._plots)
        if self._active_plot_row is None:
            updated.append(payload)
            candidate_row = len(updated) - 1
        else:
            updated[self._active_plot_row] = payload
            candidate_row = self._active_plot_row
        problem = self._plot_problems(tuple(updated))[candidate_row]
        if problem is not None:
            self.plot_commit_rejected.emit(problem.field, problem.row, problem.message)
            self.message.emit(problem.message)
            return False
        previous = self._observable_state()
        self._plots = tuple(updated)
        self._discard_active_plot()
        self._state_changed(previous=previous)
        return True

    @Slot(result=bool)
    def cancel_plot(self) -> bool:
        if self._active_plot_draft is None:
            return False
        self._discard_active_plot()
        return True

    @Slot(int, result=bool)
    def remove_plot(self, row: int) -> bool:
        if not self._ordinary_plot_mutation_allowed() or not 0 <= row < len(self._plots):
            return False
        previous = self._observable_state()
        self._plots = (*self._plots[:row], *self._plots[row + 1 :])
        self._state_changed(previous=previous)
        return True

    @Slot(int, int, result=bool)
    def move_plot(self, row: int, offset: int) -> bool:
        if not self._ordinary_plot_mutation_allowed():
            return False
        target = row + offset
        if not 0 <= row < len(self._plots) or not 0 <= target < len(self._plots):
            return False
        previous = self._observable_state()
        updated = list(self._plots)
        payload = updated.pop(row)
        updated.insert(target, payload)
        self._plots = tuple(updated)
        self._state_changed(previous=previous)
        return True

    def _can_begin_plot_edit(self) -> bool:
        if not self._loaded or not self._enabled:
            self.message.emit("Enable configured visualization before editing plots.")
            return False
        if self._capabilities is None or not self._dataset_payload:
            self.message.emit("Visualization capabilities and dataset context are required.")
            return False
        if self._active_plot_draft is not None:
            self.message.emit("Finish or cancel the active plot edit first.")
            return False
        return True

    def _ordinary_plot_mutation_allowed(self) -> bool:
        if self._active_plot_draft is None:
            return True
        self.message.emit("Finish or cancel the active plot edit first.")
        return False

    def _shared_mutation_allowed(self) -> bool:
        if self._loading or self._active_plot_draft is None:
            return True
        self.message.emit("Finish or cancel the active plot edit first.")
        return False

    def _set_active_plot(self, draft: PlotDraft, row: int | None) -> None:
        self._active_plot_draft = draft
        self._active_plot_row = row
        self.active_plot_draft_changed.emit()

    def _discard_active_plot(self) -> None:
        draft = self._active_plot_draft
        if draft is None:
            return
        self._active_plot_draft = None
        self._active_plot_row = None
        draft.deleteLater()
        self.active_plot_draft_changed.emit()

    def _mapping_changed(self) -> None:
        if self._loading:
            return
        previous = self._observable_state()
        self._refresh_models()
        self._refresh_derived()
        self._emit_observable_changes(previous)
        self.changed.emit()

    def _state_changed(
        self,
        *,
        previous: tuple[object, ...] | None = None,
    ) -> None:
        before = self._observable_state() if previous is None else previous
        self._refresh_models()
        self._refresh_derived()
        self._emit_observable_changes(before)
        self.changed.emit()

    def _refresh_models(self) -> None:
        formats = self._formats()
        self.format_choices.replace(_choice_items(formats, self._format))
        dataset_fluids = self._dataset_fluid_values()
        dataset_canonical = set(self._canonical_fluid_values(dataset_fluids))
        selected_canonical = set(self._canonical_fluid_values(self._fluids))
        self.fluid_choices.replace(
            DraftItem(
                value=value,
                display=value,
                canonical=self._canonical_fluid(value),
                selected=self._canonical_fluid(value) in selected_canonical,
            )
            for value in dataset_fluids
        )
        self.selected_fluids.replace(
            DraftItem(
                value=value,
                display=value if compatible else f"Unavailable: {value}",
                canonical=canonical,
                compatible=compatible,
                selected=True,
                issue=(
                    "" if compatible else f"visualization fluid {value!r} is not in the dataset"
                ),
            )
            for value in self._fluids
            for canonical in (self._canonical_fluid(value),)
            for compatible in (canonical in dataset_canonical,)
        )
        self._configure_mapping_models()
        issues = self._plot_issues(self._plots)
        self.plot_model.replace(self._plots, issues)

    def _configure_mapping_models(self) -> None:
        visualization = self._visualization_capabilities()
        definitions = visualization.get("fields")
        available = self._available_fields()
        field_kinds = self._field_kinds()
        filter_fields = tuple(
            sorted(
                str(item["name"])
                for item in (definitions if isinstance(definitions, list) else [])
                if isinstance(item, Mapping)
                and item.get("filter_allowed")
                and str(item.get("name")) in available
            )
        )
        categorical = visualization.get("categorical_values")
        self.filters.configure(
            filter_fields,
            field_kinds=field_kinds,
            value_choices={
                str(field): [str(value) for value in values]
                for field, values in (
                    categorical.items() if isinstance(categorical, Mapping) else ()
                )
                if isinstance(values, list)
            },
        )
        units = visualization.get("display_units")
        display_fields = tuple(
            sorted(field for field in available if isinstance(units, Mapping) and field in units)
        )
        self.display_units.configure(
            display_fields,
            field_kinds=field_kinds,
            value_choices={
                field: [str(value) for value in values]
                for field in display_fields
                if isinstance(units, Mapping)
                and isinstance((values := units.get(field)), (list, tuple))
            },
        )

    def _refresh_derived(self) -> None:
        problem = self._validation_problem()
        self._valid = problem is None
        self._issue = "" if problem is None else problem.message
        self._first_invalid_field = "" if problem is None else problem.field
        self._first_invalid_row = -1 if problem is None else problem.row
        if self._baseline_yaml is None or self._baseline_raw is None:
            self._dirty = False
        elif self._valid:
            self._dirty = self._canonical_bytes() != self._baseline_yaml
        else:
            self._dirty = self.raw_state() != self._baseline_raw

    def _validation_issue(self) -> str:
        problem = self._validation_problem()
        return "" if problem is None else problem.message

    def _validation_problem(self) -> _VisualizationIssue | None:
        return self._validation_problem_for(self._plots, enabled=self._enabled)

    def _validation_problem_for(
        self,
        plots: tuple[dict[str, Any], ...],
        *,
        enabled: bool,
    ) -> _VisualizationIssue | None:
        if not self._loaded:
            return _VisualizationIssue(
                VISUALIZATION_ENABLED,
                -1,
                "No dataset configuration is open.",
            )
        if not enabled:
            return None
        if self._capabilities is None:
            return _VisualizationIssue(
                VISUALIZATION_PLOTS,
                -1,
                "Visualization capabilities are not loaded.",
            )
        if not self._dataset_payload:
            return _VisualizationIssue(
                VISUALIZATION_PLOTS,
                -1,
                "Dataset context is not loaded.",
            )
        if self._format not in self._formats():
            return _VisualizationIssue(
                VISUALIZATION_FORMAT,
                -1,
                f"visualization format {self._format!r} is unavailable",
            )
        fluid_issue = self._fluid_issue()
        if fluid_issue:
            return _VisualizationIssue(VISUALIZATION_FLUIDS, -1, fluid_issue)
        if not self.filters.get_valid():
            return _VisualizationIssue(
                VISUALIZATION_FILTERS,
                self.filters.get_first_invalid_row(),
                self.filters.get_issue(),
            )
        if not self.display_units.get_valid():
            return _VisualizationIssue(
                VISUALIZATION_DISPLAY_UNITS,
                self.display_units.get_first_invalid_row(),
                self.display_units.get_issue(),
            )
        if not plots:
            return _VisualizationIssue(
                VISUALIZATION_PLOTS,
                -1,
                "configured visualization requires at least one plot",
            )
        names = [str(plot.get("name", "")) for plot in plots]
        if len(set(names)) != len(names):
            duplicated = next(row for row, name in enumerate(names) if names.count(name) > 1)
            return _VisualizationIssue(
                VISUALIZATION_PLOTS,
                duplicated,
                "configured visualization plot names must be unique",
            )
        for row, problem in enumerate(self._plot_problems(plots)):
            if problem is not None:
                return _VisualizationIssue(VISUALIZATION_PLOTS, row, problem.message)
        return None

    def _plot_issues(self, plots: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
        return tuple(
            "" if problem is None else problem.message for problem in self._plot_problems(plots)
        )

    def _plot_problems(
        self,
        plots: tuple[dict[str, Any], ...],
    ) -> tuple[_VisualizationIssue | None, ...]:
        names = [str(plot.get("name", "")) for plot in plots]
        issues: list[_VisualizationIssue | None] = []
        for plot, name in zip(plots, names, strict=True):
            if name and names.count(name) > 1:
                issues.append(
                    _VisualizationIssue(
                        PLOT_NAME,
                        -1,
                        f"configured visualization plot name {name!r} is duplicated",
                    )
                )
                continue
            try:
                effective = self._effective_plot(plot)
            except ValueError as exc:
                issues.append(_VisualizationIssue(PLOT_FILTERS, -1, str(exc)))
                continue
            if self._capabilities is None or not self._dataset_payload:
                issues.append(
                    _VisualizationIssue(
                        VISUALIZATION_PLOTS,
                        -1,
                        "Visualization capabilities and dataset context are required.",
                    )
                )
                continue
            probe = PlotDraft(self._capabilities, self._dataset_payload, effective)
            if probe.get_locally_valid():
                issues.append(None)
            else:
                issues.append(
                    _VisualizationIssue(
                        probe.get_first_invalid_field(),
                        probe.get_first_invalid_row(),
                        probe.get_issue(),
                    )
                )
        return tuple(issues)

    def _effective_plot(self, plot: Mapping[str, object]) -> dict[str, Any]:
        effective = copy.deepcopy(dict(plot))
        shared_filters = self.filters.mapping()
        plot_filters = _mapping(plot.get("filters"))
        for field, value in plot_filters.items():
            if field in shared_filters and shared_filters[field] != value:
                raise ValueError(
                    f"conflicting shared and per-plot visualization filters for {field!r}"
                )
        merged_filters = {**shared_filters, **plot_filters}
        if merged_filters:
            effective["filters"] = merged_filters
        else:
            effective.pop("filters", None)
        shared_units = self.display_units.mapping()
        plot_units = _mapping(plot.get("display_units"))
        merged_units = {**shared_units, **plot_units}
        if merged_units:
            effective["display_units"] = merged_units
        else:
            effective.pop("display_units", None)
        if "fluids" not in effective and self._fluids:
            effective["fluids"] = list(self._fluids)
        if "format" not in effective:
            effective["format"] = self._format
        return effective

    def _fluid_issue(self) -> str:
        canonical = self._canonical_fluid_values(self._fluids)
        if len(set(canonical)) != len(canonical):
            return "visualization fluid aliases resolve to duplicate canonical fluids"
        dataset = set(self._canonical_fluid_values(self._dataset_fluid_values()))
        for value, canonical_value in zip(self._fluids, canonical, strict=True):
            if canonical_value not in dataset:
                return f"visualization fluid {value!r} is not in the dataset"
        return ""

    def _canonical_bytes(self) -> bytes:
        return _visualization_bytes(self.visualization_payload())

    def _formats(self) -> tuple[str, ...]:
        return _string_tuple(self._visualization_capabilities().get("formats"))

    def _default_format(self) -> str:
        formats = self._formats()
        return "png" if "png" in formats or not formats else formats[0]

    def _dataset_fluid_values(self) -> tuple[str, ...]:
        return _string_tuple(self._dataset_payload.get("fluids"))

    def _canonical_fluid(self, value: str) -> str:
        lookup: dict[str, str] = {}
        capabilities = self._capabilities or {}
        fluids = capabilities.get("fluids")
        if isinstance(fluids, list):
            for entry in fluids:
                if not isinstance(entry, Mapping):
                    continue
                canonical = str(entry.get("name", ""))
                for candidate in (canonical, *_string_tuple(entry.get("aliases"))):
                    lookup[candidate.casefold()] = canonical
        return lookup.get(value.casefold(), value.casefold())

    def _canonical_fluid_values(self, values: Iterable[str]) -> tuple[str, ...]:
        return tuple(self._canonical_fluid(value) for value in values)

    def _visualization_capabilities(self) -> Mapping[str, object]:
        capabilities = self._capabilities or {}
        value = capabilities.get("visualization")
        return value if isinstance(value, Mapping) else {}

    def _field_kinds(self) -> dict[str, str]:
        definitions = self._visualization_capabilities().get("fields")
        return {
            str(item["name"]): str(item["kind"])
            for item in (definitions if isinstance(definitions, list) else [])
            if isinstance(item, Mapping) and "name" in item and "kind" in item
        }

    def _available_fields(self) -> set[str]:
        properties = _string_tuple(self._dataset_payload.get("properties"))
        fields = {"temperature", "pressure", "phase", "fluid", *properties}
        mode = self._dataset_payload.get("mode")
        if mode in {"saturation_table", "vapor_mass_fraction_table"}:
            fields.add("vapor_mass_fraction")
        if mode == "saturation_table":
            fields.add("saturation_endpoint")
        if "mass_density" in properties:
            fields.add("specific_volume")
        return fields

    def _observable_state(self) -> tuple[object, ...]:
        return (
            self._enabled,
            self._format,
            self._valid,
            self._issue,
            self._first_invalid_field,
            self._first_invalid_row,
            self._dirty,
            self.raw_state(),
        )

    def _emit_observable_changes(self, previous: tuple[object, ...]) -> None:
        current = self._observable_state()
        if previous[0] != current[0]:
            self.enabled_changed.emit()
        if previous[1] != current[1]:
            self.format_changed.emit()
        if previous[2:6] != current[2:6]:
            self.validity_changed.emit()
        if previous[6] != current[6]:
            self.dirty_changed.emit()


def _choice_items(values: Iterable[str], selected: str) -> list[DraftItem]:
    available = tuple(values)
    items = [
        DraftItem(
            value=value,
            display=value,
            canonical=value,
            selected=value == selected,
        )
        for value in available
    ]
    if selected and selected not in available:
        items.append(
            DraftItem(
                value=selected,
                display=f"Unavailable: {selected}",
                canonical=selected,
                compatible=False,
                selected=True,
                issue=f"visualization format {selected!r} is unavailable",
            )
        )
    return items


def _visualization_bytes(value: Mapping[str, object] | None) -> bytes:
    wrapper: dict[str, Any] = {}
    if value is not None:
        wrapper["visualization"] = copy.deepcopy(dict(value))
    return serialize_dataset_config(wrapper)


def _mapping(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple((str(key), _freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return copy.deepcopy(value)
