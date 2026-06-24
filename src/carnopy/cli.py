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
    model_sweep = "model_sweep"
    preparation = "preparation"


class InspectFormatCli(str, Enum):
    text = "text"
    json = "json"


class CoolPropModelCli(str, Enum):
    heos = "heos"
    pr = "pr"
    srk = "srk"


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
        "Workflow: init → edit → optional validate → generate/sweep → inspect "
        "→ optional plot → optional prepare."
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
    typer.echo(
        f"Backend: {result.backend} {result.backend_version} (model: {result.backend_model})"
    )
    typer.echo(f"Mode: {result.mode}")
    typer.echo(f"Projected rows: {result.projected_rows}")
    typer.echo(f"Dataset formats: {', '.join(result.dataset_formats)}")
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
    typer.echo(
        f"Backend: {result.backend} {result.backend_version} (model: {result.backend_model})"
    )
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


@app.command("sweep", short_help="Generate a model sweep.")
def sweep_command(
    config: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    output_root: Annotated[
        Path,
        typer.Option(
            "--out",
            file_okay=False,
            help="Parent directory for immutable model-sweep bundles.",
        ),
    ] = Path("outputs"),
) -> None:
    """Generate child runs for multiple backend models and compare emitted values."""
    from carnopy.api import generate_model_sweep
    from carnopy.domain.failures import CarnopyError, ConfigError

    try:
        result = generate_model_sweep(config, output_root=output_root)
    except ConfigError as exc:
        typer.echo(f"Sweep validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except CarnopyError as exc:
        typer.echo(f"Sweep failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Sweep status: {result.sweep_status}")
    typer.echo(f"Mode: {result.mode}")
    typer.echo(f"Models: {', '.join(result.models)}")
    typer.echo(f"Reference model: {result.reference_model}")
    typer.echo(f"Output directory: {result.output_directory}")
    typer.echo(f"Child runs: {len(result.child_runs)}")
    if result.values_path is not None:
        typer.echo(f"Comparison values: {result.values_path}")
    if result.deltas_path is not None:
        typer.echo(f"Comparison deltas: {result.deltas_path}")
    if result.comparison_plot_directory is not None:
        typer.echo(f"Comparison plots: {result.comparison_plot_directory}")
    else:
        typer.echo("Comparison plots: not configured")
    if result.failure_message is not None:
        typer.echo(f"Failure: {result.failure_message}", err=True)
    if result.sweep_status != "completed":
        raise typer.Exit(code=1)


@app.command("prepare", short_help="Prepare ML-ready data.")
def prepare_command(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            help="Dataset run directory or model-sweep bundle.",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Preparation YAML configuration.",
        ),
    ],
    output_root: Annotated[
        Path,
        typer.Option(
            "--out",
            file_okay=False,
            help="Parent directory for immutable preparation bundles.",
        ),
    ] = Path("prepared"),
) -> None:
    """Prepare deterministic Parquet and optional array outputs without backend calls.

    Preparation can write an unsplit table or optional split scenarios with
    log10, standard, and minmax numeric transformations. Optional NumPy and
    SafeTensors exports are derived from the canonical Parquet tables.
    """
    from carnopy.api import prepare_dataset
    from carnopy.domain.failures import CarnopyError, ConfigError

    try:
        result = prepare_dataset(source, config=config, output_root=output_root)
    except ConfigError as exc:
        typer.echo(f"Preparation validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except CarnopyError as exc:
        typer.echo(f"Preparation failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Preparation status: {result.status}")
    typer.echo(f"Eligible rows: {result.eligible_row_count}")
    typer.echo(f"Excluded rows: {result.excluded_row_count}")
    typer.echo(f"Output directory: {result.output_directory}")
    typer.echo(f"Manifest: {result.manifest_path}")
    if result.table_path is not None:
        typer.echo(f"Prepared table: {result.table_path}")
    typer.echo(f"Provenance: {result.provenance_path}")
    typer.echo(f"Diagnostics table: {result.source_diagnostics_path}")
    typer.echo(f"Exclusions: {result.exclusions_path}")
    if result.scenario_report_path is not None:
        typer.echo(f"Scenario report: {result.scenario_report_path}")
    if result.status == "no_eligible_rows":
        raise typer.Exit(code=1)


@app.command("fluids", short_help="List backend fluids.")
def fluids_command(
    model: Annotated[
        CoolPropModelCli,
        typer.Option("--model", help="CoolProp thermodynamic model."),
    ] = CoolPropModelCli.heos,
) -> None:
    """List pure fluids available from one CoolProp model."""
    from carnopy.backends import CoolPropBackend

    backend = CoolPropBackend(model=model.value)
    typer.echo(f"CoolProp {backend.version} (model: {backend.model})")
    for fluid in backend.list_fluids():
        aliases = ", ".join(backend.aliases_for(fluid))
        typer.echo(f"{fluid}: {aliases}")


@app.command("properties", short_help="List dataset properties.")
def properties_command() -> None:
    """List semantic properties accepted by configuration schema version 2."""
    from carnopy.backends.coolprop_models import unsupported_properties
    from carnopy.config.models import CoolPropModel
    from carnopy.domain.properties import PROPERTY_REGISTRY

    models: tuple[CoolPropModel, ...] = ("heos", "pr", "srk")
    unsupported_by_model = {model: set(unsupported_properties(model)) for model in models}
    header = (
        f"{'PROPERTY':<40} {'COLUMN':<48} {'UNIT':<12} "
        f"{'CLASSIFICATION':<20} {'REFERENCE':<9} {'MODELS':<12} DEPENDENCIES"
    )
    typer.echo(header)
    for name in sorted(PROPERTY_REGISTRY):
        definition = PROPERTY_REGISTRY[name]
        dependencies = ", ".join(definition.dependencies) or "-"
        reference = "yes" if definition.reference_dependent else "no"
        supported_models = ",".join(
            model for model in models if name not in unsupported_by_model[model]
        )
        typer.echo(
            f"{definition.name:<40} {definition.column:<48} {definition.unit:<12} "
            f"{definition.classification:<20} {reference:<9} "
            f"{supported_models:<12} {dependencies}"
        )


@app.command("inspect", short_help="Inspect Carnopy outputs.")
def inspect_command(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            help="Dataset run, model-sweep bundle, preparation bundle, CSV, or Parquet file.",
        ),
    ],
    output_format: Annotated[
        InspectFormatCli,
        typer.Option("--format", help="Inspection output format."),
    ] = InspectFormatCli.text,
    write_visualization: Annotated[
        Path | None,
        typer.Option(
            "--write-visualization",
            dir_okay=False,
            metavar="PATH",
            help="Write a visualization-only starter YAML without overwriting files.",
        ),
    ] = None,
) -> None:
    """Inspect dataset, sweep, or preparation outputs without backend calls."""
    from carnopy.inspection import inspect_source
    from carnopy.visualization.models import VisualizationError

    try:
        inspection = inspect_source(source)
        if write_visualization is not None:
            writer = getattr(inspection, "write_visualization", None)
            if not callable(writer):
                raise VisualizationError("--write-visualization is only supported for dataset runs")
            created = writer(write_visualization)
    except VisualizationError as exc:
        typer.echo(f"Inspection failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        inspection.format_json()
        if output_format is InspectFormatCli.json
        else inspection.format_text()
    )
    if write_visualization is not None:
        typer.echo(
            f"Created visualization configuration: {created}",
            err=output_format is InspectFormatCli.json,
        )


