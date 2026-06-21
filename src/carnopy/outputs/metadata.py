from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from carnopy._version import __version__
from carnopy.config.models import NormalizedConfig
from carnopy.domain.properties import (
    PROPERTY_REGISTRY,
    REFERENCE_DEPENDENT_PROPERTIES,
)
from carnopy.provenance import (
    DATASET_SCHEMA_VERSION,
    METADATA_SCHEMA_VERSION,
    REFERENCE_STATE_POLICY,
    Identity,
    runtime_versions,
)
from carnopy.results import RunStatus


def build_metadata(
    *,
    frame: pd.DataFrame,
    config: NormalizedConfig,
    identity: Identity,
    run_id: str,
    run_status: RunStatus,
    created_at_utc: str,
    backend_version: str,
    output_directory: Path,
    output_files: list[str],
    artifact_hashes: dict[str, str],
    unit_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": identity.spec_id,
        "spec_id": identity.spec_id,
        "generation_context_id": identity.generation_context_id,
        "run_id": run_id,
        "run_status": run_status,
        "mode": config.mode,
        "created_at_utc": created_at_utc,
        "carnopy_version": __version__,
        "backend": config.backend,
        "backend_version": backend_version,
        "reference_state_policy": REFERENCE_STATE_POLICY,
        "reference_state_mutated_at_backend_initialization": True,
        "reference_state_changed_during_generation": False,
        "raw_config_sha256": identity.raw_config_sha256,
        "normalized_config_sha256": identity.normalized_config_sha256,
        "row_count": len(frame),
        "valid_row_count": int(frame["valid"].sum()),
        "invalid_row_count": int((~frame["valid"]).sum()),
        "failure_counts_by_layer": _counts(frame["failure_layer"]),
        "failure_counts_by_code": _counts(frame["failure_code"]),
        "failure_counts_by_property": _counts(frame["failure_property"]),
        "canonical_fluids": config.fluids,
        "requested_fluid_aliases": config.requested_fluid_aliases,
        "requested_fluid_canonical_names": config.requested_fluid_canonical_names,
        "canonical_properties": config.properties,
        "requested_property_order": config.requested_property_order,
        "sampling": {
            "original": config.original_grid,
            "materialized_si": config.grid,
        },
        "original_units": {
            axis: str(definition["unit"])
            for axis, definition in config.original_grid.items()
            if isinstance(definition, dict) and "unit" in definition
        },
        "canonical_units": unit_map,
        "property_registry_metadata": {
            name: PROPERTY_REGISTRY[name].metadata() for name in config.properties
        },
        "reference_dependent_properties": [
            name for name in config.properties if name in REFERENCE_DEPENDENT_PROPERTIES
        ],
        "fluid_constants": _fluid_constants(frame, config),
        "runtime_versions": runtime_versions(),
        "output_directory": str(output_directory),
        "output_files": output_files,
        "artifact_hashes": artifact_hashes,
    }


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value) for key, value in series.dropna().value_counts().sort_index().items()
    }


def _fluid_constants(
    frame: pd.DataFrame,
    config: NormalizedConfig,
) -> dict[str, dict[str, float | None]]:
    constants = [
        PROPERTY_REGISTRY[name]
        for name in config.properties
        if PROPERTY_REGISTRY[name].classification == "fluid_constant"
    ]
    result: dict[str, dict[str, float | None]] = {}
    for fluid in config.fluids:
        subset = frame.loc[frame["fluid"] == fluid]
        result[fluid] = {}
        for definition in constants:
            values = subset[definition.column].dropna()
            result[fluid][definition.name] = float(values.iloc[0]) if not values.empty else None
    return result
