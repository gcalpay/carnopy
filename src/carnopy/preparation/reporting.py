from __future__ import annotations

import platform
from datetime import datetime
from importlib import metadata
from typing import Any

from carnopy._version import __version__
from carnopy.config.normalize import canonical_json_bytes
from carnopy.preparation.fields import (
    DERIVED_UNITS,
    GAS_CONSTANT_J_MOL_K,
    ResolvedPreparation,
    derived_dependencies,
    derived_formula,
    sanitize_category,
)
from carnopy.preparation.models import LoadedPreparationConfig, PreparationConfig
from carnopy.preparation.source import LoadedPreparationSource
from carnopy.provenance import sha256_bytes
from carnopy.results import PreparationStatus

PREPARATION_SCHEMA_VERSION = 1


def normalized_preparation_bytes(config: PreparationConfig) -> bytes:
    payload = config.model_dump(mode="json", by_alias=True)
    return canonical_json_bytes(payload)


def preparation_context_id(
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
        "runtime_versions": runtime_versions(),
        "output_formats": list(formats),
    }
    return f"prepctx-{sha256_bytes(canonical_json_bytes(payload))}"


def build_manifest(
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
    data_artifacts: dict[str, str | None],
    table_columns: list[str],
    scenario_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
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
        "data_artifacts": data_artifacts,
        "column_roles": {
            "table": table_columns,
            "provenance": [
                "prepared_row_id",
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
            ],
            "diagnostics": [
                "prepared_row_id",
                "source_valid",
                "source_failure_layer",
                "source_failure_code",
                "source_failure_message",
                "source_failure_property",
                "source_backend_error_type",
                "source_backend_error_message",
            ],
        },
        "runtime_versions": runtime_versions(),
        "output_formats": list(loaded.model.outputs.formats),
        "artifact_hashes": artifact_hashes,
    }
    if scenario_summary is not None:
        manifest["scenarios"] = scenario_summary
    return manifest


def build_diagnostics(
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


def build_dataset_card(manifest: dict[str, Any], diagnostics: dict[str, Any]) -> str:
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
    artifacts = manifest.get("data_artifacts")
    if isinstance(artifacts, dict):
        if artifacts.get("table") is not None:
            lines.append(f"Prepared table: `{artifacts['table']}`")
        lines.append(f"Provenance: `{artifacts.get('provenance')}`")
        lines.append(f"Source diagnostics: `{artifacts.get('diagnostics')}`")
        lines.append(f"Exclusions: `{artifacts.get('exclusions')}`")
    if diagnostics["partial_sweep_source"]:
        lines.append("Partial sweep source: `true`")
        lines.append("Included child models: " + ", ".join(diagnostics["included_child_models"]))
        lines.append("Missing child models: " + ", ".join(diagnostics["missing_child_models"]))
    if manifest["status"] == "no_eligible_rows":
        lines.append("")
        lines.append("No eligible rows remained for the requested prepared representation.")
    return "\n".join(lines) + "\n"


def runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pandas": metadata.version("pandas"),
        "pyarrow": metadata.version("pyarrow"),
    }
