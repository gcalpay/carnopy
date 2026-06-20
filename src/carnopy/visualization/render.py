from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from carnopy.visualization.models import (
    PlotCoordinate,
    PlotKind,
    PlotScale,
    PlotSource,
    VisualizationDependencyError,
    VisualizationError,
)

DEFAULT_COLORMAP = "viridis"
DEFAULT_CONTOUR_LEVELS = 20


def import_matplotlib() -> dict[str, Any]:
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import LogNorm, Normalize
    except ImportError as exc:
        raise VisualizationDependencyError(
            "Matplotlib visualization is unavailable. Install it with "
            '`python -m pip install -e ".[viz]"`.'
        ) from exc
    return {
        "matplotlib": matplotlib,
        "pyplot": plt,
        "ScalarMappable": ScalarMappable,
        "LogNorm": LogNorm,
        "Normalize": Normalize,
    }


def create_figure(
    *,
    mpl: dict[str, Any],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    property_name: str,
    property_column: str,
    property_unit: str,
    reference_dependent: bool,
    fluids: list[str],
    kind: PlotKind,
    scale: PlotScale,
    invalid_rows_excluded: int,
) -> tuple[Any, dict[str, Any]]:
    plt = mpl["pyplot"]
    figure, axes_array = plt.subplots(
        1,
        len(fluids),
        figsize=(6.4 * len(fluids), 4.8),
        squeeze=False,
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    axes = list(axes_array.ravel())
    if kind == "curves":
        settings = _plot_curves(
            mpl=mpl,
            figure=figure,
            axes=axes,
            frame=frame,
            fluids=fluids,
            property_name=property_name,
            property_unit=property_unit,
            coordinate=plot_source.coordinate,
            coordinate_unit=plot_source.coordinate_display_unit,
            scale=scale,
        )
    else:
        settings = _plot_contours(
            mpl=mpl,
            figure=figure,
            axes=axes,
            frame=frame,
            fluids=fluids,
            property_name=property_name,
            property_unit=property_unit,
            coordinate=plot_source.coordinate,
            coordinate_unit=plot_source.coordinate_display_unit,
            scale=scale,
        )
    for axis, fluid in zip(axes, fluids, strict=True):
        axis.set_title(fluid)
    figure.suptitle(f"{_pretty_name(property_name)} — vapor mass fraction {kind}")
    footer_parts = [
        f"Backend: {_single_or_joined(frame['backend'])} "
        f"{_single_or_joined(frame['backend_version'])}",
        f"Run: {plot_source.run_id[:8]}",
        f"Excluded rows: {invalid_rows_excluded}",
        f"Integrity: {plot_source.source_integrity}",
    ]
    if reference_dependent:
        policy = None
        if plot_source.metadata is not None:
            candidate = plot_source.metadata.get("reference_state_policy")
            if isinstance(candidate, str):
                policy = candidate
        footer_parts.append(f"Reference state: {policy or 'unreported'}")
    figure.text(0.5, 0.012, " | ".join(footer_parts), ha="center", fontsize=7)
    layout_engine = figure.get_layout_engine()
    if layout_engine is not None:
        layout_engine.set(rect=(0.0, 0.08, 1.0, 0.92))
    settings.update(
        {
            "figure_size_inches": [6.4 * len(fluids), 4.8],
            "constrained_layout": True,
            "property_column": property_column,
        }
    )
    return figure, settings


def _plot_curves(
    *,
    mpl: dict[str, Any],
    figure: Any,
    axes: list[Any],
    frame: pd.DataFrame,
    fluids: list[str],
    property_name: str,
    property_unit: str,
    coordinate: PlotCoordinate,
    coordinate_unit: str,
    scale: PlotScale,
) -> dict[str, Any]:
    cmap = mpl["pyplot"].get_cmap(DEFAULT_COLORMAP)
    coordinate_values = np.sort(frame["_coordinate_display"].unique())
    norm = _normalization(
        mpl,
        float(coordinate_values.min()),
        float(coordinate_values.max()),
        scale="linear",
    )
    all_fractions = np.sort(frame["vapor_mass_fraction"].unique())
    for axis, fluid in zip(axes, fluids, strict=True):
        fluid_frame = frame.loc[frame["fluid"] == fluid]
        for coordinate_value in np.sort(fluid_frame["_coordinate_display"].unique()):
            group = fluid_frame.loc[
                fluid_frame["_coordinate_display"] == coordinate_value
            ].set_index("vapor_mass_fraction")
            values = group["_plot_value"].reindex(all_fractions)
            axis.plot(
                all_fractions,
                values,
                color=cmap(norm(float(coordinate_value))),
                marker="o",
                markersize=3.5,
                linewidth=1.2,
            )
        axis.set_xlabel("Vapor mass fraction [-]")
        axis.set_ylabel(f"{_pretty_name(property_name)} [{_display_unit(property_unit)}]")
        axis.grid(True, alpha=0.25)
        if scale == "log":
            axis.set_yscale("log")
    scalar_mappable = mpl["ScalarMappable"](norm=norm, cmap=cmap)
    scalar_mappable.set_array([])
    colorbar = figure.colorbar(scalar_mappable, ax=axes)
    colorbar.set_label(f"{_pretty_name(coordinate)} [{_display_unit(coordinate_unit)}]")
    return {
        "colormap": DEFAULT_COLORMAP,
        "contour_levels": None,
        "marker": "o",
        "coordinate_values": coordinate_values.tolist(),
    }


def _plot_contours(
    *,
    mpl: dict[str, Any],
    figure: Any,
    axes: list[Any],
    frame: pd.DataFrame,
    fluids: list[str],
    property_name: str,
    property_unit: str,
    coordinate: PlotCoordinate,
    coordinate_unit: str,
    scale: PlotScale,
) -> dict[str, Any]:
    valid_values = frame.loc[frame["_plot_valid"], "_plot_value"]
    value_min = float(valid_values.min())
    value_max = float(valid_values.max())
    if value_min == value_max:
        raise VisualizationError("contour plotting requires a non-constant property")
    norm = _normalization(mpl, value_min, value_max, scale=scale)
    levels = (
        np.geomspace(value_min, value_max, DEFAULT_CONTOUR_LEVELS)
        if scale == "log"
        else np.linspace(value_min, value_max, DEFAULT_CONTOUR_LEVELS)
    )
    cmap = mpl["pyplot"].get_cmap(DEFAULT_COLORMAP)
    for axis, fluid in zip(axes, fluids, strict=True):
        fluid_frame = frame.loc[frame["fluid"] == fluid]
        fractions = np.sort(fluid_frame["vapor_mass_fraction"].unique())
        coordinates = np.sort(fluid_frame["_coordinate_display"].unique())
        if len(fractions) < 2 or len(coordinates) < 2:
            raise VisualizationError(
                "contour plotting requires at least two vapor-fraction and "
                f"two {coordinate} values for each selected fluid"
            )
        pivot = fluid_frame.pivot(
            index="_coordinate_display",
            columns="vapor_mass_fraction",
            values="_plot_value",
        ).reindex(index=coordinates, columns=fractions)
        x_values, y_values = np.meshgrid(fractions, coordinates)
        masked_values = np.ma.masked_invalid(pivot.to_numpy(dtype=float))
        axis.contourf(
            x_values,
            y_values,
            masked_values,
            levels=levels,
            norm=norm,
            cmap=cmap,
        )
        valid_points = fluid_frame.loc[fluid_frame["_plot_valid"]]
        axis.scatter(
            valid_points["vapor_mass_fraction"],
            valid_points["_coordinate_display"],
            s=9,
            c="black",
            alpha=0.45,
            linewidths=0,
        )
        axis.set_xlabel("Vapor mass fraction [-]")
        axis.set_ylabel(f"{_pretty_name(coordinate)} [{_display_unit(coordinate_unit)}]")
    scalar_mappable = mpl["ScalarMappable"](norm=norm, cmap=cmap)
    scalar_mappable.set_array([])
    colorbar = figure.colorbar(scalar_mappable, ax=axes)
    colorbar.set_label(f"{_pretty_name(property_name)} [{_display_unit(property_unit)}]")
    return {
        "colormap": DEFAULT_COLORMAP,
        "contour_levels": DEFAULT_CONTOUR_LEVELS,
        "sample_point_overlay": True,
        "property_range": [value_min, value_max],
    }


def _normalization(
    mpl: dict[str, Any],
    minimum: float,
    maximum: float,
    *,
    scale: PlotScale,
) -> Any:
    if minimum == maximum:
        delta = abs(minimum) * 0.01 or 0.5
        minimum -= delta
        maximum += delta
    if scale == "log":
        return mpl["LogNorm"](vmin=minimum, vmax=maximum)
    return mpl["Normalize"](vmin=minimum, vmax=maximum)


def _pretty_name(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _display_unit(unit: str) -> str:
    return {"degC": "°C", "1": "-"}.get(unit, unit)


def _single_or_joined(series: pd.Series) -> str:
    values = sorted(series.dropna().astype(str).unique().tolist())
    return ", ".join(values) if values else "unreported"
