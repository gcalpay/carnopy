from __future__ import annotations

import json
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
    assert "Backend: coolprop" in result.stdout
    assert "(model: heos)" in result.stdout
    assert "Thermodynamic row validity will be determined during generation" in result.stdout
    assert "Dataset formats: csv, parquet" in result.stdout


def test_properties_reports_model_capabilities() -> None:
    result = runner.invoke(app, ["properties"])
    assert result.exit_code == 0
    assert "MODELS" in result.stdout
    assert "mass_density" in result.stdout
    assert "heos,pr,srk" in result.stdout
    dynamic_line = next(
        line for line in result.stdout.splitlines() if line.startswith("dynamic_viscosity")
    )
    assert "no        heos         -" in dynamic_line
    assert "heos,pr,srk" not in dynamic_line


def test_fluids_can_be_listed_for_a_selected_model() -> None:
    result = runner.invoke(app, ["fluids", "--model", "pr"])
    assert result.exit_code == 0
    assert "CoolProp" in result.stdout
    assert "(model: pr)" in result.stdout
    assert "n-Propane:" in result.stdout
    assert "\nAir:" not in result.stdout


def test_generate_creates_output(property_config_path: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["generate", str(property_config_path), "--out", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Run status: completed" in result.stdout
    assert "(model: heos)" in result.stdout
    assert list(tmp_path.iterdir())


def test_zero_valid_rows_exit_three(tmp_path: Path) -> None:
    config = tmp_path / "invalid_rows.yaml"
    config.write_text(
        """
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
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
    assert "available from one CoolProp model" in fluids.stdout
    assert "--model [heos|pr|srk]" in fluids.stdout


def test_version_is_lightweight_and_exact() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == f"carnopy {__version__}\n"


def test_root_help_has_complete_summaries_at_narrow_width() -> None:
    result = runner.invoke(app, ["--help"], terminal_width=48)
    assert result.exit_code == 0
    for command, summary in (
        ("validate", "Check a configuration."),
        ("generate", "Generate an immutable run."),
        ("sweep", "Generate a model sweep."),
        ("prepare", "Prepare ML-ready data."),
        ("fluids", "List backend fluids."),
        ("properties", "List dataset properties."),
        ("inspect", "Inspect generated artifacts."),
        ("init", "Create a starter configuration."),
        ("plot", "Plot a generated dataset."),
    ):
        assert command in result.stdout
        assert summary in result.stdout
    assert "init → edit → optional validate" in result.stdout
    assert "generate/sweep" in result.stdout
    assert "optional prepare" in result.stdout


def test_subcommand_help_retains_detailed_descriptions() -> None:
    expectations = {
        "validate": "without evaluating thermodynamic rows",
        "generate": "Generation performs configuration",
        "sweep": "multiple backend models",
        "prepare": "optional split scenarios",
        "fluids": "available from one CoolProp model",
        "properties": "semantic properties accepted",
        "inspect": "without backend calls",
        "init": "commented configuration template",
        "plot": "without backend calls or interpolation",
    }
    for command, description in expectations.items():
        result = runner.invoke(app, [command, "--help"], terminal_width=80)
        assert result.exit_code == 0
        assert description in result.stdout


def test_generate_help_includes_configured_figure_root() -> None:
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--figures-out DIRECTORY" in result.stdout


def test_prepare_help_documents_current_artifacts_without_future_tensor_exports() -> None:
    result = runner.invoke(app, ["prepare", "--help"])
    assert result.exit_code == 0
    assert "deterministic Parquet artifacts" in result.stdout
    assert "optional split scenarios" in result.stdout
    assert "log10" in result.stdout
    assert "standard" in result.stdout
    assert "minmax" in result.stdout
    assert "SafeTensors" not in result.stdout
    assert "PyTorch" not in result.stdout


def test_plot_help_describes_inputs_and_constrained_choices() -> None:
    result = runner.invoke(app, ["plot", "--help"], terminal_width=100)
    assert result.exit_code == 0
    required_content = (
        "Run directory, CSV, or Parquet file.",
        "--property PROPERTY",
        "--kind KIND",
        "--config FILE",
        "--figures-out DIRECTORY",
        "Manual plot kind:",
        "property-curves",
        "--x FIELD",
        "--y FIELD",
        "--group-by FIELD",
        "--fluid FLUID",
        "Repeat --fluid to select multiple fluids.",
        "--filter FIELD=VALUE",
        "--series FIELD=VALUE",
        "--display-unit FIELD=UNIT",
        "--value-scale [linear|log]",
        "--color-scale [linear|log]",
        "--x-scale [linear|log]",
        "--y-scale [linear|log]",
        "--saturation-coordinate [pressure|temperature]",
        "--output PATH",
        "--show",
    )
    for content in required_content:
        assert content in result.stdout


def test_inspect_help_exposes_json_and_visualization_writer() -> None:
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    assert "--format [text|json]" in result.stdout
    assert "--write-visualization PATH" in result.stdout


def test_plot_scale_choices_are_rejected_by_cli_parser() -> None:
    result = runner.invoke(
        app,
        [
            "plot",
            "missing.csv",
            "--property",
            "mass_density",
            "--kind",
            "property-curves",
            "--value-scale",
            "automatic",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--value-scale'" in result.output


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("curves", "replaced by 'property-curves'"),
        ("heatmap", "Use --kind property-heatmap"),
        ("contour", "Contour plots interpolate"),
    ],
)
def test_plot_legacy_kinds_have_migration_guidance(
    vapor_config_path: Path,
    tmp_path: Path,
    kind: str,
    message: str,
) -> None:
    from carnopy.api import generate_dataset

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    result = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--property",
            "mass_density",
            "--kind",
            kind,
        ],
    )
    assert result.exit_code == 2
    assert message in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["--version"],
        ["validate", "--help"],
        ["generate", "--help"],
        ["sweep", "--help"],
        ["prepare", "--help"],
        ["fluids", "--help"],
        ["properties", "--help"],
        ["inspect", "--help"],
        ["init", "--help"],
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
            "--kind",
            "property-curves",
            "--output",
            str(tmp_path / "density.png"),
        ],
    )
    assert result.exit_code == 1
    assert result.output == f"{MISSING_VISUALIZATION_MESSAGE}\n"


def test_init_creates_packaged_template_and_prints_workflow(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "property.yaml"
    result = runner.invoke(
        app,
        [
            "init",
            "property_table",
            str(output),
            "--create-parents",
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert "mode: property_table" in output.read_text(encoding="utf-8")
    assert f"carnopy validate {output.resolve()}" in result.stdout
    assert f"carnopy generate {output.resolve()}" in result.stdout


def test_init_full_appends_exhaustive_reference(tmp_path: Path) -> None:
    output = tmp_path / "full.yaml"
    result = runner.invoke(
        app,
        ["init", "property_table", str(output), "--full"],
    )
    assert result.exit_code == 0, result.output
    content = output.read_text(encoding="utf-8")
    assert "mode: property_table" in content
    assert "Carnopy configuration reference" in content
    assert "property_heatmap" in content
    assert "kind: logspace" in content


def test_init_help_documents_full_reference() -> None:
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "Configuration template type" in result.stdout
    assert "--full" in result.stdout
    assert "exhaustive commented configuration reference" in result.stdout


def test_init_preparation_prints_prepare_next_step(tmp_path: Path) -> None:
    output = tmp_path / "preparation.yaml"
    result = runner.invoke(app, ["init", "preparation", str(output)])
    assert result.exit_code == 0, result.output
    assert "document_type: preparation" in output.read_text(encoding="utf-8")
    assert f"carnopy prepare SOURCE --config {output.resolve()}" in result.stdout


def test_init_refuses_wrong_suffix_existing_file_and_missing_noninteractive_parent(
    tmp_path: Path,
) -> None:
    wrong_suffix = runner.invoke(app, ["init", "property_table", str(tmp_path / "config.txt")])
    assert wrong_suffix.exit_code == 2
    assert "must end in .yaml or .yml" in wrong_suffix.output

    existing = tmp_path / "existing.yaml"
    existing.write_text("preserve me\n", encoding="utf-8")
    existing_result = runner.invoke(app, ["init", "property_table", str(existing)])
    assert existing_result.exit_code == 2
    assert "refusing to overwrite" in existing_result.output
    assert existing.read_text(encoding="utf-8") == "preserve me\n"

    missing_parent = runner.invoke(
        app,
        ["init", "saturation_table", str(tmp_path / "missing" / "config.yaml")],
    )
    assert missing_parent.exit_code == 2
    assert "--create-parents" in missing_parent.output


def test_properties_lists_semantic_registry_details() -> None:
    result = runner.invoke(app, ["properties"])
    assert result.exit_code == 0
    assert "PROPERTY" in result.stdout
    assert "specific_enthalpy" in result.stdout
    assert "specific_enthalpy_J_kg" in result.stdout
    assert "kinematic_viscosity" in result.stdout
    assert "dynamic_viscosity, mass_density" in result.stdout


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
            "--kind",
            "property-curves",
            "--output",
            str(output),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl")},
    )
    assert result.exit_code == 0, result.stdout
    assert output.is_file()
    assert output.with_suffix(".plot.json").is_file()
    assert "Source integrity: verified" in result.stdout


def test_plot_command_accepts_repeated_series_and_display_units(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    from carnopy.api import generate_dataset

    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    output = tmp_path / "selected.png"
    result = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "property-curves",
            "--property",
            "mass_density",
            "--x",
            "temperature",
            "--series",
            "pressure=1bar",
            "--series",
            "pressure=5bar",
            "--display-unit",
            "temperature=degC",
            "--display-unit",
            "pressure=bar",
            "--output",
            str(output),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-series")},
    )
    assert result.exit_code == 0, result.output
    sidecar = json.loads(output.with_suffix(".plot.json").read_text(encoding="utf-8"))
    assert sidecar["normalized_request"]["series"] == [
        {"field": "pressure", "values": [100000.0, 500000.0]}
    ]
    assert sidecar["data_selection"]["display_units"] == {
        "pressure": "bar",
        "temperature": "degC",
    }


def test_plot_command_exports_xy_and_pv(
    tmp_path: Path,
) -> None:
    from carnopy.api import generate_dataset

    config = tmp_path / "diagram.yaml"
    config.write_text(
        """
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [250, 260], unit: K}
  pressure: {kind: explicit, values: [1, 2], unit: bar}
properties: [mass_density, specific_enthalpy, specific_entropy]
""",
        encoding="utf-8",
    )
    run = generate_dataset(config, output_root=tmp_path / "runs")
    xy_output = tmp_path / "xy.png"
    xy = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "xy",
            "--x",
            "specific_enthalpy",
            "--y",
            "specific_entropy",
            "--group-by",
            "pressure",
            "--output",
            str(xy_output),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-xy")},
    )
    assert xy.exit_code == 0, xy.output
    assert xy_output.is_file()

    pv_output = tmp_path / "pv.png"
    pv = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "pv",
            "--output",
            str(pv_output),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-pv")},
    )
    assert pv.exit_code == 0, pv.output
    assert pv_output.is_file()


def test_plot_cli_validates_kind_specific_options(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    from carnopy.api import generate_dataset

    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    missing_property = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "property-curves",
        ],
    )
    assert missing_property.exit_code == 2
    assert "requires --property" in missing_property.output

    fixed_axes = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "pv",
            "--x",
            "pressure",
        ],
    )
    assert fixed_axes.exit_code == 2
    assert "fixed axes" in fixed_axes.output
