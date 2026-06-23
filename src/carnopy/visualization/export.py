from __future__ import annotations

import errno
import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from carnopy._version import __version__
from carnopy.provenance import sha256_file
from carnopy.visualization.fields import FieldDefinition
from carnopy.visualization.models import (
    Advisory,
    PlotSource,
    RenderedPlot,
    VisualizationError,
)
from carnopy.visualization.requests import PlotRequest
from carnopy.visualization.selection import FilterMatch, SeriesMatch

PLOT_SCHEMA_VERSION = 2
DEFAULT_RASTER_DPI = 300
ALLOWED_OUTPUT_SUFFIXES = {".png", ".pdf", ".svg"}


def export_figure(
    *,
    rendered: RenderedPlot,
    plot_source: PlotSource,
    output: str | Path | None,
    selected_fluids: tuple[str, ...],
    property_field: FieldDefinition | None,
    valid_rows_plotted: int,
    invalid_rows_excluded: int,
    matplotlib_version: str,
    request: PlotRequest,
    visualization_request_id: str,
    filter_matches: tuple[FilterMatch, ...],
    series_matches: tuple[SeriesMatch, ...],
    advisories: tuple[Advisory, ...],
) -> tuple[Path, Path]:
    image_path = _resolve_output_path(
        output=output,
        plot_source=plot_source,
        selected_fluids=selected_fluids,
        descriptor=_plot_descriptor(request, property_field),
        kind=request.kind,
    )
    _ensure_output_outside_source_run(image_path, plot_source)
    sidecar_path = image_path.with_suffix(".plot.json")
    try:
        image_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisualizationError(
            f"could not create figure output directory {image_path.parent}: {exc}"
        ) from exc
    existing = next(
        (path for path in (image_path, sidecar_path) if os.path.lexists(path)),
        None,
    )
    if existing is not None:
        raise VisualizationError(f"refusing to overwrite existing plot artifact: {existing}")

    token = uuid4().hex
    staged_image = image_path.parent / (
        f".{image_path.stem}.{token}.tmp{image_path.suffix.lower()}"
    )
    staged_sidecar = image_path.parent / f".{image_path.name}.{token}.tmp.plot.json"
    linked_image = False
    linked_sidecar = False
    try:
        save_kwargs: dict[str, Any] = {
            "format": image_path.suffix.lower().removeprefix("."),
        }
        if image_path.suffix.lower() == ".png":
            save_kwargs["dpi"] = DEFAULT_RASTER_DPI
        rendered.figure.savefig(staged_image, **save_kwargs)
        image_sha256 = _hash_file(staged_image)
        sidecar = _build_sidecar(
            plot_source=plot_source,
            image_path=image_path,
            image_sha256=image_sha256,
            sidecar_path=sidecar_path,
            selected_fluids=selected_fluids,
            property_field=property_field,
            valid_rows_plotted=valid_rows_plotted,
            invalid_rows_excluded=invalid_rows_excluded,
            matplotlib_version=matplotlib_version,
            rendered=rendered,
            request=request,
            visualization_request_id=visualization_request_id,
            filter_matches=filter_matches,
            series_matches=series_matches,
            advisories=advisories,
        )
        with staged_sidecar.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(sidecar, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        os.link(staged_image, image_path)
        linked_image = True
        os.link(staged_sidecar, sidecar_path)
        linked_sidecar = True
    except VisualizationError:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        raise
    except OSError as exc:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        if exc.errno in {
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
            errno.EPERM,
            errno.EXDEV,
        }:
            raise VisualizationError(
                "plot export requires same-filesystem hard-link support; "
                f"could not promote staged artifacts: {exc}"
            ) from exc
        raise VisualizationError(f"could not export plot artifacts: {exc}") from exc
    except Exception as exc:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        raise VisualizationError(f"could not export plot artifacts: {exc}") from exc
    finally:
        _unlink_staged(staged_sidecar)
        _unlink_staged(staged_image)
    return image_path, sidecar_path


def _resolve_output_path(
    *,
    output: str | Path | None,
    plot_source: PlotSource,
    selected_fluids: tuple[str, ...],
    descriptor: str,
    kind: str,
) -> Path:
    if output is None:
        fluid_part = _slug(selected_fluids[0]) if len(selected_fluids) == 1 else "multifluid"
        filename = f"{fluid_part}_{descriptor}_{kind}_{plot_source.run_id[:8]}.png"
        path = Path.cwd() / "figures" / filename
    else:
        path = Path(output).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    if path.suffix.lower() not in ALLOWED_OUTPUT_SUFFIXES:
        raise VisualizationError("figure output must use a .png, .pdf, or .svg extension")
    return path.resolve()


def _ensure_output_outside_source_run(
    image_path: Path,
    plot_source: PlotSource,
) -> None:
    if plot_source.metadata is None:
        return
    source_directory = plot_source.dataset_path.parent.resolve()
    if image_path.is_relative_to(source_directory):
        raise VisualizationError(
            "figures cannot be written inside an immutable source run directory"
        )


def _build_sidecar(
    *,
    plot_source: PlotSource,
    image_path: Path,
    image_sha256: str,
    sidecar_path: Path,
    selected_fluids: tuple[str, ...],
    property_field: FieldDefinition | None,
    valid_rows_plotted: int,
    invalid_rows_excluded: int,
    matplotlib_version: str,
    rendered: RenderedPlot,
    request: PlotRequest,
    visualization_request_id: str,
    filter_matches: tuple[FilterMatch, ...],
    series_matches: tuple[SeriesMatch, ...],
    advisories: tuple[Advisory, ...],
) -> dict[str, Any]:
    return {
        "plot_schema_version": PLOT_SCHEMA_VERSION,
        "plot_kind": request.kind,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_identity": {
            "requested_path": str(plot_source.requested_path),
            "dataset_path": str(plot_source.dataset_path),
            "dataset_format": plot_source.source_format,
            "dataset_sha256": plot_source.source_sha256,
            "integrity": plot_source.source_integrity,
            "metadata_path": (
                str(plot_source.metadata_path) if plot_source.metadata_path is not None else None
            ),
            "run_id": plot_source.run_id,
            "spec_id": plot_source.spec_id,
            "generation_context_id": plot_source.generation_context_id,
            "mode": plot_source.mode,
            "backend": _single_or_joined(plot_source.frame["backend"]),
            "backend_version": _single_or_joined(plot_source.frame["backend_version"]),
            "reference_state_policy": _metadata_text(plot_source, "reference_state_policy"),
        },
        "visualization_request_id": visualization_request_id,
        "normalized_request": request.canonical_dict(),
        "data_selection": {
            "fluids": list(selected_fluids),
            "property": property_field.name if property_field is not None else None,
            "property_column": (property_field.column if property_field is not None else None),
            "property_unit": property_field.unit if property_field is not None else None,
            "x_field": request.x_field,
            "y_field": request.y_field,
            "group_by": request.group_by,
            "filters": [
                {
                    "field": match.field,
                    "requested_value": match.requested_value,
                    "matched_values": list(match.matched_values),
                }
                for match in filter_matches
            ],
            "series": [
                {
                    "field": match.field,
                    "requested_values": list(match.requested_values),
                    "matched_values": list(match.matched_values),
                }
                for match in series_matches
            ],
            "display_units": {
                selection.field: selection.unit for selection in request.display_units
            },
            "saturation_coordinate": plot_source.saturation_coordinate,
            "saturation_coordinate_display_unit": (plot_source.saturation_coordinate_display_unit),
        },
        "axes": rendered.axes,
        "scales": rendered.scales,
        "effective_settings": {
            **rendered.settings,
            "raster_dpi": (DEFAULT_RASTER_DPI if image_path.suffix.lower() == ".png" else None),
        },
        "series_or_cells": rendered.series_or_cells,
        "advisories": [asdict(advisory) for advisory in advisories],
        "valid_sample_count": valid_rows_plotted,
        "excluded_sample_count": invalid_rows_excluded,
        "image": {
            "path": str(image_path),
            "sidecar_path": str(sidecar_path),
            "sha256": image_sha256,
            "format": image_path.suffix.lower().removeprefix("."),
        },
        "runtime_versions": {
            "carnopy": __version__,
            "matplotlib": matplotlib_version,
        },
    }


