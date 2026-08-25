from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from carnopy.domain.failures import CarnopyError

SCENE_REQUEST_SCHEMA_VERSION: Final[Literal[1]] = 1
SCENE_PROFILE_SCHEMA_VERSION: Final[Literal[1]] = 1

MAX_SCENE_POINTS = 250_000
MAX_SCENE_EDGES = 499_999
MAX_SCENE_QUADS = 249_999
MAX_SCENE_BUNDLE_BYTES = 64 * 1024 * 1024

_SHA256_LENGTH = 64
_CONTEXT_FIELDS = (
    "source_artifact",
    "source_run_id",
    "fluid",
    "backend_model",
    "phase",
    "saturation_endpoint",
    "scenario",
    "partition",
)

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]

SceneSourceKind = Literal["dataset", "model_sweep", "preparation"]
SceneFieldKind = Literal["numeric", "categorical"]
SceneFieldClassification = Literal[
    "source_coordinate",
    "emitted_property",
    "prepared_feature",
    "prepared_target",
    "prepared_auxiliary",
    "derived_feature",
    "recorded_transform",
    "context",
]
SceneFieldOrigin = Literal["table", "provenance", "scenario", "metadata"]
SceneUnitStatus = Literal["canonical", "dimensionless", "transformed", "unreported"]
SceneFilterKind = Literal["categorical_set", "numeric_range"]
SceneTopologyStatus = Literal["exact", "unavailable"]
SceneRepresentation = Literal["points", "wireframe", "surface"]
SceneGapCode = Literal[
    "filtered",
    "source_invalid",
    "missing_selected_value",
    "nonfinite_selected_value",
    "missing_topology_corner",
    "incompatible_context",
    "duplicate_topology_location",
    "zero_length_edge",
    "degenerate_quad",
    "unsupported_topology_dimension",
]
SceneCapabilityBlockerCode = Literal[
    "topology_unavailable",
    "unsupported_topology_dimension",
    "missing_context",
    "duplicate_topology_location",
    "no_valid_edges",
    "no_valid_quads",
]
SceneErrorCode = Literal[
    "invalid_scene_binding",
    "invalid_scene_profile",
    "invalid_scene_request",
    "unsupported_scene_source",
    "scene_source_changed",
    "scene_no_retained_points",
    "scene_topology_unavailable",
    "scene_limit_exceeded",
    "scene_integrity_error",
    "scene_write_failed",
    "scene_cleanup_failed",
    "scene_pick_stale",
]


class SceneContractError(CarnopyError):
    """One private scene contract could not be satisfied exactly."""

    def __init__(
        self,
        code: SceneErrorCode,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = dict(self.details)
        return payload


class SceneFileIdentity(BaseModel):
    """Immutable identity copied from one worker-verified regular file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: StrictStr
    sha256: StrictStr
    device: NonNegativeInt
    inode: PositiveInt
    size: NonNegativeInt
    modified_ns: NonNegativeInt

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        _require_exact_text(value, "scene file path")
        if not Path(value).is_absolute():
            raise ValueError("scene file path must be absolute")
        return value

    @field_validator("sha256")
    @classmethod
    def canonical_sha256(cls, value: str) -> str:
        if len(value) != _SHA256_LENGTH or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("scene file sha256 must be 64 lowercase hexadecimal characters")
        return value


class SceneBoundTable(BaseModel):
    """One table and optional metadata file accepted by Inspect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_id: StrictStr
    label: StrictStr
    source_format: Literal["csv", "parquet"]
    artifact: SceneFileIdentity
    metadata: SceneFileIdentity | None = None

    @field_validator("table_id")
    @classmethod
    def valid_table_id(cls, value: str) -> str:
        return _require_exact_text(value, "scene table ID")

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str) -> str:
        return _require_exact_text(value, "scene table label")


