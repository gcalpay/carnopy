from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy._version import __version__
from carnopy.backends.coolprop import CoolPropBackend
from carnopy.config.io import LoadedSweepConfig
from carnopy.domain.failures import CarnopyError, OutputError
from carnopy.outputs import hash_artifacts, write_bytes, write_json
from carnopy.pipeline import run_generation
from carnopy.provenance import sha256_bytes
from carnopy.results import RunResult, SweepResult, SweepStatus
from carnopy.sweeps.comparison import ComparisonArtifacts, write_comparison_artifacts
from carnopy.sweeps.layout import (
    SweepLayout,
    cleanup_sweep_layout,
    create_sweep_layout,
    finalize_sweep_layout,
)
from carnopy.sweeps.normalize import NormalizedSweep, normalize_sweep_config
from carnopy.sweeps.plots import render_comparison_plots
from carnopy.visualization.render import import_matplotlib

SWEEP_METADATA_SCHEMA_VERSION = 1
SWEEP_REPORT_SCHEMA_VERSION = 1


def run_model_sweep(
    loaded: LoadedSweepConfig,
    output_root: Path,
    *,
    execution: ExecutionControl | None = None,
) -> SweepResult:
    return _run_model_sweep(
        loaded,
        normalize_sweep_config(loaded),
        output_root,
        execution=execution,
    )


