from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from carnopy._version import __version__
from carnopy.results import RunStatus, VisualizationStatus, VisualizationSummary
from carnopy.visualization.configuration import NormalizedVisualization
from carnopy.visualization.models import PlotResult
from carnopy.visualization.plots import render_plot_request
from carnopy.visualization.render import import_matplotlib

VISUALIZATION_REPORT_SCHEMA_VERSION = 1


def ensure_visualization_dependencies() -> None:
    import_matplotlib()


def render_configured_visualizations(
    *,
    source_run: Path,
    figures_root: Path,
    run_status: RunStatus,
    run_id: str,
    spec_id: str,
    generation_context_id: str,
    visualization: NormalizedVisualization,
) -> VisualizationSummary:
    figure_directory = figures_root.expanduser().resolve() / source_run.name
    try:
        figure_directory.parent.mkdir(parents=True, exist_ok=True)
        figure_directory.mkdir()
    except OSError:
        return _summary(
            visualization=visualization,
            status="failed",
            figure_directory=None,
            report_path=None,
            succeeded=0,
            failed=len(visualization.requests),
            skipped=0,
        )

    outcomes: list[dict[str, Any]] = []
    if run_status == "completed_zero_valid_rows":
        outcomes.extend(
            {
                "name": request.name,
                "kind": request.kind,
                "status": "skipped",
                "reason": "dataset contains zero valid rows",
            }
            for request in visualization.requests
        )
        return _finalize_report(
            source_run=source_run,
            figure_directory=figure_directory,
            run_id=run_id,
            spec_id=spec_id,
            generation_context_id=generation_context_id,
            visualization=visualization,
            status="skipped_zero_valid_rows",
            outcomes=outcomes,
            succeeded=0,
            failed=0,
            skipped=len(visualization.requests),
        )

    mpl = import_matplotlib()
    succeeded = 0
    failed = 0
    for request in visualization.requests:
        result: PlotResult | None = None
        output = figure_directory / f"{request.name}.{request.output_format}"
        try:
            result = render_plot_request(
                source_run,
                request=request,
                output=output,
                show=False,
                visualization_request_id=visualization.visualization_request_id,
            )
        except Exception as exc:
            failed += 1
            outcomes.append(
                {
                    "name": request.name,
                    "kind": request.kind,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        else:
            succeeded += 1
            outcomes.append(
                {
                    "name": request.name,
                    "kind": request.kind,
                    "status": "completed",
                    "image_path": str(result.image_path),
                    "sidecar_path": str(result.sidecar_path),
                    "valid_sample_count": result.valid_rows_plotted,
                    "excluded_sample_count": result.invalid_rows_excluded,
                    "advisories": [asdict(advisory) for advisory in result.advisories],
                }
            )
        finally:
            if result is not None:
                mpl["pyplot"].close(result.figure)

    status: VisualizationStatus
    if failed == 0:
        status = "completed"
    elif succeeded:
        status = "completed_with_failures"
    else:
        status = "failed"
    return _finalize_report(
        source_run=source_run,
        figure_directory=figure_directory,
        run_id=run_id,
        spec_id=spec_id,
        generation_context_id=generation_context_id,
        visualization=visualization,
        status=status,
        outcomes=outcomes,
        succeeded=succeeded,
        failed=failed,
        skipped=0,
    )


def _finalize_report(
    *,
    source_run: Path,
    figure_directory: Path,
    run_id: str,
    spec_id: str,
    generation_context_id: str,
    visualization: NormalizedVisualization,
    status: VisualizationStatus,
    outcomes: list[dict[str, Any]],
    succeeded: int,
    failed: int,
    skipped: int,
) -> VisualizationSummary:
    report_path = figure_directory / "visualization-report.json"
    report = {
        "visualization_report_schema_version": VISUALIZATION_REPORT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "visualization_request_id": visualization.visualization_request_id,
        "status": status,
        "source_identity": {
            "run_directory": str(source_run),
            "run_id": run_id,
            "spec_id": spec_id,
            "generation_context_id": generation_context_id,
        },
        "normalized_visualization": visualization.canonical_dict(),
        "requested_plot_count": len(visualization.requests),
        "succeeded_plot_count": succeeded,
        "failed_plot_count": failed,
        "skipped_plot_count": skipped,
        "outcomes": outcomes,
        "runtime_versions": {
            "carnopy": __version__,
            "matplotlib": metadata.version("matplotlib"),
        },
    }
    try:
        with report_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        return _summary(
            visualization=visualization,
            status="failed",
            figure_directory=figure_directory,
            report_path=None,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
        )
    return _summary(
        visualization=visualization,
        status=status,
        figure_directory=figure_directory,
        report_path=report_path,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
    )


def _summary(
    *,
    visualization: NormalizedVisualization,
    status: VisualizationStatus,
    figure_directory: Path | None,
    report_path: Path | None,
    succeeded: int,
    failed: int,
    skipped: int,
) -> VisualizationSummary:
    return VisualizationSummary(
        visualization_request_id=visualization.visualization_request_id,
        status=status,
        figure_directory=figure_directory,
        report_path=report_path,
        requested_plot_count=len(visualization.requests),
        succeeded_plot_count=succeeded,
        failed_plot_count=failed,
        skipped_plot_count=skipped,
    )
