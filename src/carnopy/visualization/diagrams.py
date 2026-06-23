from __future__ import annotations

import numpy as np
import pandas as pd

from carnopy.visualization.models import PlotSource, RenderedPlot, VisualizationError
from carnopy.visualization.requests import PlotRequest
from carnopy.visualization.series import (
    SeriesData,
    level_mask,
    ordered_levels,
    render_series_facets,
    required_saturation_coordinate,
    series_from_frame,
    series_label,
)


def render_thermodynamic_diagram(
    *,
    mpl: dict[str, object],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
    fluids: tuple[str, ...],
    invalid_rows_excluded: int,
) -> RenderedPlot:
    if request.kind == "pv":
        x_field, y_field = "specific_volume", "pressure"
        title = "Pressure-specific-volume diagram"
        reference_dependent = False
    elif request.kind == "ts":
        x_field, y_field = "specific_entropy", "temperature"
        title = "Temperature-specific-entropy diagram"
        reference_dependent = True
    else:
        raise VisualizationError(f"unsupported thermodynamic diagram {request.kind!r}")
    facet_series = {
        fluid: _thermodynamic_series(
            plot_source=plot_source,
            frame=frame.loc[frame["fluid"] == fluid].copy(),
            request=request,
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
        title=title,
        invalid_rows_excluded=invalid_rows_excluded,
        reference_dependent=reference_dependent,
        group_by=_thermodynamic_group_field(plot_source, request.kind),
        path_coordinate=_thermodynamic_path_field(plot_source, request.kind),
    )


def _thermodynamic_series(
    *,
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
) -> list[SeriesData]:
    kind = request.kind
    if plot_source.mode == "property_table":
        group_field = "temperature" if kind == "pv" else "pressure"
        ordering_field = "pressure" if kind == "pv" else "temperature"
        return [
            series_from_frame(
                plot_source=plot_source,
                frame=frame.loc[level_mask(frame, group_field, level)].copy(),
                label=series_label(plot_source, request, group_field, level),
                ordering_field=ordering_field,
                split_phase=True,
                markers_only=False,
            )
            for level in ordered_levels(plot_source, frame, group_field)
        ]
    if plot_source.mode == "saturation_table":
        coordinate = required_saturation_coordinate(plot_source)
        return [
            series_from_frame(
                plot_source=plot_source,
                frame=frame.loc[level_mask(frame, "saturation_endpoint", endpoint)].copy(),
                label=str(endpoint).replace("_", " "),
                ordering_field=coordinate,
                split_phase=False,
                markers_only=False,
            )
            for endpoint in ordered_levels(
                plot_source,
                frame,
                "saturation_endpoint",
            )
        ]
    if plot_source.mode == "vapor_mass_fraction_table":
        return _vapor_quality_series(plot_source, frame, request)
    raise VisualizationError(f"unsupported thermodynamic diagram mode {plot_source.mode!r}")


def _vapor_quality_series(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
) -> list[SeriesData]:
    coordinate = required_saturation_coordinate(plot_source)
    result = [
        series_from_frame(
            plot_source=plot_source,
            frame=frame.loc[level_mask(frame, coordinate, level)].copy(),
            label=(f"{series_label(plot_source, request, coordinate, level)} vapor-fraction line"),
            ordering_field="vapor_mass_fraction",
            split_phase=False,
            markers_only=False,
        )
        for level in ordered_levels(plot_source, frame, coordinate)
    ]
    quality_values = pd.to_numeric(frame["vapor_mass_fraction"], errors="coerce")
    for quality in (0.0, 1.0):
        if bool(
            np.isclose(
                quality_values,
                quality,
                rtol=1e-12,
                atol=1e-12,
            ).any()
        ):
            result.append(
                series_from_frame(
                    plot_source=plot_source,
                    frame=frame.loc[level_mask(frame, "vapor_mass_fraction", quality)].copy(),
                    label=rf"$x_{{\mathrm{{vap}}}}$ = {quality:.0f} boundary",
                    ordering_field=coordinate,
                    split_phase=False,
                    markers_only=False,
                )
            )
    return result


def _thermodynamic_group_field(plot_source: PlotSource, kind: str) -> str:
    if plot_source.mode == "property_table":
        return "temperature" if kind == "pv" else "pressure"
    if plot_source.mode == "saturation_table":
        return "saturation_endpoint"
    return required_saturation_coordinate(plot_source)


def _thermodynamic_path_field(plot_source: PlotSource, kind: str) -> str:
    if plot_source.mode == "property_table":
        return "pressure" if kind == "pv" else "temperature"
    if plot_source.mode == "saturation_table":
        return required_saturation_coordinate(plot_source)
    return "vapor_mass_fraction"
