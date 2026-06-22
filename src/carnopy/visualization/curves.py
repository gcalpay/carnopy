from __future__ import annotations

from dataclasses import dataclass
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
from carnopy.visualization.render import create_faceted_figure, finish_figure
from carnopy.visualization.requests import PlotRequest

LINE_STYLES = ("-", "--", "-.", ":")


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    x_values: np.ndarray[Any, np.dtype[np.float64]]
    y_values: np.ndarray[Any, np.dtype[np.float64]]
    sample_count: int
    gap_count: int


def render_property_curves(
    *,
    mpl: dict[str, Any],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
    property_field: FieldDefinition,
    fluids: tuple[str, ...],
    invalid_rows_excluded: int,
) -> RenderedPlot:
    x_field, series_field = _curve_fields(plot_source, request)
    x_definition = get_field(x_field)
    x_unit = _display_unit(plot_source, x_field)
    series_unit = _display_unit(plot_source, series_field)
    figure, axes = create_faceted_figure(mpl=mpl, fluids=fluids)
    facet_series: dict[str, list[SeriesSpec]] = {}
    maximum_series = 0
    for axis, fluid in zip(axes, fluids, strict=True):
        fluid_frame = frame.loc[frame["fluid"] == fluid].copy()
        series = _series_for_fluid(
            plot_source=plot_source,
            frame=fluid_frame,
            x_field=x_field,
            series_field=series_field,
        )
        facet_series[fluid] = series
        maximum_series = max(maximum_series, len(series))
        colors = _series_colors(mpl, len(series))
        for index, item in enumerate(series):
            axis.plot(
                item.x_values,
                item.y_values,
                color=colors[index % len(colors)],
                linestyle=LINE_STYLES[(index // len(colors)) % len(LINE_STYLES)],
                marker="o",
                markersize=4.0,
                linewidth=1.2,
                label=item.label,
            )
        axis.set_xlabel(x_definition.label_for_unit(x_unit))
        axis.set_ylabel(property_field.display_label)
        axis.minorticks_on()
        axis.tick_params(which="both", direction="in", top=True, right=True)
        axis.grid(True, which="major", color="0.80", linewidth=0.6)
        axis.grid(True, which="minor", color="0.90", linewidth=0.4, alpha=0.8)
        if request.value_scale == "log":
            axis.set_yscale("log")
        if series:
            axis.legend(
                title=get_field(series_field).label_for_unit(series_unit),
                fontsize=7,
                title_fontsize=7,
                loc="best",
            )
    finish_figure(
        figure=figure,
        axes=axes,
        plot_source=plot_source,
        frame=frame,
        fluids=fluids,
        title=f"{property_field.label} — sampled property curves",
        invalid_rows_excluded=invalid_rows_excluded,
        reference_dependent=_reference_dependent(property_field),
    )
    series_summary = {
        fluid: [
            {
                "label": item.label,
                "sample_count": item.sample_count,
                "gap_count": item.gap_count,
                "markers_only": False,
            }
            for item in items
        ]
        for fluid, items in facet_series.items()
    }
    finite_x = [
        float(value)
        for items in facet_series.values()
        for item in items
        for value in item.x_values
        if np.isfinite(value)
    ]
    return RenderedPlot(
        figure=figure,
        axes={
            "x": _axis_metadata(x_field, x_unit),
            "y": _axis_metadata(property_field.name, property_field.unit),
            "series": _axis_metadata(series_field, series_unit),
            "color": None,
        },
        scales={"x": "linear", "y": request.value_scale, "color": None},
        settings={
            "figure_size_inches": [6.4 * len(fluids), 4.8],
            "constrained_layout": True,
            "palette": "tab10" if maximum_series <= 10 else "tab20",
            "line_styles": list(LINE_STYLES),
            "marker": "o",
            "major_grid": True,
            "minor_grid": True,
            "smoothing": False,
            "x_range": [min(finite_x), max(finite_x)] if finite_x else None,
        },
        series_or_cells={
            "representation": "sampled_series",
            "series": series_summary,
        },
    )


def _curve_fields(plot_source: PlotSource, request: PlotRequest) -> tuple[str, str]:
    if plot_source.mode == "property_table":
        if request.x_field not in {"temperature", "pressure"}:
            raise VisualizationError(
                "property_table property-curves requires --x temperature or --x pressure"
            )
        return (
            request.x_field,
            "pressure" if request.x_field == "temperature" else "temperature",
        )
    if request.x_field is not None:
        raise VisualizationError(
            f"{plot_source.mode} property-curves determines its x axis from mode metadata; "
            "do not supply --x"
        )
    coordinate = _required_saturation_coordinate(plot_source)
    if plot_source.mode == "saturation_table":
        return coordinate, "saturation_endpoint"
    if plot_source.mode == "vapor_mass_fraction_table":
        return "vapor_mass_fraction", coordinate
    raise VisualizationError(f"unsupported property-curves mode {plot_source.mode!r}")


def _series_for_fluid(
    *,
    plot_source: PlotSource,
    frame: pd.DataFrame,
    x_field: str,
    series_field: str,
) -> list[SeriesSpec]:
    x_levels = _ordered_levels(plot_source, frame, x_field)
    series_levels = _ordered_levels(plot_source, frame, series_field)
    x_display = _display_values(plot_source, x_field, x_levels)
    result: list[SeriesSpec] = []
    for level in series_levels:
        group = frame.loc[_level_mask(frame, series_field, level)].copy()
        if group.empty:
            continue
        duplicate = group.duplicated(subset=[get_field(x_field).column], keep=False)
        if bool(duplicate.any()):
            raise VisualizationError(
                f"property-curves found duplicate {x_field} samples for {series_field}={level!r}"
            )
        y_values: list[float] = []
        phases: list[str | None] = []
        sample_count = 0
        for x_level in x_levels:
            matches = group.loc[_level_mask(group, x_field, x_level)]
            if matches.empty:
                y_values.append(float("nan"))
                phases.append(None)
                continue
            row = matches.iloc[0]
            if bool(row["_plot_valid"]):
                y_values.append(float(row["_plot_value"]))
                phases.append(str(row.get("phase")) if pd.notna(row.get("phase")) else None)
                sample_count += 1
            else:
                y_values.append(float("nan"))
                phases.append(None)
        plotted_x, plotted_y = _split_phase_changes(
            np.asarray(x_display, dtype=float),
            np.asarray(y_values, dtype=float),
            phases,
            enabled=plot_source.mode == "property_table",
        )
        label = _series_label(plot_source, series_field, level)
        gap_count = int(np.isnan(np.asarray(y_values, dtype=float)).sum())
        result.append(
            SeriesSpec(
                label=label,
                x_values=plotted_x,
                y_values=plotted_y,
                sample_count=sample_count,
                gap_count=gap_count,
            )
        )
    return result


def _split_phase_changes(
    x_values: np.ndarray[Any, np.dtype[np.float64]],
    y_values: np.ndarray[Any, np.dtype[np.float64]],
    phases: list[str | None],
    *,
    enabled: bool,
) -> tuple[
    np.ndarray[Any, np.dtype[np.float64]],
    np.ndarray[Any, np.dtype[np.float64]],
]:
    if not enabled or len(x_values) < 2:
        return x_values, y_values
    split_x: list[float] = []
    split_y: list[float] = []
    previous_phase: str | None = None
    previous_valid = False
    for x_value, y_value, phase in zip(x_values, y_values, phases, strict=True):
        current_valid = bool(np.isfinite(y_value))
        if (
            previous_valid
            and current_valid
            and previous_phase is not None
            and phase is not None
            and phase != previous_phase
        ):
            split_x.append(float("nan"))
            split_y.append(float("nan"))
        split_x.append(float(x_value))
        split_y.append(float(y_value))
        previous_phase = phase
        previous_valid = current_valid
    return np.asarray(split_x), np.asarray(split_y)


def _ordered_levels(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    field: str,
) -> list[float | str]:
    if field == "saturation_endpoint":
        preferred = ["saturated_liquid", "saturated_vapor"]
        available = frame[get_field(field).column].dropna().astype(str).unique().tolist()
        return [value for value in preferred if value in available]
    metadata = plot_source.metadata
    if metadata is not None:
        sampling = metadata.get("sampling")
        materialized = sampling.get("materialized_si") if isinstance(sampling, dict) else None
        values = materialized.get(field) if isinstance(materialized, dict) else None
        if isinstance(values, list):
            available = pd.to_numeric(
                frame[get_field(field).column],
                errors="coerce",
            ).dropna()
            return [
                float(value)
                for value in values
                if bool(
                    np.isclose(
                        available.to_numpy(dtype=float),
                        float(value),
                        rtol=1e-12,
                        atol=1e-12,
                    ).any()
                )
            ]
    ordered = frame.sort_values("case_id", kind="stable")
    column = get_field(field).column
    return _unique_preserving_order(ordered[column].dropna().tolist())


def _unique_preserving_order(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _level_mask(frame: pd.DataFrame, field: str, value: float | str) -> pd.Series:
    series = frame[get_field(field).column]
    if isinstance(value, str):
        return series.astype("string").eq(value).fillna(False)
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.Series(
        np.isclose(numeric.to_numpy(dtype=float), float(value), rtol=1e-12, atol=1e-12),
        index=frame.index,
    )


def _display_values(
    plot_source: PlotSource,
    field: str,
    values: list[float | str],
) -> list[float | str]:
    if field not in {"temperature", "pressure"}:
        return values
    unit = display_unit_for_field(plot_source, cast(PlotCoordinate, field))
    converter = UNITS[unit].from_si
    return [converter(float(value)) for value in values]


def _display_unit(plot_source: PlotSource, field: str) -> str | None:
    if field in {"temperature", "pressure"}:
        return display_unit_for_field(plot_source, cast(PlotCoordinate, field))
    return get_field(field).unit


def _series_label(plot_source: PlotSource, field: str, value: float | str) -> str:
    if field == "saturation_endpoint":
        return str(value).replace("_", " ")
    display = _display_values(plot_source, field, [value])[0]
    return _format_value(display)


def _format_value(value: float | str) -> str:
    if isinstance(value, str):
        return value
    return format(float(value), ".6g")


def _series_colors(mpl: dict[str, Any], count: int) -> list[Any]:
    palette_name = "tab10" if count <= 10 else "tab20"
    return list(mpl["pyplot"].get_cmap(palette_name).colors)


def _required_saturation_coordinate(plot_source: PlotSource) -> str:
    if plot_source.saturation_coordinate is None:
        raise VisualizationError(
            f"{plot_source.mode} plotting requires metadata that identifies the sampled "
            "saturation coordinate"
        )
    return plot_source.saturation_coordinate


def _axis_metadata(field: str, unit: str | None) -> dict[str, object]:
    definition = get_field(field)
    return {"field": field, "column": definition.column, "unit": unit}


def _reference_dependent(field: FieldDefinition) -> bool:
    if field.required_property is None:
        return False
    from carnopy.domain.properties import PROPERTY_REGISTRY

    definition = PROPERTY_REGISTRY.get(field.required_property)
    return bool(definition is not None and definition.reference_dependent)
