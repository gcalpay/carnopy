from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from carnopy.config.normalize import canonical_json_bytes
from carnopy.domain.failures import ConfigError
from carnopy.preparation.fields import (
    ResolvedPreparation,
    compute_derived_value,
    sanitize_category,
)
from carnopy.preparation.models import PreparationConfig
from carnopy.preparation.source import LoadedPreparationSource, SourceTable
from carnopy.provenance import sha256_bytes
from carnopy.results import PreparationStatus

IDENTITY_COLUMNS = [
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
]
SOURCE_DIAGNOSTIC_COLUMNS = [
    "source_valid",
    "source_failure_layer",
    "source_failure_code",
    "source_failure_message",
    "source_failure_property",
    "source_backend_error_type",
    "source_backend_error_message",
]


@dataclass(frozen=True)
class CandidateRow:
    values: dict[str, Any]
    exclusion: dict[str, Any] | None
    categorical_values: dict[str, str]


@dataclass(frozen=True)
class PreparedRows:
    prepared_rows: list[dict[str, Any]]
    exclusion_rows: list[dict[str, Any]]
    categories: dict[str, list[str]]
    status: PreparationStatus


def build_prepared_rows(
    config: PreparationConfig,
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
) -> PreparedRows:
    candidates = _candidate_rows(config, source_data, resolved)
    categories = _resolve_categories(config, candidates)
    prepared_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.exclusion is not None:
            exclusion_rows.append(candidate.exclusion)
            continue
        prepared_rows.append(
            _encode_candidate(candidate.values, candidate.categorical_values, categories)
        )

    status: PreparationStatus
    if not prepared_rows:
        status = "no_eligible_rows"
    elif exclusion_rows:
        status = "completed_with_exclusions"
    else:
        status = "completed"
    return PreparedRows(
        prepared_rows=prepared_rows,
        exclusion_rows=exclusion_rows,
        categories=categories,
        status=status,
    )


def exclusions_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        *IDENTITY_COLUMNS,
        *SOURCE_DIAGNOSTIC_COLUMNS,
        "primary_reason",
        "reason_codes",
        "missing_or_invalid_fields",
    ]
    return pd.DataFrame(rows, columns=columns)


def _candidate_rows(
    config: PreparationConfig,
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
) -> list[CandidateRow]:
    candidates: list[CandidateRow] = []
    for table in source_data.tables:
        for row_position, (_, row) in enumerate(table.frame.iterrows()):
            identity = _source_identity(row, table, row_position)
            diagnostics = _source_diagnostics(row)
            values: dict[str, Any] = {**identity, **diagnostics}
            reasons: list[str] = []
            fields: list[str] = []

            for field in resolved.numeric_features:
                _copy_required_numeric(
                    field.semantic_name,
                    field.column,
                    row,
                    values,
                    reasons,
                    fields,
                )
            for field in resolved.targets:
                _copy_required_numeric(
                    field.semantic_name,
                    field.column,
                    row,
                    values,
                    reasons,
                    fields,
                )
            for field in resolved.auxiliary:
                _copy_auxiliary(field.semantic_name, field.column, row, values, reasons, fields)
            for derived in resolved.derived_features:
                value, derived_reasons, derived_fields = compute_derived_value(derived, row, table)
                if derived_reasons:
                    reasons.extend(derived_reasons)
                    fields.extend(derived_fields)
                else:
                    values[derived] = value

            categorical_values: dict[str, str] = {}
            for categorical in config.categorical_features:
                value = row.get(categorical.field)
                if _missing(value):
                    reasons.append("missing_required_field")
                    fields.append(categorical.field)
                else:
                    categorical_values[categorical.field] = str(value)

            if not bool(row.get("valid", True)):
                reasons.append("source_row_invalid_diagnostic")
            blocking_reasons = [
                reason for reason in reasons if reason != "source_row_invalid_diagnostic"
            ]
            exclusion = None
            if blocking_reasons:
                reason_codes = _unique(reasons)
                exclusion = {
                    **identity,
                    **diagnostics,
                    "primary_reason": blocking_reasons[0],
                    "reason_codes": reason_codes,
                    "missing_or_invalid_fields": _unique(fields),
                }
            candidates.append(CandidateRow(values, exclusion, categorical_values))
    return candidates


