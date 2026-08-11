from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.field_ids import (
    PREPARATION_AUXILIARY,
    PREPARATION_CATEGORICAL_FEATURES,
    PREPARATION_FEATURES,
    PREPARATION_SOURCE_POLICY,
    PREPARATION_TARGETS,
)

DERIVED_FEATURES = (
    "specific_volume",
    "reduced_temperature",
    "reduced_pressure",
    "compressibility_factor",
)
CATEGORICAL_FIELDS = ("phase", "fluid")


class PreparationDraft(QObject):
    """Compose source-independent Preparation roles for the global document."""

    changed = Signal()
    validity_changed = Signal()
    dirty_changed = Signal()
    profile_changed = Signal()
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.numeric_choices = DraftListModel(self, disable_incompatible=True)
        self.derived_choices = DraftListModel(self, disable_incompatible=True)
        self.target_choices = DraftListModel(self, disable_incompatible=True)
        self.auxiliary_choices = DraftListModel(self, disable_incompatible=True)
        self.categorical_choices = DraftListModel(self, disable_incompatible=True)
        self._profile: dict[str, Any] = {}
        self._preserved: dict[str, Any] | None = None
        self._numeric: tuple[str, ...] = ()
        self._derived: tuple[str, ...] = ()
        self._categorical: dict[str, str | tuple[str, ...]] = {}
        self._targets: tuple[str, ...] = ()
        self._auxiliary: tuple[str, ...] = ()
        self._known_numeric: tuple[str, ...] = ()
        self._known_auxiliary: tuple[str, ...] = ()
        self._allow_partial_sweep = False
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

    def get_first_invalid_field(self) -> str:
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
        return PREPARATION_FEATURES

    firstInvalidField = Property(str, get_first_invalid_field, notify=validity_changed)

    def get_first_invalid_row(self) -> int:
        return -1

    firstInvalidRow = Property(int, get_first_invalid_row, notify=validity_changed)

    def get_dirty(self) -> bool:
        if self._baseline is None or self._baseline_raw is None:
            return False
        try:
            return self.payload() != self._baseline
        except ValueError:
            return self.raw_state() != self._baseline_raw

    dirty = Property(bool, get_dirty, notify=dirty_changed)

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
        self._loading = True
        try:
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
            self._loaded = True
            self._refresh_models()
        finally:
            self._loading = False
        self._baseline = copy.deepcopy(value)
        self._baseline_raw = self.raw_state()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.changed.emit()

    def clear(self) -> None:
        self._loading = True
        try:
            self._preserved = None
            self._numeric = ()
            self._derived = ()
            self._categorical = {}
            self._targets = ()
            self._auxiliary = ()
            self._known_numeric = ()
            self._known_auxiliary = ()
            self._allow_partial_sweep = False
            self._baseline = None
            self._baseline_raw = None
            self._loaded = False
            self._refresh_models()
        finally:
            self._loading = False
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.changed.emit()

    def mark_baseline(self) -> None:
        if issue := self.get_issue():
            raise ValueError(f"cannot mark an invalid ML Preparation draft as saved: {issue}")
        self._baseline = self.payload()
        self._baseline_raw = self.raw_state()
        self.dirty_changed.emit()

    def payload(self) -> dict[str, Any]:
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
        try:
            model = PreparationConfig.model_validate(result)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump(mode="json", exclude_none=True)

    def raw_state(self) -> tuple[object, ...]:
        return (
            self._loaded,
            self._allow_partial_sweep,
            self._numeric,
            self._derived,
            tuple(self._categorical.items()),
            self._targets,
            self._auxiliary,
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

    def _state_changed(self) -> None:
        if self._loading:
            return
        self._refresh_models()
        self.validity_changed.emit()
        self.dirty_changed.emit()
        self.profile_changed.emit()
        self.changed.emit()

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


def _display(value: str) -> str:
    return value.replace("_", " ").title()
