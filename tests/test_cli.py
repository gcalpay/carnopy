from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from carnopy.cli import app

runner = CliRunner()


def test_validate_reports_row_validity_is_deferred(property_config_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(property_config_path)])
    assert result.exit_code == 0
    assert "Thermodynamic row validity will be determined during generation" in result.stdout


def test_generate_creates_output(property_config_path: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["generate", str(property_config_path), "--out", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Run status: completed" in result.stdout
    assert list(tmp_path.iterdir())


def test_zero_valid_rows_exit_three(tmp_path: Path) -> None:
    config = tmp_path / "invalid_rows.yaml"
    config.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300], unit: K}
  pressure: {kind: explicit, values: [1], unit: bar}
properties: [surface_tension]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "runs"
    result = runner.invoke(
        app,
        ["generate", str(config), "--out", str(output_root)],
    )
    assert result.exit_code == 3
    assert "completed_zero_valid_rows" in result.stdout
    assert list(output_root.iterdir())


def test_help_uses_backend_neutral_wording() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "from configured backends" in result.stdout
    fluids = runner.invoke(app, ["fluids", "--help"])
    assert fluids.exit_code == 0
    assert "available from the current backend" in fluids.stdout


def test_plot_command_exports_figure_and_sidecar(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    from carnopy.api import generate_dataset

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "density.png"
    result = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--property",
            "mass_density",
            "--output",
            str(output),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl")},
    )
    assert result.exit_code == 0, result.stdout
    assert output.is_file()
    assert output.with_suffix(".plot.json").is_file()
    assert "Source integrity: verified" in result.stdout
