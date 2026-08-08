from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from carnopy._execution import ExecutionControl
from carnopy.domain.failures import OutputError
from carnopy.outputs.writers import hash_artifacts, write_bytes, write_json
from carnopy.preparation.arrays import ArrayExportResult, write_array_exports
from carnopy.preparation.computation import (
    PreparationComputation,
    compute_preparation,
    fit_preparation_baselines,
)
from carnopy.preparation.fields import (
    ResolvedPreparation,
    sanitize_category,
)
from carnopy.preparation.layout import (
    PreparationLayout,
    cleanup_preparation_layout,
    create_preparation_layout,
    finalize_preparation_layout,
)
from carnopy.preparation.models import (
    LoadedPreparationConfig,
    PreparationArrayOutputsConfig,
    load_preparation_config,
)
from carnopy.preparation.quality import build_quality_artifacts
from carnopy.preparation.reporting import (
    build_dataset_card,
    build_diagnostics,
    build_manifest,
    preparation_context_id,
)
from carnopy.preparation.rows import (
    IDENTITY_COLUMNS,
    PREPARED_ROW_ID_COLUMN,
    SOURCE_DIAGNOSTIC_COLUMNS,
    PreparedRows,
    exclusions_frame,
)
from carnopy.preparation.scenarios import ScenarioOutput
from carnopy.preparation.source import verify_loaded_source_unchanged
from carnopy.results import PreparationResult, PreparationStatus


@dataclass(frozen=True)
class BundleWriteResult:
    preparation_request_id: str
    preparation_context_id: str
    status: PreparationStatus
    eligible_row_count: int
    excluded_row_count: int
    table_path: Path | None
    provenance_path: Path
    source_diagnostics_path: Path
    scenario_report_path: Path | None
    scenario_count: int
    partition_count: int


@dataclass(frozen=True)
class DataArtifactPaths:
    table_path: Path | None
    provenance_path: Path
    source_diagnostics_path: Path
    exclusions_path: Path
    table_columns: list[str]
    array_artifacts: list[str]
    array_manifest: dict[str, Any]


@dataclass(frozen=True)
class ScenarioWriteResult:
    report_path: Path | None
    artifact_names: list[str]
    summary: dict[str, Any]
    scenario_count: int
    partition_count: int
    partition_target_summaries: list[dict[str, Any]]
    matrix_diagnostics: list[dict[str, Any]]
    baseline_diagnostics: list[dict[str, Any]]


@dataclass(frozen=True)
class ScenarioPartitionWriteResult:
    artifact_names: list[str]
    array_manifests: dict[str, dict[str, Any]]


def prepare_dataset(
    source: str | Path,
    config: str | Path,
    *,
    output_root: str | Path = "prepared",
) -> PreparationResult:
    loaded = load_preparation_config(config)
    computation = compute_preparation(loaded, source)
    return execute_preparation_computation(computation, output_root=output_root)


def execute_preparation_computation(
    computation: PreparationComputation,
    *,
    output_root: str | Path,
    execution: ExecutionControl | None = None,
    source_revalidator: Callable[[], None] | None = None,
) -> PreparationResult:
    """Fit, stage, serialize, revalidate, and atomically finalize one computation."""
    if execution is not None:
        execution.phase("baseline_fitting")
    baseline_diagnostics = fit_preparation_baselines(
        computation,
        checkpoint=None if execution is None else execution.raise_if_cancelled,
    )
    verify_loaded_source_unchanged(computation.source_data)
    if source_revalidator is not None:
        source_revalidator()
    if execution is not None:
        execution.phase("staging")
    preparation_run_id = str(uuid4())
    created_at = datetime.now(UTC)
    layout = create_preparation_layout(
        Path(output_root),
        preparation_run_id=preparation_run_id,
        created_at=created_at,
    )
    try:
        if execution is not None:
            execution.phase("serialization")
        result = _write_preparation_bundle(
            computation=computation,
            baseline_diagnostics=baseline_diagnostics,
            layout=layout,
            preparation_run_id=preparation_run_id,
            created_at=created_at,
            execution=execution,
        )
        verify_loaded_source_unchanged(computation.source_data)
        if source_revalidator is not None:
            source_revalidator()
        if execution is not None:
            execution.protected_phase("finalization")
        finalize_preparation_layout(layout)
        return _preparation_result(result, layout, preparation_run_id)
    except Exception as original:
        try:
            cleanup_preparation_layout(layout)
        except Exception as cleanup_error:
            raise OutputError(
                f"preparation failed ({original}); staging cleanup failed: {cleanup_error}"
            ) from cleanup_error
        raise


