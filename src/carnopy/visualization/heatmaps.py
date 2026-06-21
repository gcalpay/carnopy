from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from carnopy.domain.units import UNITS
from carnopy.visualization.fields import FieldDefinition, get_field
from carnopy.visualization.io import display_unit_for_field
from carnopy.visualization.models import (
    PlotCoordinate,
    PlotSource,
    RenderedPlot,
    VisualizationError,
)
from carnopy.visualization.render import (
    DEFAULT_COLORMAP,
    create_faceted_figure,
    finish_figure,
    normalization,
)
from carnopy.visualization.requests import PlotRequest

HEATMAP_DIMENSION_ERROR = (
    "property_heatmap requires at least two unique x values and two unique y values\n"
    "to construct non-interpolated cell boundaries. Use property-curves or xy for\n"
    "one-dimensional data, or generate a denser grid."
)
SATURATION_HEATMAP_ERROR = (
    "saturation_table does not support property_heatmap because it contains only\n"
    "q=0 and q=1 endpoint states. Use vapor_mass_fraction_table for quality-resolved maps."
)


def render_property_heatmap(
    *,
    mpl: dict[str, Any],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
    property_field: FieldDefinition,
    fluids: tuple[str, ...],
    invalid_rows_excluded: int,
) -> RenderedPlot:
    x_field, y_field = _heatmap_fields(plot_source, request)
    x_unit = _display_unit(plot_source, x_field)
    y_unit = _display_unit(plot_source, y_field)
    valid_values = frame.loc[frame["_plot_valid"], "_plot_value"]
    value_min = float(valid_values.min())
    value_max = float(valid_values.max())
    norm = normalization(
        mpl,
        value_min,
        value_max,
        scale=request.color_scale,
    )
    cmap = mpl["pyplot"].get_cmap(DEFAULT_COLORMAP)
    figure, axes = create_faceted_figure(mpl=mpl, fluids=fluids)
    cell_summaries: dict[str, dict[str, object]] = {}
    all_x_values: list[float] = []
    all_y_values: list[float] = []
    for axis, fluid in zip(axes, fluids, strict=True):
        fluid_frame = frame.loc[frame["fluid"] == fluid].copy()
        _reject_duplicate_cells(fluid_frame, x_field, y_field)
        x_values = _sorted_display_levels(plot_source, fluid_frame, x_field)
        y_values = _sorted_display_levels(plot_source, fluid_frame, y_field)
        if len(x_values) < 2 or len(y_values) < 2:
            raise VisualizationError(HEATMAP_DIMENSION_ERROR)
        all_x_values.extend(x_values)
        all_y_values.extend(y_values)
        x_column = get_field(x_field).column
        y_column = get_field(y_field).column
        fluid_frame["_x_display"] = _display_series(plot_source, fluid_frame, x_field)
        fluid_frame["_y_display"] = _display_series(plot_source, fluid_frame, y_field)
        pivot = fluid_frame.pivot(
            index="_y_display",
            columns="_x_display",
            values="_plot_value",
        ).reindex(index=y_values, columns=x_values)
        masked = np.ma.masked_invalid(pivot.to_numpy(dtype=float))
        axis.pcolormesh(
            _cell_boundaries(np.asarray(x_values, dtype=float)),
            _cell_boundaries(np.asarray(y_values, dtype=float)),
            masked,
            cmap=cmap,
            norm=norm,
            shading="flat",
        )
        valid_points = fluid_frame.loc[fluid_frame["_plot_valid"]]
        invalid_points = fluid_frame.loc[~fluid_frame["_plot_valid"]]
        axis.scatter(
            valid_points["_x_display"],
            valid_points["_y_display"],
            s=10,
            marker="o",
            facecolors="none",
            edgecolors="black",
            linewidths=0.45,
        )
        if not invalid_points.empty:
            axis.scatter(
                invalid_points["_x_display"],
                invalid_points["_y_display"],
                s=13,
                marker="x",
                color="black",
                linewidths=0.55,
            )
        axis.set_xlabel(get_field(x_field).label_for_unit(x_unit))
        axis.set_ylabel(get_field(y_field).label_for_unit(y_unit))
        axis.tick_params(which="both", direction="in", top=True, right=True)
        cell_summaries[fluid] = {
            "x_value_count": len(x_values),
            "y_value_count": len(y_values),
            "sampled_cell_count": len(fluid_frame),
            "masked_cell_count": int(np.ma.getmaskarray(masked).sum()),
            "x_column": x_column,
            "y_column": y_column,
        }
    scalar_mappable = mpl["ScalarMappable"](norm=norm, cmap=cmap)
    scalar_mappable.set_array([])
    colorbar = figure.colorbar(scalar_mappable, ax=axes)
    colorbar.set_label(property_field.display_label)
    finish_figure(
        figure=figure,
        axes=axes,
        plot_source=plot_source,
        frame=frame,
        fluids=fluids,
        title=f"{property_field.label} — sampled property heatmap",
        invalid_rows_excluded=invalid_rows_excluded,
        reference_dependent=_reference_dependent(property_field),
    )
    return RenderedPlot(
        figure=figure,
        axes={
            "x": _axis_metadata(x_field, x_unit),
            "y": _axis_metadata(y_field, y_unit),
            "series": None,
            "color": _axis_metadata(property_field.name, property_field.unit),
        },
        scales={"x": "linear", "y": "linear", "color": request.color_scale},
        settings={
            "figure_size_inches": [6.4 * len(fluids), 4.8],
            "constrained_layout": True,
            "colormap": DEFAULT_COLORMAP,
            "shading": "flat",
            "cell_boundary_policy": "adjacent_midpoints_with_half_spacing_endpoints",
            "interpolation": False,
            "sample_point_overlay": True,
            "invalid_marker": "x",
            "property_range": [value_min, value_max],
            "x_range": [min(all_x_values), max(all_x_values)],
            "y_range": [min(all_y_values), max(all_y_values)],
        },
        series_or_cells={
            "representation": "sampled_cells",
            "cells": cell_summaries,
        },
    )


