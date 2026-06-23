from __future__ import annotations

import json
import math
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pandas as pd

from carnopy._version import __version__
from carnopy.config.normalize import canonical_json_bytes
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.preparation.fields import (
    DERIVED_UNITS,
    GAS_CONSTANT_J_MOL_K,
    ResolvedPreparation,
    compute_derived_value,
    derived_dependencies,
    derived_formula,
    resolve_preparation_fields,
    sanitize_category,
)
from carnopy.preparation.models import (
    LoadedPreparationConfig,
    PreparationConfig,
    load_preparation_config,
)
from carnopy.preparation.source import (
    LoadedPreparationSource,
    SourceTable,
    load_preparation_source,
)
from carnopy.provenance import sha256_bytes, sha256_file
from carnopy.results import PreparationResult, PreparationStatus

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
PREPARATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PreparationLayout:
    staging_directory: Path
    final_directory: Path


@dataclass(frozen=True)
class CandidateRow:
    values: dict[str, Any]
    exclusion: dict[str, Any] | None
    categorical_values: dict[str, str]


def prepare_dataset(
    source: str | Path,
    config: str | Path,
    *,
    output_root: str | Path = "prepared",
) -> PreparationResult:
    loaded = load_preparation_config(config)
    source_data = load_preparation_source(
        source,
        allow_partial_sweep=loaded.model.source_policy.allow_partial_sweep,
    )
    resolved = resolve_preparation_fields(loaded.model, source_data.tables)
    normalized_bytes = _normalized_preparation_bytes(loaded.model)
    request_id = f"prep-{sha256_bytes(normalized_bytes)}"
    preparation_run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    layout = _create_layout(
        Path(output_root),
        preparation_run_id=preparation_run_id,
        created_at=created_at,
    )
    try:
        result = _write_preparation_bundle(
            loaded=loaded,
            source_data=source_data,
            resolved=resolved,
            layout=layout,
            request_id=request_id,
            normalized_bytes=normalized_bytes,
            preparation_run_id=preparation_run_id,
            created_at=created_at,
        )
        _finalize_layout(layout)
        return PreparationResult(
            preparation_request_id=result["preparation_request_id"],
            preparation_context_id=result["preparation_context_id"],
            preparation_run_id=preparation_run_id,
            status=result["status"],
            output_directory=layout.final_directory,
            eligible_row_count=result["eligible_row_count"],
            excluded_row_count=result["excluded_row_count"],
            unsplit_path=(
                None
                if result["unsplit_path"] is None
                else layout.final_directory / "data" / "unsplit.parquet"
            ),
            exclusions_path=layout.final_directory / "data" / "exclusions.parquet",
            manifest_path=layout.final_directory / "manifest.json",
            diagnostics_path=layout.final_directory / "diagnostics.json",
            dataset_card_path=layout.final_directory / "dataset_card.md",
        )
    except Exception:
        # The staging directory is intentionally left in place only if cleanup itself fails;
        # source runs and sweep bundles are never modified.
        _cleanup_staging(layout.staging_directory)
        raise


