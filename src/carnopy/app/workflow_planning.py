from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from collections.abc import Callable
from typing import Any

from carnopy._version import __version__
from carnopy.config.io import LoadedSweepConfig
from carnopy.preparation.computation import PreparationComputation, compute_preparation
from carnopy.preparation.models import LoadedPreparationConfig
from carnopy.provenance import sha256_bytes
from carnopy.sweeps.normalize import normalize_sweep_config

PLAN_SCHEMA_VERSION = 1


def plan_sweep(loaded: LoadedSweepConfig) -> dict[str, Any]:
    normalized = normalize_sweep_config(loaded)
    comparison_plots_requested = loaded.model.comparison_plots is not None
    runtime = {
        "coolprop": _distribution_version("CoolProp"),
        "numpy": _distribution_version("numpy"),
        "pandas": _distribution_version("pandas"),
        "pyarrow": _distribution_version("pyarrow"),
        **(
            {"matplotlib": _distribution_version("matplotlib")}
            if comparison_plots_requested
            else {}
        ),
    }
    projected_by_model = {
        model: normalized.child_normalized[model].projected_rows
        for model in loaded.model.backend.models
    }
    canonical_record = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "workflow_kind": "sweep",
        "carnopy_version": __version__,
        "python_version": platform.python_version(),
        "configuration_sha256": sha256_bytes(loaded.raw_bytes),
        "normalized_configuration_sha256": sha256_bytes(normalized.normalized_bytes),
        "selected_backend_models": list(loaded.model.backend.models),
        "reference_model": loaded.model.backend.reference_model,
        "runtime": runtime,
    }
    plan_id = _plan_id(canonical_record)
    dependencies = {
        name: {"available": version is not None, "version": version}
        for name, version in runtime.items()
    }
    return {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "workflow_kind": "sweep",
        "plan_id": plan_id,
        "configuration_sha256": canonical_record["configuration_sha256"],
        "normalized_configuration_sha256": canonical_record["normalized_configuration_sha256"],
        "fingerprint": canonical_record,
        "models": list(loaded.model.backend.models),
        "reference_model": loaded.model.backend.reference_model,
        "mode": loaded.model.mode,
        "projected_rows_by_model": projected_by_model,
        "projected_rows_total": sum(projected_by_model.values()),
        "outputs": list(loaded.model.outputs.dataset_formats),
        "comparison_plots": (
            []
            if loaded.model.comparison_plots is None
            else [
                plot.model_dump(mode="json", by_alias=True, exclude_none=True)
                for plot in loaded.model.comparison_plots.plots
            ]
        ),
        "dependency_readiness": dependencies,
    }


def plan_preparation(
    loaded: LoadedPreparationConfig,
    source_path: str,
    *,
    inspection_revision: str,
    inspection_descriptor: dict[str, Any],
    checkpoint: Callable[[int, int], None] | None = None,
    cancellation_checkpoint: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], PreparationComputation]:
    computation = compute_preparation(
        loaded,
        source_path,
        accepted_descriptor=inspection_descriptor,
        checkpoint=checkpoint,
        cancellation_checkpoint=cancellation_checkpoint,
    )
    requested_arrays = loaded.model.outputs.arrays
    runtime = {
        "numpy": _distribution_version("numpy"),
        "pandas": _distribution_version("pandas"),
        "pyarrow": _distribution_version("pyarrow"),
        **(
            {"safetensors": _distribution_version("safetensors")}
            if requested_arrays is not None and "safetensors" in requested_arrays.formats
            else {}
        ),
        **(
            {"scikit-learn": _distribution_version("scikit-learn")}
            if loaded.model.quality.baseline_diagnostics is not None
            else {}
        ),
    }
    source_revision = {
        "inspection_revision": inspection_revision,
        "inspection_descriptor": inspection_descriptor,
        "consumed_source": computation.source_data.revision_descriptor(),
    }
    selected_backend_models = list(
        dict.fromkeys(table.backend_model for table in computation.source_data.tables)
    )
    canonical_record = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "workflow_kind": "preparation",
        "carnopy_version": __version__,
        "python_version": platform.python_version(),
        "configuration_sha256": sha256_bytes(loaded.raw_bytes),
        "normalized_configuration_sha256": sha256_bytes(computation.normalized_bytes),
        "source_identity": computation.source_data.source_identity,
        "source_revision": source_revision,
        "selected_backend_models": selected_backend_models,
        "runtime": runtime,
    }
    scenarios = [
        {
            "name": output.name,
            "kind": output.kind,
            "partition_counts": output.metadata.get("partition_counts", {}),
            "transformations": output.metadata.get("transformations", []),
            "state_leakage": output.metadata.get("state_leakage", {}),
        }
        for output in computation.scenario_outputs
    ]
    resolved = computation.resolved
    plan_id = _plan_id(canonical_record)
    return (
        {
            "plan_schema_version": PLAN_SCHEMA_VERSION,
            "workflow_kind": "preparation",
            "plan_id": plan_id,
            "configuration_sha256": canonical_record["configuration_sha256"],
            "normalized_configuration_sha256": canonical_record["normalized_configuration_sha256"],
            "fingerprint": canonical_record,
            "source_identity": computation.source_data.source_identity,
            "source_revision": source_revision,
            "selected_backend_models": selected_backend_models,
            "source_row_count": sum(len(table.frame) for table in computation.source_data.tables),
            "resolved_semantics": resolved.semantic_mapping,
            "reference_state": computation.reference_state,
            "eligible_row_count": len(computation.rows.prepared_rows),
            "excluded_row_count": len(computation.rows.exclusion_rows),
            "exclusion_reason_counts": computation.exclusion_reason_counts,
            "categories": computation.rows.categories,
            "scenarios": scenarios,
            "outputs": {
                "formats": list(loaded.model.outputs.output_format_names),
                "array_feasibility": computation.array_feasibility,
            },
            "matrix_diagnostics": computation.matrix_diagnostics,
            "baseline_feasibility": computation.baseline_feasibility,
            "dependency_readiness": {
                name: {"available": version is not None, "version": version}
                for name, version in runtime.items()
            },
        },
        computation,
    )


def current_sweep_runtime_fingerprint(loaded: LoadedSweepConfig) -> dict[str, Any]:
    return dict(plan_sweep(loaded)["fingerprint"])


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _plan_id(record: dict[str, Any]) -> str:
    encoded = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
