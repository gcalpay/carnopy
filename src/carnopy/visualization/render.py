from __future__ import annotations

from typing import Any

import pandas as pd

from carnopy.visualization.models import (
    PlotScale,
    PlotSource,
    VisualizationDependencyError,
)

DEFAULT_COLORMAP = "viridis"


def import_matplotlib() -> dict[str, Any]:
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import LogNorm, Normalize
    except ImportError as exc:
        raise VisualizationDependencyError(
            "Plotting requires the visualization extra.\n\n"
            "For an isolated CLI:\n"
            '  uv tool install --force "carnopy[viz]"\n\n'
            "With pip:\n"
            '  python -m pip install "carnopy[viz]"'
        ) from exc
    return {
        "matplotlib": matplotlib,
        "pyplot": plt,
        "ScalarMappable": ScalarMappable,
        "LogNorm": LogNorm,
        "Normalize": Normalize,
    }


def create_faceted_figure(
    *,
    mpl: dict[str, Any],
    fluids: tuple[str, ...],
) -> tuple[Any, list[Any]]:
    figure, axes_array = mpl["pyplot"].subplots(
        1,
        len(fluids),
        figsize=(6.4 * len(fluids), 4.8),
        squeeze=False,
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    return figure, list(axes_array.ravel())


def finish_figure(
    *,
    figure: Any,
    axes: list[Any],
    plot_source: PlotSource,
    frame: pd.DataFrame,
    fluids: tuple[str, ...],
    title: str,
    invalid_rows_excluded: int,
    reference_dependent: bool,
) -> None:
    for axis, fluid in zip(axes, fluids, strict=True):
        axis.set_title(fluid)
    figure.suptitle(title)
    backend_model = (
        _single_or_joined(frame["backend_model"])
        if "backend_model" in frame.columns
        else (
            plot_source.metadata.get("backend_model") if plot_source.metadata is not None else None
        )
    )
    backend_label = (
        f"Backend: {_single_or_joined(frame['backend'])} "
        f"{_single_or_joined(frame['backend_version'])}"
    )
    if isinstance(backend_model, str) and backend_model:
        backend_label += f" ({backend_model})"
    footer_parts = [
        backend_label,
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


def normalization(
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


def _single_or_joined(series: pd.Series) -> str:
    values = sorted(series.dropna().astype(str).unique().tolist())
    return ", ".join(values) if values else "unreported"