def _hash_file(path: Path) -> str:
    try:
        return sha256_file(path)
    except OSError as exc:
        raise VisualizationError(f"could not hash exported figure {path}: {exc}") from exc


def _unlink_if_same_file(final_path: Path, staged_path: Path) -> None:
    try:
        final_stat = os.stat(final_path, follow_symlinks=False)
        staged_stat = os.stat(staged_path, follow_symlinks=False)
    except OSError:
        return
    if (final_stat.st_dev, final_stat.st_ino) != (staged_stat.st_dev, staged_stat.st_ino):
        return
    try:
        final_path.unlink()
    except OSError:
        return


def _unlink_staged(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return cleaned or "fluid"


def _single_or_joined(series: Any) -> str:
    values = sorted(series.dropna().astype(str).unique().tolist())
    return ", ".join(values) if values else "unreported"


def _metadata_text(plot_source: PlotSource, key: str) -> str | None:
    if plot_source.metadata is None:
        return None
    value = plot_source.metadata.get(key)
    return value if isinstance(value, str) else None


def _plot_descriptor(
    request: PlotRequest,
    property_field: FieldDefinition | None,
) -> str:
    if property_field is not None:
        return property_field.name
    if request.kind == "xy":
        return f"{request.x_field}_vs_{request.y_field}"
    return request.kind
