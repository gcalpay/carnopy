from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd

from carnopy.visualization.fields import get_field
from carnopy.visualization.models import PlotSource, RenderedPlot, VisualizationError
from carnopy.visualization.render import create_faceted_figure, finish_figure
from carnopy.visualization.requests import PlotRequest

LINE_STYLES = ("-", "--", "-.", ":")


@dataclass(frozen=True)
class SeriesData:
    label: str
    x_values: np.ndarray[Any, np.dtype[np.float64]]
    y_values: np.ndarray[Any, np.dtype[np.float64]]
    sample_count: int
    gap_count: int
    markers_only: bool = False


def render_series_facets(
    *,
    mpl: dict[str, Any],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    request: PlotRequest,
    fluids: tuple[str, ...],
    facet_series: dict[str, list[SeriesData]],
    x_field: str,
    y_field: str,
    title: str,
    invalid_rows_excluded: int,
    reference_dependent: bool,
    group_by: str | None,
    path_coordinate: str | None,
) -> RenderedPlot:
    figure, axes = create_faceted_figure(mpl=mpl, fluids=fluids)
    maximum_series = max((len(items) for items in facet_series.values()), default=0)
    colors = _series_colors(mpl, maximum_series)
    for axis, fluid in zip(axes, fluids, strict=True):
        for index, item in enumerate(facet_series[fluid]):
            axis.plot(
                item.x_values,
                item.y_values,
                color=colors[index % len(colors)],
                linestyle=(
                    "None"
                    if item.markers_only
                    else LINE_STYLES[(index // len(colors)) % len(LINE_STYLES)]
                ),
                marker="o",
                markersize=4.0,
                linewidth=1.2,
                label=item.label,
            )
        axis.set_xlabel(get_field(x_field).display_label)
        axis.set_ylabel(get_field(y_field).display_label)
        axis.set_xscale(request.x_scale)
        axis.set_yscale(request.y_scale)
        axis.minorticks_on()
        axis.tick_params(which="both", direction="in", top=True, right=True)
        axis.grid(True, which="major", color="0.80", linewidth=0.6)
        axis.grid(True, which="minor", color="0.90", linewidth=0.4, alpha=0.8)
        if facet_series[fluid] and (
            len(facet_series[fluid]) > 1 or facet_series[fluid][0].label != "samples"
        ):
            axis.legend(fontsize=7, title_fontsize=7, loc="best")
    finish_figure(
        figure=figure,
        axes=axes,
        plot_source=plot_source,
        frame=frame,
        fluids=fluids,
        title=title,
        invalid_rows_excluded=invalid_rows_excluded,
        reference_dependent=reference_dependent,
    )
    finite_x = _finite_series_values(facet_series, axis="x")
    finite_y = _finite_series_values(facet_series, axis="y")
    return RenderedPlot(
        figure=figure,
        axes={
            "x": axis_metadata(x_field),
            "y": axis_metadata(y_field),
            "series": axis_metadata(group_by) if group_by is not None else None,
            "color": None,
        },
        scales={"x": request.x_scale, "y": request.y_scale, "color": None},
        settings={
            "figure_size_inches": [6.4 * len(fluids), 4.8],
            "constrained_layout": True,
            "palette": "tab10" if maximum_series <= 10 else "tab20",
            "line_styles": list(LINE_STYLES),
            "marker": "o",
            "major_grid": True,
            "minor_grid": True,
            "smoothing": False,
            "group_by": group_by,
            "path_coordinate": path_coordinate,
            "x_range": [min(finite_x), max(finite_x)] if finite_x else None,
            "y_range": [min(finite_y), max(finite_y)] if finite_y else None,
        },
        series_or_cells={
            "representation": "sampled_series",
            "series": {
                fluid: [
                    {
                        "label": item.label,
                        "sample_count": item.sample_count,
                        "gap_count": item.gap_count,
                        "markers_only": item.markers_only,
                    }
                    for item in items
                ]
                for fluid, items in facet_series.items()
            },
        },
    )


def series_from_frame(
    *,
    plot_source: PlotSource,
    frame: pd.DataFrame,
    label: str,
    ordering_field: str | None,
    split_phase: bool,
    markers_only: bool,
) -> SeriesData:
    ordered = ordered_frame(plot_source, frame, ordering_field)
    if ordering_field is not None:
        column = get_field(ordering_field).column
        duplicate = ordered.duplicated(subset=[column], keep=False)
        if bool(duplicate.any()):
            raise VisualizationError(
                f"series {label!r} contains duplicate {ordering_field} levels; "
                "an additional grouping choice is required"
            )
    x_values = ordered["_x_plot"].to_numpy(dtype=float)
    y_values = ordered["_y_plot"].to_numpy(dtype=float)
    if split_phase:
        x_values, y_values = split_phase_changes(
            x_values,
            y_values,
            ordered["phase"].astype("string").tolist(),
        )
    return SeriesData(
        label=label,
        x_values=x_values,
        y_values=y_values,
        sample_count=int(ordered["_plot_valid"].sum()),
        gap_count=int((~ordered["_plot_valid"]).sum()),
        markers_only=markers_only,
    )


def ordered_frame(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    ordering_field: str | None,
) -> pd.DataFrame:
    if ordering_field is None:
        return cast(pd.DataFrame, frame.sort_values("case_id", kind="stable"))
    levels = ordered_levels(plot_source, frame, ordering_field)
    rank = {_canonical_level(level): index for index, level in enumerate(levels)}
    ordered = frame.copy()
    ordered["_series_order"] = ordered[get_field(ordering_field).column].map(
        lambda value: rank.get(_canonical_level(value), len(rank))
    )
    return cast(
        pd.DataFrame,
        ordered.sort_values(["_series_order", "case_id"], kind="stable"),
    )


def ordered_levels(
    plot_source: PlotSource,
    frame: pd.DataFrame,
    field: str,
) -> list[float | str]:
    if field == "saturation_endpoint":
        available = frame["saturation_endpoint"].dropna().astype(str).unique().tolist()
        return [value for value in ("saturated_liquid", "saturated_vapor") if value in available]
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
    values = ordered[get_field(field).column].dropna().tolist()
    result: list[float | str] = []
    for value in values:
        canonical = _canonical_level(value)
        if all(_canonical_level(existing) != canonical for existing in result):
            result.append(float(value) if _is_numeric(value) else str(value))
    return result


def level_mask(
    frame: pd.DataFrame,
    field: str,
    value: float | str,
) -> pd.Series:
    series = frame[get_field(field).column]
    if isinstance(value, str):
        return series.astype("string").eq(value).fillna(False)
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.Series(
        np.isclose(
            numeric.to_numpy(dtype=float),
            float(value),
            rtol=1e-12,
            atol=1e-12,
        ),
        index=frame.index,
    )


def series_label(field: str, value: float | str) -> str:
    if isinstance(value, str):
        return value.replace("_", " ")
    unit = get_field(field).unit
    suffix = f" {unit}" if unit not in (None, "1") else ""
    return f"{get_field(field).symbol or field} = {float(value):.6g}{suffix}"


def required_saturation_coordinate(plot_source: PlotSource) -> str:
    if plot_source.saturation_coordinate is None:
        raise VisualizationError(
            f"{plot_source.mode} plotting requires metadata or "
            "--saturation-coordinate to identify the sampled saturation coordinate"
        )
    return plot_source.saturation_coordinate


def axis_metadata(field: str | None) -> dict[str, object] | None:
    if field is None:
        return None
    definition = get_field(field)
    return {
        "field": field,
        "column": definition.column,
        "unit": definition.unit,
    }


def split_phase_changes(
    x_values: np.ndarray[Any, np.dtype[np.float64]],
    y_values: np.ndarray[Any, np.dtype[np.float64]],
    phases: list[str],
) -> tuple[
    np.ndarray[Any, np.dtype[np.float64]],
    np.ndarray[Any, np.dtype[np.float64]],
]:
    split_x: list[float] = []
    split_y: list[float] = []
    previous_phase: str | None = None
    previous_valid = False
    for x_value, y_value, phase_value in zip(
        x_values,
        y_values,
        phases,
        strict=True,
    ):
        phase = None if pd.isna(phase_value) else str(phase_value)
        current_valid = bool(np.isfinite(x_value) and np.isfinite(y_value))
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


def _finite_series_values(
    facet_series: dict[str, list[SeriesData]],
    *,
    axis: str,
) -> list[float]:
    values: list[float] = []
    for items in facet_series.values():
        for item in items:
            source = item.x_values if axis == "x" else item.y_values
            values.extend(float(value) for value in source if np.isfinite(value))
    return values


def _series_colors(mpl: dict[str, Any], count: int) -> list[Any]:
    palette_name = "tab10" if count <= 10 else "tab20"
    return list(mpl["pyplot"].get_cmap(palette_name).colors)


def _canonical_level(value: object) -> str:
    if _is_numeric(value):
        return format(float(str(value)), ".15g")
    return str(value)


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating))
