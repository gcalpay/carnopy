from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from carnopy.api import generate_dataset, validate_config
from carnopy.backends import CoolPropBackend
from carnopy.domain.failures import CarnopyError, ConfigError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    help="Generate reproducible CoolProp-derived thermophysical datasets.",
)


@app.command("validate")
def validate_command(
    config: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Validate a configuration without evaluating thermodynamic rows."""
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


@app.command("generate")
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


@app.command("fluids")
def fluids_command() -> None:
    """List pure fluids supported by the installed CoolProp backend."""
    backend = CoolPropBackend()
    typer.echo(f"CoolProp {backend.version}")
    for fluid in backend.list_fluids():
        aliases = ", ".join(backend.aliases_for(fluid))
        typer.echo(f"{fluid}: {aliases}")
