from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import CoolProp.CoolProp as CP
import pytest
from typer.testing import CliRunner

from carnopy.api import generate_dataset
from carnopy.cli import app
from carnopy.visualization.inspect import inspect_plot_source

runner = CliRunner()


def _write_property_config(
    path: Path,
    *,
    fluids: str = "Propane",
    properties: str = "mass_density, specific_entropy",
) -> Path:
    path.write_text(
        f"""
schema_version: 1
backend: coolprop
mode: property_table
fluids: [{fluids}]
grid:
  temperature: {{kind: explicit, values: [300, 310], unit: K}}
  pressure: {{kind: explicit, values: [1, 2], unit: bar}}
properties: [{properties}]
""",
        encoding="utf-8",
    )
    return path


def test_inspect_reports_available_plot_contracts(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(
            tmp_path / "multi.yaml",
            fluids="Propane, Isobutane",
        ),
        output_root=tmp_path / "runs",
    )
    inspection = inspect_plot_source(run.output_directory)

    assert inspection.mode == "property_table"
    assert inspection.integrity == "verified"
    assert inspection.fluids == ("IsoButane", "n-Propane")
    assert inspection.valid_rows == 8
    assert inspection.invalid_rows == 0
    assert inspection.properties == ("mass_density", "specific_entropy")
    assert inspection.plot_kinds == (
        "property-curves",
        "property-heatmap",
        "xy",
        "pv",
        "ts",
    )
    assert any("--property mass_density" in example for example in inspection.examples)
    assert any("--fluid IsoButane" in example for example in inspection.examples)

    result = runner.invoke(app, ["inspect", str(run.output_directory)])
    assert result.exit_code == 0, result.output
    assert "Mode: property_table" in result.output
    assert "temperature: 2 level(s)" in result.output
    assert "Compatible plot kinds:" in result.output


