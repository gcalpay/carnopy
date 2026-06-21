from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from carnopy._version import __version__
from carnopy.cli import app

runner = CliRunner()
MISSING_VISUALIZATION_MESSAGE = (
    "Plotting requires the visualization extra.\n\n"
    "For an isolated CLI:\n"
    '  uv tool install --force "carnopy[viz]"\n\n'
    "With pip:\n"
    '  python -m pip install "carnopy[viz]"'
)


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


def test_version_is_lightweight_and_exact() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == f"carnopy {__version__}\n"


def test_root_help_has_complete_summaries_at_narrow_width() -> None:
    result = runner.invoke(app, ["--help"], terminal_width=48)
    assert result.exit_code == 0
    assert "validate  Check a configuration." in result.stdout
    assert "generate  Generate an immutable run." in result.stdout
    assert "fluids    List backend fluids." in result.stdout
    assert "plot      Plot a generated dataset." in result.stdout


def test_subcommand_help_retains_detailed_descriptions() -> None:
    expectations = {
        "validate": "without evaluating thermodynamic rows",
        "generate": "finalize one immutable dataset run",
        "fluids": "available from the current backend",
        "plot": "from a vapor-mass-fraction dataset",
    }
    for command, description in expectations.items():
        result = runner.invoke(app, [command, "--help"], terminal_width=80)
        assert result.exit_code == 0
        assert description in result.stdout


def test_plot_help_describes_inputs_and_constrained_choices() -> None:
    result = runner.invoke(app, ["plot", "--help"], terminal_width=100)
    assert result.exit_code == 0
    required_content = (
        "Run directory, CSV, or Parquet file.",
        "--property PROPERTY",
        "Semantic property, e.g. mass_density.",
        "--kind [curves|contour]",
        "--fluid FLUID",
        "Repeat --fluid to select multiple fluids.",
        "--scale [linear|log]",
        "--coordinate [pressure|temperature]",
        "--output PATH",
        "--show",
    )
    for content in required_content:
        assert content in result.stdout


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--kind", "surface"),
        ("--scale", "automatic"),
        ("--coordinate", "enthalpy"),
    ],
)
def test_plot_choices_are_rejected_by_cli_parser(option: str, value: str) -> None:
    result = runner.invoke(
        app,
        ["plot", "missing.csv", "--property", "mass_density", option, value],
    )
    assert result.exit_code == 2
    assert f"Invalid value for '{option}'" in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["--version"],
        ["validate", "--help"],
        ["generate", "--help"],
        ["fluids", "--help"],
        ["plot", "--help"],
    ],
)
def test_help_and_version_do_not_load_scientific_dependencies(arguments: list[str]) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    script = f"""
import sys
from typer.testing import CliRunner
from carnopy.cli import app

result = CliRunner().invoke(app, {arguments!r})
if result.exit_code != 0:
    raise SystemExit(result.output)

for module_name in ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib"):
    if module_name in sys.modules:
        raise SystemExit(f"{{module_name}} imported by command")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_missing_matplotlib_message_is_exact(
    vapor_config_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    from carnopy.api import generate_dataset

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    original_import = builtins.__import__

    def block_matplotlib(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError("controlled missing Matplotlib")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", block_matplotlib)
    from carnopy.visualization.models import VisualizationDependencyError
    from carnopy.visualization.render import import_matplotlib

    with pytest.raises(VisualizationDependencyError) as error:
        import_matplotlib()
    assert str(error.value) == MISSING_VISUALIZATION_MESSAGE

    result = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--property",
            "mass_density",
            "--output",
            str(tmp_path / "density.png"),
        ],
    )
    assert result.exit_code == 1
    assert result.output == f"{MISSING_VISUALIZATION_MESSAGE}\n"


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
