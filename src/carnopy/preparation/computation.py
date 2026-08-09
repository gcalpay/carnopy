from __future__ import annotations

import importlib.metadata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from carnopy.domain.failures import ConfigError
from carnopy.preparation.arrays import (
    _auxiliary_arrays,
    _conversion_errors,
    _numeric_matrix,
)
from carnopy.preparation.baselines import (
    assess_baseline_feasibility,
    build_baseline_diagnostics,
)
from carnopy.preparation.fields import (
    ResolvedPreparation,
    resolve_preparation_fields,
    sanitize_category,
)
from carnopy.preparation.matrix_diagnostics import build_matrix_diagnostics
from carnopy.preparation.models import LoadedPreparationConfig
from carnopy.preparation.quality import partition_target_summaries
from carnopy.preparation.reference import build_reference_state_summary
from carnopy.preparation.reporting import normalized_preparation_bytes
from carnopy.preparation.rows import PreparedRows, build_prepared_rows
from carnopy.preparation.scenarios import ScenarioOutput, build_scenario_outputs
from carnopy.preparation.source import (
    LoadedPreparationSource,
    load_preparation_source,
    verify_loaded_source_unchanged,
)
from carnopy.provenance import sha256_bytes


@dataclass(frozen=True)
class PreparationComputation:
    loaded: LoadedPreparationConfig
    source_data: LoadedPreparationSource
    resolved: ResolvedPreparation
    reference_state: dict[str, Any]
    normalized_bytes: bytes
    request_id: str
    rows: PreparedRows
    prepared_frame: pd.DataFrame
    scenario_outputs: tuple[ScenarioOutput, ...]
    partition_target_summaries: list[dict[str, Any]]
    matrix_diagnostics: list[dict[str, Any]] | None
    baseline_feasibility: list[dict[str, Any]] | None
    array_feasibility: list[dict[str, Any]]
    exclusion_reason_counts: dict[str, int]


def compute_preparation(
    loaded: LoadedPreparationConfig,
    source: str | Path,
    *,
    accepted_descriptor: dict[str, Any] | None = None,
    checkpoint: Callable[[int, int], None] | None = None,
    cancellation_checkpoint: Callable[[], None] | None = None,
) -> PreparationComputation:
    """Compute a complete non-writing preparation plan in memory."""
    _cancel(cancellation_checkpoint)
    source_data = load_preparation_source(
        source,
        allow_partial_sweep=loaded.model.source_policy.allow_partial_sweep,
        accepted_descriptor=accepted_descriptor,
        cancellation_checkpoint=cancellation_checkpoint,
    )
    _cancel(cancellation_checkpoint)
    resolved = resolve_preparation_fields(loaded.model, source_data.tables)
    reference_state = build_reference_state_summary(source_data, resolved)
    normalized_bytes = normalized_preparation_bytes(loaded.model)
    request_id = f"prep-{sha256_bytes(normalized_bytes)}"
    rows = build_prepared_rows(
        loaded.model,
        source_data,
        resolved,
        checkpoint=checkpoint,
    )
    _cancel(cancellation_checkpoint)
    prepared_frame = pd.DataFrame(rows.prepared_rows)
    scenario_outputs = (
        tuple(
            build_scenario_outputs(
                loaded.model.scenarios,
                prepared_frame,
                source_kind=source_data.source_kind,
                checkpoint=cancellation_checkpoint,
            )
        )
        if loaded.model.scenarios and rows.prepared_rows
        else ()
    )
    target_summaries = _partition_target_summaries(
        scenario_outputs,
        resolved,
        checkpoint=cancellation_checkpoint,
    )
    matrix_diagnostics = _compute_matrix_diagnostics(
        loaded,
        prepared_frame,
        rows,
        resolved,
        scenario_outputs,
        checkpoint=cancellation_checkpoint,
    )
    baseline_feasibility = _assess_baselines(
        loaded,
        rows,
        resolved,
        scenario_outputs,
        checkpoint=cancellation_checkpoint,
    )
    array_feasibility = _assess_arrays(
        loaded,
        rows,
        prepared_frame,
        resolved,
        scenario_outputs,
        checkpoint=cancellation_checkpoint,
    )
    _cancel(cancellation_checkpoint)
    verify_loaded_source_unchanged(
        source_data,
        cancellation_checkpoint=cancellation_checkpoint,
    )
    return PreparationComputation(
        loaded=loaded,
        source_data=source_data,
        resolved=resolved,
        reference_state=reference_state,
        normalized_bytes=normalized_bytes,
        request_id=request_id,
        rows=rows,
        prepared_frame=prepared_frame,
        scenario_outputs=scenario_outputs,
        partition_target_summaries=target_summaries,
        matrix_diagnostics=matrix_diagnostics,
        baseline_feasibility=baseline_feasibility,
        array_feasibility=array_feasibility,
        exclusion_reason_counts=_exclusion_reason_counts(rows),
    )


