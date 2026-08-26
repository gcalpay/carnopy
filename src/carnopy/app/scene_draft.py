from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, Signal, Slot

from carnopy.app.draft_models import DraftItem, DraftListModel
from carnopy.app.inspection_models import InspectionListModel
from carnopy.app.scene_contracts import (
    CategoricalSetFilter,
    NumericRangeFilter,
    SceneContractError,
    SceneFieldProfile,
    SceneProfile,
    SceneRequest,
    SceneSourceBinding,
    validate_scene_defaults,
    validate_scene_request,
)

SceneFilterValue = CategoricalSetFilter | NumericRangeFilter


@dataclass(frozen=True)
class SceneProfileSubmission:
    """Immutable explicit Profile-command input copied from the draft."""

    binding: SceneSourceBinding

    def worker_payload(self) -> dict[str, object]:
        return {"binding": self.binding.model_dump(mode="json")}


@dataclass(frozen=True)
class SceneBuildSubmission:
    """Immutable explicit Build/Update-command input copied from the draft."""

    profile: SceneProfile
    request: SceneRequest

    def __post_init__(self) -> None:
        if self.profile.binding != self.request.binding or not self.profile.build_eligible:
            raise ValueError("scene build submission is inconsistent with its profile")
        validate_scene_request(self.request, self.profile.fields)

    @property
    def request_id(self) -> str:
        return self.request.request_id