class SceneBoundControl(BaseModel):
    """One control artifact contributing to an inspection revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr
    artifact: SceneFileIdentity

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _require_exact_text(value, "scene control name")


class SceneSourceBinding(BaseModel):
    """Deeply immutable source binding copied explicitly from Inspect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: StrictStr
    source_kind: SceneSourceKind
    inspection_revision: StrictStr
    selected_table_id: StrictStr
    tables: tuple[SceneBoundTable, ...]
    controls: tuple[SceneBoundControl, ...] = ()

    @field_validator("source_path")
    @classmethod
    def absolute_source_path(cls, value: str) -> str:
        _require_exact_text(value, "scene source path")
        if not Path(value).is_absolute():
            raise ValueError("scene source path must be absolute")
        return value

    @field_validator("inspection_revision")
    @classmethod
    def canonical_revision(cls, value: str) -> str:
        if len(value) != _SHA256_LENGTH or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "scene inspection revision must be 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("selected_table_id")
    @classmethod
    def valid_selected_table_id(cls, value: str) -> str:
        return _require_exact_text(value, "selected scene table ID")

    @field_validator("tables")
    @classmethod
    def canonical_tables(
        cls,
        values: tuple[SceneBoundTable, ...],
    ) -> tuple[SceneBoundTable, ...]:
        if not values:
            raise ValueError("scene source binding requires at least one table")
        identifiers = [value.table_id for value in values]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scene source binding contains duplicate table IDs")
        return tuple(sorted(values, key=lambda value: value.table_id))

    @field_validator("controls")
    @classmethod
    def canonical_controls(
        cls,
        values: tuple[SceneBoundControl, ...],
    ) -> tuple[SceneBoundControl, ...]:
        names = [value.name for value in values]
        if len(set(names)) != len(names):
            raise ValueError("scene source binding contains duplicate control names")
        return tuple(sorted(values, key=lambda value: value.name))

    @model_validator(mode="after")
    def selected_table_exists(self) -> SceneSourceBinding:
        if self.selected_table_id not in {table.table_id for table in self.tables}:
            raise ValueError("selected scene table is absent from the copied binding")
        return self

    def selected_table(self) -> SceneBoundTable:
        return next(table for table in self.tables if table.table_id == self.selected_table_id)

    def identity_payload(self) -> dict[str, object]:
        """Return stable scientific identity without operational paths/stat data."""

        return {
            "source_kind": self.source_kind,
            "inspection_revision": self.inspection_revision,
            "table_id": self.selected_table_id,
            "table_sha256": self.selected_table().artifact.sha256,
        }


