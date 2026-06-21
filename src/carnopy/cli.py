from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from carnopy._version import __version__


class PlotScaleCli(str, Enum):
    linear = "linear"
    log = "log"


class PlotCoordinateCli(str, Enum):
    pressure = "pressure"
    temperature = "temperature"


class ConfigModeCli(str, Enum):
    property_table = "property_table"
    saturation_table = "saturation_table"
    vapor_mass_fraction_table = "vapor_mass_fraction_table"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"carnopy {__version__}")
        raise typer.Exit


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    help="Generate reproducible thermophysical datasets from configured backends.",
    epilog=(
        "Workflow: init → edit → optional validate → generate → inspect report/metadata "
        "→ optional plot."
    ),
)


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the Carnopy version and exit.",
        ),
    ] = False,
) -> None:
    """Generate reproducible thermophysical datasets."""


@app.command("validate", short_help="Check a configuration.")
def validate_command(
    config: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Validate a configuration without evaluating thermodynamic rows."""
    from carnopy.api import validate_config
    from carnopy.domain.failures import CarnopyError, ConfigError

    try:
        result = validate_config(config)
    except ConfigError as exc:
        typer.echo(f"Configuration validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except CarnopyError as exc:
        typer.echo(f"Validation environment failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
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
    figures_root: Annotated[
        Path,
        typer.Option(
            "--figures-out",
            file_okay=False,
            help="Root directory for configured figure outputs.",
        ),
    ] = Path("figures"),
) -> None:
    """Generate and finalize one immutable dataset run.

    Modes: property_table requires temperature and pressure; saturation_table
    requires exactly one of them; vapor_mass_fraction_table requires vapor mass
    fraction plus exactly one temperature or pressure axis.

    Start with `carnopy init MODE CONFIG.yaml`. Generation performs configuration
    validation automatically; `carnopy validate` is an optional separate check.
    """
    from carnopy.api import generate_dataset
    from carnopy.domain.failures import CarnopyError, ConfigError

    try:
        result = generate_dataset(
            config,
            output_root=output_root,
            figures_root=figures_root,
        )
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
    if result.visualization is not None:
        typer.echo(f"Visualization status: {result.visualization.status}")
        if result.visualization.figure_directory is not None:
            typer.echo(f"Figure directory: {result.visualization.figure_directory}")
        if result.visualization.report_path is not None:
            typer.echo(f"Visualization report: {result.visualization.report_path}")
    if result.valid_row_count == 0:
        raise typer.Exit(code=3)
    if result.visualization is not None and result.visualization.status in {
        "completed_with_failures",
        "failed",
    }:
        raise typer.Exit(code=1)


@app.command("fluids", short_help="List backend fluids.")
def fluids_command() -> None:
    """List pure fluids available from the current backend."""
    from carnopy.backends import CoolPropBackend

    backend = CoolPropBackend()
    typer.echo(f"CoolProp {backend.version}")
    for fluid in backend.list_fluids():
        aliases = ", ".join(backend.aliases_for(fluid))
        typer.echo(f"{fluid}: {aliases}")


@app.command("properties", short_help="List dataset properties.")
def properties_command() -> None:
    """List semantic properties accepted by configuration schema version 1."""
    from carnopy.domain.properties import PROPERTY_REGISTRY

    header = (
        f"{'PROPERTY':<40} {'COLUMN':<48} {'UNIT':<12} "
        f"{'CLASSIFICATION':<20} {'REFERENCE':<9} DEPENDENCIES"
    )
    typer.echo(header)
    for name in sorted(PROPERTY_REGISTRY):
        definition = PROPERTY_REGISTRY[name]
        dependencies = ", ".join(definition.dependencies) or "-"
        reference = "yes" if definition.reference_dependent else "no"
        typer.echo(
            f"{definition.name:<40} {definition.column:<48} {definition.unit:<12} "
            f"{definition.classification:<20} {reference:<9} {dependencies}"
        )


@app.command("init", short_help="Create a starter configuration.")
def init_command(
    mode: Annotated[
        ConfigModeCli,
        typer.Argument(help="Dataset mode for the starter configuration."),
    ],
    output: Annotated[
        Path,
        typer.Argument(
            dir_okay=False,
            metavar="OUTPUT",
            help="New .yaml or .yml configuration path.",
        ),
    ],
    create_parents: Annotated[
        bool,
        typer.Option(
            "--create-parents",
            help="Create missing parent directories without prompting.",
        ),
    ] = False,
) -> None:
    """Create a commented configuration template without overwriting files."""
    from carnopy.templates import TemplateError, initialize_config

    def confirm_create(parent: Path) -> bool:
        return typer.confirm(f"Parent directory {parent} does not exist. Create it?", default=False)

    try:
        created = initialize_config(
            mode.value,
            output,
            create_parents=create_parents,
            interactive=sys.stdin.isatty(),
            confirm_create=confirm_create,
        )
    except TemplateError as exc:
        typer.echo(f"Configuration initialization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Created configuration: {created}")
    typer.echo("Next:")
    typer.echo(f"  edit {created}")
    typer.echo(f"  carnopy validate {created}")
    typer.echo(f"  carnopy generate {created}")


@app.command("plot", short_help="Plot a generated dataset.")
def plot_command(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            help="Run directory, CSV, or Parquet file.",
        ),
    ],
    kind: Annotated[
        str,
        typer.Option(
            "--kind",
            metavar="KIND",
            help="Required kind: property-curves, property-heatmap, xy, pv, or ts.",
        ),
    ],
    property_name: Annotated[
        str | None,
        typer.Option(
            "--property",
            metavar="PROPERTY",
            help="Semantic property for property-curves or property-heatmap.",
        ),
    ] = None,
    x_field: Annotated[
        str | None,
        typer.Option(
            "--x",
            metavar="FIELD",
            help="X field for xy, or temperature/pressure for property-table curves.",
        ),
    ] = None,
    y_field: Annotated[
        str | None,
        typer.Option(
            "--y",
            metavar="FIELD",
            help="Y field for xy.",
        ),
    ] = None,
    group_by: Annotated[
        str | None,
        typer.Option(
            "--group-by",
            metavar="FIELD",
            help="Explicit xy series grouping field when sampling is ambiguous.",
        ),
    ] = None,
    fluids: Annotated[
        list[str] | None,
        typer.Option(
            "--fluid",
            metavar="FLUID",
            help="Repeat --fluid to select multiple fluids.",
        ),
    ] = None,
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            metavar="FIELD=VALUE",
            help="Exact canonical-value filter; repeat to combine with AND.",
        ),
    ] = None,
    value_scale: Annotated[
        PlotScaleCli | None,
        typer.Option(
            "--value-scale",
            help="Property-curves y scale: linear or log.",
        ),
    ] = None,
    color_scale: Annotated[
        PlotScaleCli | None,
        typer.Option(
            "--color-scale",
            help="Property-heatmap color scale: linear or log.",
        ),
    ] = None,
    x_scale: Annotated[
        PlotScaleCli | None,
        typer.Option(
            "--x-scale",
            help="X-axis scale for xy, pv, or ts.",
        ),
    ] = None,
    y_scale: Annotated[
        PlotScaleCli | None,
        typer.Option(
            "--y-scale",
            help="Y-axis scale for xy, pv, or ts.",
        ),
    ] = None,
    saturation_coordinate: Annotated[
        PlotCoordinateCli | None,
        typer.Option(
            "--saturation-coordinate",
            help=(
                "Independent saturation coordinate for standalone saturation "
                "or vapor-quality files."
            ),
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
    """Plot emitted Carnopy values without backend calls or interpolation.

    property-curves supports all dataset modes. property_table sources require
    --x temperature or --x pressure. property-heatmap supports property_table
    and vapor_mass_fraction_table sources. xy uses explicit semantic axes.
    pv and ts use conventional fixed axes derived from emitted columns.
    """
    from carnopy.visualization import (
        VisualizationDependencyError,
        VisualizationError,
        plot_dataset,
    )
    from carnopy.visualization.requests import (
        normalize_public_plot_kind,
        parse_exact_filter,
    )

    try:
        normalized_kind = normalize_public_plot_kind(kind)
        if normalized_kind == "property_curves" and color_scale is not None:
            raise VisualizationError("--color-scale is valid only with --kind property-heatmap")
        if normalized_kind == "property_heatmap" and value_scale is not None:
            raise VisualizationError("--value-scale is valid only with --kind property-curves")
        if normalized_kind in {"property_curves", "property_heatmap"} and (
            x_scale is not None or y_scale is not None
        ):
            raise VisualizationError("--x-scale and --y-scale are valid only with xy, pv, or ts")
        exact_filters = tuple(parse_exact_filter(value) for value in (filters or ()))
        result = plot_dataset(
            source,
            property_name=property_name,
            kind=normalized_kind,
            x=x_field,
            y=y_field,
            group_by=group_by,
            fluids=fluids,
            filters=exact_filters,
            value_scale=(value_scale or PlotScaleCli.linear).value,
            color_scale=(color_scale or PlotScaleCli.linear).value,
            x_scale=(x_scale or PlotScaleCli.linear).value,
            y_scale=(y_scale or PlotScaleCli.linear).value,
            output=output,
            show=show,
            saturation_coordinate=(
                saturation_coordinate.value if saturation_coordinate is not None else None
            ),
        )
    except ValueError as exc:
        typer.echo(f"Visualization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except VisualizationDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except VisualizationError as exc:
        typer.echo(f"Visualization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Figure: {result.image_path}")
    typer.echo(f"Plot metadata: {result.sidecar_path}")
    typer.echo(f"Valid rows plotted: {result.valid_rows_plotted}")
    typer.echo(f"Invalid rows excluded: {result.invalid_rows_excluded}")
    typer.echo(f"Source integrity: {result.source_integrity}")
    for advisory in result.advisories:
        typer.echo(f"Advisory: {advisory.message}")
