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


@dataclass(frozen=True)
class ValidationResult:
    backend: str
    backend_version: str
    mode: str
    projected_rows: int
    canonical_fluids: tuple[str, ...]
    normalized_config_sha256: str


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
class RunResult:
    run_id: str
    run_status: RunStatus
    mode: str
    output_directory: Path
    row_count: int
    valid_row_count: int
    invalid_row_count: int
    spec_id: str
    generation_context_id: str
    visualization: VisualizationSummary | None = None
