from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from carnopy.domain.failures import ConfigError
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.preparation.models import DerivedFeature, PreparationConfig
from carnopy.preparation.source import SourceTable

GAS_CONSTANT_J_MOL_K = 8.31446261815324

FieldKind = Literal["numeric", "categorical", "auxiliary"]

COORDINATE_FIELDS = {
    "temperature": ("temperature_K", "K"),
    "pressure": ("pressure_Pa", "Pa"),
    "vapor_mass_fraction": ("vapor_mass_fraction", "1"),
}
CATEGORICAL_FIELDS = {
    "phase": "phase",
    "fluid": "fluid",
    "saturation_endpoint": "saturation_endpoint",
    "backend_model": "backend_model",
}
AUXILIARY_SOURCE_FIELDS = {
    "run_id",
    "case_id",
    "mode",
    "backend",
    "backend_model",
    "backend_version",
    "phase",
    "backend_phase",
    "valid",
    "failure_layer",
    "failure_code",
    "failure_message",
    "failure_property",
    "backend_error_type",
    "backend_error_message",
    "state_key",
    "state_key_version",
    "saturation_endpoint",
}
DERIVED_UNITS: dict[str, str] = {
    "specific_volume": "m^3/kg",
    "reduced_temperature": "1",
    "reduced_pressure": "1",
    "compressibility_factor": "1",
}


@dataclass(frozen=True)
class ResolvedField:
    semantic_name: str
    column: str
    unit: str | None
    kind: FieldKind
    source: Literal["coordinate", "property", "categorical", "auxiliary"]


@dataclass(frozen=True)
class ResolvedPreparation:
    numeric_features: tuple[ResolvedField, ...]
    targets: tuple[ResolvedField, ...]
    auxiliary: tuple[ResolvedField, ...]
    categorical_feature_fields: tuple[str, ...]
    derived_features: tuple[DerivedFeature, ...]
    semantic_mapping: dict[str, dict[str, Any]]


def resolve_preparation_fields(
    config: PreparationConfig,
    tables: tuple[SourceTable, ...],
) -> ResolvedPreparation:
    numeric = tuple(_resolve_numeric(field, tables) for field in config.features.numeric)
    targets = tuple(_resolve_numeric(field, tables) for field in config.targets)
    auxiliary = tuple(_resolve_auxiliary(field, tables) for field in config.auxiliary)
    categorical = tuple(item.field for item in config.categorical_features)
    for field in categorical:
        _resolve_categorical(field, tables)
    mapping: dict[str, dict[str, Any]] = {}
    for resolved_field in (*numeric, *targets, *auxiliary):
        mapping[resolved_field.semantic_name] = {
            "column": resolved_field.column,
            "unit": resolved_field.unit,
            "kind": resolved_field.kind,
            "source": resolved_field.source,
        }
    for field in categorical:
        resolved = _resolve_categorical(field, tables)
        mapping[field] = {
            "column": resolved.column,
            "unit": resolved.unit,
            "kind": resolved.kind,
            "source": resolved.source,
        }
    for derived in config.features.derived:
        mapping[derived] = {
            "column": derived,
            "unit": DERIVED_UNITS[derived],
            "kind": "numeric",
            "source": "derived",
            "formula": derived_formula(derived),
            "dependencies": derived_dependencies(derived),
        }
    return ResolvedPreparation(
        numeric_features=numeric,
        targets=targets,
        auxiliary=auxiliary,
        categorical_feature_fields=categorical,
        derived_features=config.features.derived,
        semantic_mapping=mapping,
    )


def derived_formula(feature: DerivedFeature) -> str:
    return {
        "specific_volume": "1 / mass_density",
        "reduced_temperature": "temperature / critical_temperature",
        "reduced_pressure": "pressure / critical_pressure",
        "compressibility_factor": ("pressure * molar_mass / (mass_density * R * temperature)"),
    }[feature]


def derived_dependencies(feature: DerivedFeature) -> tuple[str, ...]:
    return {
        "specific_volume": ("mass_density",),
        "reduced_temperature": ("temperature", "critical_temperature"),
        "reduced_pressure": ("pressure", "critical_pressure"),
        "compressibility_factor": (
            "pressure",
            "molar_mass",
            "mass_density",
            "temperature",
        ),
    }[feature]