class SceneDraft(QObject):
    """QtCore-only editable state for one explicitly copied scene binding."""

    changed = Signal()
    binding_changed = Signal()
    profile_changed = Signal()
    selection_changed = Signal()
    filters_changed = Signal()
    validity_changed = Signal()
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.axis_choices = DraftListModel(self, disable_incompatible=True)
        self.scalar_choices = DraftListModel(self, disable_incompatible=True)
        self.filter_rows = InspectionListModel(
            (
                "fieldId",
                "label",
                "kind",
                "classification",
                "unit",
                "active",
                "summary",
                "availableValues",
                "sourceMinimum",
                "sourceMaximum",
                "selectedValues",
                "selectedMinimum",
                "selectedMaximum",
                "caseSensitive",
                "inclusive",
            ),
            self,
        )
        self._binding: SceneSourceBinding | None = None
        self._profile: SceneProfile | None = None
        self._x_field = ""
        self._y_field = ""
        self._z_field = ""
        self._scalar_field = ""
        self._filters: dict[str, SceneFilterValue] = {}

    def _constant_model(self, model: QObject) -> QObject:
        return model

    axisChoices = Property(
        QObject,
        lambda self: self._constant_model(self.axis_choices),
        constant=True,
    )
    scalarChoices = Property(
        QObject,
        lambda self: self._constant_model(self.scalar_choices),
        constant=True,
    )
    filterRows = Property(
        QObject,
        lambda self: self._constant_model(self.filter_rows),
        constant=True,
    )

    def get_binding_available(self) -> bool:
        return self._binding is not None

    bindingAvailable = Property(bool, get_binding_available, notify=binding_changed)

    def get_profile_available(self) -> bool:
        return self._profile is not None

    profileAvailable = Property(bool, get_profile_available, notify=profile_changed)

    def get_source_path(self) -> str:
        return "" if self._binding is None else self._binding.source_path

    sourcePath = Property(str, get_source_path, notify=binding_changed)

    def get_source_kind(self) -> str:
        return "" if self._binding is None else self._binding.source_kind

    sourceKind = Property(str, get_source_kind, notify=binding_changed)

    def get_table_id(self) -> str:
        return "" if self._binding is None else self._binding.selected_table_id

    tableId = Property(str, get_table_id, notify=binding_changed)

    def get_inspection_revision(self) -> str:
        return "" if self._binding is None else self._binding.inspection_revision

    inspectionRevision = Property(str, get_inspection_revision, notify=binding_changed)

    def get_x_field(self) -> str:
        return self._x_field

    @Slot(str, result=bool)
    def set_x_field(self, value: str) -> bool:
        return self._set_coordinate("x", value)

    def _set_x_property(self, value: str) -> None:
        self.set_x_field(value)

    xField = Property(
        str,
        get_x_field,
        _set_x_property,
        notify=selection_changed,
    )

    def get_y_field(self) -> str:
        return self._y_field

    @Slot(str, result=bool)
    def set_y_field(self, value: str) -> bool:
        return self._set_coordinate("y", value)

    def _set_y_property(self, value: str) -> None:
        self.set_y_field(value)

    yField = Property(
        str,
        get_y_field,
        _set_y_property,
        notify=selection_changed,
    )

    def get_z_field(self) -> str:
        return self._z_field

    @Slot(str, result=bool)
    def set_z_field(self, value: str) -> bool:
        return self._set_coordinate("z", value)

    def _set_z_property(self, value: str) -> None:
        self.set_z_field(value)

    zField = Property(
        str,
        get_z_field,
        _set_z_property,
        notify=selection_changed,
    )

    def get_scalar_field(self) -> str:
        return self._scalar_field

    @Slot(str, result=bool)
    def set_scalar_field(self, value: str) -> bool:
        profile = self._profile
        if profile is None:
            return self._reject("Profile the copied scene source before selecting a scalar.")
        if value:
            field = _field_by_id(profile, value)
            if field is None:
                return self._reject(f"Scene scalar field {value!r} is unavailable.")
            if not field.scalar_eligible:
                return self._reject(
                    field.ineligible_reason
                    or f"Scene scalar field {value!r} is not scalar eligible."
                )
        if value == self._scalar_field:
            return False
        self._scalar_field = value
        self._refresh_choice_models()
        self.selection_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    def _set_scalar_property(self, value: str) -> None:
        self.set_scalar_field(value)

    scalarField = Property(
        str,
        get_scalar_field,
        _set_scalar_property,
        notify=selection_changed,
    )

    def get_can_profile(self) -> bool:
        return self._binding is not None

    canProfile = Property(bool, get_can_profile, notify=binding_changed)

    def get_can_build(self) -> bool:
        return self.get_locally_valid()

    canBuild = Property(bool, get_can_build, notify=validity_changed)

    def get_locally_valid(self) -> bool:
        return not self.get_issue()

    locallyValid = Property(bool, get_locally_valid, notify=validity_changed)

    def get_issue(self) -> str:
        if self._binding is None:
            return "Copy a supported table binding from Inspect before profiling a scene."
        if self._profile is None:
            return "Profile the copied scene source before choosing scene fields."
        if not self._profile.build_eligible:
            return self._profile.ineligible_reason
        try:
            self._scene_request()
        except SceneContractError as exc:
            return exc.message
        return ""

    issue = Property(str, get_issue, notify=validity_changed)

    def get_request_id(self) -> str:
        try:
            return self._scene_request().request_id
        except SceneContractError:
            return ""

    requestId = Property(str, get_request_id, notify=validity_changed)

    def get_topology_status(self) -> str:
        return "" if self._profile is None else self._profile.topology.status

    topologyStatus = Property(str, get_topology_status, notify=profile_changed)

    def get_topology_axis_fields(self) -> list[str]:
        if self._profile is None:
            return []
        return [axis.field_id for axis in self._profile.topology.axes]

    topologyAxisFields = Property(list, get_topology_axis_fields, notify=profile_changed)

    def get_has_filters(self) -> bool:
        return bool(self._filters)

    hasFilters = Property(bool, get_has_filters, notify=filters_changed)

    def copy_binding(self, binding: SceneSourceBinding) -> bool:
        """Explicitly copy one immutable Inspect snapshot into the draft."""

        if not isinstance(binding, SceneSourceBinding):
            raise TypeError("scene binding must be a SceneSourceBinding")
        copied = binding.model_copy(deep=True)
        if copied == self._binding:
            return False
        self._binding = copied
        self._profile = None
        self._clear_settings()
        self._refresh_models()
        self.binding_changed.emit()
        self.profile_changed.emit()
        self.selection_changed.emit()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    @Slot(result=bool)
    def clear(self) -> bool:
        if self._binding is None and self._profile is None:
            return False
        self._binding = None
        self._profile = None
        self._clear_settings()
        self._refresh_models()
        self.binding_changed.emit()
        self.profile_changed.emit()
        self.selection_changed.emit()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    def accept_profile(self, value: SceneProfile | Mapping[str, object]) -> bool:
        """Accept only a profile for the exact binding currently held by the draft."""

        try:
            profile = (
                value if isinstance(value, SceneProfile) else SceneProfile.model_validate(value)
            ).model_copy(deep=True)
        except ValidationError as exc:
            raise SceneContractError(
                "invalid_scene_profile",
                "scene profile result is structurally invalid",
            ) from exc
        if self._binding is None or profile.binding != self._binding:
            raise SceneContractError(
                "invalid_scene_profile",
                "scene profile binding disagrees with the explicitly copied Inspect binding",
            )
        validate_scene_defaults(profile.defaults, profile.fields)
        defaults = (
            profile.defaults.x_field or "",
            profile.defaults.y_field or "",
            profile.defaults.z_field or "",
            profile.defaults.scalar_field or "",
        )
        unchanged = (
            profile == self._profile
            and defaults == (self._x_field, self._y_field, self._z_field, self._scalar_field)
            and not self._filters
        )
        if unchanged:
            return False
        self._profile = profile
        (
            self._x_field,
            self._y_field,
            self._z_field,
            self._scalar_field,
        ) = defaults
        self._filters = {}
        self._refresh_models()
        self.profile_changed.emit()
        self.selection_changed.emit()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    @Slot(result=bool)
    def reset_to_profile_defaults(self) -> bool:
        profile = self._profile
        if profile is None:
            return False
        defaults = (
            profile.defaults.x_field or "",
            profile.defaults.y_field or "",
            profile.defaults.z_field or "",
            profile.defaults.scalar_field or "",
        )
        if (
            defaults
            == (
                self._x_field,
                self._y_field,
                self._z_field,
                self._scalar_field,
            )
            and not self._filters
        ):
            return False
        (
            self._x_field,
            self._y_field,
            self._z_field,
            self._scalar_field,
        ) = defaults
        self._filters = {}
        self._refresh_models()
        self.selection_changed.emit()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    @Slot(str, list, result=bool)
    def set_categorical_filter(self, field_id: str, values: list[str]) -> bool:
        field = self._filterable_field(field_id, "categorical_set")
        if field is None:
            return False
        try:
            filter_value = CategoricalSetFilter(field_id=field_id, values=tuple(values))
        except ValidationError as exc:
            return self._reject(_validation_message(exc, "Categorical filter is invalid."))
        unknown = [value for value in filter_value.values if value not in field.distinct_values]
        if unknown:
            return self._reject(
                f"Scene filter for {field_id!r} contains unobserved exact values: "
                + ", ".join(repr(value) for value in unknown)
            )
        return self._replace_filter(filter_value)

    def set_numeric_filter(
        self,
        field_id: str,
        minimum: float | int | None,
        maximum: float | int | None,
    ) -> bool:
        if self._filterable_field(field_id, "numeric_range") is None:
            return False
        try:
            filter_value = NumericRangeFilter(
                field_id=field_id,
                minimum=minimum,
                maximum=maximum,
            )
        except ValidationError as exc:
            return self._reject(_validation_message(exc, "Numeric filter is invalid."))
        return self._replace_filter(filter_value)

    @Slot(str, bool, float, bool, float, result=bool)
    def set_numeric_range_filter(
        self,
        field_id: str,
        has_minimum: bool,
        minimum: float,
        has_maximum: bool,
        maximum: float,
    ) -> bool:
        return self.set_numeric_filter(
            field_id,
            minimum if has_minimum else None,
            maximum if has_maximum else None,
        )

    @Slot(str, result=bool)
    def clear_filter(self, field_id: str) -> bool:
        if field_id not in self._filters:
            return False
        del self._filters[field_id]
        self._refresh_filter_model()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    def binding_snapshot(self) -> SceneSourceBinding | None:
        return None if self._binding is None else self._binding.model_copy(deep=True)

    def profile_snapshot(self) -> SceneProfile | None:
        return None if self._profile is None else self._profile.model_copy(deep=True)

    def filters_snapshot(self) -> tuple[SceneFilterValue, ...]:
        return tuple(
            self._filters[field_id].model_copy(deep=True) for field_id in sorted(self._filters)
        )

    def request_snapshot(self) -> SceneRequest:
        return self._scene_request().model_copy(deep=True)

    def create_profile_submission(self) -> SceneProfileSubmission:
        """Create the only Profile command input; never starts a worker itself."""

        if self._binding is None:
            raise SceneContractError(
                "invalid_scene_binding",
                "copy a supported table binding from Inspect before profiling a scene",
            )
        return SceneProfileSubmission(binding=self._binding.model_copy(deep=True))

    def create_build_submission(self) -> SceneBuildSubmission:
        """Create the only Build/Update input; never starts a worker itself."""

        profile = self._require_profile()
        request = self._scene_request()
        return SceneBuildSubmission(
            profile=profile.model_copy(deep=True),
            request=request.model_copy(deep=True),
        )

    def _set_coordinate(self, role: str, value: str) -> bool:
        profile = self._profile
        if profile is None:
            return self._reject("Profile the copied scene source before selecting coordinates.")
        if value:
            field = _field_by_id(profile, value)
            if field is None:
                return self._reject(f"Scene {role} field {value!r} is unavailable.")
            if not field.axis_eligible:
                return self._reject(
                    field.ineligible_reason or f"Scene {role} field {value!r} is not axis eligible."
                )
        attribute = f"_{role}_field"
        if cast(str, getattr(self, attribute)) == value:
            return False
        setattr(self, attribute, value)
        self._refresh_choice_models()
        self.selection_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    def _filterable_field(
        self,
        field_id: str,
        expected_kind: str,
    ) -> SceneFieldProfile | None:
        profile = self._profile
        if profile is None:
            self._reject("Profile the copied scene source before adding filters.")
            return None
        field = _field_by_id(profile, field_id)
        if field is None:
            self._reject(f"Scene filter field {field_id!r} is unavailable.")
            return None
        if field.filter_kind != expected_kind:
            self._reject(f"Scene filter field {field_id!r} does not support {expected_kind!r}.")
            return None
        return field

    def _replace_filter(self, filter_value: SceneFilterValue) -> bool:
        if self._filters.get(filter_value.field_id) == filter_value:
            return False
        self._filters[filter_value.field_id] = filter_value
        self._refresh_filter_model()
        self.filters_changed.emit()
        self.validity_changed.emit()
        self.changed.emit()
        return True

    def _require_profile(self) -> SceneProfile:
        if self._profile is None:
            raise SceneContractError(
                "invalid_scene_profile",
                "profile the copied scene source before building a scene",
            )
        if not self._profile.build_eligible:
            raise SceneContractError(
                "invalid_scene_profile",
                "scene profile is not eligible for a build",
                details={"reason": self._profile.ineligible_reason},
            )
        return self._profile

    def _scene_request(self) -> SceneRequest:
        profile = self._require_profile()
        binding = self._binding
        if binding is None or profile.binding != binding:
            raise SceneContractError(
                "invalid_scene_binding",
                "scene draft binding is unavailable or inconsistent with its profile",
            )
        missing = [
            role
            for role, value in (
                ("x", self._x_field),
                ("y", self._y_field),
                ("z", self._z_field),
            )
            if not value
        ]
        if missing:
            raise SceneContractError(
                "invalid_scene_request",
                "Choose explicit scene fields for " + ", ".join(role.upper() for role in missing),
                details={"roles": missing},
            )
        if len({self._x_field, self._y_field, self._z_field}) != 3:
            raise SceneContractError(
                "invalid_scene_request",
                "Scene coordinate fields X, Y, and Z must be distinct.",
            )
        try:
            request = SceneRequest(
                binding=binding,
                x_field=self._x_field,
                y_field=self._y_field,
                z_field=self._z_field,
                scalar_field=self._scalar_field or None,
                filters=self.filters_snapshot(),
            )
        except ValidationError as exc:
            raise SceneContractError(
                "invalid_scene_request",
                _validation_message(exc, "Scene request is structurally invalid."),
            ) from exc
        return validate_scene_request(request, profile.fields)

    def _clear_settings(self) -> None:
        self._x_field = ""
        self._y_field = ""
        self._z_field = ""
        self._scalar_field = ""
        self._filters = {}

    def _refresh_models(self) -> None:
        self._refresh_choice_models()
        self._refresh_filter_model()

    def _refresh_choice_models(self) -> None:
        profile = self._profile
        if profile is None:
            self.axis_choices.replace(())
            self.scalar_choices.replace(())
            return
        selected_axes = {self._x_field, self._y_field, self._z_field}
        axis_items = [
            DraftItem(
                value="",
                display="Select a field",
                canonical="",
                selected="" in selected_axes,
                label="Select a field",
            )
        ]
        scalar_items = [
            DraftItem(
                value="",
                display="None",
                canonical="",
                selected=not self._scalar_field,
                label="No scalar colour field",
            )
        ]
        for field in profile.fields:
            display = _field_display(field)
            axis_items.append(
                DraftItem(
                    value=field.field_id,
                    display=display,
                    canonical=field.column,
                    compatible=field.axis_eligible,
                    selected=field.field_id in selected_axes,
                    issue=_axis_choice_issue(field),
                    label=field.label,
                    unit=field.unit or "",
                )
            )
            scalar_items.append(
                DraftItem(
                    value=field.field_id,
                    display=display,
                    canonical=field.column,
                    compatible=field.scalar_eligible,
                    selected=field.field_id == self._scalar_field,
                    issue=field.ineligible_reason if not field.scalar_eligible else "",
                    label=field.label,
                    unit=field.unit or "",
                )
            )
        self.axis_choices.replace(axis_items)
        self.scalar_choices.replace(scalar_items)

    def _refresh_filter_model(self) -> None:
        profile = self._profile
        if profile is None:
            self.filter_rows.clear()
            return
        rows: list[dict[str, object]] = []
        for field in profile.fields:
            if field.filter_kind is None:
                continue
            current = self._filters.get(field.field_id)
            categorical = current if isinstance(current, CategoricalSetFilter) else None
            numeric = current if isinstance(current, NumericRangeFilter) else None
            rows.append(
                {
                    "fieldId": field.field_id,
                    "label": field.label,
                    "kind": field.filter_kind,
                    "classification": field.classification,
                    "unit": field.unit or "",
                    "active": current is not None,
                    "summary": _filter_summary(current),
                    "availableValues": list(field.distinct_values),
                    "sourceMinimum": field.minimum,
                    "sourceMaximum": field.maximum,
                    "selectedValues": [] if categorical is None else list(categorical.values),
                    "selectedMinimum": None if numeric is None else numeric.minimum,
                    "selectedMaximum": None if numeric is None else numeric.maximum,
                    "caseSensitive": field.filter_kind == "categorical_set",
                    "inclusive": field.filter_kind == "numeric_range",
                }
            )
        self.filter_rows.set_rows(rows, available=True)

    def _reject(self, message: str) -> bool:
        self.message.emit(message)
        return False


def _field_by_id(profile: SceneProfile, field_id: str) -> SceneFieldProfile | None:
    return next((field for field in profile.fields if field.field_id == field_id), None)


def _field_display(field: SceneFieldProfile) -> str:
    return field.label if field.unit is None else f"{field.label} [{field.unit}]"


def _axis_choice_issue(field: SceneFieldProfile) -> str:
    if not field.axis_eligible:
        return field.ineligible_reason
    if not field.varying:
        return "Constant in the accepted profile; valid but adds no varying display dimension."
    return ""


def _filter_summary(value: SceneFilterValue | None) -> str:
    if isinstance(value, CategoricalSetFilter):
        return ", ".join(value.values)
    if isinstance(value, NumericRangeFilter):
        if value.minimum is not None and value.maximum is not None:
            return f"[{value.minimum!r}, {value.maximum!r}]"
        if value.minimum is not None:
            return f">= {value.minimum!r}"
        assert value.maximum is not None
        return f"<= {value.maximum!r}"
    return ""


def _validation_message(error: ValidationError, fallback: str) -> str:
    errors = error.errors(include_url=False)
    if not errors:
        return fallback
    message = errors[0].get("msg")
    return str(message) if message else fallback
