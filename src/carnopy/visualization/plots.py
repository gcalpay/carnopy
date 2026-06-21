from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from pydantic import ValidationError

from carnopy.visualization.curves import render_property_curves
from carnopy.visualization.diagrams import render_thermodynamic_diagram
from carnopy.visualization.export import DEFAULT_RASTER_DPI, export_figure
from carnopy.visualization.fields import FieldDefinition, get_field
from carnopy.visualization.heatmaps import render_property_heatmap
from carnopy.visualization.io import load_plot_source
from carnopy.visualization.models import (
    Advisory,
    PlotCoordinate,
    PlotResult,
    PlotScale,
    PlotSource,
    RenderedPlot,
    VisualizationError,
)
from carnopy.visualization.render import import_matplotlib
from carnopy.visualization.requests import (
    ExactFilter,
    PlotFormat,
    PlotRequest,
    normalize_public_plot_kind,
    property_plot_request,
    request_id,
    thermodynamic_diagram_request,
    xy_plot_request,
)
from carnopy.visualization.selection import (
    FilterMatch,
    dynamic_range_advisories,
    numeric_field_values,
    row_valid_mask,
    select_rows,
)
from carnopy.visualization.xy import render_xy


def plot_dataset(
    source: str | Path,
    *,
    kind: str,
    property_name: str | None = None,
    x: str | None = None,
    y: str | None = None,
    group_by: str | None = None,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    value_scale: PlotScale = "linear",
    color_scale: PlotScale = "linear",
    x_scale: PlotScale = "linear",
    y_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    """Render one normalized visualization request from emitted dataset columns."""
    try:
        normalized_kind = normalize_public_plot_kind(kind)
    except ValueError as exc:
        raise VisualizationError(str(exc)) from exc
    if normalized_kind in {"property_curves", "property_heatmap"}:
        if property_name is None:
            raise VisualizationError(f"{normalized_kind} requires --property")
        if y is not None or group_by is not None:
            raise VisualizationError(f"{normalized_kind} rejects y and group_by")
        if x_scale != "linear" or y_scale != "linear":
            raise VisualizationError("x_scale and y_scale are valid only for xy, pv, and ts")
    if normalized_kind == "property_curves":
        if color_scale != "linear":
            raise VisualizationError("color_scale is valid only for property_heatmap")
        return plot_property_curves(
            source,
            property_name=cast(str, property_name),
            x=x,
            fluids=fluids,
            filters=filters,
            value_scale=value_scale,
            output=output,
            show=show,
            saturation_coordinate=saturation_coordinate,
        )
    if x is not None and normalized_kind == "property_heatmap":
        raise VisualizationError("property_heatmap uses mode-defined axes and rejects x")
    if normalized_kind == "property_heatmap":
        if value_scale != "linear":
            raise VisualizationError("value_scale is valid only for property_curves")
        return plot_property_heatmap(
            source,
            property_name=cast(str, property_name),
            fluids=fluids,
            filters=filters,
            color_scale=color_scale,
            output=output,
            show=show,
            saturation_coordinate=saturation_coordinate,
        )
    if value_scale != "linear" or color_scale != "linear":
        raise VisualizationError("value_scale and color_scale are valid only for property plots")
    if normalized_kind == "xy":
        if property_name is not None:
            raise VisualizationError("xy rejects property_name")
        if x is None or y is None:
            raise VisualizationError("xy requires both x and y")
        return plot_xy(
            source,
            x=x,
            y=y,
            group_by=group_by,
            fluids=fluids,
            filters=filters,
            x_scale=x_scale,
            y_scale=y_scale,
            output=output,
            show=show,
            saturation_coordinate=saturation_coordinate,
        )
    if any(value is not None for value in (property_name, x, y, group_by)):
        raise VisualizationError(
            f"{normalized_kind} uses fixed axes and rejects property, x, y, and group_by"
        )
    return plot_thermodynamic_diagram(
        source,
        kind=normalized_kind,
        fluids=fluids,
        filters=filters,
        x_scale=x_scale,
        y_scale=y_scale,
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


def plot_xy(
    source: str | Path,
    *,
    x: str,
    y: str,
    group_by: str | None = None,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    x_scale: PlotScale = "linear",
    y_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    try:
        request = xy_plot_request(
            x_field=x,
            y_field=y,
            group_by=group_by,
            fluids=tuple(fluids or ()),
            filters=tuple(filters),
            x_scale=x_scale,
            y_scale=y_scale,
            saturation_coordinate=saturation_coordinate,
            output_format=_output_format(output),
        )
    except (ValidationError, ValueError) as exc:
        raise VisualizationError(str(exc)) from exc
    return _plot_axes_request(
        source,
        request=request,
        x_field=x,
        y_field=y,
        fluids=fluids,
        filters=filters,
        output=output,
        show=show,
        saturation_coordinate=saturation_coordinate,
    )


def plot_thermodynamic_diagram(
    source: str | Path,
    *,
    kind: Literal["pv", "ts"],
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
    x_scale: PlotScale = "linear",
    y_scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    try:
        request = thermodynamic_diagram_request(
            kind=kind,
            fluids=tuple(fluids or ()),
            filters=tuple(filters),
            x_scale=x_scale,
            y_scale=y_scale,
            saturation_coordinate=saturation_coordinate,
            output_format=_output_format(output),
        )
    except (ValidationError, ValueError) as exc:
        raise VisualizationError(str(exc)) from exc
    return _plot_axes_request(
        source,
        request=request,
        x_field="specific_volume" if kind == "pv" else "specific_entropy",
        y_field="pressure" if kind == "pv" else "temperature",
        fluids=fluids,
        filters=filters,
        output=output,
        show=show,
        saturation_coordinate=saturation_coordinate,
    )


def _plot_property(
    source: str | Path,
    *,
    kind: Literal["property_curves", "property_heatmap"],
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
    return _finalize_plot(
        mpl=mpl,
        rendered=rendered,
        plot_source=plot_source,
        request=request,
        output=output,
        selected_fluids=selection.selected_fluids,
        property_field=property_field,
        valid_count=valid_count,
        excluded_count=excluded_count,
        filter_matches=selection.filter_matches,
        advisories=advisories,
        show=show,
    )


def _plot_axes_request(
    source: str | Path,
    *,
    request: PlotRequest,
    x_field: str,
    y_field: str,
    fluids: Sequence[str] | None,
    filters: Sequence[ExactFilter],
    output: str | Path | None,
    show: bool,
    saturation_coordinate: PlotCoordinate | None,
) -> PlotResult:
    plot_source = load_plot_source(
        source,
        saturation_coordinate=saturation_coordinate,
    )
    if request.kind == "ts":
        policy = (
            plot_source.metadata.get("reference_state_policy")
            if plot_source.metadata is not None
            else None
        )
        if not isinstance(policy, str) or not policy.strip():
            raise VisualizationError(
                "ts requires dataset metadata containing reference_state_policy"
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
    prepared, valid_count, excluded_count = _prepare_axes_frame(
        selection.frame,
        x_field=x_field,
        y_field=y_field,
    )
    valid = prepared.loc[prepared["_plot_valid"]]
    if valid.empty:
        raise VisualizationError("no valid axis values remain to plot")
    _validate_axis_scale(valid["_x_plot"], request.x_scale, x_field)
    _validate_axis_scale(valid["_y_plot"], request.y_scale, y_field)
    mpl = import_matplotlib()
    if request.kind == "xy":
        rendered = render_xy(
            mpl=mpl,
            plot_source=plot_source,
            frame=prepared,
            request=request,
            fluids=selection.selected_fluids,
            invalid_rows_excluded=excluded_count,
        )
    else:
        rendered = render_thermodynamic_diagram(
            mpl=mpl,
            plot_source=plot_source,
            frame=prepared,
            request=request,
            fluids=selection.selected_fluids,
            invalid_rows_excluded=excluded_count,
        )
    advisories = _layout_advisories(rendered, selection.selected_fluids)
    return _finalize_plot(
        mpl=mpl,
        rendered=rendered,
        plot_source=plot_source,
        request=request,
        output=output,
        selected_fluids=selection.selected_fluids,
        property_field=None,
        valid_count=valid_count,
        excluded_count=excluded_count,
        filter_matches=selection.filter_matches,
        advisories=advisories,
        show=show,
    )


def _finalize_plot(
    *,
    mpl: dict[str, Any],
    rendered: RenderedPlot,
    plot_source: PlotSource,
    request: PlotRequest,
    output: str | Path | None,
    selected_fluids: tuple[str, ...],
    property_field: FieldDefinition | None,
    valid_count: int,
    excluded_count: int,
    filter_matches: tuple[FilterMatch, ...],
    advisories: tuple[Advisory, ...],
    show: bool,
) -> PlotResult:
    visualization_request_id = request_id((request,))
    image_path, sidecar_path = export_figure(
        rendered=rendered,
        plot_source=plot_source,
        output=output,
        selected_fluids=selected_fluids,
        property_field=property_field,
        valid_rows_plotted=valid_count,
        invalid_rows_excluded=excluded_count,
        matplotlib_version=mpl["matplotlib"].__version__,
        request=request,
        visualization_request_id=visualization_request_id,
        filter_matches=filter_matches,
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
        selected_fluids=selected_fluids,
        property_name=property_field.name if property_field is not None else None,
        kind=request.kind,
        scale=(
            request.value_scale
            if request.kind == "property_curves"
            else request.color_scale
            if request.kind == "property_heatmap"
            else request.y_scale
        ),
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
    values, supported = numeric_field_values(selected, property_field.name)
    selected["_plot_value"] = values
    selected["_plot_valid"] = row_valid_mask(selected) & supported
    selected.loc[~selected["_plot_valid"], "_plot_value"] = np.nan
    valid_count = int(selected["_plot_valid"].sum())
    return selected, valid_count, len(selected) - valid_count


def _prepare_axes_frame(
    frame: pd.DataFrame,
    *,
    x_field: str,
    y_field: str,
) -> tuple[pd.DataFrame, int, int]:
    selected = frame.copy()
    x_values, x_supported = numeric_field_values(selected, x_field)
    y_values, y_supported = numeric_field_values(selected, y_field)
    valid = row_valid_mask(selected) & x_supported & y_supported
    selected["_plot_valid"] = valid
    selected["_x_plot"] = x_values.where(valid, np.nan)
    selected["_y_plot"] = y_values.where(valid, np.nan)
    valid_count = int(valid.sum())
    return selected, valid_count, len(selected) - valid_count


def _validate_axis_scale(
    values: pd.Series,
    scale: PlotScale,
    field: str,
) -> None:
    if scale == "log" and bool((values <= 0.0).any()):
        raise VisualizationError(f"log scaling requires positive {field} values")


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
