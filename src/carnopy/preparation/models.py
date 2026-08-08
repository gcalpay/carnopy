from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from carnopy.domain.failures import ConfigError

PreparationStatus = Literal[
    "completed",
    "completed_with_exclusions",
    "no_eligible_rows",
    "failed",
]
DerivedFeature = Literal[
    "specific_volume",
    "reduced_temperature",
    "reduced_pressure",
    "compressibility_factor",
]
LegacyPreparationFormat = Literal["parquet"]
ArrayFormat = Literal["npy", "npz", "safetensors"]
ArrayDType = Literal["float32", "float64"]
PartitionName = Literal["train", "validation", "test", "all"]
ScenarioKind = Literal[
    "unsplit",
    "shuffle",
    "stratified_hash",
    "coordinate_block",
    "range_holdout",
    "leave_fluid_out",
    "phase_holdout",
    "model_holdout",
]
TransformMethod = Literal["log10", "standard", "minmax", "robust"]
BaselineModel = Literal["dummy_mean", "ridge", "hist_gradient_boosting"]

IDENTITY_FIELDS = {
    "source_kind",
    "source_run_id",
    "source_artifact",
    "source_row_index",
    "source_row_hash",
    "source_state_hash",
    "source_mode",
    "source_fluid",
    "source_phase",
    "source_temperature_K",
    "source_pressure_Pa",
    "source_vapor_mass_fraction",
    "source_saturation_endpoint",
    "backend_model",
    "state_key",
    "state_key_version",
    "sweep_id",
    "sweep_run_id",
}


class SourcePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_partial_sweep: bool = False


class PreparationFeatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    numeric: tuple[str, ...] = ()
    derived: tuple[DerivedFeature, ...] = ()

    @field_validator("numeric")
    @classmethod
    def unique_numeric(cls, fields: tuple[str, ...]) -> tuple[str, ...]:
        return _clean_unique(fields, "numeric feature")

    @field_validator("derived")
    @classmethod
    def unique_derived(cls, fields: tuple[DerivedFeature, ...]) -> tuple[DerivedFeature, ...]:
        if len(set(fields)) != len(fields):
            raise ValueError("duplicate derived features are not allowed")
        return fields


class CategoricalFeatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["phase", "fluid"]
    encoding: Literal["one_hot"]
    categories: Literal["observed"] | tuple[str, ...] = "observed"

    @field_validator("categories", mode="before")
    @classmethod
    def normalize_categories(cls, value: object) -> object:
        if value == "observed":
            return value
        if isinstance(value, list | tuple):
            cleaned = tuple(str(item).strip() for item in value)
            if any(not item for item in cleaned):
                raise ValueError("explicit categories must not contain blank values")
            if len(set(cleaned)) != len(cleaned):
                raise ValueError("duplicate explicit categories are not allowed")
            return cleaned
        return value


class PreparationArrayOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    formats: tuple[ArrayFormat, ...] = Field(default_factory=tuple)
    dtype: ArrayDType | None = None
    include_auxiliary: bool = False

    @field_validator("formats", mode="before")
    @classmethod
    def normalize_formats(cls, value: object) -> object:
        if value is None:
            return ()
        if not isinstance(value, list | tuple):
            return value
        normalized = tuple(str(item).strip().lower() for item in value)
        return normalized

    @field_validator("formats")
    @classmethod
    def validate_formats(
        cls,
        formats: tuple[ArrayFormat, ...],
    ) -> tuple[ArrayFormat, ...]:
        if not formats:
            raise ValueError("at least one array output format is required")
        if len(set(formats)) != len(formats):
            raise ValueError("duplicate array output formats are not allowed")
        order: tuple[ArrayFormat, ...] = ("npy", "npz", "safetensors")
        selected = set(formats)
        return tuple(item for item in order if item in selected)

    @model_validator(mode="after")
    def validate_dtype(self) -> PreparationArrayOutputsConfig:
        if self.dtype is None:
            raise ValueError("array output dtype is required when arrays are requested")
        return self


class PreparationOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    formats: tuple[str, ...] = ("parquet",)
    parquet: bool = True
    arrays: PreparationArrayOutputsConfig | None = None

    @field_validator("formats", mode="before")
    @classmethod
    def normalize_formats(cls, value: object) -> object:
        if value is None:
            return ("parquet",)
        if not isinstance(value, list | tuple):
            return value
        return tuple(str(item).strip().lower() for item in value)

    @field_validator("formats")
    @classmethod
    def validate_formats(
        cls,
        formats: tuple[str, ...],
    ) -> tuple[LegacyPreparationFormat, ...]:
        if not formats:
            raise ValueError("at least one preparation output format is required")
        if len(set(formats)) != len(formats):
            raise ValueError("duplicate preparation output formats are not allowed")
        if formats != ("parquet",):
            raise ValueError("array formats must be declared under outputs.arrays")
        return ("parquet",)

    @model_validator(mode="after")
    def validate_parquet(self) -> PreparationOutputsConfig:
        if not self.parquet:
            raise ValueError("Parquet output is mandatory in this stage")
        return self

    @property
    def output_format_names(self) -> tuple[str, ...]:
        if self.arrays is None:
            return ("parquet",)
        return ("parquet", *self.arrays.formats)


class MatrixDiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_threshold: float = Field(default=0.995, gt=0.0, le=1.0)
    near_constant_relative_spread: float = Field(default=1e-12, gt=0.0)


class BaselineDiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[BaselineModel, ...] = ("dummy_mean", "ridge")
    random_seed: int = 42
    ridge_alpha: float = Field(default=1.0, gt=0.0)
    histogram_max_iterations: int = Field(default=100, ge=1)

    @field_validator("models")
    @classmethod
    def validate_models(cls, models: tuple[BaselineModel, ...]) -> tuple[BaselineModel, ...]:
        if not models:
            raise ValueError("baseline diagnostics require at least one model")
        if len(set(models)) != len(models):
            raise ValueError("duplicate baseline diagnostic models are not allowed")
        canonical: tuple[BaselineModel, ...] = (
            "dummy_mean",
            "ridge",
            "hist_gradient_boosting",
        )
        selected = set(models)
        return tuple(model for model in canonical if model in selected)


class PreparationQualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix_diagnostics: MatrixDiagnosticsConfig | None = None
    baseline_diagnostics: BaselineDiagnosticsConfig | None = None


class StratificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    categorical: tuple[str, ...] = ()
    numeric_bins: dict[str, tuple[float, ...]] = Field(default_factory=dict)

    @field_validator("categorical")
    @classmethod
    def unique_categorical(cls, fields: tuple[str, ...]) -> tuple[str, ...]:
        return _clean_unique(fields, "stratification field")

    @field_validator("numeric_bins")
    @classmethod
    def validate_numeric_bins(
        cls,
        bins: dict[str, tuple[float, ...]],
    ) -> dict[str, tuple[float, ...]]:
        result: dict[str, tuple[float, ...]] = {}
        for raw_field, boundaries in bins.items():
            field = str(raw_field).strip()
            if not field:
                raise ValueError("numeric stratification fields must not be blank")
            if not boundaries:
                raise ValueError(f"numeric stratification field {field!r} requires boundaries")
            values = tuple(float(value) for value in boundaries)
            if any(not math.isfinite(value) for value in values):
                raise ValueError(
                    f"numeric stratification field {field!r} has non-finite boundaries"
                )
            if any(right <= left for left, right in pairwise(values)):
                raise ValueError(
                    f"numeric stratification field {field!r} boundaries must be strictly increasing"
                )
            result[field] = values
        return {field: result[field] for field in sorted(result)}

    @model_validator(mode="after")
    def require_strata(self) -> StratificationConfig:
        if not self.categorical and not self.numeric_bins:
            raise ValueError("stratification requires categorical fields or numeric bins")
        overlap = set(self.categorical) & set(self.numeric_bins)
        if overlap:
            raise ValueError(
                "stratification fields cannot be both categorical and numeric: "
                + ", ".join(sorted(overlap))
            )
        return self


class TransformationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    methods: tuple[TransformMethod, ...] = Field(min_length=1)

    @field_validator("field")
    @classmethod
    def clean_field(cls, field: str) -> str:
        cleaned = field.strip()
        if not cleaned:
            raise ValueError("transformation field must not be blank")
        return cleaned

    @field_validator("methods")
    @classmethod
    def unique_methods(cls, methods: tuple[TransformMethod, ...]) -> tuple[TransformMethod, ...]:
        if len(set(methods)) != len(methods):
            raise ValueError("duplicate transformation methods are not allowed")
        return methods


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: ScenarioKind
    seed: int | None = None
    partitions: dict[PartitionName, float] = Field(default_factory=dict)
    field: str | None = None
    holdouts: dict[PartitionName, Any] = Field(default_factory=dict)
    remainder: PartitionName | None = None
    strata: StratificationConfig | None = None
    transformations: tuple[TransformationConfig, ...] = ()

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        cleaned = name.strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", cleaned) is None:
            raise ValueError(
                "scenario names must be safe slugs using letters, numbers, hyphens, or underscores"
            )
        return cleaned

    @field_validator("field")
    @classmethod
    def clean_optional_field(cls, field: str | None) -> str | None:
        if field is None:
            return None
        cleaned = field.strip()
        if not cleaned:
            raise ValueError("scenario field must not be blank")
        return cleaned

    @field_validator("partitions")
    @classmethod
    def validate_partitions(
        cls,
        partitions: dict[PartitionName, float],
    ) -> dict[PartitionName, float]:
        for partition, value in partitions.items():
            if value <= 0.0:
                raise ValueError(f"partition {partition!r} must have a positive ratio")
        return partitions

    @field_validator("transformations")
    @classmethod
    def unique_transform_outputs(
        cls,
        transformations: tuple[TransformationConfig, ...],
    ) -> tuple[TransformationConfig, ...]:
        outputs = [
            f"{transform.field}__{'__'.join(transform.methods)}" for transform in transformations
        ]
        if len(set(outputs)) != len(outputs):
            raise ValueError("duplicate transformation output columns are not allowed")
        return transformations

    @model_validator(mode="after")
    def validate_shape(self) -> ScenarioConfig:
        if self.kind == "unsplit":
            if self.partitions and set(self.partitions) != {"all"}:
                raise ValueError("unsplit scenarios may only declare the all partition")
            if self.holdouts:
                raise ValueError("unsplit scenarios must not declare holdouts")
            if self.remainder is not None:
                raise ValueError("unsplit scenarios must not declare a remainder")
            if self.strata is not None:
                raise ValueError("unsplit scenarios must not declare strata")
            return self
        if self.kind == "shuffle":
            if not self.partitions:
                raise ValueError("shuffle scenarios require partitions")
            if "all" in self.partitions:
                raise ValueError("shuffle scenarios must not use the all partition")
            if self.holdouts:
                raise ValueError("shuffle scenarios must not declare holdouts")
            if self.remainder is not None:
                raise ValueError("shuffle scenarios must not declare a remainder")
            if self.strata is not None:
                raise ValueError("shuffle scenarios must not declare strata")
            return self
        if self.kind == "stratified_hash":
            if not self.partitions:
                raise ValueError("stratified_hash scenarios require partitions")
            if "all" in self.partitions:
                raise ValueError("stratified_hash scenarios must not use the all partition")
            if self.holdouts:
                raise ValueError("stratified_hash scenarios must not declare holdouts")
            if self.remainder is not None:
                raise ValueError("stratified_hash scenarios must not declare a remainder")
            if self.strata is None:
                raise ValueError("stratified_hash scenarios require strata")
            return self
        if self.strata is not None:
            raise ValueError(f"{self.kind} scenarios must not declare strata")
        if self.kind in {"range_holdout", "coordinate_block"}:
            if not self.holdouts:
                raise ValueError(f"{self.kind} scenarios require holdouts")
            if self.remainder is None:
                raise ValueError(f"{self.kind} scenarios require a remainder partition")
            if self.remainder in self.holdouts:
                raise ValueError(f"{self.kind} scenarios cannot use the remainder as a holdout")
            if "all" in self.holdouts or self.remainder == "all":
                raise ValueError(f"{self.kind} scenarios must not use the all partition")
            if self.partitions:
                raise ValueError(f"{self.kind} scenarios must not declare partitions")
            if self.kind == "range_holdout" and self.field is None:
                raise ValueError("range_holdout scenarios require field")
            return self
        if not self.holdouts:
            raise ValueError(f"{self.kind} scenarios require holdouts")
        if self.remainder is None:
            raise ValueError(f"{self.kind} scenarios require a remainder partition")
        if self.remainder in self.holdouts:
            raise ValueError(f"{self.kind} scenarios cannot use the remainder as a holdout")
        if "all" in self.holdouts or self.remainder == "all":
            raise ValueError(f"{self.kind} scenarios must not use the all partition")
        if self.partitions:
            raise ValueError(f"{self.kind} scenarios must not declare partitions")
        if self.field is not None:
            raise ValueError(f"{self.kind} scenarios use their fixed categorical field")
        return self


class PreparationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    document_type: Literal["preparation"]
    source_policy: SourcePolicyConfig = Field(default_factory=SourcePolicyConfig)
    features: PreparationFeatureConfig
    categorical_features: tuple[CategoricalFeatureConfig, ...] = ()
    targets: tuple[str, ...] = Field(min_length=1)
    auxiliary: tuple[str, ...] = ()
    scenarios: tuple[ScenarioConfig, ...] = ()
    quality: PreparationQualityConfig = Field(default_factory=PreparationQualityConfig)
    outputs: PreparationOutputsConfig = Field(default_factory=PreparationOutputsConfig)

    @field_validator("targets")
    @classmethod
    def unique_targets(cls, fields: tuple[str, ...]) -> tuple[str, ...]:
        return _clean_unique(fields, "target")

    @field_validator("auxiliary")
    @classmethod
    def unique_auxiliary(cls, fields: tuple[str, ...]) -> tuple[str, ...]:
        return _clean_unique(fields, "auxiliary field")

    @model_validator(mode="after")
    def validate_roles(self) -> PreparationConfig:
        categorical_fields = tuple(item.field for item in self.categorical_features)
        if len(set(categorical_fields)) != len(categorical_fields):
            raise ValueError("duplicate categorical feature fields are not allowed")
        scenario_names = tuple(item.name for item in self.scenarios)
        if len(set(scenario_names)) != len(scenario_names):
            raise ValueError("duplicate preparation scenario names are not allowed")
        feature_names = (
            set(self.features.numeric) | set(self.features.derived) | set(categorical_fields)
        )
        if not feature_names:
            raise ValueError("at least one preparation feature is required")
        feature_target_overlap = feature_names & set(self.targets)
        if feature_target_overlap:
            raise ValueError(
                "fields may not be both features and targets: "
                + ", ".join(sorted(feature_target_overlap))
            )
        identity_feature_targets = (
            set(self.features.numeric) | set(self.targets)
        ) & IDENTITY_FIELDS
        if identity_feature_targets:
            raise ValueError(
                "identity fields cannot be requested as features or targets: "
                + ", ".join(sorted(identity_feature_targets))
            )
        aux_conflicts = set(self.auxiliary) & (
            set(self.features.numeric) | set(self.features.derived) | set(self.targets)
        )
        if aux_conflicts:
            raise ValueError(
                "auxiliary fields cannot duplicate numeric features, derived features, or targets: "
                + ", ".join(sorted(aux_conflicts))
            )
        invalid_identity_derived = set(self.features.derived) & IDENTITY_FIELDS
        if invalid_identity_derived:
            raise ValueError(
                "identity fields cannot be requested as derived features: "
                + ", ".join(sorted(invalid_identity_derived))
            )
        return self


@dataclass(frozen=True)
class LoadedPreparationConfig:
    path: Path
    raw_bytes: bytes
    model: PreparationConfig


def load_preparation_config(path: str | Path) -> LoadedPreparationConfig:
    config_path = Path(path)
    try:
        raw_bytes = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"could not read preparation configuration {config_path}: {exc}") from exc
    return load_preparation_config_bytes(raw_bytes, source_name=str(config_path))


def load_preparation_config_bytes(
    raw_bytes: bytes,
    *,
    source_name: str = "<memory>",
) -> LoadedPreparationConfig:
    """Load one preparation configuration from exact in-memory YAML bytes."""
    config_path = Path(source_name)
    try:
        payload: Any = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("preparation configuration root must be a YAML mapping")
    try:
        model = PreparationConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
    return LoadedPreparationConfig(path=config_path, raw_bytes=raw_bytes, model=model)


def _clean_unique(fields: tuple[str, ...], label: str) -> tuple[str, ...]:
    cleaned = tuple(str(field).strip() for field in fields)
    if any(not field for field in cleaned):
        raise ValueError(f"{label} names must not be blank")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"duplicate {label}s are not allowed")
    return cleaned