class SceneFieldProfile(BaseModel):
    """Metadata-governed field facts computed by the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: StrictStr
    column: StrictStr
    label: StrictStr
    dtype: StrictStr
    kind: SceneFieldKind
    classification: SceneFieldClassification
    origin: SceneFieldOrigin
    unit: StrictStr | None = None
    unit_status: SceneUnitStatus
    source_row_count: NonNegativeInt
    source_valid_count: NonNegativeInt
    value_count: NonNegativeInt
    missing_count: NonNegativeInt
    finite_count: NonNegativeInt | None = None
    minimum: float | None = None
    maximum: float | None = None
    distinct_values: tuple[StrictStr, ...] = ()
    varying: StrictBool
    positive_domain: StrictBool | None = None
    axis_eligible: StrictBool
    scalar_eligible: StrictBool
    filter_kind: SceneFilterKind | None = None
    ineligible_reason: StrictStr = ""

    @field_validator("field_id", "column", "label", "dtype")
    @classmethod
    def exact_required_text(cls, value: str, info: Any) -> str:
        return _require_exact_text(value, str(info.field_name).replace("_", " "))

    @field_validator("unit")
    @classmethod
    def exact_optional_unit(cls, value: str | None) -> str | None:
        return None if value is None else _require_exact_text(value, "scene field unit")

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def strict_finite_bound(cls, value: object) -> float | None:
        return None if value is None else _finite_binary64(value, "scene field bound")

    @field_validator("distinct_values", mode="before")
    @classmethod
    def canonical_distinct_values(cls, value: object) -> tuple[str, ...]:
        return _canonical_exact_strings(value, "scene field distinct values", allow_empty=True)

    @field_validator("ineligible_reason")
    @classmethod
    def exact_reason(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("scene field ineligibility reason must not contain NUL")
        return value

    @model_validator(mode="after")
    def consistent_profile(self) -> SceneFieldProfile:
        if self.source_valid_count > self.source_row_count:
            raise ValueError("scene field valid row count exceeds its source row count")
        if self.value_count + self.missing_count != self.source_valid_count:
            raise ValueError("scene field value and missing counts do not equal valid rows")
        if self.kind == "numeric":
            self._validate_numeric_profile()
        else:
            self._validate_categorical_profile()
        if (self.axis_eligible or self.scalar_eligible) and self.kind != "numeric":
            raise ValueError("only numeric scene fields may be axis or scalar eligible")
        if self.axis_eligible and not self.finite_count:
            raise ValueError("axis-eligible scene fields require finite values")
        if self.scalar_eligible and not self.finite_count:
            raise ValueError("scalar-eligible scene fields require finite values")
        if self.unit_status == "canonical" and self.unit is None:
            raise ValueError("canonical scene fields require a unit")
        if self.unit_status == "dimensionless" and self.unit != "1":
            raise ValueError("dimensionless scene fields require unit '1'")
        if self.unit_status == "unreported" and self.unit is not None:
            raise ValueError("scene fields with unreported units must not declare a unit")
        if self.classification == "recorded_transform" and self.unit_status != "transformed":
            raise ValueError("recorded scene transforms require transformed-unit status")
        return self

    def _validate_numeric_profile(self) -> None:
        if self.distinct_values:
            raise ValueError("numeric scene fields must not declare categorical values")
        if self.finite_count is None:
            raise ValueError("numeric scene fields require a finite-value count")
        if self.finite_count > self.value_count:
            raise ValueError("scene field finite count exceeds its value count")
        if self.filter_kind not in {None, "numeric_range"}:
            raise ValueError("numeric scene fields require numeric-range filters")
        if self.finite_count == 0:
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("numeric fields without finite values cannot declare a range")
            if self.positive_domain is not None:
                raise ValueError(
                    "numeric fields without finite values cannot declare log-domain status"
                )
            expected_varying = False
        else:
            if self.minimum is None or self.maximum is None:
                raise ValueError("numeric scene fields with finite values require a range")
            if self.minimum > self.maximum:
                raise ValueError("scene field minimum exceeds its maximum")
            if self.positive_domain is None:
                raise ValueError("numeric scene fields require explicit log-domain status")
            if self.positive_domain != (self.minimum > 0.0):
                raise ValueError("scene field log-domain status disagrees with its range")
            expected_varying = self.minimum != self.maximum
        if self.varying != expected_varying:
            raise ValueError("numeric scene field variability disagrees with its range")

    def _validate_categorical_profile(self) -> None:
        if self.finite_count is not None:
            raise ValueError("categorical scene fields must not declare finite-value counts")
        if self.minimum is not None or self.maximum is not None:
            raise ValueError("categorical scene fields must not declare numeric ranges")
        if self.positive_domain is not None:
            raise ValueError("categorical scene fields must not declare log-domain status")
        if self.filter_kind not in {None, "categorical_set"}:
            raise ValueError("categorical scene fields require categorical-set filters")
        if self.filter_kind == "categorical_set" and not self.distinct_values:
            raise ValueError("filterable categorical scene fields require observed values")
        if any(value == "" for value in self.distinct_values):
            raise ValueError("categorical scene fields must not declare empty values")
        if len(self.distinct_values) > self.value_count:
            raise ValueError("categorical distinct-value count exceeds its value count")
        if self.unit is not None or self.unit_status != "unreported":
            raise ValueError("categorical scene fields must not declare scientific units")
        if self.varying != (len(self.distinct_values) > 1):
            raise ValueError(
                "categorical scene field variability disagrees with its distinct values"
            )


class CategoricalSetFilter(BaseModel):
    """An exact, case-sensitive OR-set for one categorical field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["categorical_set"] = "categorical_set"
    field_id: StrictStr
    values: tuple[StrictStr, ...]

    @field_validator("field_id")
    @classmethod
    def valid_field_id(cls, value: str) -> str:
        return _require_exact_text(value, "categorical filter field ID")

    @field_validator("values", mode="before")
    @classmethod
    def canonical_values(cls, value: object) -> tuple[str, ...]:
        values = _canonical_exact_strings(value, "categorical filter values", allow_empty=False)
        if any(item == "" for item in values):
            raise ValueError("categorical filter values must not contain an empty string")
        return values

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and value in self.values