@app.command("init", short_help="Create a starter configuration.")
def init_command(
    mode: Annotated[
        ConfigModeCli,
        typer.Argument(help="Configuration template type for the starter file."),
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
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Append the exhaustive commented configuration reference.",
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
            full=full,
        )
    except TemplateError as exc:
        typer.echo(f"Configuration initialization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Created configuration: {created}")
    typer.echo("Next:")
    typer.echo(f"  edit {created}")
    if mode is ConfigModeCli.model_sweep:
        typer.echo(f"  carnopy sweep {created}")
    elif mode is ConfigModeCli.preparation:
        typer.echo(f"  carnopy prepare SOURCE --config {created}")
    else:
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
        str | None,
        typer.Option(
            "--kind",
            metavar="KIND",
            help="Manual plot kind: property-curves, property-heatmap, xy, pv, or ts.",
        ),
    ] = None,
    plot_config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Render all visualization requests from YAML for an existing run.",
        ),
    ] = None,
    figures_root: Annotated[
        Path | None,
        typer.Option(
            "--figures-out",
            file_okay=False,
            help="Batch figure root; defaults to ./figures.",
        ),
    ] = None,
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
    series: Annotated[
        list[str] | None,
        typer.Option(
            "--series",
            metavar="FIELD=VALUE",
            help=(
                "Select exact curve-series levels; repeat values for the same "
                "field to combine with OR."
            ),
        ),
    ] = None,
    display_units: Annotated[
        list[str] | None,
        typer.Option(
            "--display-unit",
            metavar="FIELD=UNIT",
            help="Override a plotted engineering display unit; repeat by field.",
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

    Manual mode uses --kind and creates one figure. Batch mode uses --config
    with an immutable run directory and renders every visualization request in
    the YAML file.
    """
    from carnopy.visualization import (
        VisualizationDependencyError,
        VisualizationError,
        plot_dataset,
    )
    from carnopy.visualization.requests import (
        normalize_public_plot_kind,
        parse_display_units,
        parse_exact_filter,
        parse_series_selections,
    )

    try:
        if plot_config is not None:
            manual_values = {
                "--kind": kind,
                "--property": property_name,
                "--x": x_field,
                "--y": y_field,
                "--group-by": group_by,
                "--fluid": fluids,
                "--filter": filters,
                "--series": series,
                "--display-unit": display_units,
                "--value-scale": value_scale,
                "--color-scale": color_scale,
                "--x-scale": x_scale,
                "--y-scale": y_scale,
                "--saturation-coordinate": saturation_coordinate,
                "--output": output,
                "--show": show or None,
            }
            conflicting = [name for name, value in manual_values.items() if value is not None]
            if conflicting:
                raise VisualizationError(
                    "--config batch mode cannot be combined with manual plot options: "
                    + ", ".join(conflicting)
                )
            from carnopy.visualization.automation import (
                render_existing_run_visualizations,
            )

            summary = render_existing_run_visualizations(
                source_run=source,
                config_path=plot_config,
                figures_root=figures_root or Path("figures"),
            )
            typer.echo(f"Visualization status: {summary.status}")
            if summary.figure_directory is not None:
                typer.echo(f"Figure directory: {summary.figure_directory}")
            if summary.report_path is not None:
                typer.echo(f"Visualization report: {summary.report_path}")
            typer.echo(f"Plots succeeded: {summary.succeeded_plot_count}")
            typer.echo(f"Plots failed: {summary.failed_plot_count}")
            if summary.status in {"completed_with_failures", "failed"}:
                raise typer.Exit(code=1)
            return
        if figures_root is not None:
            raise VisualizationError("--figures-out is valid only with --config")
        if kind is None:
            raise VisualizationError(
                "manual plotting requires --kind KIND. "
                f"Run `carnopy inspect {source}` to list compatible plots."
            )
        normalized_kind = normalize_public_plot_kind(kind)
        if normalized_kind in {"property_curves", "property_heatmap"} and property_name is None:
            raise VisualizationError(
                f"{kind} requires --property PROPERTY. "
                f"Run `carnopy inspect {source}` to list emitted properties and compatible plots."
            )
        if normalized_kind == "property_curves" and x_field is None:
            from carnopy.visualization.io import load_plot_source

            if load_plot_source(source).mode == "property_table":
                raise VisualizationError(
                    "property-table property-curves requires --x temperature or --x pressure. "
                    f"Run `carnopy inspect {source}` to list compatible plots."
                )
        if normalized_kind == "property_curves" and color_scale is not None:
            raise VisualizationError("--color-scale is valid only with --kind property-heatmap")
        if normalized_kind == "property_heatmap" and value_scale is not None:
            raise VisualizationError("--value-scale is valid only with --kind property-curves")
        if normalized_kind in {"property_curves", "property_heatmap"} and (
            x_scale is not None or y_scale is not None
        ):
            raise VisualizationError("--x-scale and --y-scale are valid only with xy, pv, or ts")
        exact_filters = tuple(parse_exact_filter(value) for value in (filters or ()))
        series_selections = parse_series_selections(series or ())
        unit_selections = parse_display_units(display_units or ())
        result = plot_dataset(
            source,
            property_name=property_name,
            kind=normalized_kind,
            x=x_field,
            y=y_field,
            group_by=group_by,
            fluids=fluids,
            filters=exact_filters,
            series=series_selections,
            display_units={selection.field: selection.unit for selection in unit_selections},
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