def _preparation_result(
    result: BundleWriteResult,
    layout: PreparationLayout,
    preparation_run_id: str,
) -> PreparationResult:
    return PreparationResult(
        preparation_request_id=result.preparation_request_id,
        preparation_context_id=result.preparation_context_id,
        preparation_run_id=preparation_run_id,
        status=result.status,
        output_directory=layout.final_directory,
        eligible_row_count=result.eligible_row_count,
        excluded_row_count=result.excluded_row_count,
        table_path=(
            None if result.table_path is None else layout.final_directory / "data" / "table.parquet"
        ),
        provenance_path=layout.final_directory / "data" / "provenance.parquet",
        source_diagnostics_path=layout.final_directory / "data" / "diagnostics.parquet",
        exclusions_path=layout.final_directory / "data" / "exclusions.parquet",
        manifest_path=layout.final_directory / "manifest.json",
        diagnostics_path=layout.final_directory / "diagnostics.json",
        dataset_card_path=layout.final_directory / "dataset_card.md",
        scenario_report_path=(
            None
            if result.scenario_report_path is None
            else layout.final_directory / "scenario_report.json"
        ),
        scenario_count=result.scenario_count,
        partition_count=result.partition_count,
    )


def _write_preparation_bundle(
    *,
    computation: PreparationComputation,
    baseline_diagnostics: list[dict[str, Any]] | None,
    layout: PreparationLayout,
    preparation_run_id: str,
    created_at: datetime,
    execution: ExecutionControl | None,
) -> BundleWriteResult:
    loaded = computation.loaded
    source_data = computation.source_data
    resolved = computation.resolved
    rows = computation.rows
    prepared_frame = computation.prepared_frame
    data_directory = layout.staging_directory / "data"
    data_directory.mkdir()
    if execution is not None:
        execution.raise_if_cancelled()
    data_artifacts = _write_data_artifacts(
        rows,
        data_directory,
        prepared_frame,
        auxiliary_fields=loaded.model.auxiliary,
        resolved=resolved,
        array_config=loaded.model.outputs.arrays,
        execution=execution,
    )
    if execution is not None:
        execution.raise_if_cancelled()
    scenario_result = _write_scenario_artifacts(
        loaded=loaded,
        layout=layout,
        data_directory=data_directory,
        rows=rows,
        public_table_columns=data_artifacts.table_columns,
        resolved=resolved,
        outputs=computation.scenario_outputs,
        target_summaries=computation.partition_target_summaries,
        matrix_diagnostics=computation.matrix_diagnostics,
        baseline_diagnostics=baseline_diagnostics,
        execution=execution,
    )
    if execution is not None:
        execution.raise_if_cancelled()
    quality_report, quality_flags = build_quality_artifacts(
        frame=prepared_frame,
        rows=rows,
        resolved=resolved,
        scenario_summary=None if scenario_result is None else scenario_result.summary,
        partition_target_summaries=(
            [] if scenario_result is None else scenario_result.partition_target_summaries
        ),
        matrix_diagnostics=computation.matrix_diagnostics,
        baseline_diagnostics=baseline_diagnostics,
    )
    write_json(layout.staging_directory / "quality_report.json", quality_report)
    if execution is not None:
        execution.raise_if_cancelled()
    _write_parquet(quality_flags, data_directory / "quality_flags.parquet")

    write_bytes(layout.staging_directory / "preparation.original.yaml", loaded.raw_bytes)
    if execution is not None:
        execution.raise_if_cancelled()
    write_bytes(
        layout.staging_directory / "preparation.normalized.json",
        computation.normalized_bytes,
    )

    context_id = preparation_context_id(
        request_id=computation.request_id,
        source_data=source_data,
        outputs=loaded.model.outputs,
    )
    artifact_names = [
        "preparation.original.yaml",
        "preparation.normalized.json",
        "data/provenance.parquet",
        "data/diagnostics.parquet",
        "data/exclusions.parquet",
        "data/quality_flags.parquet",
        "quality_report.json",
    ]
    if data_artifacts.table_path is not None:
        artifact_names.append("data/table.parquet")
    artifact_names.extend(data_artifacts.array_artifacts)
    if scenario_result is not None:
        artifact_names.extend(scenario_result.artifact_names)
    if execution is not None:
        execution.raise_if_cancelled()
    artifact_hashes = hash_artifacts(layout.staging_directory, artifact_names)
    manifest = build_manifest(
        loaded=loaded,
        source_data=source_data,
        resolved=resolved,
        categories=rows.categories,
        status=rows.status,
        request_id=computation.request_id,
        context_id=context_id,
        preparation_run_id=preparation_run_id,
        created_at=created_at,
        eligible_row_count=len(rows.prepared_rows),
        excluded_row_count=len(rows.exclusion_rows),
        artifact_hashes=artifact_hashes,
        data_artifacts={
            "table": None if data_artifacts.table_path is None else "data/table.parquet",
            "provenance": "data/provenance.parquet",
            "diagnostics": "data/diagnostics.parquet",
            "exclusions": "data/exclusions.parquet",
        },
        quality_artifacts={
            "report": "quality_report.json",
            "flags": "data/quality_flags.parquet",
        },
        table_columns=data_artifacts.table_columns,
        array_exports=data_artifacts.array_manifest,
        reference_state=computation.reference_state,
        scenario_summary=None if scenario_result is None else scenario_result.summary,
    )
    write_json(layout.staging_directory / "manifest.json", manifest)
    if execution is not None:
        execution.raise_if_cancelled()
    diagnostics = build_diagnostics(
        source_data,
        rows.status,
        rows.exclusion_rows,
        reference_state=computation.reference_state,
    )
    write_json(layout.staging_directory / "diagnostics.json", diagnostics)
    if execution is not None:
        execution.raise_if_cancelled()
    _write_text(
        layout.staging_directory / "dataset_card.md",
        build_dataset_card(manifest, diagnostics),
    )
    final_hash_names = [*artifact_names, "diagnostics.json", "dataset_card.md"]
    manifest["artifact_hashes"] = hash_artifacts(layout.staging_directory, final_hash_names)
    write_json(layout.staging_directory / "manifest.json", manifest)
    if execution is not None:
        execution.raise_if_cancelled()
    return BundleWriteResult(
        preparation_request_id=computation.request_id,
        preparation_context_id=context_id,
        status=rows.status,
        eligible_row_count=len(rows.prepared_rows),
        excluded_row_count=len(rows.exclusion_rows),
        table_path=data_artifacts.table_path,
        provenance_path=data_artifacts.provenance_path,
        source_diagnostics_path=data_artifacts.source_diagnostics_path,
        scenario_report_path=None if scenario_result is None else scenario_result.report_path,
        scenario_count=0 if scenario_result is None else scenario_result.scenario_count,
        partition_count=0 if scenario_result is None else scenario_result.partition_count,
    )