def _run_model_sweep(
    loaded: LoadedSweepConfig,
    normalized: NormalizedSweep,
    output_root: Path,
    *,
    execution: ExecutionControl | None = None,
) -> SweepResult:
    if execution is not None:
        execution.phase("validation")
    if loaded.model.comparison_plots is not None:
        import_matplotlib()
    if execution is not None:
        execution.raise_if_cancelled()
    sweep_run_id = str(uuid4())
    sweep_id = f"sweep-{sha256_bytes(normalized.normalized_bytes)}"
    created_at = datetime.now(UTC)
    layout = create_sweep_layout(
        output_root=output_root,
        sweep_run_id=sweep_run_id,
        created_at=created_at,
    )
    child_results: dict[str, RunResult] = {}
    child_paths: dict[str, Path] = {}
    failure_message: str | None = None
    comparison: ComparisonArtifacts | None = None
    comparison_plot_directory: Path | None = None
    comparison_report_path: Path | None = None
    comparison_plot_failure_count = 0
    status: SweepStatus = "failed"
    try:
        if execution is not None:
            execution.phase("sweep_configuration")
        write_bytes(layout.staging_directory / "sweep.original.yaml", loaded.raw_bytes)
        if execution is not None:
            execution.raise_if_cancelled()
        write_bytes(layout.staging_directory / "sweep.normalized.json", normalized.normalized_bytes)
        models_root = layout.staging_directory / "models"
        public_models_root = layout.final_directory / "models"
        projected_by_model = {
            model: normalized.child_normalized[model].projected_rows
            for model in loaded.model.backend.models
        }
        projected_total = sum(projected_by_model.values())
        completed_before_model = 0
        try:
            for model in loaded.model.backend.models:
                if execution is not None:
                    execution.phase(f"model:{model}")
                child_parent = models_root / model
                public_child_parent = public_models_root / model
                result = run_generation(
                    normalized.child_configs[model],
                    child_parent,
                    public_output_root=public_child_parent,
                    add_state_keys=True,
                    execution=_child_execution(
                        execution,
                        model=model,
                        completed_before_model=completed_before_model,
                        projected_total=projected_total,
                    ),
                )
                child_results[model] = result
                child_paths[model] = child_parent / result.output_directory.name
                completed_before_model += projected_by_model[model]
                if execution is not None:
                    execution.checkpoint(completed_before_model, projected_total)
            status = "completed"
            if execution is not None:
                execution.phase("comparison")
            comparison = write_comparison_artifacts(
                sweep_id=sweep_id,
                reference_model=loaded.model.backend.reference_model,
                child_run_paths=child_paths,
                child_results=child_results,
                properties=normalized.child_normalized[
                    loaded.model.backend.reference_model
                ].properties,
                comparison_directory=layout.staging_directory / "comparison",
                checkpoint=(None if execution is None else execution.raise_if_cancelled),
            )
            if loaded.model.comparison_plots is not None:
                if execution is not None:
                    execution.phase("comparison_plots")
                (
                    comparison_plot_directory,
                    comparison_report_path,
                    comparison_plot_failure_count,
                ) = render_comparison_plots(
                    comparison_plots=loaded.model.comparison_plots,
                    values_path=comparison.values_path,
                    deltas_path=comparison.deltas_path,
                    output_directory=layout.staging_directory / "comparison_plots",
                    sweep_identity=_sweep_identity(
                        sweep_id=sweep_id,
                        sweep_run_id=sweep_run_id,
                        normalized=normalized,
                    ),
                    selected_models=loaded.model.backend.models,
                    reference_model=loaded.model.backend.reference_model,
                    fluid_aliases=_fluid_aliases(normalized),
                    checkpoint=(None if execution is None else execution.raise_if_cancelled),
                )
                if execution is not None:
                    execution.raise_if_cancelled()
                if comparison_plot_failure_count:
                    status = "incomplete"
                    failure_message = (
                        f"{comparison_plot_failure_count} comparison plot request(s) failed"
                    )
        except ExecutionCancelled:
            raise
        except CarnopyError as exc:
            status = "incomplete" if child_results else "failed"
            failure_message = str(exc)

        if execution is not None:
            execution.phase("reporting")
        _write_sweep_reports(
            loaded=loaded,
            normalized=normalized,
            layout=layout,
            sweep_id=sweep_id,
            sweep_run_id=sweep_run_id,
            status=status,
            created_at=created_at,
            child_results=child_results,
            comparison=comparison,
            comparison_plot_directory=comparison_plot_directory,
            comparison_report_path=comparison_report_path,
            failure_message=failure_message,
        )
        if execution is not None:
            execution.protected_phase("finalization")
        finalize_sweep_layout(layout)
    except Exception as original:
        try:
            cleanup_sweep_layout(layout)
        except Exception as cleanup_error:
            raise OutputError(
                f"model sweep failed ({original}); staging cleanup failed: {cleanup_error}"
            ) from cleanup_error
        raise
    return SweepResult(
        sweep_id=sweep_id,
        sweep_run_id=sweep_run_id,
        sweep_status=status,
        output_directory=layout.final_directory,
        backend=loaded.model.backend.name,
        backend_version=CoolPropBackend(model=loaded.model.backend.reference_model).version,
        models=loaded.model.backend.models,
        reference_model=loaded.model.backend.reference_model,
        mode=loaded.model.mode,
        child_runs=tuple(child_results[model] for model in child_results),
        values_path=(
            None
            if comparison is None
            else layout.final_directory / "comparison" / comparison.values_path.name
        ),
        deltas_path=(
            None
            if comparison is None
            else layout.final_directory / "comparison" / comparison.deltas_path.name
        ),
        comparison_plot_directory=(
            None
            if comparison_plot_directory is None
            else layout.final_directory / "comparison_plots"
        ),
        comparison_report_path=(
            None
            if comparison_report_path is None
            else layout.final_directory / "comparison_plots" / comparison_report_path.name
        ),
        failure_message=failure_message,
    )


def _child_execution(
    parent: ExecutionControl | None,
    *,
    model: str,
    completed_before_model: int,
    projected_total: int,
) -> ExecutionControl | None:
    if parent is None:
        return None
    return ExecutionControl(
        cancellation_requested=parent.cancellation_requested,
        on_phase=lambda name, cancellable: parent.phase(
            f"model:{model}:{name}",
            cancellable=cancellable,
        ),
        on_progress=lambda completed, _total: parent.checkpoint(
            completed_before_model + completed,
            projected_total,
        ),
        on_protected_phase=lambda name: parent.on_phase(
            f"model:{model}:{name}",
            False,
        ),
        minimum_progress_interval=parent.minimum_progress_interval,
    )


