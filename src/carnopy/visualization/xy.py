from __future__ import annotations

import pandas as pd

from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.visualization.fields import get_field
from carnopy.visualization.models import PlotSource, RenderedPlot, VisualizationError
from carnopy.visualization.requests import PlotRequest
from carnopy.visualization.selection import GroupingResolution, resolve_group_by
from carnopy.visualization.series import (
    SeriesData,
    level_mask,
    ordered_levels,
    render_series_facets,
    required_saturation_coordinate,
    series_from_frame,
    series_label,
)

SAMPLING_FIELDS_BY_MODE = {
    "property_table": ("temperature", "pressure"),
    "saturation_table": ("temperature", "pressure"),
    "vapor_mass_fraction_table": (
        "temperature",
        "pressure",
        "vapor_mass_fraction",
    ),
}


def render_xy(
    *,
    mpl: dict[str, object],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
    fluids: tuple[str, ...],
    invalid_rows_excluded: int,
) -> RenderedPlot:
    if request.x_field is None or request.y_field is None:
        raise VisualizationError("xy requires both x and y fields")
    x_field = request.x_field
    y_field = request.y_field
    sampling_fields = _sampling_fields(plot_source)
    resolution = _xy_grouping(
        plot_source,
        frame,
        x_field=x_field,
        y_field=y_field,
        sampling_fields=sampling_fields,
        requested=request.group_by,
    )
    facet_series = {
        fluid: _generic_xy_series(
            plot_source=plot_source,
            frame=frame.loc[frame["fluid"] == fluid].copy(),
            x_field=x_field,
            y_field=y_field,
            sampling_fields=sampling_fields,
            resolution=resolution,
        )
        for fluid in fluids
    }
    return render_series_facets(
        mpl=mpl,
        plot_source=plot_source,
        frame=frame,
        request=request,
        fluids=fluids,
        facet_series=facet_series,
        x_field=x_field,
        y_field=y_field,
        title=f"{get_field(y_field).label} versus {get_field(x_field).label}",
        invalid_rows_excluded=invalid_rows_excluded,
        reference_dependent=_field_reference_dependent(x_field)
        or _field_reference_dependent(y_field),
        group_by=resolution.group_by,
        path_coordinate=resolution.varying_coordinate,
    )


def _xy_grouping(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    *,
    x_field: str,
    y_field: str,
    sampling_fields: tuple[str, ...],
    requested: str | None,
) -> GroupingResolution:
    if plot_source.mode == "saturation_table":
        if requested not in (None, "saturation_endpoint"):
            raise VisualizationError(
                "saturation_table xy plots must group by saturation_endpoint "
                "to keep liquid and vapor branches separate"
            )
        coordinate = required_saturation_coordinate(plot_source)
        varying = (
            coordinate
            if coordinate not in {x_field, y_field}
            and frame[get_field(coordinate).column].nunique(dropna=True) > 1
            else None
        )
        return GroupingResolution(
            group_by="saturation_endpoint",
            varying_coordinate=varying,
        )
    return resolve_group_by(
        frame,
        axis_fields=(x_field, y_field),
        sampling_fields=sampling_fields,
        requested=requested,
    )


def _generic_xy_series(
    *,
    plot_source: PlotSource,
    frame: pd.DataFrame,
    x_field: str,
    y_field: str,
    sampling_fields: tuple[str, ...],
    resolution: GroupingResolution,
) -> list[SeriesData]:
    group_field = resolution.group_by
    if group_field is None:
        return [
            series_from_frame(
                plot_source=plot_source,
                frame=frame,
                label="samples",
                ordering_field=resolution.varying_coordinate,
                split_phase=plot_source.mode == "property_table",
                markers_only=resolution.varying_coordinate is None,
            )
        ]
    series: list[SeriesData] = []
    for level in ordered_levels(plot_source, frame, group_field):
        group = frame.loc[level_mask(frame, group_field, level)].copy()
        if group.empty:
            continue
        ordering_field = resolution.varying_coordinate or _axis_sampling_field(
            group,
            axis_fields=(x_field, y_field),
            sampling_fields=sampling_fields,
        )
        series.append(
            series_from_frame(
                plot_source=plot_source,
                frame=group,
                label=series_label(group_field, level),
                ordering_field=ordering_field,
                split_phase=plot_source.mode == "property_table",
                markers_only=ordering_field is None,
            )
        )
    return series


def _sampling_fields(plot_source: PlotSource) -> tuple[str, ...]:
    if plot_source.metadata is not None:
        sampling = plot_source.metadata.get("sampling")
        materialized = sampling.get("materialized_si") if isinstance(sampling, dict) else None
        if isinstance(materialized, dict):
            return tuple(
                field
                for field in ("temperature", "pressure", "vapor_mass_fraction")
                if field in materialized
            )
    if plot_source.mode == "saturation_table":
        return (required_saturation_coordinate(plot_source),)
    if plot_source.mode == "vapor_mass_fraction_table":
        return (
            required_saturation_coordinate(plot_source),
            "vapor_mass_fraction",
        )
    return SAMPLING_FIELDS_BY_MODE[plot_source.mode]


def _axis_sampling_field(
    frame: pd.DataFrame,
    *,
    axis_fields: tuple[str, str],
    sampling_fields: tuple[str, ...],
) -> str | None:
    candidates = [
        field
        for field in sampling_fields
        if field in axis_fields
        and get_field(field).column in frame.columns
        and frame[get_field(field).column].nunique(dropna=True) > 1
    ]
    return candidates[0] if len(candidates) == 1 else None


def _field_reference_dependent(field: str) -> bool:
    definition = get_field(field)
    if definition.required_property is None:
        return False
    property_definition = PROPERTY_REGISTRY.get(definition.required_property)
    return bool(property_definition is not None and property_definition.reference_dependent)
