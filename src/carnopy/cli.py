from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    help="Generate reproducible thermophysical datasets from configured backends.",
)


@app.command("validate", short_help="Check a configuration.")
def validate_command(
    config: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Validate a configuration without evaluating thermodynamic rows."""
    from carnopy.api import validate_config
    from carnopy.domain.failures import ConfigError

    try:
        result = validate_config(config)
    except ConfigError as exc:
        typer.echo(f"Configuration validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Backend: {result.backend} {result.backend_version}")
    typer.echo(f"Mode: {result.mode}")
    typer.echo(f"Projected rows: {result.projected_rows}")
    typer.echo(
        "Configuration is valid. Thermodynamic row validity will be determined during generation."
    )


@app.command("generate", short_help="Generate an immutable run.")
def generate_command(
    config: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    output_root: Annotated[
        Path,
        typer.Option(
            "--out",
            file_okay=False,
            help="Root directory for immutable generated runs.",
        ),
    ] = Path("outputs"),
) -> None:
    """Generate and finalize one immutable dataset run."""
    from carnopy.api import generate_dataset
    from carnopy.domain.failures import CarnopyError, ConfigError

    try:
        result = generate_dataset(config, output_root=output_root)
    except ConfigError as exc:
        typer.echo(f"Configuration validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except CarnopyError as exc:
        typer.echo(f"Generation failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Mode: {result.mode}")
    typer.echo(f"Rows: {result.row_count}")
    typer.echo(f"Valid rows: {result.valid_row_count}")
    typer.echo(f"Invalid rows: {result.invalid_row_count}")
    typer.echo(f"Run status: {result.run_status}")
    typer.echo(f"Output directory: {result.output_directory}")
    if result.valid_row_count == 0:
        raise typer.Exit(code=3)


@app.command("fluids", short_help="List backend fluids.")
def fluids_command() -> None:
    """List pure fluids available from the current backend."""
    from carnopy.backends import CoolPropBackend

    backend = CoolPropBackend()
    typer.echo(f"CoolProp {backend.version}")
    for fluid in backend.list_fluids():
        aliases = ", ".join(backend.aliases_for(fluid))
        typer.echo(f"{fluid}: {aliases}")


@app.command("plot", short_help="Plot a generated dataset.")
def plot_command(
    source: Annotated[
        Path,
        typer.Argument(exists=True, readable=True),
    ],
    property_name: Annotated[
        str,
        typer.Option(
            "--property",
            help="Semantic Carnopy property name to plot.",
        ),
    ],
    kind: Annotated[
        str,
        typer.Option("--kind", help="Plot kind: curves or contour."),
    ] = "curves",
    fluids: Annotated[
        list[str] | None,
        typer.Option(
            "--fluid",
            help="Fluid to plot; repeat for multiple pure-fluid facets.",
        ),
    ] = None,
    scale: Annotated[
        str,
        typer.Option("--scale", help="Property scale: linear or log."),
    ] = "linear",
    coordinate: Annotated[
        str | None,
        typer.Option(
            "--coordinate",
            help="Driving coordinate for standalone files: pressure or temperature.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="Figure path (.png, .pdf, or .svg). Defaults to ./figures/.",
        ),
    ] = None,
    show: Annotated[
        bool,
        typer.Option("--show", help="Display the figure after exporting it."),
    ] = False,
) -> None:
    """Export a scientific plot from a vapor-mass-fraction dataset."""
    from carnopy.visualization import (
        VisualizationDependencyError,
        VisualizationError,
        plot_dataset,
    )
    from carnopy.visualization.models import PlotCoordinate, PlotKind, PlotScale

    try:
        result = plot_dataset(
            source,
            property_name=property_name,
            kind=cast(PlotKind, kind),
            fluids=fluids,
            scale=cast(PlotScale, scale),
            output=output,
            show=show,
            coordinate=cast(PlotCoordinate | None, coordinate),
        )
    except VisualizationDependencyError as exc:
        typer.echo(f"Visualization dependency error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except VisualizationError as exc:
        typer.echo(f"Visualization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Figure: {result.image_path}")
    typer.echo(f"Plot metadata: {result.sidecar_path}")
    typer.echo(f"Valid rows plotted: {result.valid_rows_plotted}")
    typer.echo(f"Invalid rows excluded: {result.invalid_rows_excluded}")
    typer.echo(f"Source integrity: {result.source_integrity}")