def compute_derived_value(
    feature: DerivedFeature,
    row: pd.Series,
    table: SourceTable,
) -> tuple[float | None, list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []

    def need(field: str) -> float | None:
        value = source_value(field, row, table)
        if value is None:
            missing.append(field)
            return None
        if not math.isfinite(value):
            missing.append(field)
            reasons.append("nonfinite_derived_dependency")
            return None
        return value

    if feature == "specific_volume":
        density = need("mass_density")
        if density is None:
            reasons.append("missing_derived_dependency")
            return None, _unique(reasons), missing
        if density <= 0.0:
            return None, ["nonpositive_mass_density"], ["mass_density"]
        return 1.0 / density, [], []
    if feature == "reduced_temperature":
        temperature = need("temperature")
        critical = need("critical_temperature")
        if temperature is None or critical is None:
            reasons.append("missing_derived_dependency")
            return None, _unique(reasons), missing
        if critical <= 0.0:
            return None, ["nonpositive_critical_constant"], ["critical_temperature"]
        return temperature / critical, [], []
    if feature == "reduced_pressure":
        pressure = need("pressure")
        critical = need("critical_pressure")
        if pressure is None or critical is None:
            reasons.append("missing_derived_dependency")
            return None, _unique(reasons), missing
        if critical <= 0.0:
            return None, ["nonpositive_critical_constant"], ["critical_pressure"]
        return pressure / critical, [], []
    pressure = need("pressure")
    molar_mass = need("molar_mass")
    density = need("mass_density")
    temperature = need("temperature")
    if None in {pressure, molar_mass, density, temperature}:
        reasons.append("missing_derived_dependency")
        return None, _unique(reasons), missing
    assert pressure is not None
    assert molar_mass is not None
    assert density is not None
    assert temperature is not None
    if density <= 0.0:
        return None, ["nonpositive_mass_density"], ["mass_density"]
    if temperature <= 0.0:
        return None, ["nonpositive_temperature"], ["temperature"]
    return pressure * molar_mass / (density * GAS_CONSTANT_J_MOL_K * temperature), [], []


def source_value(field: str, row: pd.Series, table: SourceTable) -> float | None:
    column: str | None = None
    if field in COORDINATE_FIELDS:
        column = COORDINATE_FIELDS[field][0]
    elif field in PROPERTY_REGISTRY:
        column = PROPERTY_REGISTRY[field].column
    if column is not None and column in row.index:
        value = row[column]
        if pd.isna(value):
            return None
        return float(value)
    return _constant_from_metadata(field, row, table)


def sanitize_category(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value.strip().lower()).strip("_")
    return cleaned or "blank"


def _resolve_numeric(field: str, tables: tuple[SourceTable, ...]) -> ResolvedField:
    first = _resolve_numeric_for_table(field, tables[0])
    if first is None:
        raise ConfigError(f"unknown or unavailable numeric preparation field: {field}")
    for table in tables[1:]:
        candidate = _resolve_numeric_for_table(field, table)
        if candidate is None:
            raise ConfigError(
                "numeric preparation field "
                f"{field!r} is unavailable in {table.artifact_relative_path}"
            )
        if candidate.column != first.column or candidate.unit != first.unit:
            raise ConfigError(f"numeric preparation field {field!r} resolves inconsistently")
    return first


def _resolve_numeric_for_table(field: str, table: SourceTable) -> ResolvedField | None:
    if field in COORDINATE_FIELDS:
        column, unit = COORDINATE_FIELDS[field]
        return _from_column(field, column, unit, "coordinate", table, kind="numeric")
    if field in PROPERTY_REGISTRY:
        definition = PROPERTY_REGISTRY[field]
        return _from_column(
            field,
            definition.column,
            definition.unit,
            "property",
            table,
            kind="numeric",
        )
    return None


def _resolve_categorical(field: str, tables: tuple[SourceTable, ...]) -> ResolvedField:
    try:
        column = CATEGORICAL_FIELDS[field]
    except KeyError as exc:
        raise ConfigError(f"unsupported categorical preparation field: {field}") from exc
    first = _from_column(field, column, None, "categorical", tables[0], kind="categorical")
    for table in tables[1:]:
        _from_column(field, column, None, "categorical", table, kind="categorical")
    return first


def _resolve_auxiliary(field: str, tables: tuple[SourceTable, ...]) -> ResolvedField:
    numeric = _resolve_numeric_for_table(field, tables[0])
    if numeric is not None:
        for table in tables[1:]:
            if _resolve_numeric_for_table(field, table) is None:
                raise ConfigError(f"auxiliary field {field!r} is unavailable in all sources")
        return ResolvedField(field, numeric.column, numeric.unit, "auxiliary", numeric.source)
    if field in CATEGORICAL_FIELDS:
        categorical = _resolve_categorical(field, tables)
        return ResolvedField(field, categorical.column, None, "auxiliary", "categorical")
    if field in AUXILIARY_SOURCE_FIELDS:
        for table in tables:
            if field not in table.frame.columns:
                raise ConfigError(
                    f"auxiliary field {field!r} is unavailable in {table.artifact_relative_path}"
                )
        return ResolvedField(field, field, None, "auxiliary", "auxiliary")
    raise ConfigError(f"unknown or unavailable auxiliary preparation field: {field}")


def _from_column(
    field: str,
    column: str,
    unit: str | None,
    source: Literal["coordinate", "property", "categorical", "auxiliary"],
    table: SourceTable,
    *,
    kind: FieldKind,
) -> ResolvedField:
    if column not in table.frame.columns:
        raise ConfigError(
            f"semantic field {field!r} resolves to missing source column {column!r} "
            f"in {table.artifact_relative_path}"
        )
    if unit is not None:
        canonical_units = table.metadata.get("canonical_units")
        if not isinstance(canonical_units, dict):
            raise ConfigError("source metadata does not contain canonical_units")
        actual = canonical_units.get(column)
        if actual != unit:
            raise ConfigError(
                f"semantic field {field!r} expected unit {unit!r} for column {column!r}, "
                f"found {actual!r}"
            )
    return ResolvedField(field, column, unit, kind, source)


def _constant_from_metadata(field: str, row: pd.Series, table: SourceTable) -> float | None:
    if field not in {"critical_temperature", "critical_pressure", "molar_mass"}:
        return None
    constants = table.metadata.get("fluid_constants")
    if not isinstance(constants, dict):
        return None
    fluid = row.get("fluid")
    if not isinstance(fluid, str):
        return None
    fluid_constants = constants.get(fluid)
    if not isinstance(fluid_constants, dict):
        return None
    value = fluid_constants.get(field)
    if value is None or pd.isna(value):
        return None
    return float(value)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