def _write_data_artifacts(
    rows: PreparedRows,
    data_directory: Path,
    prepared_frame: pd.DataFrame,
    *,
    auxiliary_fields: tuple[str, ...],
    resolved: ResolvedPreparation,
    array_config: PreparationArrayOutputsConfig | None,
    execution: ExecutionControl | None,
) -> DataArtifactPaths:
    table_path: Path | None = None
    table_columns = _public_table_columns(prepared_frame, auxiliary_fields=auxiliary_fields)
    if rows.prepared_rows:
        if execution is not None:
            execution.raise_if_cancelled()
        table_path = data_directory / "table.parquet"
        _write_parquet(prepared_frame.loc[:, table_columns], table_path)
    array_result = _write_table_arrays(
        prepared_frame=prepared_frame,
        data_directory=data_directory,
        rows=rows,
        table_columns=table_columns,
        auxiliary_fields=auxiliary_fields,
        resolved=resolved,
        array_config=array_config,
        execution=execution,
    )
    provenance_path = data_directory / "provenance.parquet"
    source_diagnostics_path = data_directory / "diagnostics.parquet"
    if execution is not None:
        execution.raise_if_cancelled()
    _write_parquet(_provenance_frame(prepared_frame), provenance_path)
    if execution is not None:
        execution.raise_if_cancelled()
    _write_parquet(_source_diagnostics_frame(prepared_frame), source_diagnostics_path)
    if execution is not None:
        execution.raise_if_cancelled()
    _write_parquet(exclusions_frame(rows.exclusion_rows), data_directory / "exclusions.parquet")
    return DataArtifactPaths(
        table_path=table_path,
        provenance_path=provenance_path,
        source_diagnostics_path=source_diagnostics_path,
        exclusions_path=data_directory / "exclusions.parquet",
        table_columns=table_columns,
        array_artifacts=array_result.artifact_names,
        array_manifest=array_result.manifest,
    )