def _heatmap_fields(plot_source: PlotSource, request: PlotRequest) -> tuple[str, str]:
    if request.x_field is not None:
        raise VisualizationError("property-heatmap uses mode-defined axes; do not supply --x")
    if plot_source.mode == "saturation_table":
        raise VisualizationError(SATURATION_HEATMAP_ERROR)
    if plot_source.mode == "property_table":
        return "temperature", "pressure"
    if plot_source.mode == "vapor_mass_fraction_table":
        coordinate = plot_source.saturation_coordinate
        if coordinate is None:
            raise VisualizationError(
                "vapor_mass_fraction_table property-heatmap requires metadata that "
                "identifies the sampled saturation coordinate"
            )
        return "vapor_mass_fraction", coordinate
    raise VisualizationError(f"unsupported property-heatmap mode {plot_source.mode!r}")


def _reject_duplicate_cells(frame: pd.DataFrame, x_field: str, y_field: str) -> None:
    duplicate = frame.duplicated(
        subset=[get_field(x_field).column, get_field(y_field).column],
        keep=False,
    )
    if bool(duplicate.any()):
        raise VisualizationError(
            f"property-heatmap found duplicate {x_field}/{y_field} cells; "
            "duplicate rows are not aggregated"
        )


def _sorted_display_levels(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    field: str,
) -> list[float]:
    values = _display_series(plot_source, frame, field)
    return sorted(float(value) for value in values.dropna().unique().tolist())


def _display_series(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    field: str,
) -> pd.Series:
    column = get_field(field).column
    numeric = pd.to_numeric(frame[column], errors="coerce")
    if field in {"temperature", "pressure"}:
        unit = display_unit_for_field(plot_source, cast(PlotCoordinate, field))
        converter = UNITS[unit].from_si
        return numeric.map(converter)
    return numeric


def _cell_boundaries(values: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, Any]:
    if len(values) < 2:
        raise VisualizationError(HEATMAP_DIMENSION_ERROR)
    midpoints = (values[:-1] + values[1:]) / 2.0
    first = values[0] - (values[1] - values[0]) / 2.0
    last = values[-1] + (values[-1] - values[-2]) / 2.0
    return np.concatenate(([first], midpoints, [last]))


def _display_unit(plot_source: PlotSource, field: str) -> str | None:
    if field in {"temperature", "pressure"}:
        return display_unit_for_field(plot_source, cast(PlotCoordinate, field))
    return get_field(field).unit


def _axis_metadata(field: str, unit: str | None) -> dict[str, object]:
    definition = get_field(field)
    return {"field": field, "column": definition.column, "unit": unit}


def _reference_dependent(field: FieldDefinition) -> bool:
    if field.required_property is None:
        return False
    from carnopy.domain.properties import PROPERTY_REGISTRY

    definition = PROPERTY_REGISTRY.get(field.required_property)
    return bool(definition is not None and definition.reference_dependent)