def _copy_required_numeric(
    semantic_name: str,
    column: str,
    row: pd.Series,
    values: dict[str, Any],
    reasons: list[str],
    fields: list[str],
) -> None:
    value = row.get(column)
    if _missing(value):
        reasons.append("missing_required_field")
        fields.append(semantic_name)
        return
    numeric = float(cast(Any, value))
    if not math.isfinite(numeric):
        reasons.append("nonfinite_required_field")
        fields.append(semantic_name)
        return
    values[semantic_name] = numeric


def _copy_auxiliary(
    semantic_name: str,
    column: str,
    row: pd.Series,
    values: dict[str, Any],
    reasons: list[str],
    fields: list[str],
) -> None:
    if semantic_name in values:
        return
    value = row.get(column)
    if _missing(value):
        reasons.append("missing_auxiliary_field")
        fields.append(semantic_name)
        return
    values[semantic_name] = _json_value(value)


def _resolve_categories(
    config: PreparationConfig,
    candidates: list[CandidateRow],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    non_excluded = [candidate for candidate in candidates if candidate.exclusion is None]
    for categorical in config.categorical_features:
        observed = sorted(
            {candidate.categorical_values[categorical.field] for candidate in non_excluded},
            key=str,
        )
        if categorical.categories == "observed":
            selected = observed
        else:
            selected = list(categorical.categories)
            missing = sorted(set(observed) - set(selected), key=str)
            if missing:
                raise ConfigError(
                    f"explicit categories for {categorical.field!r} omit observed values: "
                    + ", ".join(missing)
                )
        _validate_category_columns(categorical.field, selected)
        result[categorical.field] = selected
    _validate_global_output_columns(result)
    return result


def _encode_candidate(
    values: dict[str, Any],
    categorical_values: dict[str, str],
    categories: dict[str, list[str]],
) -> dict[str, Any]:
    row = dict(values)
    for field, selected in categories.items():
        value = categorical_values[field]
        for category in selected:
            row[f"{field}__{sanitize_category(category)}"] = value == category
    return row


def _source_identity(row: pd.Series, table: SourceTable, row_index: int) -> dict[str, Any]:
    return {
        "source_kind": table.kind,
        "source_run_id": _text_or_none(row.get("run_id")) or table.run_id,
        "source_artifact": table.artifact_relative_path,
        "source_row_index": row_index,
        "source_row_hash": _row_hash(row),
        "backend_model": _text_or_none(row.get("backend_model")) or table.backend_model,
        "state_key": _text_or_none(row.get("state_key")),
        "state_key_version": _int_or_none(row.get("state_key_version")),
        "sweep_id": table.sweep_id,
        "sweep_run_id": table.sweep_run_id,
    }


def _source_diagnostics(row: pd.Series) -> dict[str, Any]:
    return {
        "source_valid": bool(row.get("valid", False)),
        "source_failure_layer": _text_or_none(row.get("failure_layer")),
        "source_failure_code": _text_or_none(row.get("failure_code")),
        "source_failure_message": _text_or_none(row.get("failure_message")),
        "source_failure_property": _text_or_none(row.get("failure_property")),
        "source_backend_error_type": _text_or_none(row.get("backend_error_type")),
        "source_backend_error_message": _text_or_none(row.get("backend_error_message")),
    }


def _row_hash(row: pd.Series) -> str:
    payload = {str(key): _json_value(value) for key, value in row.items()}
    return sha256_bytes(canonical_json_bytes(payload))


def _json_value(value: Any) -> Any:
    if _missing(value):
        return None
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, float):
        return value
    if isinstance(value, int | str | bool):
        return value
    return str(value)


def _missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text_or_none(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if _missing(value):
        return None
    return int(value)


def _validate_category_columns(field: str, categories: list[str]) -> None:
    columns = [f"{field}__{sanitize_category(category)}" for category in categories]
    if len(columns) != len(set(columns)):
        raise ConfigError(f"one-hot column-name collision for categorical field {field!r}")
    pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    invalid = [column for column in columns if pattern.fullmatch(column) is None]
    if invalid:
        raise ConfigError(f"invalid one-hot output columns: {', '.join(invalid)}")


def _validate_global_output_columns(categories: dict[str, list[str]]) -> None:
    columns: list[str] = []
    for field, selected in categories.items():
        columns.extend(f"{field}__{sanitize_category(category)}" for category in selected)
    if len(columns) != len(set(columns)):
        raise ConfigError("one-hot output columns collide across categorical fields")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
