from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.visualization.export import DEFAULT_RASTER_DPI, export_figure
from carnopy.visualization.io import (
    convert_coordinate_for_display,
    load_plot_source,
)
from carnopy.visualization.models import (
    PlotCoordinate,
    PlotKind,
    PlotResult,
    PlotScale,
    PlotSource,
    VisualizationError,
)
from carnopy.visualization.render import create_figure, import_matplotlib
from carnopy.visualization.requests import legacy_property_request, request_id
from carnopy.visualization.selection import dynamic_range_advisories, select_rows


def plot_dataset(
    source: str | Path,
    *,
    property_name: str = "mass_density",
    kind: PlotKind = "curves",
    fluids: Sequence[str] | None = None,
    scale: PlotScale = "linear",
    output: str | Path | None = None,
    show: bool = False,
    coordinate: PlotCoordinate | None = None,
) -> PlotResult:
    """Plot one property from a Carnopy vapor-mass-fraction dataset."""
    if kind not in ("curves", "contour"):
        raise VisualizationError("plot kind must be 'curves' or 'contour'")
    if scale not in ("linear", "log"):
        raise VisualizationError("plot scale must be 'linear' or 'log'")
    if coordinate not in (None, "pressure", "temperature"):
        raise VisualizationError("plot coordinate must be 'pressure' or 'temperature'")
    request = legacy_property_request(
        property_name=property_name,
        kind=kind,
        fluids=tuple(fluids or ()),
        scale=scale,
        coordinate=coordinate,
    )
    plot_source = load_plot_source(source, coordinate=coordinate)
    if request.saturation_coordinate is None:
        request = request.model_copy(update={"saturation_coordinate": plot_source.coordinate})
    visualization_request_id = request_id((request,))
    definition = PROPERTY_REGISTRY.get(property_name)
    if definition is None:
        raise VisualizationError(f"unknown Carnopy property {property_name!r}")
    if definition.column not in plot_source.frame.columns:
        raise VisualizationError(f"property {property_name!r} is not present in the source dataset")
    selection = select_rows(plot_source.frame, fluids=fluids)
    selected_fluids = list(selection.selected_fluids)
    prepared, valid_count, excluded_count = _prepare_frame(
        plot_source,
        frame=selection.frame,
        property_column=definition.column,
    )
    valid_values = prepared.loc[prepared["_plot_valid"], "_plot_value"]
    if valid_values.empty:
        raise VisualizationError("no valid property values remain to plot")
    if scale == "log" and bool((valid_values <= 0.0).any()):
        raise VisualizationError(f"log scaling requires positive {property_name} values")
    advisories = dynamic_range_advisories(
        valid_values.tolist(),
        scale=scale,
        subject=f"{property_name} property",
    )

    mpl = import_matplotlib()
    figure, settings = create_figure(
        mpl=mpl,
        plot_source=plot_source,
        frame=prepared,
        property_name=property_name,
        property_column=definition.column,
        property_unit=definition.unit,
        reference_dependent=definition.reference_dependent,
        fluids=selected_fluids,
        kind=kind,
        scale=scale,
        invalid_rows_excluded=excluded_count,
    )
    image_path, sidecar_path = export_figure(
        figure=figure,
        plot_source=plot_source,
        output=output,
        selected_fluids=selected_fluids,
        property_name=property_name,
        property_column=definition.column,
        property_unit=definition.unit,
        kind=kind,
        scale=scale,
        valid_rows_plotted=valid_count,
        invalid_rows_excluded=excluded_count,
        matplotlib_version=mpl["matplotlib"].__version__,
        settings=settings,
        request=request,
        visualization_request_id=visualization_request_id,
        advisories=advisories,
    )
    if show:
        mpl["pyplot"].show()
    effective_settings = {
        **settings,
        "raster_dpi": (DEFAULT_RASTER_DPI if image_path.suffix.lower() == ".png" else None),
    }
    return PlotResult(
        figure=figure,
        image_path=image_path,
        sidecar_path=sidecar_path,
        selected_fluids=tuple(selected_fluids),
        property_name=property_name,
        kind=kind,
        scale=scale,
        valid_rows_plotted=valid_count,
        invalid_rows_excluded=excluded_count,
        source_integrity=plot_source.source_integrity,
        visualization_request_id=visualization_request_id,
        effective_settings=effective_settings,
        advisories=advisories,
    )


def _prepare_frame(
    plot_source: PlotSource,
    *,
    frame: pd.DataFrame,
    property_column: str,
) -> tuple[pd.DataFrame, int, int]:
    selected = frame.copy()
    if selected.empty:
        raise VisualizationError("fluid selection produced no rows")
    coordinate_values = pd.to_numeric(selected[plot_source.coordinate_column], errors="coerce")
    fractions = pd.to_numeric(selected["vapor_mass_fraction"], errors="coerce")
    if not bool(np.isfinite(coordinate_values).all()):
        raise VisualizationError("driving coordinate contains non-finite values")
    if not bool(np.isfinite(fractions).all()):
        raise VisualizationError("vapor mass fraction contains non-finite values")
    if bool(((fractions < 0.0) | (fractions > 1.0)).any()):
        raise VisualizationError("vapor mass fraction must be between 0 and 1")
    selected[plot_source.coordinate_column] = coordinate_values
    selected["vapor_mass_fraction"] = fractions
    selected["_coordinate_display"] = convert_coordinate_for_display(plot_source, selected)
    selected["_plot_value"] = pd.to_numeric(selected[property_column], errors="coerce")
    valid_column = selected["valid"]
    if valid_column.dtype == object:
        row_valid = valid_column.astype(str).str.casefold().eq("true")
    else:
        row_valid = valid_column.astype(bool)
    finite_property = np.isfinite(selected["_plot_value"])
    selected["_plot_valid"] = row_valid & selected["_plot_value"].notna() & finite_property
    selected.loc[~selected["_plot_valid"], "_plot_value"] = np.nan
    valid_count = int(selected["_plot_valid"].sum())
    excluded_count = len(selected) - valid_count
    duplicate_mask = selected.duplicated(
        subset=["fluid", "_coordinate_display", "vapor_mass_fraction"],
        keep=False,
    )
    if bool(duplicate_mask.any()):
        raise VisualizationError("source contains duplicate fluid/coordinate/vapor-fraction states")
    return selected, valid_count, excluded_count