def _write_table_arrays(
    *,
    prepared_frame: pd.DataFrame,
    data_directory: Path,
    rows: PreparedRows,
    table_columns: list[str],
    auxiliary_fields: tuple[str, ...],
    resolved: ResolvedPreparation,
    array_config: PreparationArrayOutputsConfig | None,
    execution: ExecutionControl | None,
) -> ArrayExportResult:
    if not rows.prepared_rows:
        return ArrayExportResult(artifact_names=[], manifest={"enabled": False, "exports": []})
    return write_array_exports(
        frame=prepared_frame.loc[:, table_columns],
        output_directory=data_directory,
        source_table_path=data_directory / "table.parquet",
        artifact_prefix="data",
        file_prefix="",
        config=array_config,
        feature_columns=_feature_columns(rows, resolved),
        target_columns=[field.semantic_name for field in resolved.targets],
        auxiliary_columns=[field for field in auxiliary_fields if field in table_columns],
        units=_unit_mapping(resolved),
        checkpoint=None if execution is None else execution.raise_if_cancelled,
    )


def _public_table_columns(
    prepared_frame: pd.DataFrame,
    *,
    auxiliary_fields: tuple[str, ...],
) -> list[str]:
    explicit_auxiliary = set(auxiliary_fields)
    excluded = (set(IDENTITY_COLUMNS) - explicit_auxiliary) | set(SOURCE_DIAGNOSTIC_COLUMNS)
    return [column for column in prepared_frame.columns if column not in excluded]


def _provenance_frame(prepared_frame: pd.DataFrame) -> pd.DataFrame:
    columns = [PREPARED_ROW_ID_COLUMN, *IDENTITY_COLUMNS]
    return pd.DataFrame(prepared_frame, columns=columns)


def _source_diagnostics_frame(prepared_frame: pd.DataFrame) -> pd.DataFrame:
    columns = [PREPARED_ROW_ID_COLUMN, *SOURCE_DIAGNOSTIC_COLUMNS]
    return pd.DataFrame(prepared_frame, columns=columns)


def _write_scenario_artifacts(
    *,
    loaded: LoadedPreparationConfig,
    layout: PreparationLayout,
    data_directory: Path,
    rows: PreparedRows,
    public_table_columns: list[str],
    resolved: ResolvedPreparation,
    outputs: tuple[ScenarioOutput, ...],
    target_summaries: list[dict[str, Any]],
    matrix_diagnostics: list[dict[str, Any]] | None,
    baseline_diagnostics: list[dict[str, Any]] | None,
    execution: ExecutionControl | None,
) -> ScenarioWriteResult | None:
    if not loaded.model.scenarios:
        return None
    if not rows.prepared_rows:
        return ScenarioWriteResult(
            report_path=None,
            artifact_names=[],
            summary={
                "scenario_count": 0,
                "partition_count": 0,
                "status": "skipped_no_eligible_rows",
                "report": None,
                "scenarios": [],
            },
            scenario_count=0,
            partition_count=0,
            partition_target_summaries=[],
            matrix_diagnostics=matrix_diagnostics or [],
            baseline_diagnostics=baseline_diagnostics or [],
        )
    scenario_root = data_directory / "scenarios"
    scenario_root.mkdir()
    artifact_names: list[str] = []
    report_scenarios: list[dict[str, Any]] = []
    for output in outputs:
        if execution is not None:
            execution.raise_if_cancelled()
        scenario_directory = scenario_root / output.name
        scenario_directory.mkdir()
        partition_result = _write_scenario_partitions(
            output,
            scenario_directory,
            public_table_columns=public_table_columns,
            rows=rows,
            resolved=resolved,
            array_config=loaded.model.outputs.arrays,
            auxiliary_fields=loaded.model.auxiliary,
            execution=execution,
        )
        partition_hashes = hash_artifacts(layout.staging_directory, partition_result.artifact_names)
        scenario_metadata = {
            **output.metadata,
            "partition_artifact_hashes": partition_hashes,
            "array_exports": partition_result.array_manifests,
        }
        write_json(scenario_directory / "scenario.json", scenario_metadata)
        if execution is not None:
            execution.raise_if_cancelled()
        scenario_json = f"data/scenarios/{output.name}/scenario.json"
        artifact_names.extend([*partition_result.artifact_names, scenario_json])
        report_scenarios.append(
            {
                "name": output.name,
                "kind": output.kind,
                "partition_counts": output.metadata["partition_counts"],
                "transformations": output.metadata["transformations"],
                "partition_artifacts": partition_result.artifact_names,
                "partition_artifact_hashes": partition_hashes,
                "array_exports": partition_result.array_manifests,
                "scenario_artifact": scenario_json,
                **(
                    {"stratification": output.metadata["stratification"]}
                    if "stratification" in output.metadata
                    else {}
                ),
            }
        )
    if execution is not None:
        execution.raise_if_cancelled()
    scenario_artifact_hashes = hash_artifacts(layout.staging_directory, artifact_names)
    report = {
        "scenario_report_schema_version": 1,
        "scenario_count": len(outputs),
        "partition_count": sum(len(output.partitions) for output in outputs),
        "scenarios": [
            {
                **scenario,
                "artifact_hashes": {
                    name: scenario_artifact_hashes[name]
                    for name in [*scenario["partition_artifacts"], scenario["scenario_artifact"]]
                },
            }
            for scenario in report_scenarios
        ],
    }
    write_json(layout.staging_directory / "scenario_report.json", report)
    artifact_names.append("scenario_report.json")
    return ScenarioWriteResult(
        report_path=layout.staging_directory / "scenario_report.json",
        artifact_names=artifact_names,
        summary={
            "scenario_count": report["scenario_count"],
            "partition_count": report["partition_count"],
            "status": "completed",
            "report": "scenario_report.json",
            "scenarios": report["scenarios"],
        },
        scenario_count=len(outputs),
        partition_count=sum(len(output.partitions) for output in outputs),
        partition_target_summaries=target_summaries,
        matrix_diagnostics=matrix_diagnostics or [],
        baseline_diagnostics=baseline_diagnostics or [],
    )