def fit_preparation_baselines(
    computation: PreparationComputation,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> list[dict[str, Any]] | None:
    """Fit requested diagnostic estimators before any staging path is created."""
    config = computation.loaded.model.quality.baseline_diagnostics
    if config is None:
        return None
    if not computation.rows.prepared_rows:
        return [
            {
                "scenario": scenario.name,
                "status": "skipped_no_eligible_rows",
            }
            for scenario in computation.loaded.model.scenarios
        ]
    if not computation.scenario_outputs:
        return [{"scenario": None, "status": "skipped_requires_evaluation_scenario"}]
    diagnostics: list[dict[str, Any]] = []
    for output in computation.scenario_outputs:
        if checkpoint is not None:
            checkpoint()
        diagnostics.append(
            build_baseline_diagnostics(
                output.partitions,
                feature_columns=_scenario_feature_columns(
                    computation.rows,
                    computation.resolved,
                    output.metadata.get("transformations", []),
                ),
                target_columns=[field.semantic_name for field in computation.resolved.targets],
                config=config,
                scenario=output.name,
                checkpoint=checkpoint,
            )
        )
    return diagnostics


def _partition_target_summaries(
    outputs: tuple[ScenarioOutput, ...],
    resolved: ResolvedPreparation,
    *,
    checkpoint: Callable[[], None] | None,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for output in outputs:
        _cancel(checkpoint)
        summaries.extend(
            partition_target_summaries(
                scenario_name=output.name,
                partitions=output.partitions,
                resolved=resolved,
            )
        )
    return summaries


def _compute_matrix_diagnostics(
    loaded: LoadedPreparationConfig,
    frame: pd.DataFrame,
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    outputs: tuple[ScenarioOutput, ...],
    *,
    checkpoint: Callable[[], None] | None,
) -> list[dict[str, Any]] | None:
    config = loaded.model.quality.matrix_diagnostics
    if config is None:
        return None
    if not rows.prepared_rows:
        return [
            {
                "scenario": scenario.name,
                "fit_partition": "all" if scenario.kind == "unsplit" else "train",
                "status": "skipped_no_eligible_rows",
            }
            for scenario in loaded.model.scenarios
        ]
    if not outputs:
        return [
            build_matrix_diagnostics(
                frame,
                feature_columns=_feature_columns(rows, resolved),
                target_columns=[field.semantic_name for field in resolved.targets],
                config=config,
                scenario=None,
                fit_partition="all",
            )
        ]
    diagnostics: list[dict[str, Any]] = []
    for output in outputs:
        _cancel(checkpoint)
        fit_partition = "all" if output.kind == "unsplit" else "train"
        if fit_partition not in output.partitions:
            diagnostics.append(
                {
                    "scenario": output.name,
                    "fit_partition": fit_partition,
                    "status": "skipped_missing_train_partition",
                }
            )
            continue
        diagnostics.append(
            build_matrix_diagnostics(
                output.partitions[fit_partition],
                feature_columns=_scenario_feature_columns(
                    rows,
                    resolved,
                    output.metadata.get("transformations", []),
                ),
                target_columns=[field.semantic_name for field in resolved.targets],
                config=config,
                scenario=output.name,
                fit_partition=fit_partition,
            )
        )
    return diagnostics


def _assess_baselines(
    loaded: LoadedPreparationConfig,
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    outputs: tuple[ScenarioOutput, ...],
    *,
    checkpoint: Callable[[], None] | None,
) -> list[dict[str, Any]] | None:
    config = loaded.model.quality.baseline_diagnostics
    if config is None:
        return None
    if not rows.prepared_rows:
        return [
            {"scenario": scenario.name, "status": "skipped_no_eligible_rows"}
            for scenario in loaded.model.scenarios
        ]
    if not outputs:
        return [{"scenario": None, "status": "skipped_requires_evaluation_scenario"}]
    return [
        assess_baseline_feasibility(
            output.partitions,
            feature_columns=_scenario_feature_columns(
                rows,
                resolved,
                output.metadata.get("transformations", []),
            ),
            target_columns=[field.semantic_name for field in resolved.targets],
            config=config,
            scenario=output.name,
            checkpoint=checkpoint,
        )
        for output in outputs
    ]


def _assess_arrays(
    loaded: LoadedPreparationConfig,
    rows: PreparedRows,
    frame: pd.DataFrame,
    resolved: ResolvedPreparation,
    outputs: tuple[ScenarioOutput, ...],
    *,
    checkpoint: Callable[[], None] | None,
) -> list[dict[str, Any]]:
    config = loaded.model.outputs.arrays
    if config is None:
        return [{"scope": "table", "status": "not_requested"}]
    if "safetensors" in config.formats:
        try:
            importlib.metadata.version("safetensors")
        except importlib.metadata.PackageNotFoundError as exc:
            raise ConfigError(
                "SafeTensors export requires the ml extra. Install carnopy[ml]."
            ) from exc
    if not rows.prepared_rows:
        return [{"scope": "table", "status": "skipped_no_eligible_rows"}]
    results = [
        _array_scope_feasibility(
            scope="table",
            frame=frame,
            feature_columns=_feature_columns(rows, resolved),
            target_columns=[field.semantic_name for field in resolved.targets],
            auxiliary_columns=[field for field in loaded.model.auxiliary if field in frame.columns],
            config=config,
        )
    ]
    for output in outputs:
        _cancel(checkpoint)
        feature_columns = _scenario_feature_columns(
            rows,
            resolved,
            output.metadata.get("transformations", []),
        )
        for partition, partition_frame in output.partitions.items():
            _cancel(checkpoint)
            results.append(
                _array_scope_feasibility(
                    scope=f"scenario:{output.name}:{partition}",
                    frame=partition_frame,
                    feature_columns=feature_columns,
                    target_columns=[field.semantic_name for field in resolved.targets],
                    auxiliary_columns=[
                        field
                        for field in loaded.model.auxiliary
                        if field in partition_frame.columns
                    ],
                    config=config,
                )
            )
    return results


def _array_scope_feasibility(
    *,
    scope: str,
    frame: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    auxiliary_columns: list[str],
    config: Any,
) -> dict[str, Any]:
    dtype = config.dtype
    if dtype is None:
        raise ConfigError("array output dtype is required when arrays are requested")
    feature_matrix = _numeric_matrix(frame, feature_columns, dtype, role="features")
    target_matrix = _numeric_matrix(frame, target_columns, dtype, role="targets")
    auxiliary = _auxiliary_arrays(
        frame,
        auxiliary_columns=auxiliary_columns,
        dtype=dtype,
        include=config.include_auxiliary,
    )
    return {
        "scope": scope,
        "status": "ready",
        "dtype": dtype,
        "formats": list(config.formats),
        "feature_shape": list(feature_matrix.shape),
        "target_shape": list(target_matrix.shape),
        "auxiliary_shapes": {name: list(array.shape) for name, array in auxiliary.arrays.items()},
        "float_conversion": {
            "features": _conversion_errors(frame, feature_columns, dtype),
            "targets": _conversion_errors(frame, target_columns, dtype),
        },
    }


def _feature_columns(rows: PreparedRows, resolved: ResolvedPreparation) -> list[str]:
    columns: list[str] = [
        *(field.semantic_name for field in resolved.numeric_features),
        *resolved.derived_features,
    ]
    for field, categories in rows.categories.items():
        columns.extend(f"{field}__{sanitize_category(category)}" for category in categories)
    return list(dict.fromkeys(columns))


def _scenario_feature_columns(
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    transformations: object,
) -> list[str]:
    feature_columns = _feature_columns(rows, resolved)
    if not isinstance(transformations, list):
        return feature_columns
    transform_columns: list[str] = []
    for item in transformations:
        if not isinstance(item, dict):
            continue
        source = item.get("field")
        output = item.get("output_column")
        if isinstance(source, str) and isinstance(output, str) and source in feature_columns:
            transform_columns.append(output)
    return list(dict.fromkeys([*feature_columns, *transform_columns]))


def _exclusion_reason_counts(rows: PreparedRows) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows.exclusion_rows:
        reasons = row.get("reason_codes")
        if isinstance(reasons, list):
            counts.update(str(reason) for reason in reasons)
    return dict(sorted(counts.items()))


def _cancel(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()
