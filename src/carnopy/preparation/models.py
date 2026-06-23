from __future__ import annotations

from dataclasses import dataclass
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
PreparationFormat = Literal["parquet"]

IDENTITY_FIELDS = {
    "source_kind",
    "source_run_id",
    "source_artifact",
    "source_row_index",
    "source_row_hash",
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


class PreparationOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    formats: tuple[PreparationFormat, ...] = ("parquet",)

    @field_validator("formats", mode="before")
    @classmethod
    def normalize_formats(cls, value: object) -> object:
        if value is None:
            return ("parquet",)
        if not isinstance(value, list | tuple):
            return value
        normalized = tuple(str(item).strip().lower() for item in value)
        return normalized

    @field_validator("formats")
    @classmethod
    def validate_formats(
        cls,
        formats: tuple[PreparationFormat, ...],
    ) -> tuple[PreparationFormat, ...]:
        if not formats:
            raise ValueError("at least one preparation output format is required")
        if len(set(formats)) != len(formats):
            raise ValueError("duplicate preparation output formats are not allowed")
        if formats != ("parquet",):
            raise ValueError("only parquet preparation output is supported in this stage")
        return formats


class PreparationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    document_type: Literal["preparation"]
    source_policy: SourcePolicyConfig = Field(default_factory=SourcePolicyConfig)
    features: PreparationFeatureConfig
    categorical_features: tuple[CategoricalFeatureConfig, ...] = ()
    targets: tuple[str, ...] = Field(min_length=1)
    auxiliary: tuple[str, ...] = ()
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
