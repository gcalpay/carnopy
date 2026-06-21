from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from pydantic import ValidationError

from carnopy.visualization.curves import render_property_curves
from carnopy.visualization.export import DEFAULT_RASTER_DPI, export_figure
from carnopy.visualization.fields import FieldDefinition, get_field
from carnopy.visualization.heatmaps import render_property_heatmap
from carnopy.visualization.io import load_plot_source
from carnopy.visualization.models import (
    Advisory,
    PlotCoordinate,
    PlotKind,
    PlotResult,
    PlotScale,
    RenderedPlot,
    VisualizationError,
)
from carnopy.visualization.render import import_matplotlib
from carnopy.visualization.requests import (
    ExactFilter,
    PlotFormat,
    normalize_public_plot_kind,
    property_plot_request,
    request_id,
)
from carnopy.visualization.selection import dynamic_range_advisories, select_rows


def plot_dataset(
    source: str | Path,
    *,
    kind: str,
    property_name: str,
    x: str | None = None,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    value_scale: PlotScale = "linear",
    color_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    """Render one normalized property-plot request from emitted dataset columns."""
    try:
        normalized_kind = normalize_public_plot_kind(kind)
    except ValueError as exc:
        raise VisualizationError(str(exc)) from exc
    if normalized_kind == "property_curves":
        if color_scale != "linear":
            raise VisualizationError("color_scale is valid only for property_heatmap")
        return plot_property_curves(
            source,
            property_name=property_name,
            x=x,
            fluids=fluids,
            filters=filters,
            value_scale=value_scale,
            output=output,
            show=show,
            saturation_coordinate=saturation_coordinate,
        )
    if x is not None:
        raise VisualizationError("property_heatmap uses mode-defined axes and rejects x")
    if value_scale != "linear":
        raise VisualizationError("value_scale is valid only for property_curves")
    return plot_property_heatmap(
        source,
        property_name=property_name,
        fluids=fluids,
        filters=filters,
        color_scale=color_scale,
        output=output,
        show=show,
        saturation_coordinate=saturation_coordinate,
    )


def plot_property_curves(
    source: str | Path,
    *,
    property_name: str,
    x: str | None = None,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    value_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    return _plot_property(
        source,
        kind="property_curves",
        property_name=property_name,
        x=x,
        fluids=fluids,
        filters=filters,
        value_scale=value_scale,
        color_scale="linear",
        output=output,
        show=show,
        saturation_coordinate=saturation_coordinate,
    )


def plot_property_heatmap(
    source: str | Path,
    *,
    property_name: str,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    color_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    return _plot_property(
        source,
        kind="property_heatmap",
        property_name=property_name,
        x=None,
        fluids=fluids,
        filters=filters,
        value_scale="linear",
        color_scale=color_scale,
        output=output,
        show=show,
        saturation_coordinate=saturation_coordinate,
    )


def _plot_property(
    source: str | Path,
    *,
    kind: PlotKind,
    property_name: str,
    x: str | None,
    fluids: Sequence[str] | None,
    filters: Sequence[ExactFilter],
    value_scale: PlotScale,
    color_scale: PlotScale,
    output: str | Path | None,
    show: bool,
    saturation_coordinate: PlotCoordinate | None,
) -> PlotResult:
    try:
        output_format = _output_format(output)
        request = property_plot_request(
            property_name=property_name,
            kind=kind,
            x_field=x,
            filters=tuple(filters),
            fluids=tuple(fluids or ()),
            value_scale=value_scale,
            color_scale=color_scale,
            saturation_coordinate=saturation_coordinate,
            output_format=output_format,
        )
    except (ValidationError, ValueError) as exc:
        raise VisualizationError(str(exc)) from exc
    plot_source = load_plot_source(
        source,
        saturation_coordinate=saturation_coordinate,
    )
    if request.saturation_coordinate is None and plot_source.saturation_coordinate is not None:
        request = request.model_copy(
            update={"saturation_coordinate": plot_source.saturation_coordinate}
        )
    selection = select_rows(
        plot_source.frame,
        fluids=fluids,
        filters=filters,
    )
    property_field = _property_field(property_name)
    prepared, valid_count, excluded_count = _prepare_property_frame(
        selection.frame,
        property_field,
    )
    valid_values = prepared.loc[prepared["_plot_valid"], "_plot_value"]
    if valid_values.empty:
        raise VisualizationError("no valid property values remain to plot")
    effective_scale = value_scale if kind == "property_curves" else color_scale
    if effective_scale == "log" and bool((valid_values <= 0.0).any()):
        raise VisualizationError(f"log scaling requires positive {property_name} values")
    advisories = dynamic_range_advisories(
        valid_values.tolist(),
        scale=effective_scale,
        subject=f"{property_name} property",
    )
    visualization_request_id = request_id((request,))
    mpl = import_matplotlib()
    if kind == "property_curves":
        rendered = render_property_curves(
            mpl=mpl,
            plot_source=plot_source,
            frame=prepared,
            request=request,
            property_field=property_field,
            fluids=selection.selected_fluids,
            invalid_rows_excluded=excluded_count,
        )
    else:
        rendered = render_property_heatmap(
            mpl=mpl,
            plot_source=plot_source,
            frame=prepared,
            request=request,
            property_field=property_field,
            fluids=selection.selected_fluids,
            invalid_rows_excluded=excluded_count,
        )
    advisories = (
        *advisories,
        *_layout_advisories(rendered, selection.selected_fluids),
    )
    image_path, sidecar_path = export_figure(
        rendered=rendered,
        plot_source=plot_source,
        output=output,
        selected_fluids=selection.selected_fluids,
        property_field=property_field,
        valid_rows_plotted=valid_count,
        invalid_rows_excluded=excluded_count,
        matplotlib_version=mpl["matplotlib"].__version__,
        request=request,
        visualization_request_id=visualization_request_id,
        filter_matches=selection.filter_matches,
        advisories=advisories,
    )
    if show:
        mpl["pyplot"].show()
    effective_settings = {
        **rendered.settings,
        "raster_dpi": (DEFAULT_RASTER_DPI if image_path.suffix.lower() == ".png" else None),
    }
    return PlotResult(
        figure=rendered.figure,
        image_path=image_path,
        sidecar_path=sidecar_path,
        selected_fluids=selection.selected_fluids,
        property_name=property_name,
        kind=kind,
        scale=effective_scale,
        valid_rows_plotted=valid_count,
        invalid_rows_excluded=excluded_count,
        source_integrity=plot_source.source_integrity,
        visualization_request_id=visualization_request_id,
        effective_settings=effective_settings,
        advisories=advisories,
    )


def _property_field(property_name: str) -> FieldDefinition:
    try:
        definition = get_field(property_name)
    except ValueError as exc:
        raise VisualizationError(str(exc)) from exc
    if definition.kind != "numeric" or definition.required_property is None:
        raise VisualizationError(f"{property_name!r} is not a plottable Carnopy property")
    return definition


def _prepare_property_frame(
    frame: pd.DataFrame,
    property_field: FieldDefinition,
) -> tuple[pd.DataFrame, int, int]:
    selected = frame.copy()
    dependency = property_field.required_property
    if dependency is None:
        raise VisualizationError(f"{property_field.name!r} has no emitted dependency")
    dependency_field = get_field(dependency)
    if dependency_field.column not in selected.columns:
        raise VisualizationError(
            f"property {dependency!r} required by {property_field.name!r} "
            "is not present in the source dataset"
        )
    numeric = pd.to_numeric(selected[dependency_field.column], errors="coerce")
    if property_field.derivation == "reciprocal":
        values = pd.Series(np.nan, index=selected.index, dtype=float)
        positive = numeric > 0.0
        values.loc[positive] = 1.0 / numeric.loc[positive]
    else:
        values = numeric.astype(float)
        positive = pd.Series(True, index=selected.index)
    selected["_plot_value"] = values
    valid_column = selected["valid"]
    if valid_column.dtype == object:
        row_valid = valid_column.astype(str).str.casefold().eq("true")
    else:
        row_valid = valid_column.astype(bool)
    finite = pd.Series(
        np.isfinite(selected["_plot_value"].to_numpy(dtype=float)),
        index=selected.index,
    )
    selected["_plot_valid"] = row_valid & finite & positive
    selected.loc[~selected["_plot_valid"], "_plot_value"] = np.nan
    valid_count = int(selected["_plot_valid"].sum())
    return selected, valid_count, len(selected) - valid_count


def _layout_advisories(
    rendered: RenderedPlot,
    fluids: tuple[str, ...],
) -> tuple[Advisory, ...]:
    advisories: list[Advisory] = []
    x_range = rendered.settings.get("x_range")
    if isinstance(x_range, list):
        advisories.extend(
            dynamic_range_advisories(
                x_range,
                scale=cast(PlotScale, rendered.scales["x"] or "linear"),
                subject="x-axis",
            )
        )
    y_range = rendered.settings.get("y_range")
    if isinstance(y_range, list):
        advisories.extend(
            dynamic_range_advisories(
                y_range,
                scale=cast(PlotScale, rendered.scales["y"] or "linear"),
                subject="y-axis",
            )
        )
    if len(fluids) > 6:
        advisories.append(
            Advisory(
                code="crowded_fluid_facets",
                message=(
                    f"the figure contains {len(fluids)} fluid facets; "
                    "consider selecting fewer fluids or separate plots"
                ),
            )
        )
    if rendered.series_or_cells.get("representation") == "sampled_series":
        raw_series = rendered.series_or_cells.get("series")
        if isinstance(raw_series, dict):
            maximum = max(
                (len(items) for items in raw_series.values() if isinstance(items, list)),
                default=0,
            )
            if maximum > 20:
                advisories.append(
                    Advisory(
                        code="crowded_curve_family",
                        message=(
                            f"the largest facet contains {maximum} curve series; "
                            "consider exact filters or separate plots"
                        ),
                    )
                )
    return tuple(advisories)


def _output_format(output: str | Path | None) -> PlotFormat:
    if output is None:
        return "png"
    suffix = Path(output).suffix.lower().removeprefix(".")
    if suffix not in {"png", "pdf", "svg"}:
        raise VisualizationError("figure output must use a .png, .pdf, or .svg extension")
    return cast(PlotFormat, suffix)