class NumericRangeFilter(BaseModel):
    """One exact inclusive range over raw binary64 field values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["numeric_range"] = "numeric_range"
    field_id: StrictStr
    minimum: float | None = None
    maximum: float | None = None

    @field_validator("field_id")
    @classmethod
    def valid_field_id(cls, value: str) -> str:
        return _require_exact_text(value, "numeric filter field ID")

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def strict_finite_bound(cls, value: object) -> float | None:
        return None if value is None else _finite_binary64(value, "numeric filter bound")

    @model_validator(mode="after")
    def valid_range(self) -> NumericRangeFilter:
        if self.minimum is None and self.maximum is None:
            raise ValueError("numeric range filter requires at least one bound")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("numeric range filter minimum exceeds its maximum")
        return self

    def matches(self, value: object) -> bool:
        try:
            numeric = _finite_binary64(value, "numeric filter value")
        except ValueError:
            return False
        return (self.minimum is None or numeric >= self.minimum) and (
            self.maximum is None or numeric <= self.maximum
        )


SceneFilter = Annotated[
    CategoricalSetFilter | NumericRangeFilter,
    Field(discriminator="kind"),
]


class SceneSelectionDefaults(BaseModel):
    """Deterministic profile defaults, which may be incomplete."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x_field: StrictStr | None = None
    y_field: StrictStr | None = None
    z_field: StrictStr | None = None
    scalar_field: StrictStr | None = None

    @field_validator("x_field", "y_field", "z_field", "scalar_field")
    @classmethod
    def valid_optional_field(cls, value: str | None) -> str | None:
        return None if value is None else _require_exact_text(value, "scene default field ID")

    @model_validator(mode="after")
    def distinct_coordinates(self) -> SceneSelectionDefaults:
        coordinates = [
            value for value in (self.x_field, self.y_field, self.z_field) if value is not None
        ]
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("scene default coordinate fields must be distinct")
        return self

    @property
    def complete(self) -> bool:
        return self.x_field is not None and self.y_field is not None and self.z_field is not None