def _write_scenario_partitions(
    output: ScenarioOutput,
    scenario_directory: Path,
    *,
    public_table_columns: list[str],
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    array_config: PreparationArrayOutputsConfig | None,
    auxiliary_fields: tuple[str, ...],
    execution: ExecutionControl | None,
) -> ScenarioPartitionWriteResult:
    artifacts: list[str] = []
    array_manifests: dict[str, dict[str, Any]] = {}
    transform_columns = [
        item["output_column"]
        for item in output.metadata.get("transformations", [])
        if isinstance(item, dict) and isinstance(item.get("output_column"), str)
    ]
    output_columns = list(dict.fromkeys([*public_table_columns, *transform_columns]))
    for partition, frame in output.partitions.items():
        if execution is not None:
            execution.raise_if_cancelled()
        path = scenario_directory / f"{partition}.parquet"
        clean_frame = frame.loc[:, [column for column in output_columns if column in frame.columns]]
        _write_parquet(clean_frame, path)
        artifacts.append(f"data/scenarios/{output.name}/{partition}.parquet")
        array_result = write_array_exports(
            frame=clean_frame,
            output_directory=scenario_directory,
            source_table_path=path,
            artifact_prefix=f"data/scenarios/{output.name}",
            file_prefix=f"{partition}.",
            config=array_config,
            feature_columns=_scenario_feature_columns(
                rows,
                resolved,
                output.metadata.get("transformations", []),
            ),
            target_columns=[field.semantic_name for field in resolved.targets],
            auxiliary_columns=[field for field in auxiliary_fields if field in clean_frame.columns],
            units=_unit_mapping(resolved),
            checkpoint=None if execution is None else execution.raise_if_cancelled,
        )
        artifacts.extend(array_result.artifact_names)
        array_manifests[partition] = array_result.manifest
        if execution is not None:
            execution.raise_if_cancelled()
    return ScenarioPartitionWriteResult(
        artifact_names=artifacts,
        array_manifests=array_manifests,
    )


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


def _unit_mapping(resolved: ResolvedPreparation) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in (*resolved.numeric_features, *resolved.targets, *resolved.auxiliary):
        result[field.semantic_name] = field.unit
    for derived_name in resolved.derived_features:
        mapping = resolved.semantic_mapping.get(derived_name, {})
        unit = mapping.get("unit")
        result[derived_name] = unit if isinstance(unit, str) else None
    for categorical_name in resolved.categorical_feature_fields:
        result[categorical_name] = None
    return result


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:
        raise OutputError(f"could not write preparation Parquet {path.name}: {exc}") from exc


def _write_text(path: Path, value: str) -> None:
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc
