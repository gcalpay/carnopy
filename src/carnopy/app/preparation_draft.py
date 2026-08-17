from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.field_ids import (
    PREPARATION_AUXILIARY,
    PREPARATION_BASELINE_DIAGNOSTICS,
    PREPARATION_CATEGORICAL_FEATURES,
    PREPARATION_FEATURES,
    PREPARATION_MATRIX_DIAGNOSTICS,
    PREPARATION_OUTPUTS,
    PREPARATION_SCENARIO_ACTIVE,
    PREPARATION_SOURCE_POLICY,
    PREPARATION_TARGETS,
)
from carnopy.app.scenario_draft import ScenarioDraft
from carnopy.app.workflow_models import WorkflowListModel

DERIVED_FEATURES = (
    "specific_volume",
    "reduced_temperature",
    "reduced_pressure",
    "compressibility_factor",
)
CATEGORICAL_FIELDS = ("phase", "fluid")
ARRAY_FORMATS = ("npy", "npz", "safetensors")
ARRAY_DTYPES = ("float32", "float64")
BASELINE_MODELS = ("dummy_mean", "ridge", "hist_gradient_boosting")


class PreparationDraft(QObject):
    """Compose source-independent Preparation roles for the global document."""

    changed = Signal()
    validity_changed = Signal()
    dirty_changed = Signal()
    profile_changed = Signal()
    capability_changed = Signal()
    active_scenario_draft_changed = Signal()
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.numeric_choices = DraftListModel(self, disable_incompatible=True)
        self.derived_choices = DraftListModel(self, disable_incompatible=True)
        self.target_choices = DraftListModel(self, disable_incompatible=True)
        self.auxiliary_choices = DraftListModel(self, disable_incompatible=True)
        self.categorical_choices = DraftListModel(self, disable_incompatible=True)
        self.array_format_choices = DraftListModel(self, disable_incompatible=True)
        self.baseline_model_choices = DraftListModel(self, disable_incompatible=True)
        self.scenarios_model = WorkflowListModel(("name", "kind", "summary"), self)
        self._profile: dict[str, Any] = {}
        self._capabilities: dict[str, Any] = {}
        self._preserved: dict[str, Any] | None = None
        self._numeric: tuple[str, ...] = ()
        self._derived: tuple[str, ...] = ()
        self._categorical: dict[str, str | tuple[str, ...]] = {}
        self._targets: tuple[str, ...] = ()
        self._auxiliary: tuple[str, ...] = ()
        self._known_numeric: tuple[str, ...] = ()
        self._known_auxiliary: tuple[str, ...] = ()
        self._allow_partial_sweep = False
        self._array_formats: tuple[str, ...] = ()
        self._array_dtype = "float32"
        self._include_auxiliary = False
        self._matrix_enabled = False
        self._correlation_threshold = "0.995"
        self._near_constant_spread = "1e-12"
        self._baseline_enabled = False
        self._baseline_models: tuple[str, ...] = ("dummy_mean", "ridge")
        self._baseline_seed = "42"
        self._ridge_alpha = "1.0"
        self._histogram_iterations = "100"
        self._scenarios: tuple[dict[str, Any], ...] = ()
        self._active_scenario: ScenarioDraft | None = None
        self._active_scenario_row = -1
        self._safetensors_available = False
        self._safetensors_guidance = (
            'Install the optional dependency with: pip install "carnopy[ml]"'
        )
        self._analysis_available = False
        self._analysis_guidance = (
            'Install the optional dependency with: pip install "carnopy[analysis]"'
        )
        self._baseline: dict[str, Any] | None = None
        self._baseline_raw: tuple[object, ...] | None = None
        self._loaded = False
        self._loading = False
        self._refresh_models()

    def get_numeric_choices(self) -> QObject:
        return self.numeric_choices

    numericChoices = Property(QObject, get_numeric_choices, constant=True)

    def get_derived_choices(self) -> QObject:
        return self.derived_choices

    derivedChoices = Property(QObject, get_derived_choices, constant=True)

    def get_target_choices(self) -> QObject:
        return self.target_choices

    targetChoices = Property(QObject, get_target_choices, constant=True)

    def get_auxiliary_choices(self) -> QObject:
        return self.auxiliary_choices

    auxiliaryChoices = Property(QObject, get_auxiliary_choices, constant=True)

    def get_categorical_choices(self) -> QObject:
        return self.categorical_choices

    categoricalChoices = Property(QObject, get_categorical_choices, constant=True)

    def get_array_format_choices(self) -> QObject:
        return self.array_format_choices

    arrayFormatChoices = Property(QObject, get_array_format_choices, constant=True)

    def get_baseline_model_choices(self) -> QObject:
        return self.baseline_model_choices

    baselineModelChoices = Property(QObject, get_baseline_model_choices, constant=True)

    def get_scenarios_model(self) -> QObject:
        return self.scenarios_model

    scenarios = Property(QObject, get_scenarios_model, constant=True)

    def get_active_scenario_draft(self) -> QObject | None:
        return self._active_scenario

    activeScenarioDraft = Property(
        QObject,
        get_active_scenario_draft,
        notify=active_scenario_draft_changed,
    )

    def get_has_active_scenario_edit(self) -> bool:
        return self._active_scenario is not None

    hasActiveScenarioEdit = Property(
        bool,
        get_has_active_scenario_edit,
        notify=active_scenario_draft_changed,
    )

    def get_active_scenario_row(self) -> int:
        return self._active_scenario_row

    activeScenarioRow = Property(
        int,
        get_active_scenario_row,
        notify=active_scenario_draft_changed,
    )

    def get_allow_partial_sweep(self) -> bool:
        return self._allow_partial_sweep

    @Slot(bool, result=bool)
    def set_allow_partial_sweep(self, value: bool) -> bool:
        selected = bool(value)
        if selected == self._allow_partial_sweep:
            return False
        self._allow_partial_sweep = selected
        self._state_changed()
        return True

    def _set_allow_partial_sweep_property(self, value: bool) -> None:
        self.set_allow_partial_sweep(value)

    allowPartialSweep = Property(
        bool,
        get_allow_partial_sweep,
        _set_allow_partial_sweep_property,
        notify=changed,
    )

    def get_array_outputs_enabled(self) -> bool:
        return bool(self._array_formats)

    @Slot(bool, result=bool)
    def set_array_outputs_enabled(self, value: bool) -> bool:
        enabled = bool(value)
        if enabled == bool(self._array_formats):
            return False
        self._array_formats = ("npz",) if enabled else ()
        self._state_changed()
        return True

    def _set_array_outputs_enabled_property(self, value: bool) -> None:
        self.set_array_outputs_enabled(value)

    arrayOutputsEnabled = Property(
        bool,
        get_array_outputs_enabled,
        _set_array_outputs_enabled_property,
        notify=changed,
    )

    def get_array_dtype(self) -> str:
        return self._array_dtype

    @Slot(str, result=bool)
    def set_array_dtype(self, value: str) -> bool:
        if value not in ARRAY_DTYPES or value == self._array_dtype:
            return False
        self._array_dtype = value
        self._state_changed()
        return True

    def _set_array_dtype_property(self, value: str) -> None:
        self.set_array_dtype(value)

    arrayDtype = Property(str, get_array_dtype, _set_array_dtype_property, notify=changed)

    def get_include_auxiliary(self) -> bool:
        return self._include_auxiliary

    @Slot(bool, result=bool)
    def set_include_auxiliary(self, value: bool) -> bool:
        selected = bool(value)
        if selected == self._include_auxiliary:
            return False
        self._include_auxiliary = selected
        self._state_changed()
        return True

    def _set_include_auxiliary_property(self, value: bool) -> None:
        self.set_include_auxiliary(value)

    includeAuxiliary = Property(
        bool,
        get_include_auxiliary,
        _set_include_auxiliary_property,
        notify=changed,
    )

    def get_matrix_enabled(self) -> bool:
        return self._matrix_enabled

    @Slot(bool, result=bool)
    def set_matrix_enabled(self, value: bool) -> bool:
        selected = bool(value)
        if selected == self._matrix_enabled:
            return False
        self._matrix_enabled = selected
        self._state_changed()
        return True

    def _set_matrix_enabled_property(self, value: bool) -> None:
        self.set_matrix_enabled(value)

    matrixDiagnosticsEnabled = Property(
        bool,
        get_matrix_enabled,
        _set_matrix_enabled_property,
        notify=changed,
    )

    def get_correlation_threshold(self) -> str:
        return self._correlation_threshold

    @Slot(str, result=bool)
    def set_correlation_threshold(self, value: str) -> bool:
        return self._set_text("_correlation_threshold", value)

    def _set_correlation_threshold_property(self, value: str) -> None:
        self.set_correlation_threshold(value)

    correlationThreshold = Property(
        str,
        get_correlation_threshold,
        _set_correlation_threshold_property,
        notify=changed,
    )

    def get_near_constant_spread(self) -> str:
        return self._near_constant_spread

    @Slot(str, result=bool)
    def set_near_constant_spread(self, value: str) -> bool:
        return self._set_text("_near_constant_spread", value)

    def _set_near_constant_spread_property(self, value: str) -> None:
        self.set_near_constant_spread(value)

    nearConstantRelativeSpread = Property(
        str,
        get_near_constant_spread,
        _set_near_constant_spread_property,
        notify=changed,
    )

    def get_baseline_enabled(self) -> bool:
        return self._baseline_enabled

    @Slot(bool, result=bool)
    def set_baseline_enabled(self, value: bool) -> bool:
        selected = bool(value)
        if selected == self._baseline_enabled:
            return False
        if selected and not self._analysis_available:
            self.message.emit(self._analysis_guidance)
            return False
        self._baseline_enabled = selected
        self._state_changed()
        return True

    def _set_baseline_enabled_property(self, value: bool) -> None:
        self.set_baseline_enabled(value)

    baselineDiagnosticsEnabled = Property(
        bool,
        get_baseline_enabled,
        _set_baseline_enabled_property,
        notify=changed,
    )

    def get_baseline_seed(self) -> str:
        return self._baseline_seed

    @Slot(str, result=bool)
    def set_baseline_seed(self, value: str) -> bool:
        return self._set_text("_baseline_seed", value)

    def _set_baseline_seed_property(self, value: str) -> None:
        self.set_baseline_seed(value)

    baselineRandomSeed = Property(
        str,
        get_baseline_seed,
        _set_baseline_seed_property,
        notify=changed,
    )

    def get_ridge_alpha(self) -> str:
        return self._ridge_alpha

    @Slot(str, result=bool)
    def set_ridge_alpha(self, value: str) -> bool:
        return self._set_text("_ridge_alpha", value)

    def _set_ridge_alpha_property(self, value: str) -> None:
        self.set_ridge_alpha(value)

    ridgeAlpha = Property(str, get_ridge_alpha, _set_ridge_alpha_property, notify=changed)

    def get_histogram_iterations(self) -> str:
        return self._histogram_iterations

    @Slot(str, result=bool)
    def set_histogram_iterations(self, value: str) -> bool:
        return self._set_text("_histogram_iterations", value)

    def _set_histogram_iterations_property(self, value: str) -> None:
        self.set_histogram_iterations(value)

    histogramMaxIterations = Property(
        str,
        get_histogram_iterations,
        _set_histogram_iterations_property,
        notify=changed,
    )

    def get_safetensors_available(self) -> bool:
        return self._safetensors_available

    safetensorsAvailable = Property(bool, get_safetensors_available, notify=capability_changed)

    def get_baseline_available(self) -> bool:
        return self._analysis_available

    baselineDiagnosticsAvailable = Property(
        bool,
        get_baseline_available,
        notify=capability_changed,
    )

    def get_baseline_guidance(self) -> str:
        return "" if self._analysis_available else self._analysis_guidance

    baselineDiagnosticsGuidance = Property(
        str,
        get_baseline_guidance,
        notify=capability_changed,
    )

    def get_dependency_issue(self) -> str:
        if "safetensors" in self._array_formats and not self._safetensors_available:
            return self._safetensors_guidance
        if self._baseline_enabled and not self._analysis_available:
            return self._analysis_guidance
        return ""

    dependencyIssue = Property(str, get_dependency_issue, notify=capability_changed)

    def get_source_kind(self) -> str:
        value = self._profile.get("source_kind")
        return value if isinstance(value, str) else ""

    sourceKind = Property(str, get_source_kind, notify=profile_changed)

    def get_profile_available(self) -> bool:
        return bool(self._profile)

    profileAvailable = Property(bool, get_profile_available, notify=profile_changed)

    def get_locally_valid(self) -> bool:
        return not self.get_issue()

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        if not self._loaded:
            return "No ML Preparation configuration is open."
        try:
            self.payload()
        except ValueError as exc:
            return str(exc)
        return ""

    issue = Property(str, get_issue, notify=validity_changed)

    def get_source_issue(self) -> str:
        if not self._profile:
            return ""
        completion = self._profile.get("completion")
        if (
            self.get_source_kind() == "model_sweep"
            and isinstance(completion, Mapping)
            and bool(completion.get("partial", False))
            and not self._allow_partial_sweep
        ):
            return (
                "The bound Model Sweep is partial. Enable the explicit partial-sweep source "
                "policy before planning."
            )
        checks = (
            ("numeric feature", self._numeric, self._candidate_names("numeric_candidates")),
            ("target", self._targets, self._candidate_names("target_candidates")),
            ("auxiliary field", self._auxiliary, self._candidate_names("auxiliary_candidates")),
            (
                "categorical feature",
                tuple(self._categorical),
                self._candidate_names("categorical_candidates"),
            ),
        )
        for label, selected, available in checks:
            missing = [value for value in selected if value not in available]
            if missing:
                return (
                    f"Selected {label}s are unavailable in the bound source: {', '.join(missing)}."
                )
        derived = self._derived_status()
        unavailable_derived = [
            value for value in self._derived if not bool(derived.get(value, {}).get("available"))
        ]
        if unavailable_derived:
            return (
                "Selected derived features are unavailable in the bound source: "
                + ", ".join(unavailable_derived)
                + "."
            )
        if issue := self._committed_scenario_source_issue():
            return issue
        reference_context = self._profile.get("reference_context")
        if isinstance(reference_context, Mapping) and not bool(
            reference_context.get("compatible", False)
        ):
            selected = (*self._numeric, *self._targets)
            reference_dependent = self._reference_dependent_fields()
            affected = [value for value in selected if value in reference_dependent]
            if affected:
                reason = str(reference_context.get("reason", "")).strip()
                return reason or (
                    "The bound source has incompatible reference contexts for: "
                    + ", ".join(affected)
                    + "."
                )
        return ""

    sourceIssue = Property(str, get_source_issue, notify=profile_changed)

    def get_model_holdout_available(self) -> bool:
        model_holdout = self._profile.get("model_holdout")
        return isinstance(model_holdout, Mapping) and bool(model_holdout.get("available", False))

    modelHoldoutAvailable = Property(
        bool,
        get_model_holdout_available,
        notify=profile_changed,
    )

    def get_model_holdout_issue(self) -> str:
        if self.get_model_holdout_available():
            return ""
        if not self._profile:
            return "Bind an eligible Model Sweep source before adding a model holdout scenario."
        model_holdout = self._profile.get("model_holdout")
        if isinstance(model_holdout, Mapping):
            reason = str(model_holdout.get("reason", "")).strip()
            if reason:
                return reason
        return "Model holdout scenarios are unavailable for the bound source."

    modelHoldoutIssue = Property(
        str,
        get_model_holdout_issue,
        notify=profile_changed,
    )

    def get_first_invalid_field(self) -> str:
        if self._active_scenario is not None:
            return self._active_scenario.get_first_invalid_field() or PREPARATION_SCENARIO_ACTIVE
        issue = self.get_issue().casefold()
        if not issue:
            return ""
        if "target" in issue:
            return PREPARATION_TARGETS
        if "auxiliary" in issue:
            return PREPARATION_AUXILIARY
        if "categor" in issue:
            return PREPARATION_CATEGORICAL_FEATURES
        if "partial" in issue or "source policy" in issue:
            return PREPARATION_SOURCE_POLICY
        if "baseline" in issue or "ridge" in issue or "histogram" in issue:
            return PREPARATION_BASELINE_DIAGNOSTICS
        if "matrix" in issue or "correlation" in issue or "spread" in issue:
            return PREPARATION_MATRIX_DIAGNOSTICS
        if "array" in issue or "parquet" in issue or "output" in issue or "dtype" in issue:
            return PREPARATION_OUTPUTS
        return PREPARATION_FEATURES

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        if self._active_scenario is not None:
            nested_row = self._active_scenario.get_first_invalid_row()
            return nested_row if nested_row >= 0 else self._active_scenario_row
        return -1

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def get_transient_edit_issue(self) -> str:
        if self._active_scenario is None:
            return ""
        return self._active_scenario.get_issue() or (
            "Commit or cancel the active Preparation scenario edit."
        )

    def get_dirty(self) -> bool:
        if self._baseline is None or self._baseline_raw is None:
            return False
        try:
            return self.payload() != self._baseline
        except ValueError:
            return self.raw_state() != self._baseline_raw

    dirty = Property(bool, get_dirty, notify=dirty_changed)

    def apply_capabilities(self, payload: Mapping[str, object]) -> bool:
        updated = copy.deepcopy(dict(payload))
        workflows = payload.get("workflows")
        preparation = workflows.get("preparation") if isinstance(workflows, Mapping) else None
        safetensors_available = False
        safetensors_guidance = self._safetensors_guidance
        analysis_available = False
        analysis_guidance = self._analysis_guidance
        if isinstance(preparation, Mapping):
            safetensors = preparation.get("safetensors")
            if isinstance(safetensors, Mapping):
                safetensors_available = bool(safetensors.get("available", False))
                safetensors_guidance = str(safetensors.get("guidance", safetensors_guidance))
            baseline = preparation.get("baseline_diagnostics")
            if isinstance(baseline, Mapping):
                analysis_available = bool(baseline.get("available", False))
                analysis_guidance = str(baseline.get("guidance", analysis_guidance))
        semantic = (
            updated,
            safetensors_available,
            safetensors_guidance,
            analysis_available,
            analysis_guidance,
        )
        current = (
            self._capabilities,
            self._safetensors_available,
            self._safetensors_guidance,
            self._analysis_available,
            self._analysis_guidance,
        )
        if semantic == current:
            return False
        self._capabilities = updated
        self._safetensors_available = safetensors_available
        self._safetensors_guidance = safetensors_guidance
        self._analysis_available = analysis_available
        self._analysis_guidance = analysis_guidance
        self._refresh_models()
        self.capability_changed.emit()
        return True

    def apply_source_profile(self, profile: Mapping[str, object] | None) -> bool:
        updated = copy.deepcopy(dict(profile)) if profile is not None else {}
        if updated == self._profile:
            return False
        self._profile = updated
        self._refresh_models()
        self.profile_changed.emit()
        return True

    def load_payload(self, payload: Mapping[str, object]) -> None:
        from carnopy.preparation.models import PreparationConfig

        validated = PreparationConfig.model_validate(payload)
        value = validated.model_dump(mode="json", exclude_none=True)
        source_policy = _mapping(value.get("source_policy"))
        features = _mapping(value.get("features"))
        categorical = value.get("categorical_features")
        quality = _mapping(value.get("quality"))
        outputs = _mapping(value.get("outputs"))
        scenarios = value.get("scenarios")
        had_active_scenario = self._active_scenario is not None
        self._loading = True
        try:
            self._discard_active_scenario()
            self._preserved = copy.deepcopy(value)
            self._allow_partial_sweep = bool(source_policy.get("allow_partial_sweep", False))
            self._numeric = _strings(features.get("numeric"))
            self._derived = _strings(features.get("derived"))
            self._targets = _strings(value.get("targets"))
            self._auxiliary = _strings(value.get("auxiliary"))
            self._known_numeric = tuple(dict.fromkeys((*self._numeric, *self._targets)))
            self._known_auxiliary = self._auxiliary
            self._categorical = {}
            if isinstance(categorical, list):
                for raw_item in categorical:
                    if not isinstance(raw_item, Mapping):
                        continue
                    field = str(raw_item.get("field", ""))
                    raw_categories = raw_item.get("categories", "observed")
                    categories: str | tuple[str, ...] = (
                        _strings(raw_categories)
                        if isinstance(raw_categories, list | tuple)
                        else "observed"
                    )
                    self._categorical[field] = categories
            arrays = outputs.get("arrays")
            if isinstance(arrays, Mapping):
                self._array_formats = _strings(arrays.get("formats"))
                self._array_dtype = str(arrays.get("dtype", "float32"))
                self._include_auxiliary = bool(arrays.get("include_auxiliary", False))
            else:
                self._array_formats = ()
                self._array_dtype = "float32"
                self._include_auxiliary = False
            matrix = quality.get("matrix_diagnostics")
            self._matrix_enabled = isinstance(matrix, Mapping)
            self._correlation_threshold = _number_text(
                matrix.get("correlation_threshold", 0.995) if isinstance(matrix, Mapping) else 0.995
            )
            self._near_constant_spread = _number_text(
                matrix.get("near_constant_relative_spread", 1e-12)
                if isinstance(matrix, Mapping)
                else 1e-12
            )
            baseline = quality.get("baseline_diagnostics")
            self._baseline_enabled = isinstance(baseline, Mapping)
            if isinstance(baseline, Mapping):
                self._baseline_models = _strings(baseline.get("models"))
                self._baseline_seed = str(baseline.get("random_seed", 42))
                self._ridge_alpha = _number_text(baseline.get("ridge_alpha", 1.0))
                self._histogram_iterations = str(baseline.get("histogram_max_iterations", 100))
            else:
                self._baseline_models = ("dummy_mean", "ridge")
                self._baseline_seed = "42"
                self._ridge_alpha = "1.0"
                self._histogram_iterations = "100"
            self._scenarios = (
                tuple(copy.deepcopy(dict(item)) for item in scenarios if isinstance(item, Mapping))
                if isinstance(scenarios, list)
                else ()
            )
            self._loaded = True
            self._refresh_models()
        finally:
            self._loading = False
        self._baseline = copy.deepcopy(value)
        self._baseline_raw = self.raw_state()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.capability_changed.emit()
        self.changed.emit()
        if had_active_scenario:
            self.active_scenario_draft_changed.emit()

    def clear(self) -> None:
        had_active_scenario = self._active_scenario is not None
        self._loading = True
        try:
            self._discard_active_scenario()
            self._preserved = None
            self._numeric = ()
            self._derived = ()
            self._categorical = {}
            self._targets = ()
            self._auxiliary = ()
            self._known_numeric = ()
            self._known_auxiliary = ()
            self._allow_partial_sweep = False
            self._array_formats = ()
            self._array_dtype = "float32"
            self._include_auxiliary = False
            self._matrix_enabled = False
            self._correlation_threshold = "0.995"
            self._near_constant_spread = "1e-12"
            self._baseline_enabled = False
            self._baseline_models = ("dummy_mean", "ridge")
            self._baseline_seed = "42"
            self._ridge_alpha = "1.0"
            self._histogram_iterations = "100"
            self._scenarios = ()
            self._baseline = None
            self._baseline_raw = None
            self._loaded = False
            self._refresh_models()
        finally:
            self._loading = False
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.capability_changed.emit()
        self.changed.emit()
        if had_active_scenario:
            self.active_scenario_draft_changed.emit()

    def mark_baseline(self) -> None:
        if issue := self.get_issue():
            raise ValueError(f"cannot mark an invalid ML Preparation draft as saved: {issue}")
        self._baseline = self.payload()
        self._baseline_raw = self.raw_state()
        self.dirty_changed.emit()

    @Slot(result=bool)
    def begin_add_scenario(self) -> bool:
        if not self._loaded or self._active_scenario is not None:
            return False
        self._active_scenario_row = -1
        self._active_scenario = ScenarioDraft(
            field_choices=self._scenario_field_choices(),
            parent=self,
        )
        self._active_scenario.validity_changed.connect(self.validity_changed.emit)
        self.active_scenario_draft_changed.emit()
        self.validity_changed.emit()
        return True

    @Slot(int, result=bool)
    def begin_edit_scenario(self, row: int) -> bool:
        if self._active_scenario is not None or not 0 <= row < len(self._scenarios):
            return False
        self._active_scenario_row = row
        self._active_scenario = ScenarioDraft(
            field_choices=self._scenario_field_choices(),
            payload=self._scenarios[row],
            parent=self,
        )
        self._active_scenario.validity_changed.connect(self.validity_changed.emit)
        self.active_scenario_draft_changed.emit()
        self.validity_changed.emit()
        return True

    @Slot(result=bool)
    def commit_scenario(self) -> bool:
        draft = self._active_scenario
        if draft is None:
            return False
        try:
            value = draft.detached_payload()
        except ValueError as exc:
            self.message.emit(str(exc))
            return False
        names = [str(item.get("name", "")) for item in self._scenarios]
        if value["name"] in names and (
            self._active_scenario_row < 0 or names[self._active_scenario_row] != value["name"]
        ):
            self.message.emit("Preparation scenario names must be unique.")
            return False
        updated = list(self._scenarios)
        if self._active_scenario_row < 0:
            updated.append(value)
        else:
            updated[self._active_scenario_row] = value
        changed = tuple(updated) != self._scenarios
        if not changed:
            self._discard_active_scenario()
            self.active_scenario_draft_changed.emit()
            self.validity_changed.emit()
            return True
        if issue := self._scenario_value_source_issue(value):
            self.message.emit(issue)
            return False
        try:
            self._validated_payload(tuple(updated))
        except ValueError as exc:
            self.message.emit(str(exc))
            return False
        self._scenarios = tuple(updated)
        self._discard_active_scenario()
        self.active_scenario_draft_changed.emit()
        self._state_changed()
        return True

    @Slot(result=bool)
    def cancel_scenario(self) -> bool:
        if self._active_scenario is None:
            return False
        self._discard_active_scenario()
        self.active_scenario_draft_changed.emit()
        self.validity_changed.emit()
        return True

    @Slot(int, result=bool)
    def remove_scenario(self, row: int) -> bool:
        if self._active_scenario is not None or not 0 <= row < len(self._scenarios):
            return False
        self._scenarios = (*self._scenarios[:row], *self._scenarios[row + 1 :])
        self._state_changed()
        return True

    @Slot(int, int, result=bool)
    def move_scenario(self, source: int, destination: int) -> bool:
        values = list(self._scenarios)
        if (
            self._active_scenario is not None
            or not 0 <= source < len(values)
            or not 0 <= destination < len(values)
            or source == destination
        ):
            return False
        item = values.pop(source)
        values.insert(destination, item)
        self._scenarios = tuple(values)
        self._state_changed()
        return True

    def payload(self) -> dict[str, Any]:
        return self._validated_payload(self._scenarios)

    def _validated_payload(
        self,
        scenarios: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        from carnopy.preparation.models import PreparationConfig

        if not self._loaded or self._preserved is None:
            raise ValueError("No ML Preparation configuration is open.")
        result = copy.deepcopy(self._preserved)
        result["source_policy"] = {"allow_partial_sweep": self._allow_partial_sweep}
        result["features"] = {
            "numeric": list(self._numeric),
            "derived": list(self._derived),
        }
        result["categorical_features"] = [
            {
                "field": field,
                "encoding": "one_hot",
                "categories": list(categories) if isinstance(categories, tuple) else categories,
            }
            for field, categories in self._categorical.items()
        ]
        result["targets"] = list(self._targets)
        result["auxiliary"] = list(self._auxiliary)
        result["scenarios"] = copy.deepcopy(list(scenarios))
        quality: dict[str, Any] = {}
        if self._matrix_enabled:
            quality["matrix_diagnostics"] = {
                "correlation_threshold": _bounded_float(
                    self._correlation_threshold,
                    "correlation threshold",
                    maximum=1.0,
                ),
                "near_constant_relative_spread": _positive_float(
                    self._near_constant_spread,
                    "near-constant relative spread",
                ),
            }
        if self._baseline_enabled:
            quality["baseline_diagnostics"] = {
                "models": list(self._baseline_models),
                "random_seed": _integer(self._baseline_seed, "baseline random seed"),
                "ridge_alpha": _positive_float(self._ridge_alpha, "ridge alpha"),
                "histogram_max_iterations": _positive_integer(
                    self._histogram_iterations,
                    "histogram maximum iterations",
                ),
            }
        result["quality"] = quality
        outputs: dict[str, Any] = {"formats": ["parquet"], "parquet": True}
        if self._array_formats:
            outputs["arrays"] = {
                "formats": list(self._array_formats),
                "dtype": self._array_dtype,
                "include_auxiliary": self._include_auxiliary,
            }
        result["outputs"] = outputs
        try:
            model = PreparationConfig.model_validate(result)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump(mode="json", exclude_none=True)

    def scenario_payloads(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(item) for item in self._scenarios)

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._loaded,
            self._allow_partial_sweep,
            self._numeric,
            self._derived,
            tuple(self._categorical.items()),
            self._targets,
            self._auxiliary,
            copy.deepcopy(self._scenarios),
            self._array_formats,
            self._array_dtype,
            self._include_auxiliary,
            self._matrix_enabled,
            self._correlation_threshold,
            self._near_constant_spread,
            self._baseline_enabled,
            self._baseline_models,
            self._baseline_seed,
            self._ridge_alpha,
            self._histogram_iterations,
        )

    def selected_values(self, role: str) -> tuple[str, ...]:
        attribute = _role_attribute(role)
        return () if attribute is None else tuple(getattr(self, attribute))

    @Slot(str, bool, result=bool)
    def set_role_selected(self, role: str, value: str, selected: bool) -> bool:
        attribute = _role_attribute(role)
        model = self._role_model(role)
        if attribute is None or model is None:
            return False
        current = list(getattr(self, attribute))
        if selected:
            candidate = next((item for item in model.items if item.value == value), None)
            if candidate is None or not candidate.compatible:
                self.message.emit(
                    candidate.issue if candidate is not None else f"Unknown {role}: {value}."
                )
                return False
            if value in current:
                return False
            current.append(value)
        else:
            if value not in current:
                return False
            current.remove(value)
        setattr(self, attribute, tuple(current))
        self._state_changed()
        return True

    @Slot(str, bool, result=bool)
    def set_categorical_selected(self, field: str, selected: bool) -> bool:
        if field not in CATEGORICAL_FIELDS:
            return False
        if selected:
            candidate = next(
                (item for item in self.categorical_choices.items if item.value == field),
                None,
            )
            if candidate is None or not candidate.compatible:
                self.message.emit(
                    candidate.issue if candidate is not None else f"Unknown category: {field}."
                )
                return False
            if field in self._categorical:
                return False
            self._categorical[field] = "observed"
        else:
            if field not in self._categorical:
                return False
            del self._categorical[field]
        self._state_changed()
        return True

    @Slot(str, str, bool, result=bool)
    def set_category_mode(
        self,
        field: str,
        mode: str,
        discard_confirmed: bool = False,
    ) -> bool:
        current = self._categorical.get(field)
        if current is None or mode not in {"observed", "explicit"}:
            return False
        if mode == self.category_mode(field):
            return False
        if mode == "observed" and current and not discard_confirmed:
            self.message.emit(
                "Confirm replacing the explicit category list with source-observed values."
            )
            return False
        self._categorical[field] = "observed" if mode == "observed" else ()
        self._state_changed()
        return True

    @Slot(str, str, result=bool)
    def set_explicit_categories(self, field: str, comma_values: str) -> bool:
        current = self._categorical.get(field)
        if not isinstance(current, tuple):
            return False
        raw_values = tuple(item.strip() for item in comma_values.split(","))
        if len(raw_values) == 1 and not raw_values[0]:
            values: tuple[str, ...] = ()
        elif any(not item for item in raw_values):
            self.message.emit("Explicit categories must not contain blank values.")
            return False
        else:
            values = raw_values
        if len(set(values)) != len(values):
            self.message.emit("Explicit categories must be unique.")
            return False
        if values == current:
            return False
        self._categorical[field] = values
        self._state_changed()
        return True

    @Slot(str, result=str)
    def category_mode(self, field: str) -> str:
        return "explicit" if isinstance(self._categorical.get(field), tuple) else "observed"

    @Slot(str, result=str)
    def explicit_categories_text(self, field: str) -> str:
        values = self._categorical.get(field)
        return ", ".join(values) if isinstance(values, tuple) else ""

    @Slot(str, result=list)
    def observed_categories(self, field: str) -> list[str]:
        observed = self._profile.get("observed_category_values")
        values = observed.get(field) if isinstance(observed, Mapping) else None
        return list(_strings(values))

    @Slot(str, bool, result=bool)
    def set_array_format_selected(self, value: str, selected: bool) -> bool:
        if value not in ARRAY_FORMATS:
            return False
        values = list(self._array_formats)
        if selected:
            candidate = next(
                (item for item in self.array_format_choices.items if item.value == value),
                None,
            )
            if candidate is None or not candidate.compatible:
                self.message.emit(
                    candidate.issue if candidate is not None else f"Unknown array format: {value}."
                )
                return False
            if value in values:
                return False
            values.append(value)
        else:
            if value not in values:
                return False
            values.remove(value)
        self._array_formats = tuple(item for item in ARRAY_FORMATS if item in values)
        self._state_changed()
        return True

    @Slot(str, bool, result=bool)
    def set_baseline_model_selected(self, value: str, selected: bool) -> bool:
        if value not in BASELINE_MODELS:
            return False
        values = list(self._baseline_models)
        if selected:
            candidate = next(
                (item for item in self.baseline_model_choices.items if item.value == value),
                None,
            )
            if candidate is None or not candidate.compatible:
                self.message.emit(
                    candidate.issue
                    if candidate is not None
                    else f"Unknown baseline model: {value}."
                )
                return False
            if value in values:
                return False
            values.append(value)
        else:
            if value not in values:
                return False
            values.remove(value)
        self._baseline_models = tuple(item for item in BASELINE_MODELS if item in values)
        self._state_changed()
        return True

    def _set_text(self, attribute: str, value: str) -> bool:
        updated = value.strip()
        if updated == getattr(self, attribute):
            return False
        setattr(self, attribute, updated)
        self._state_changed()
        return True

    def _state_changed(self) -> None:
        if self._loading:
            return
        self._refresh_models()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.profile_changed.emit()
        self.capability_changed.emit()
        self.changed.emit()

    def _discard_active_scenario(self) -> None:
        if self._active_scenario is not None:
            self._active_scenario.deleteLater()
        self._active_scenario = None
        self._active_scenario_row = -1

    def _scenario_field_choices(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self._candidate_names("numeric_candidates"),
                    *self._candidate_names("target_candidates"),
                    *self._candidate_names("auxiliary_candidates"),
                    *self._candidate_names("categorical_candidates"),
                    *self._numeric,
                    *self._derived,
                    *self._targets,
                    *self._auxiliary,
                    *self._categorical,
                    "phase",
                    "fluid",
                    "backend_model",
                )
            )
        )

    def _committed_scenario_source_issue(self) -> str:
        for scenario in self._scenarios:
            if issue := self._scenario_value_source_issue(scenario):
                return issue
        return ""

    def _scenario_value_source_issue(self, scenario: Mapping[str, object]) -> str:
        kind = str(scenario.get("kind", ""))
        name = str(scenario.get("name", "scenario"))
        if kind == "model_holdout" and not self.get_model_holdout_available():
            return self.get_model_holdout_issue()
        if not self._profile:
            return ""
        category_field = {
            "leave_fluid_out": "fluid",
            "phase_holdout": "phase",
            "model_holdout": "backend_model",
        }.get(kind)
        if category_field is None:
            return ""
        if category_field == "backend_model":
            available = _strings(self._profile.get("available_models"))
        else:
            observed = self._profile.get("observed_category_values")
            available = (
                _strings(observed.get(category_field)) if isinstance(observed, Mapping) else ()
            )
        holdouts = scenario.get("holdouts")
        selected = (
            tuple(
                str(item)
                for values in holdouts.values()
                if isinstance(values, list | tuple)
                for item in values
            )
            if isinstance(holdouts, Mapping)
            else ()
        )
        unavailable = tuple(value for value in selected if value not in available)
        if not unavailable:
            return ""
        return (
            f"Scenario {name!r} selects unavailable {_display(category_field).lower()} "
            f"holdout values: {', '.join(unavailable)}."
        )

    def _role_model(self, role: str) -> DraftListModel | None:
        return {
            "numeric": self.numeric_choices,
            "derived": self.derived_choices,
            "target": self.target_choices,
            "auxiliary": self.auxiliary_choices,
        }.get(role)

    def _candidate_names(self, key: str) -> tuple[str, ...]:
        return tuple(item["name"] for item in self._candidate_profiles(key))

    def _candidate_profiles(self, key: str) -> tuple[dict[str, Any], ...]:
        raw = self._profile.get(key)
        if not isinstance(raw, list):
            return ()
        return tuple(copy.deepcopy(item) for item in raw if isinstance(item, dict))

    def _derived_status(self) -> dict[str, dict[str, Any]]:
        raw = self._profile.get("derived_features")
        if not isinstance(raw, list):
            return {}
        return {
            str(item.get("name")): copy.deepcopy(item) for item in raw if isinstance(item, dict)
        }

    def _reference_dependent_fields(self) -> set[str]:
        result: set[str] = set()
        for key in ("numeric_candidates", "target_candidates"):
            result.update(
                str(item.get("name"))
                for item in self._candidate_profiles(key)
                if bool(item.get("reference_dependent", False))
            )
        return result

    def _refresh_models(self) -> None:
        self.numeric_choices.replace(self._role_items("numeric"))
        self.derived_choices.replace(self._derived_items())
        self.target_choices.replace(self._role_items("target"))
        self.auxiliary_choices.replace(self._role_items("auxiliary"))
        categorical_available = self._candidate_names("categorical_candidates")
        visible_categorical = tuple(dict.fromkeys((*CATEGORICAL_FIELDS, *self._categorical)))
        self.categorical_choices.replace(
            DraftItem(
                value=value,
                display=_display(value),
                canonical=value,
                compatible=(not self._profile or value in categorical_available),
                selected=value in self._categorical,
                issue=(
                    "Unavailable in the bound source."
                    if self._profile and value not in categorical_available
                    else ""
                ),
            )
            for value in visible_categorical
        )
        self.array_format_choices.replace(
            DraftItem(
                value=value,
                display=value.upper(),
                canonical=value,
                compatible=value != "safetensors" or self._safetensors_available,
                selected=value in self._array_formats,
                issue=(
                    self._safetensors_guidance
                    if value == "safetensors" and not self._safetensors_available
                    else ""
                ),
            )
            for value in ARRAY_FORMATS
        )
        self.baseline_model_choices.replace(
            DraftItem(
                value=value,
                display=_display(value),
                canonical=value,
                compatible=self._analysis_available,
                selected=value in self._baseline_models,
                issue="" if self._analysis_available else self._analysis_guidance,
            )
            for value in BASELINE_MODELS
        )
        self.scenarios_model.replace(
            {
                "name": str(item.get("name", "")),
                "kind": str(item.get("kind", "")),
                "summary": _scenario_summary(item),
            }
            for item in self._scenarios
        )
        if self._active_scenario is not None:
            self._active_scenario.set_field_choices(self._scenario_field_choices())

    def _role_items(self, role: str) -> tuple[DraftItem, ...]:
        key = {
            "numeric": "numeric_candidates",
            "target": "target_candidates",
            "auxiliary": "auxiliary_candidates",
        }[role]
        selected = self.selected_values(role)
        profiles = self._candidate_profiles(key)
        by_name = {str(item.get("name")): item for item in profiles}
        known = self._known_auxiliary if role == "auxiliary" else self._known_numeric
        visible = tuple(dict.fromkeys((*by_name, *known, *selected)))
        return tuple(
            self._role_item(role, value, by_name.get(value), selected=value in selected)
            for value in visible
        )

    def _role_item(
        self,
        role: str,
        value: str,
        profile: Mapping[str, object] | None,
        *,
        selected: bool,
    ) -> DraftItem:
        issue = self._role_choice_issue(role, value, profile)
        return DraftItem(
            value=value,
            display=_display(value),
            canonical=value,
            compatible=not issue,
            selected=selected,
            issue=issue,
            label=str(profile.get("column", "")) if profile is not None else "",
            unit=str(profile.get("unit") or "") if profile is not None else "",
        )

    def _role_choice_issue(
        self,
        role: str,
        value: str,
        profile: Mapping[str, object] | None,
    ) -> str:
        if self._profile and profile is None:
            return "Unavailable in the bound source."
        conflicts = {
            "numeric": (*self._derived, *self._targets, *self._auxiliary),
            "target": (*self._numeric, *self._derived, *self._auxiliary),
            "auxiliary": (*self._numeric, *self._derived, *self._targets),
        }[role]
        if value in conflicts:
            return "Already selected for an incompatible Preparation role."
        return ""

    def _derived_items(self) -> tuple[DraftItem, ...]:
        status = self._derived_status()
        visible = tuple(dict.fromkeys((*DERIVED_FEATURES, *self._derived)))
        return tuple(
            DraftItem(
                value=value,
                display=_display(value),
                canonical=value,
                compatible=(
                    value not in (*self._targets, *self._auxiliary)
                    and (not self._profile or bool(status.get(value, {}).get("available", False)))
                ),
                selected=value in self._derived,
                issue=(
                    "Already selected for an incompatible Preparation role."
                    if value in (*self._targets, *self._auxiliary)
                    else str(status.get(value, {}).get("reason", ""))
                    or ("Unavailable in the bound source." if self._profile else "")
                ),
                unit=str(status.get(value, {}).get("unit") or ""),
            )
            for value in visible
        )


def _role_attribute(role: str) -> str | None:
    return {
        "numeric": "_numeric",
        "derived": "_derived",
        "target": "_targets",
        "auxiliary": "_auxiliary",
    }.get(role)


def _mapping(value: object) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _strings(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list | tuple) else ()


def _number_text(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    return format(float(value), ".12g") if isinstance(value, int | float) else str(value)


def _positive_float(value: str, label: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and greater than zero")
    return result


def _bounded_float(value: str, label: str, *, maximum: float) -> float:
    result = _positive_float(value, label)
    if result > maximum:
        raise ValueError(f"{label} must be at most {maximum:g}")
    return result


def _integer(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc


def _positive_integer(value: str, label: str) -> int:
    result = _integer(value, label)
    if result < 1:
        raise ValueError(f"{label} must be at least one")
    return result


def _display(value: str) -> str:
    return value.replace("_", " ").title()


def _scenario_summary(value: Mapping[str, object]) -> str:
    kind = str(value.get("kind", "scenario"))
    details: list[str] = []
    partitions = value.get("partitions")
    if kind == "unsplit":
        details.append("All partition")
    elif isinstance(partitions, Mapping):
        details.extend(
            f"{_display(str(name))} {_percentage(ratio)}" for name, ratio in partitions.items()
        )
    holdouts = value.get("holdouts")
    if isinstance(holdouts, Mapping) and holdouts:
        details.append("Holdouts " + ", ".join(_display(str(name)) for name in holdouts))
    if value.get("seed") is not None:
        details.append(f"Seed {value['seed']}")
    transformations = value.get("transformations")
    if isinstance(transformations, list) and transformations:
        count = len(transformations)
        details.append(f"{count} transformation{'s' if count != 1 else ''}")
    return " · ".join((_display(kind), *details))


def _percentage(value: object) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{format(float(value) * 100.0, '.12g')}%"
    return _number_text(value)