class SceneTopologyAxis(BaseModel):
    """One exact source-sampling coordinate and its original ordered levels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: StrictStr
    source_column: StrictStr
    unit: StrictStr
    levels: tuple[float, ...]

    @field_validator("field_id", "source_column", "unit")
    @classmethod
    def exact_text(cls, value: str, info: Any) -> str:
        return _require_exact_text(value, str(info.field_name).replace("_", " "))

    @field_validator("levels", mode="before")
    @classmethod
    def exact_ordered_levels(cls, value: object) -> tuple[float, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("scene topology axis requires at least one ordered level")
        levels = tuple(_finite_binary64(item, "scene topology level") for item in value)
        if len(set(levels)) != len(levels):
            raise ValueError("scene topology axis contains duplicate exact levels")
        return levels


class SceneTopologyEvidence(BaseModel):
    """Metadata evidence used later to derive, but never guess, connectivity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SceneTopologyStatus
    axes: tuple[SceneTopologyAxis, ...] = ()
    context_fields: tuple[StrictStr, ...] = ()
    reason_code: StrictStr = ""
    reason: StrictStr = ""

    @field_validator("axes")
    @classmethod
    def unique_axes(cls, values: tuple[SceneTopologyAxis, ...]) -> tuple[SceneTopologyAxis, ...]:
        identifiers = [value.field_id for value in values]
        columns = [value.source_column for value in values]
        if len(set(identifiers)) != len(identifiers) or len(set(columns)) != len(columns):
            raise ValueError("scene topology axes must have unique fields and columns")
        return values

    @field_validator("context_fields", mode="before")
    @classmethod
    def exact_context_fields(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("scene topology context fields must be a list or tuple")
        fields = tuple(_require_exact_text(item, "topology context field") for item in value)
        if len(set(fields)) != len(fields):
            raise ValueError("scene topology context fields must be unique")
        unknown = [field for field in fields if field not in _CONTEXT_FIELDS]
        if unknown:
            raise ValueError("unknown scene topology context fields: " + ", ".join(unknown))
        return tuple(field for field in _CONTEXT_FIELDS if field in fields)

    @field_validator("reason_code", "reason")
    @classmethod
    def safe_reason_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("scene topology reason must not contain NUL")
        return value

    @model_validator(mode="after")
    def consistent_status(self) -> SceneTopologyEvidence:
        if self.status == "exact":
            if self.reason_code or self.reason:
                raise ValueError("exact scene topology must not declare an unavailable reason")
        else:
            if self.axes:
                raise ValueError("unavailable scene topology must not declare exact axes")
            if not self.reason_code or not self.reason:
                raise ValueError("unavailable scene topology requires a code and reason")
        return self


class SceneProfile(BaseModel):
    """One versioned, immutable scene profile returned for a copied binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_profile_schema_version: Literal[1] = SCENE_PROFILE_SCHEMA_VERSION
    binding: SceneSourceBinding
    source_row_count: NonNegativeInt
    fields: tuple[SceneFieldProfile, ...]
    topology: SceneTopologyEvidence
    defaults: SceneSelectionDefaults
    build_eligible: StrictBool
    ineligible_reason: StrictStr = ""

    @field_validator("fields")
    @classmethod
    def unique_fields(
        cls,
        values: tuple[SceneFieldProfile, ...],
    ) -> tuple[SceneFieldProfile, ...]:
        identifiers = [value.field_id for value in values]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scene profile contains duplicate field IDs")
        return values

    @field_validator("ineligible_reason")
    @classmethod
    def safe_ineligible_reason(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("scene profile ineligibility reason must not contain NUL")
        return value

    @model_validator(mode="after")
    def consistent_profile(self) -> SceneProfile:
        catalog = {field.field_id: field for field in self.fields}
        if any(field.source_row_count != self.source_row_count for field in self.fields):
            raise ValueError("scene profile fields disagree about the source row count")
        for axis in self.topology.axes:
            field = catalog.get(axis.field_id)
            if field is None:
                raise ValueError(
                    f"scene topology field {axis.field_id!r} is absent from the field profile"
                )
            if field.kind != "numeric" or field.classification != "source_coordinate":
                raise ValueError("scene topology axes must be classified source coordinates")
        self._validate_defaults(catalog)
        if self.build_eligible:
            if self.ineligible_reason:
                raise ValueError("build-eligible scene profiles must not declare a blocker")
            if self.source_row_count == 0:
                raise ValueError("build-eligible scene profiles require source rows")
            if sum(field.axis_eligible for field in self.fields) < 3:
                raise ValueError("build-eligible scene profiles require three axis fields")
        elif not self.ineligible_reason:
            raise ValueError("build-ineligible scene profiles require an explicit reason")
        return self

    def _validate_defaults(self, catalog: Mapping[str, SceneFieldProfile]) -> None:
        for role, field_id in (
            ("x", self.defaults.x_field),
            ("y", self.defaults.y_field),
            ("z", self.defaults.z_field),
        ):
            if field_id is None:
                continue
            field = catalog.get(field_id)
            if field is None:
                raise ValueError(f"default scene {role} field {field_id!r} is unavailable")
            if not field.axis_eligible or not field.varying:
                raise ValueError(f"default scene {role} field {field_id!r} is not a varying axis")
        scalar_id = self.defaults.scalar_field
        if scalar_id is not None:
            scalar = catalog.get(scalar_id)
            if scalar is None:
                raise ValueError(f"default scene scalar field {scalar_id!r} is unavailable")
            if not scalar.scalar_eligible:
                raise ValueError(f"default scene scalar field {scalar_id!r} is not scalar eligible")


class SceneBlockContext(BaseModel):
    """Fields across which connectivity is forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_artifact: StrictStr
    source_run_id: StrictStr
    fluid: StrictStr | None = None
    backend_model: StrictStr | None = None
    phase: StrictStr | None = None
    saturation_endpoint: StrictStr | None = None
    scenario: StrictStr | None = None
    partition: StrictStr | None = None

    @field_validator(*_CONTEXT_FIELDS)
    @classmethod
    def valid_context_value(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            if info.field_name in {"source_artifact", "source_run_id"}:
                raise ValueError(f"scene block {info.field_name} is required")
            return None
        return _require_exact_text(value, f"scene block {info.field_name}")

    def canonical_items(self) -> tuple[tuple[str, str | None], ...]:
        return tuple((field, getattr(self, field)) for field in _CONTEXT_FIELDS)

    @model_validator(mode="after")
    def complete_partition_identity(self) -> SceneBlockContext:
        if (self.scenario is None) != (self.partition is None):
            raise ValueError("scene block scenario and partition must be declared together")
        return self


class SceneGapSummary(BaseModel):
    """One deterministic count of rows or primitives intentionally left absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SceneGapCode
    count: PositiveInt
    block_index: NonNegativeInt | None = None
    field_id: StrictStr | None = None

    @field_validator("field_id")
    @classmethod
    def valid_optional_field_id(cls, value: str | None) -> str | None:
        return None if value is None else _require_exact_text(value, "scene gap field ID")


class SceneCapabilityBlocker(BaseModel):
    """One exact reason a representation cannot be offered."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SceneCapabilityBlockerCode
    message: StrictStr
    block_index: NonNegativeInt | None = None

    @field_validator("message")
    @classmethod
    def valid_message(cls, value: str) -> str:
        return _require_exact_text(value, "scene capability blocker message")


class SceneRepresentationCapability(BaseModel):
    """Global all-block availability for one representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    representation: SceneRepresentation
    available: StrictBool
    blockers: tuple[SceneCapabilityBlocker, ...] = ()

    @field_validator("blockers")
    @classmethod
    def canonical_blockers(
        cls,
        values: tuple[SceneCapabilityBlocker, ...],
    ) -> tuple[SceneCapabilityBlocker, ...]:
        if len(set(values)) != len(values):
            raise ValueError("scene representation contains duplicate blockers")
        return tuple(
            sorted(
                values,
                key=lambda value: (
                    -1 if value.block_index is None else value.block_index,
                    value.code,
                    value.message,
                ),
            )
        )

    @model_validator(mode="after")
    def consistent_availability(self) -> SceneRepresentationCapability:
        if self.available and self.blockers:
            raise ValueError("available scene representations must not contain blockers")
        if not self.available and not self.blockers:
            raise ValueError("unavailable scene representations require at least one blocker")
        return self


class SceneRequest(BaseModel):
    """Normalized worker-build request; presentation state is intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_request_schema_version: Literal[1] = SCENE_REQUEST_SCHEMA_VERSION
    binding: SceneSourceBinding
    x_field: StrictStr
    y_field: StrictStr
    z_field: StrictStr
    scalar_field: StrictStr | None = None
    filters: tuple[SceneFilter, ...] = ()

    @field_validator("x_field", "y_field", "z_field")
    @classmethod
    def valid_axis_field(cls, value: str) -> str:
        return _require_exact_text(value, "scene coordinate field ID")

    @field_validator("scalar_field")
    @classmethod
    def valid_scalar_field(cls, value: str | None) -> str | None:
        return None if value is None else _require_exact_text(value, "scene scalar field ID")

    @field_validator("filters")
    @classmethod
    def canonical_filters(cls, values: tuple[SceneFilter, ...]) -> tuple[SceneFilter, ...]:
        identifiers = [value.field_id for value in values]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scene request contains multiple filters for one field")
        return tuple(sorted(values, key=lambda value: value.field_id))

    @model_validator(mode="after")
    def distinct_axes(self) -> SceneRequest:
        if len({self.x_field, self.y_field, self.z_field}) != 3:
            raise ValueError("scene coordinate fields x, y, and z must be distinct")
        return self

    def canonical_payload(self) -> dict[str, object]:
        return {
            "scene_request_schema_version": self.scene_request_schema_version,
            "source": self.binding.identity_payload(),
            "coordinates": {
                "x": self.x_field,
                "y": self.y_field,
                "z": self.z_field,
            },
            "scalar": self.scalar_field,
            "filters": [filter_value.model_dump(mode="json") for filter_value in self.filters],
        }

    @property
    def request_id(self) -> str:
        return scene_request_id(self)


class SceneCounts(BaseModel):
    """Counts checked before any scene may be serialized or adopted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    points: NonNegativeInt
    edges: NonNegativeInt
    quads: NonNegativeInt
    bundle_bytes: NonNegativeInt


def scene_request_id(request: SceneRequest) -> str:
    digest = hashlib.sha256(_canonical_json_bytes(request.canonical_payload())).hexdigest()
    return f"scene-{digest}"


def scene_filters_match(
    filters: Iterable[SceneFilter],
    values: Mapping[str, object],
) -> bool:
    """Apply OR within each filter and AND across exact field filters."""

    return all(filter_value.matches(values.get(filter_value.field_id)) for filter_value in filters)


def validate_scene_request(
    request: SceneRequest,
    fields: Iterable[SceneFieldProfile],
) -> SceneRequest:
    """Check one normalized request against authoritative profile eligibility."""

    catalog: dict[str, SceneFieldProfile] = {}
    for field in fields:
        if field.field_id in catalog:
            raise SceneContractError(
                "invalid_scene_profile",
                f"scene profile repeats field {field.field_id!r}",
                details={"field_id": field.field_id},
            )
        catalog[field.field_id] = field
    for coordinate, field_id in (
        ("x", request.x_field),
        ("y", request.y_field),
        ("z", request.z_field),
    ):
        field = _request_field(catalog, field_id, role=coordinate)
        if not field.axis_eligible:
            raise SceneContractError(
                "invalid_scene_request",
                f"scene {coordinate} field {field_id!r} is not axis eligible",
                details={
                    "field_id": field_id,
                    "role": coordinate,
                    "reason": field.ineligible_reason,
                },
            )
    if request.scalar_field is not None:
        scalar = _request_field(catalog, request.scalar_field, role="scalar")
        if not scalar.scalar_eligible:
            raise SceneContractError(
                "invalid_scene_request",
                f"scene scalar field {scalar.field_id!r} is not scalar eligible",
                details={
                    "field_id": scalar.field_id,
                    "role": "scalar",
                    "reason": scalar.ineligible_reason,
                },
            )
    for filter_value in request.filters:
        field = _request_field(catalog, filter_value.field_id, role="filter")
        if field.filter_kind != filter_value.kind:
            raise SceneContractError(
                "invalid_scene_request",
                f"scene filter kind for {field.field_id!r} is not supported",
                details={
                    "field_id": field.field_id,
                    "requested_kind": filter_value.kind,
                    "supported_kind": field.filter_kind,
                },
            )
        if isinstance(filter_value, CategoricalSetFilter):
            unknown = [value for value in filter_value.values if value not in field.distinct_values]
            if unknown:
                raise SceneContractError(
                    "invalid_scene_request",
                    f"scene filter for {field.field_id!r} contains unobserved exact values",
                    details={"field_id": field.field_id, "values": unknown},
                )
    return request


def validate_scene_defaults(
    defaults: SceneSelectionDefaults,
    fields: Iterable[SceneFieldProfile],
) -> SceneSelectionDefaults:
    catalog = _unique_field_catalog(fields)
    for role, field_id in (
        ("x", defaults.x_field),
        ("y", defaults.y_field),
        ("z", defaults.z_field),
    ):
        if field_id is None:
            continue
        field = _request_field(catalog, field_id, role=role)
        if not field.axis_eligible or not field.varying:
            raise SceneContractError(
                "invalid_scene_profile",
                f"default scene {role} field {field_id!r} is not a varying axis",
                details={"field_id": field_id, "role": role},
            )
    if defaults.scalar_field is not None:
        scalar = _request_field(catalog, defaults.scalar_field, role="scalar")
        if not scalar.scalar_eligible:
            raise SceneContractError(
                "invalid_scene_profile",
                f"default scene scalar field {scalar.field_id!r} is not scalar eligible",
                details={"field_id": scalar.field_id, "role": "scalar"},
            )
    return defaults


def validate_scene_limits(counts: SceneCounts) -> SceneCounts:
    limits = (
        ("points", counts.points, MAX_SCENE_POINTS),
        ("edges", counts.edges, MAX_SCENE_EDGES),
        ("quads", counts.quads, MAX_SCENE_QUADS),
        ("bundle_bytes", counts.bundle_bytes, MAX_SCENE_BUNDLE_BYTES),
    )
    for name, actual, limit in limits:
        if actual > limit:
            raise SceneContractError(
                "scene_limit_exceeded",
                f"scene {name} count {actual:,} exceeds limit {limit:,}",
                details={"measure": name, "actual": actual, "limit": limit},
            )
    return counts


def canonical_gap_summaries(
    values: Iterable[SceneGapSummary],
) -> tuple[SceneGapSummary, ...]:
    summaries = tuple(values)
    if len(set(summaries)) != len(summaries):
        raise ValueError("scene gaps contain duplicate summaries")
    return tuple(
        sorted(
            summaries,
            key=lambda value: (
                -1 if value.block_index is None else value.block_index,
                value.code,
                "" if value.field_id is None else value.field_id,
            ),
        )
    )


def _request_field(
    catalog: Mapping[str, SceneFieldProfile],
    field_id: str,
    *,
    role: str,
) -> SceneFieldProfile:
    try:
        return catalog[field_id]
    except KeyError as exc:
        raise SceneContractError(
            "invalid_scene_request",
            f"scene {role} field {field_id!r} is unavailable",
            details={"field_id": field_id, "role": role},
        ) from exc


def _unique_field_catalog(
    fields: Iterable[SceneFieldProfile],
) -> dict[str, SceneFieldProfile]:
    catalog: dict[str, SceneFieldProfile] = {}
    for field in fields:
        if field.field_id in catalog:
            raise SceneContractError(
                "invalid_scene_profile",
                f"scene profile repeats field {field.field_id!r}",
                details={"field_id": field.field_id},
            )
        catalog[field.field_id] = field
    return catalog


def _finite_binary64(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be an explicit real number")
    try:
        binary64 = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be representable as binary64") from exc
    if not math.isfinite(binary64):
        raise ValueError(f"{label} must be finite")
    if isinstance(value, int) and int(binary64) != value:
        raise ValueError(f"{label} integer is not exactly representable as binary64")
    return 0.0 if binary64 == 0.0 else binary64


def _canonical_exact_strings(
    value: object,
    label: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list or tuple")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} must contain only exact strings")
        if "\x00" in item:
            raise ValueError(f"{label} must not contain NUL")
        values.append(item)
    result = tuple(sorted(set(values)))
    if not allow_empty and not result:
        raise ValueError(f"{label} must contain at least one value")
    return result


def _require_exact_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be exact text")
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be non-empty canonical text")
    return value


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
