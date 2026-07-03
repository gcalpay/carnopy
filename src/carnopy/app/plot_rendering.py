from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from carnopy.app.jobs import write_json_atomic
from carnopy.app.plot_staging import (
    PlotStagingPayload,
    promote_plot_artifacts,
    validate_plot_staging,
)
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.workspace import open_workspace
from carnopy.config.visualization import (
    PLOT_NAME_PATTERN,
    VisualizationConfig,
    VisualizationPlotConfig,
)
from carnopy.provenance import sha256_file
from carnopy.visualization.configuration import normalize_visualization_for_source
from carnopy.visualization.io import load_plot_source
from carnopy.visualization.models import PlotResult, VisualizationError
from carnopy.visualization.plots import render_plot_request
from carnopy.visualization.render import import_matplotlib
from carnopy.visualization.requests import PlotFormat


class RenderPlotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_path: Path
    source_path: Path
    inspection_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    plot_name: str = Field(pattern=PLOT_NAME_PATTERN)
    format: PlotFormat
    plot: dict[str, Any]
    staging: PlotStagingPayload

    @model_validator(mode="after")
    def consistent_request_identity(self) -> RenderPlotPayload:
        if "output_format" in self.plot:
            raise ValueError("plot request must use top-level format, not output_format")
        request_format = self.plot.get("format")
        if request_format is not None and request_format != self.format:
            raise ValueError("plot request format conflicts with top-level format")
        request_name = self.plot.get("name")
        if request_name is not None and request_name != self.plot_name:
            raise ValueError("plot request name conflicts with top-level plot_name")
        return self


def render_plot(payload: RenderPlotPayload) -> dict[str, Any]:
    workspace = open_workspace(payload.workspace_path)
    lease = validate_plot_staging(workspace, payload.staging)
    inspection = inspect_for_app(payload.source_path)
    if inspection.source_kind != "dataset":
        raise VisualizationError("manual plotting supports dataset sources only")
    if inspection.revision != payload.inspection_revision:
        raise VisualizationError("inspection source changed; refresh before rendering a plot")

    plot_source = load_plot_source(inspection.source)
    plot_config = VisualizationPlotConfig.model_validate(
        {
            **payload.plot,
            "name": payload.plot_name,
            "format": payload.format,
        }
    )
    visualization = VisualizationConfig(
        format=payload.format,
        plots=(plot_config,),
    )
    normalized = normalize_visualization_for_source(
        visualization,
        plot_source=plot_source,
    )
    request = normalized.requests[0]

    source_hash = inspection.tables[0].sha256
    source_name = _source_name(inspection.source, source_hash)
    final_image = _output_path(
        workspace.figures,
        source_name,
        payload.plot_name,
        payload.format,
    )
    final_sidecar = final_image.with_suffix(".plot.json")
    staged_image = lease.path / final_image.name

    mpl = import_matplotlib()
    pyplot = mpl["pyplot"]
    existing_figures = set(pyplot.get_fignums())
    result: PlotResult | None = None
    try:
        result = render_plot_request(
            inspection.source,
            request=request,
            output=staged_image,
            show=False,
            visualization_request_id=normalized.visualization_request_id,
        )
        _rewrite_sidecar_paths(result.sidecar_path, final_image, final_sidecar)
        promote_plot_artifacts(
            lease,
            staged_image=result.image_path,
            staged_sidecar=result.sidecar_path,
            final_image=final_image,
            final_sidecar=final_sidecar,
        )
        return _result_payload(
            result,
            image_path=final_image,
            sidecar_path=final_sidecar,
            source=inspection.source,
            source_name=source_name,
            inspection_revision=inspection.revision,
            normalized_request=request.canonical_dict(),
        )
    finally:
        if result is not None:
            pyplot.close(result.figure)
        for figure_number in set(pyplot.get_fignums()) - existing_figures:
            pyplot.close(figure_number)


def _source_name(source: Path, source_hash: str) -> str:
    raw_name = source.name if source.is_dir() else source.stem
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw_name.lower()).strip("-_")
    return slug or f"dataset-{source_hash[:8]}"


def _output_path(
    figures_root: Path,
    source_name: str,
    plot_name: str,
    output_format: PlotFormat,
) -> Path:
    if figures_root.is_symlink():
        raise VisualizationError("workspace figures directory must not be a symbolic link")
    resolved_root = figures_root.resolve()
    source_directory = figures_root / source_name
    if source_directory.is_symlink():
        raise VisualizationError("plot source directory must not be a symbolic link")
    if source_directory.exists() and not source_directory.is_dir():
        raise VisualizationError(f"plot source directory conflicts with a file: {source_directory}")
    source_directory.mkdir(exist_ok=True)
    if source_directory.is_symlink():
        raise VisualizationError("plot source directory must not be a symbolic link")
    resolved_source = source_directory.resolve()
    if resolved_source.parent != resolved_root:
        raise VisualizationError("plot source directory must be a direct child of figures")
    image_path = (resolved_source / f"{plot_name}.{output_format}").resolve()
    sidecar_path = image_path.with_suffix(".plot.json")
    if image_path.parent != resolved_source or not image_path.is_relative_to(resolved_root):
        raise VisualizationError("plot output path escapes the workspace figures directory")
    if sidecar_path.parent != resolved_source or not sidecar_path.is_relative_to(resolved_root):
        raise VisualizationError("plot sidecar path escapes the workspace figures directory")
    existing = next(
        (path for path in (image_path, sidecar_path) if os.path.lexists(path)),
        None,
    )
    if existing is not None:
        raise VisualizationError(f"refusing to overwrite existing plot artifact: {existing}")
    return image_path


def _rewrite_sidecar_paths(
    sidecar_path: Path,
    final_image: Path,
    final_sidecar: Path,
) -> None:
    try:
        value = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("plot sidecar has an invalid structure")
        image = value.get("image")
        if not isinstance(image, dict):
            raise ValueError("plot sidecar has an invalid structure")
        image["path"] = str(final_image)
        image["sidecar_path"] = str(final_sidecar)
        write_json_atomic(sidecar_path, value)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VisualizationError(f"could not finalize staged plot sidecar: {exc}") from exc


def _result_payload(
    result: PlotResult,
    *,
    image_path: Path,
    sidecar_path: Path,
    source: Path,
    source_name: str,
    inspection_revision: str,
    normalized_request: dict[str, object],
) -> dict[str, Any]:
    return {
        "source": str(source),
        "source_name": source_name,
        "inspection_revision": inspection_revision,
        "image_path": str(image_path),
        "sidecar_path": str(sidecar_path),
        "image_sha256": sha256_file(image_path),
        "sidecar_sha256": sha256_file(sidecar_path),
        "kind": result.kind,
        "format": image_path.suffix.removeprefix("."),
        "property": result.property_name,
        "selected_fluids": list(result.selected_fluids),
        "valid_rows_plotted": result.valid_rows_plotted,
        "invalid_rows_excluded": result.invalid_rows_excluded,
        "source_integrity": result.source_integrity,
        "visualization_request_id": result.visualization_request_id,
        "normalized_request": normalized_request,
        "effective_settings": result.effective_settings,
        "advisories": [asdict(advisory) for advisory in result.advisories],
    }