def _write_preparation_bundle(
    *,
    loaded: LoadedPreparationConfig,
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
    layout: PreparationLayout,
    request_id: str,
    normalized_bytes: bytes,
    preparation_run_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    data_directory = layout.staging_directory / "data"
    data_directory.mkdir()
    candidates = _candidate_rows(loaded.model, source_data, resolved)
    categories = _resolve_categories(loaded.model, candidates)
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

    unsplit_path: Path | None = None
    if prepared_rows:
        unsplit_path = data_directory / "unsplit.parquet"
        _write_parquet(pd.DataFrame(prepared_rows), unsplit_path)
    exclusions_path = data_directory / "exclusions.parquet"
    _write_parquet(_exclusions_frame(exclusion_rows), exclusions_path)
    _write_bytes(layout.staging_directory / "preparation.original.yaml", loaded.raw_bytes)
    _write_bytes(layout.staging_directory / "preparation.normalized.json", normalized_bytes)

    context_id = _preparation_context_id(
        request_id=request_id,
        source_data=source_data,
        formats=loaded.model.outputs.formats,
    )
    artifact_names = [
        "preparation.original.yaml",
        "preparation.normalized.json",
        "data/exclusions.parquet",
    ]
    if unsplit_path is not None:
        artifact_names.append("data/unsplit.parquet")
    artifact_hashes = _hash_artifacts(layout.staging_directory, artifact_names)
    manifest = _manifest(
        loaded=loaded,
        source_data=source_data,
        resolved=resolved,
        categories=categories,
        status=status,
        request_id=request_id,
        context_id=context_id,
        preparation_run_id=preparation_run_id,
        created_at=created_at,
        eligible_row_count=len(prepared_rows),
        excluded_row_count=len(exclusion_rows),
        artifact_hashes=artifact_hashes,
    )
    _write_json(layout.staging_directory / "manifest.json", manifest)
    diagnostics = _diagnostics(source_data, status, exclusion_rows)
    _write_json(layout.staging_directory / "diagnostics.json", diagnostics)
    _write_text(layout.staging_directory / "dataset_card.md", _dataset_card(manifest, diagnostics))
    final_hash_names = [*artifact_names, "diagnostics.json", "dataset_card.md"]
    artifact_hashes = _hash_artifacts(layout.staging_directory, final_hash_names)
    manifest["artifact_hashes"] = artifact_hashes
    _write_json(layout.staging_directory / "manifest.json", manifest)
    return {
        "preparation_request_id": request_id,
        "preparation_context_id": context_id,
        "status": status,
        "eligible_row_count": len(prepared_rows),
        "excluded_row_count": len(exclusion_rows),
        "unsplit_path": unsplit_path,
    }


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


def _manifest(
    *,
    loaded: LoadedPreparationConfig,
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
    categories: dict[str, list[str]],
    status: PreparationStatus,
    request_id: str,
    context_id: str,
    preparation_run_id: str,
    created_at: datetime,
    eligible_row_count: int,
    excluded_row_count: int,
    artifact_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "preparation_schema_version": PREPARATION_SCHEMA_VERSION,
        "preparation_request_id": request_id,
        "preparation_context_id": context_id,
        "preparation_run_id": preparation_run_id,
        "status": status,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "carnopy_version": __version__,
        "source": source_data.source_identity,
        "source_artifacts": [
            {
                "kind": table.kind,
                "run_id": table.run_id,
                "backend_model": table.backend_model,
                "artifact": table.artifact_relative_path,
                "sha256": table.artifact_sha256,
            }
            for table in source_data.tables
        ],
        "partial_sweep_source": source_data.partial_sweep_source,
        "included_child_models": list(source_data.included_child_models),
        "missing_child_models": list(source_data.missing_child_models),
        "semantic_field_mapping": resolved.semantic_mapping,
        "features": {
            "numeric": list(loaded.model.features.numeric),
            "derived": list(loaded.model.features.derived),
            "categorical": [
                item.model_dump(mode="json") for item in loaded.model.categorical_features
            ],
        },
        "targets": list(loaded.model.targets),
        "auxiliary": list(loaded.model.auxiliary),
        "derived_features": {
            feature: {
                "formula": derived_formula(feature),
                "dependencies": list(derived_dependencies(feature)),
                "unit": DERIVED_UNITS[feature],
            }
            for feature in loaded.model.features.derived
        },
        "gas_constant_J_mol_K": GAS_CONSTANT_J_MOL_K,
        "categorical_vocabularies": {
            field: {
                "categories": selected,
                "columns": [f"{field}__{sanitize_category(category)}" for category in selected],
            }
            for field, selected in categories.items()
        },
        "eligible_row_count": eligible_row_count,
        "excluded_row_count": excluded_row_count,
        "runtime_versions": _runtime_versions(),
        "output_formats": list(loaded.model.outputs.formats),
        "artifact_hashes": artifact_hashes,
    }


def _diagnostics(
    source_data: LoadedPreparationSource,
    status: PreparationStatus,
    exclusions: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in exclusions:
        for reason in row.get("reason_codes", []):
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return {
        "status": status,
        "source_kind": source_data.source_kind,
        "partial_sweep_source": source_data.partial_sweep_source,
        "included_child_models": list(source_data.included_child_models),
        "missing_child_models": list(source_data.missing_child_models),
        "source_row_count": sum(len(table.frame) for table in source_data.tables),
        "excluded_row_count": len(exclusions),
        "exclusion_counts_by_reason": dict(sorted(counts.items())),
    }


def _dataset_card(manifest: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Carnopy prepared dataset",
        "",
        f"Status: `{manifest['status']}`",
        f"Preparation request: `{manifest['preparation_request_id']}`",
        f"Preparation context: `{manifest['preparation_context_id']}`",
        f"Eligible rows: {manifest['eligible_row_count']}",
        f"Excluded rows: {manifest['excluded_row_count']}",
        f"Source kind: `{diagnostics['source_kind']}`",
    ]
    if diagnostics["partial_sweep_source"]:
        lines.append("Partial sweep source: `true`")
        lines.append("Included child models: " + ", ".join(diagnostics["included_child_models"]))
        lines.append("Missing child models: " + ", ".join(diagnostics["missing_child_models"]))
    if manifest["status"] == "no_eligible_rows":
        lines.append("")
        lines.append("No eligible rows remained for the requested prepared representation.")
    return "\n".join(lines) + "\n"


def _normalized_preparation_bytes(config: PreparationConfig) -> bytes:
    payload = config.model_dump(mode="json", by_alias=True)
    return canonical_json_bytes(payload)


def _preparation_context_id(
    *,
    request_id: str,
    source_data: LoadedPreparationSource,
    formats: tuple[str, ...],
) -> str:
    payload: dict[str, object] = {
        "preparation_request_id": request_id,
        "source": source_data.source_identity,
        "source_artifacts": [
            {
                "artifact": table.artifact_relative_path,
                "sha256": table.artifact_sha256,
                "run_id": table.run_id,
                "backend_model": table.backend_model,
            }
            for table in source_data.tables
        ],
        "carnopy_version": __version__,
        "runtime_versions": _runtime_versions(),
        "output_formats": list(formats),
    }
    return f"prepctx-{sha256_bytes(canonical_json_bytes(payload))}"


def _create_layout(
    output_root: Path,
    *,
    preparation_run_id: str,
    created_at: datetime,
) -> PreparationLayout:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"could not create preparation output root {output_root}: {exc}") from exc
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        prefix = UUID(preparation_run_id).hex[:8]
    except ValueError as exc:
        raise OutputError(f"invalid preparation_run_id: {preparation_run_id}") from exc
    name = f"{timestamp}_preparation_{prefix}"
    final = output_root / name
    staging = output_root / f".{name}.staging"
    if final.exists() or staging.exists():
        raise OutputError(f"immutable preparation path already exists: {final}")
    try:
        staging.mkdir()
    except OSError as exc:
        raise OutputError(f"could not create preparation staging directory: {exc}") from exc
    return PreparationLayout(staging, final)


def _finalize_layout(layout: PreparationLayout) -> None:
    if layout.final_directory.exists():
        raise OutputError(f"refusing to overwrite preparation directory {layout.final_directory}")
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize preparation directory: {exc}") from exc


def _cleanup_staging(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        except OSError:
            return
    try:
        path.rmdir()
    except OSError:
        return


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:
        raise OutputError(f"could not write preparation Parquet {path.name}: {exc}") from exc


def _write_json(path: Path, value: dict[str, Any]) -> None:
    try:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc


def _write_text(path: Path, value: str) -> None:
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc


def _write_bytes(path: Path, value: bytes) -> None:
    try:
        path.write_bytes(value)
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc


def _hash_artifacts(root: Path, names: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        try:
            result[name] = sha256_file(root / name)
        except OSError as exc:
            raise OutputError(f"could not hash preparation artifact {name}: {exc}") from exc
    return result


def _runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pandas": metadata.version("pandas"),
        "pyarrow": metadata.version("pyarrow"),
    }


def _exclusions_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        *IDENTITY_COLUMNS,
        *SOURCE_DIAGNOSTIC_COLUMNS,
        "primary_reason",
        "reason_codes",
        "missing_or_invalid_fields",
    ]
    return pd.DataFrame(rows, columns=columns)


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