def _write_sweep_reports(
    *,
    loaded: LoadedSweepConfig,
    normalized: NormalizedSweep,
    layout: SweepLayout,
    sweep_id: str,
    sweep_run_id: str,
    status: SweepStatus,
    created_at: datetime,
    child_results: dict[str, RunResult],
    comparison: ComparisonArtifacts | None,
    comparison_plot_directory: Path | None,
    comparison_report_path: Path | None,
    failure_message: str | None,
) -> dict[str, str]:
    hashed_names = ["sweep.original.yaml", "sweep.normalized.json"]
    if comparison is not None:
        hashed_names.extend(["comparison/values.parquet", "comparison/deltas.parquet"])
    report = {
        "sweep_report_schema_version": SWEEP_REPORT_SCHEMA_VERSION,
        "sweep_id": sweep_id,
        "sweep_run_id": sweep_run_id,
        "sweep_status": status,
        "mode": loaded.model.mode,
        "backend": loaded.model.backend.name,
        "models": list(loaded.model.backend.models),
        "reference_model": loaded.model.backend.reference_model,
        "child_run_count": len(child_results),
        "child_runs": [_child_result_dict(result) for result in child_results.values()],
        "comparison_artifacts": (
            [] if comparison is None else ["comparison/values.parquet", "comparison/deltas.parquet"]
        ),
        "comparison_plot_directory": (
            None
            if comparison_plot_directory is None
            else str(layout.final_directory / "comparison_plots")
        ),
        "comparison_report_path": (
            None
            if comparison_report_path is None
            else str(layout.final_directory / "comparison_plots" / comparison_report_path.name)
        ),
        "failure_message": failure_message,
        "output_directory": str(layout.final_directory),
    }
    write_json(layout.staging_directory / "report.json", report)
    hashed_names.append("report.json")
    artifact_hashes = hash_artifacts(layout.staging_directory, hashed_names)
    metadata = {
        "sweep_metadata_schema_version": SWEEP_METADATA_SCHEMA_VERSION,
        "sweep_id": sweep_id,
        "sweep_run_id": sweep_run_id,
        "sweep_status": status,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "carnopy_version": __version__,
        "backend": loaded.model.backend.name,
        "backend_version": CoolPropBackend(model=loaded.model.backend.reference_model).version,
        "models": list(loaded.model.backend.models),
        "reference_model": loaded.model.backend.reference_model,
        "raw_sweep_sha256": sha256_bytes(loaded.raw_bytes),
        "normalized_sweep_sha256": sha256_bytes(normalized.normalized_bytes),
        "mode": loaded.model.mode,
        "canonical_properties": normalized.child_normalized[
            loaded.model.backend.reference_model
        ].properties,
        "dataset_formats": list(loaded.model.outputs.dataset_formats),
        "child_runs": [_child_result_dict(result) for result in child_results.values()],
        "comparison_artifacts": report["comparison_artifacts"],
        "comparison_plots": (
            None
            if loaded.model.comparison_plots is None
            else loaded.model.comparison_plots.model_dump(mode="json")
        ),
        "failure_message": failure_message,
        "output_directory": str(layout.final_directory),
        "artifact_hashes": artifact_hashes,
    }
    write_json(layout.staging_directory / "metadata.json", metadata)
    return artifact_hashes


def _child_result_dict(result: RunResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "run_status": result.run_status,
        "backend": result.backend,
        "backend_model": result.backend_model,
        "output_directory": str(result.output_directory),
        "row_count": result.row_count,
        "valid_row_count": result.valid_row_count,
        "invalid_row_count": result.invalid_row_count,
        "spec_id": result.spec_id,
        "generation_context_id": result.generation_context_id,
    }


def _sweep_identity(
    *,
    sweep_id: str,
    sweep_run_id: str,
    normalized: NormalizedSweep,
) -> dict[str, str]:
    return {
        "sweep_id": sweep_id,
        "sweep_run_id": sweep_run_id,
        "normalized_sweep_sha256": sha256_bytes(normalized.normalized_bytes),
    }


def _fluid_aliases(normalized: NormalizedSweep) -> dict[str, str]:
    reference = next(iter(normalized.child_normalized.values()))
    aliases = {
        alias.casefold(): canonical
        for alias, canonical in zip(
            reference.requested_fluid_aliases,
            reference.requested_fluid_canonical_names,
            strict=True,
        )
    }
    aliases.update({fluid.casefold(): fluid for fluid in reference.fluids})
    return aliases