def test_inspect_json_reports_identity_ranges_failures_and_display_units(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_property_config(
            tmp_path / "inspect.yaml",
            properties="mass_density, specific_enthalpy, specific_entropy",
        ),
        output_root=tmp_path / "runs",
    )
    result = runner.invoke(
        app,
        ["inspect", str(run.output_directory), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["inspection_schema_version"] == 1
    assert payload["source"]["integrity"] == "verified"
    assert payload["identity"]["run_id"] == run.run_id
    assert payload["backend"]["name"] == "coolprop"
    assert payload["rows"] == {"total": 4, "valid": 4, "invalid": 0}
    assert payload["phase_counts"]
    assert payload["failure_counts"] == {
        "code": {},
        "layer": {},
        "property": {},
    }
    enthalpy = next(item for item in payload["properties"] if item["name"] == "specific_enthalpy")
    assert enthalpy["minimum"] is not None
    assert enthalpy["maximum"] is not None
    assert payload["display_units"]["pressure"] == ["Pa", "kPa", "MPa", "bar"]
    property_curves = next(
        item for item in payload["plot_capabilities"] if item["kind"] == "property-curves"
    )
    assert property_curves["series_fields"] == ["pressure", "temperature"]


def test_inspect_writes_exclusive_visualization_starter(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(tmp_path / "config.yaml"),
        output_root=tmp_path / "runs",
    )
    output = tmp_path / "plots.yaml"
    result = runner.invoke(
        app,
        [
            "inspect",
            str(run.output_directory),
            "--write-visualization",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == (
        "visualization:\n"
        "  format: png\n"
        "  plots:\n"
        "  - name: mass-density-curves\n"
        "    kind: property_curves\n"
        "    property: mass_density\n"
        "    x: temperature\n"
    )
    second = runner.invoke(
        app,
        [
            "inspect",
            str(run.output_directory),
            "--write-visualization",
            str(output),
        ],
    )
    assert second.exit_code == 2
    assert "refusing to overwrite" in second.output


def test_inspect_conditionally_excludes_unavailable_diagrams(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(
            tmp_path / "enthalpy.yaml",
            properties="specific_enthalpy",
        ),
        output_root=tmp_path / "runs",
    )
    inspection = inspect_plot_source(run.output_directory)
    assert "pv" not in inspection.plot_kinds
    assert "ts" not in inspection.plot_kinds


def test_inspect_reports_invalid_rows(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(
            tmp_path / "invalid.yaml",
            properties="surface_tension",
        ),
        output_root=tmp_path / "runs",
    )
    inspection = inspect_plot_source(run.output_directory)
    assert inspection.valid_rows == 0
    assert inspection.invalid_rows == 4
    assert inspection.properties == ("surface_tension",)


@pytest.mark.parametrize(
    ("mode", "grid", "expected_sampling"),
    [
        (
            "saturation_table",
            "pressure: {kind: explicit, values: [1, 2], unit: bar}",
            ("pressure:",),
        ),
        (
            "vapor_mass_fraction_table",
            (
                "pressure: {kind: explicit, values: [1, 2], unit: bar}\n"
                "  vapor_mass_fraction: "
                '{kind: explicit, values: [0, 0.5, 1], unit: "1"}'
            ),
            ("pressure:", "vapor_mass_fraction:"),
        ),
    ],
)
def test_inspect_supports_saturation_modes(
    tmp_path: Path,
    mode: str,
    grid: str,
    expected_sampling: tuple[str, ...],
) -> None:
    config = tmp_path / f"{mode}.yaml"
    config.write_text(
        f"""
schema_version: 1
backend: coolprop
mode: {mode}
fluids: [Propane]
grid:
  {grid}
properties: [mass_density, specific_entropy]
""",
        encoding="utf-8",
    )
    run = generate_dataset(config, output_root=tmp_path / f"{mode}-runs")
    inspection = inspect_plot_source(run.output_directory)
    assert all(
        any(item.startswith(prefix) for item in inspection.sampling) for prefix in expected_sampling
    )
    assert "property-curves" in inspection.plot_kinds


def test_plot_errors_point_to_inspection(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(tmp_path / "config.yaml"),
        output_root=tmp_path / "runs",
    )
    missing_property = runner.invoke(
        app,
        ["plot", str(run.output_directory), "--kind", "property-curves", "--x", "temperature"],
    )
    assert missing_property.exit_code == 2
    assert "requires --property PROPERTY" in missing_property.output
    assert "carnopy inspect" in missing_property.output

    missing_x = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--kind",
            "property-curves",
            "--property",
            "mass_density",
        ],
    )
    assert missing_x.exit_code == 2
    assert "requires --x temperature or --x pressure" in missing_x.output


def test_batch_plot_accepts_visualization_only_and_full_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = generate_dataset(
        _write_property_config(tmp_path / "config.yaml"),
        output_root=tmp_path / "runs",
    )

    def reject_backend_call(*_args: object, **_kwargs: object) -> float:
        raise AssertionError("batch plotting must not call CoolProp")

    monkeypatch.setattr(CP, "PropsSI", reject_backend_call)
    visualization_only = tmp_path / "plots.yaml"
    visualization_only.write_text(
        """
visualization:
  plots:
    - name: density-curves
      kind: property_curves
      property: mass_density
      x: temperature
""",
        encoding="utf-8",
    )
    first = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(visualization_only),
            "--figures-out",
            str(tmp_path / "figures-one"),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-one")},
    )
    assert first.exit_code == 0, first.output
    assert "Visualization status: completed" in first.output

    full = tmp_path / "full.yaml"
    full.write_text(
        """
schema_version: 999
backend: ignored
mode: ignored
visualization:
  plots:
    - name: density-map
      kind: property_heatmap
      property: mass_density
""",
        encoding="utf-8",
    )
    second = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(full),
            "--figures-out",
            str(tmp_path / "figures-two"),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-two")},
    )
    assert second.exit_code == 0, second.output
    report_line = next(
        line for line in second.output.splitlines() if line.startswith("Visualization report:")
    )
    report = json.loads(Path(report_line.partition(":")[2].strip()).read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["outcomes"][0]["name"] == "density-map"


def test_batch_plot_supports_series_and_display_units(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_property_config(
            tmp_path / "config.yaml",
            properties="mass_density, specific_enthalpy",
        ),
        output_root=tmp_path / "runs",
    )
    plots = tmp_path / "plots.yaml"
    plots.write_text(
        """
visualization:
  display_units:
    pressure: bar
  plots:
    - name: enthalpy-curves
      kind: property_curves
      property: specific_enthalpy
      x: temperature
      series:
        pressure: [1bar]
      display_units:
        temperature: degC
        specific_enthalpy: kJ/kg
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(plots),
            "--figures-out",
            str(tmp_path / "figures"),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl-units")},
    )
    assert result.exit_code == 0, result.output
    report_line = next(
        line for line in result.output.splitlines() if line.startswith("Visualization report:")
    )
    report = json.loads(Path(report_line.partition(":")[2].strip()).read_text(encoding="utf-8"))
    sidecar = json.loads(Path(report["outcomes"][0]["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["data_selection"]["series"][0]["matched_values"] == [100000.0]
    assert sidecar["data_selection"]["display_units"] == {
        "pressure": "bar",
        "specific_enthalpy": "kJ/kg",
        "temperature": "degC",
    }


def test_batch_plot_rejects_manual_options_files_and_existing_destination(
    tmp_path: Path,
) -> None:
    run = generate_dataset(
        _write_property_config(tmp_path / "config.yaml"),
        output_root=tmp_path / "runs",
    )
    plots = tmp_path / "plots.yaml"
    plots.write_text(
        """
visualization:
  plots:
    - name: density-curves
      kind: property_curves
      property: mass_density
      x: temperature
""",
        encoding="utf-8",
    )
    conflict = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(plots),
            "--kind",
            "pv",
        ],
    )
    assert conflict.exit_code == 2
    assert "cannot be combined" in conflict.output

    file_source = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory / "dataset.parquet"),
            "--config",
            str(plots),
        ],
    )
    assert file_source.exit_code == 2
    assert "requires an immutable run directory" in file_source.output

    inside_run = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(plots),
            "--figures-out",
            str(run.output_directory),
        ],
    )
    assert inside_run.exit_code == 2
    assert "cannot be inside the immutable run" in inside_run.output

    figures = tmp_path / "figures"
    first = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(plots),
            "--figures-out",
            str(figures),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl")},
    )
    assert first.exit_code == 0
    second = runner.invoke(
        app,
        [
            "plot",
            str(run.output_directory),
            "--config",
            str(plots),
            "--figures-out",
            str(figures),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl")},
    )
    assert second.exit_code == 2
    assert "already exists" in second.output


def test_inspect_and_batch_execution_do_not_import_coolprop(tmp_path: Path) -> None:
    run = generate_dataset(
        _write_property_config(tmp_path / "config.yaml"),
        output_root=tmp_path / "runs",
    )
    plots = tmp_path / "plots.yaml"
    plots.write_text(
        """
visualization:
  plots:
    - name: density-curves
      kind: property_curves
      property: mass_density
      x: temperature
""",
        encoding="utf-8",
    )
    script = """
import sys
from pathlib import Path
from carnopy.visualization.automation import render_existing_run_visualizations
from carnopy.visualization.inspect import inspect_plot_source

inspect_plot_source(sys.argv[1])
render_existing_run_visualizations(
    source_run=Path(sys.argv[1]),
    config_path=Path(sys.argv[2]),
    figures_root=Path(sys.argv[3]),
)
raise SystemExit("CoolProp" in sys.modules)
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(run.output_directory),
            str(plots),
            str(tmp_path / "subprocess-figures"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(tmp_path / "mpl-subprocess"),
        },
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
