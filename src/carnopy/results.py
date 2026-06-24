from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RunStatus = Literal["completed", "completed_with_invalid_rows", "completed_zero_valid_rows"]
VisualizationStatus = Literal[
    "completed",
    "completed_with_failures",
    "failed",
    "skipped_zero_valid_rows",
]
PreparationStatus = Literal[
    "completed",
    "completed_with_exclusions",
    "no_eligible_rows",
    "failed",
]


@dataclass(frozen=True)
class ValidationResult:
    backend: str
    backend_model: str
    backend_version: str
    mode: str
    projected_rows: int
    canonical_fluids: tuple[str, ...]
    normalized_config_sha256: str
    output_request_id: str
    dataset_formats: tuple[str, ...]


@dataclass(frozen=True)
class VisualizationSummary:
    visualization_request_id: str
    status: VisualizationStatus
    figure_directory: Path | None
    report_path: Path | None
    requested_plot_count: int
    succeeded_plot_count: int
    failed_plot_count: int
    skipped_plot_count: int


@dataclass(frozen=True)
class PreparationResult:
    preparation_request_id: str
    preparation_context_id: str
    preparation_run_id: str
    status: PreparationStatus
    output_directory: Path
    eligible_row_count: int
    excluded_row_count: int
    table_path: Path | None
    provenance_path: Path
    source_diagnostics_path: Path
    exclusions_path: Path
    manifest_path: Path
    diagnostics_path: Path
    dataset_card_path: Path
    scenario_report_path: Path | None = None
    scenario_count: int = 0
    partition_count: int = 0


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_status: RunStatus
    mode: str
    backend: str
    backend_model: str
    backend_version: str
    output_directory: Path
    row_count: int
    valid_row_count: int
    invalid_row_count: int
    spec_id: str
    generation_context_id: str
    output_request_id: str
    dataset_formats: tuple[str, ...]
    visualization: VisualizationSummary | None = None


SweepStatus = Literal["completed", "incomplete", "failed"]


@dataclass(frozen=True)
class SweepResult:
    sweep_id: str
    sweep_run_id: str
    sweep_status: SweepStatus
    output_directory: Path
    backend: str
    backend_version: str
    models: tuple[str, ...]
    reference_model: str
    mode: str
    child_runs: tuple[RunResult, ...]
    values_path: Path | None
    deltas_path: Path | None
    comparison_plot_directory: Path | None
    comparison_report_path: Path | None
    failure_message: str | None = None
