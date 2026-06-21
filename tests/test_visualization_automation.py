from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from carnopy.api import generate_dataset, validate_config
from carnopy.cli import app
from carnopy.config.io import load_config_file
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.pipeline import validate_loaded_config
from carnopy.visualization.models import VisualizationDependencyError

runner = CliRunner()


def _write_property_config(
    path: Path,
    *,
    visualization: str = "",
    properties: str = "mass_density, specific_enthalpy, specific_entropy",
) -> Path:
    path.write_text(
        f"""
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {{kind: explicit, values: [250, 260], unit: K}}
  pressure: {{kind: explicit, values: [1, 2], unit: bar}}
properties: [{properties}]
{visualization}
""",
        encoding="utf-8",
    )
    return path


def test_visualization_is_excluded_from_dataset_identity(tmp_path: Path) -> None:
    plain = _write_property_config(tmp_path / "plain.yaml")
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
""",
    )

    plain_run = generate_dataset(plain, output_root=tmp_path / "plain-runs")
    configured_run = generate_dataset(
        configured,
        output_root=tmp_path / "configured-runs",
        figures_root=tmp_path / "figures",
    )

    assert configured_run.visualization is not None
    assert plain_run.spec_id == configured_run.spec_id
    assert plain_run.generation_context_id == configured_run.generation_context_id
    assert (
        plain_run.output_directory.joinpath("config.normalized.json").read_bytes()
        == configured_run.output_directory.joinpath("config.normalized.json").read_bytes()
    )
    plain_metadata = json.loads(
        plain_run.output_directory.joinpath("metadata.json").read_text(encoding="utf-8")
    )
    configured_metadata = json.loads(
        configured_run.output_directory.joinpath("metadata.json").read_text(encoding="utf-8")
    )
    assert (
        plain_metadata["normalized_config_sha256"]
        == configured_metadata["normalized_config_sha256"]
    )
    assert plain_metadata["raw_config_sha256"] != configured_metadata["raw_config_sha256"]
    assert "visualization" not in configured_metadata


def test_visualization_request_normalization_and_static_validation(tmp_path: Path) -> None:
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  format: png
  fluids: [Propane]
  filters:
    phase: gas
  plots:
    - name: density_vs_temperature
      kind: property-curves
      property: mass_density
      x: temperature
      filters:
        phase: GAS
""",
    )
    validated = validate_loaded_config(load_config_file(configured))
    assert validated.visualization is not None
    request = validated.visualization.requests[0]
    assert request.kind == "property_curves"
    assert request.fluids == ("n-Propane",)
    assert request.filters[0].value == "gas"
    assert validated.visualization.visualization_request_id.startswith("viz-")

    missing_property = _write_property_config(
        tmp_path / "missing-property.yaml",
        properties="mass_density",
        visualization="""
visualization:
  plots:
    - name: temperature_entropy
      kind: ts
""",
    )
    with pytest.raises(ConfigError, match="specific_entropy"):
        validate_config(missing_property)

    conflicting = _write_property_config(
        tmp_path / "conflicting.yaml",
        visualization="""
visualization:
  filters:
    pressure: 100000
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
      filters:
        pressure: 200000
""",
    )
    with pytest.raises(ConfigError, match="conflicting"):
        validate_config(conflicting)


def test_visualization_fluid_aliases_use_existing_normalization_mapping(
    tmp_path: Path,
) -> None:
    config = tmp_path / "multifluid.yaml"
    config.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane, Water]
grid:
  temperature: {kind: explicit, values: [300, 310], unit: K}
  pressure: {kind: explicit, values: [1, 2], unit: bar}
properties: [mass_density]
visualization:
  fluids: [Propane]
  plots:
    - name: propane_density
      kind: property_curves
      property: mass_density
      x: temperature
""",
        encoding="utf-8",
    )
    validated = validate_loaded_config(load_config_file(config))
    assert validated.visualization is not None
    assert validated.visualization.requests[0].fluids == ("n-Propane",)


def test_configured_visualization_writes_report_and_shared_request_id(
    tmp_path: Path,
) -> None:
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
    - name: density_map
      kind: property_heatmap
      property: mass_density
    - name: enthalpy_entropy
      kind: xy
      x: specific_enthalpy
      y: specific_entropy
      group_by: pressure
    - name: pressure_specific_volume
      kind: pv
    - name: temperature_entropy
      kind: ts
""",
    )
    run = generate_dataset(
        configured,
        output_root=tmp_path / "runs",
        figures_root=tmp_path / "figures",
    )

    assert run.visualization is not None
    assert run.visualization.status == "completed"
    assert run.visualization.succeeded_plot_count == 5
    assert run.visualization.report_path is not None
    report = json.loads(run.visualization.report_path.read_text(encoding="utf-8"))
    assert report["visualization_request_id"] == run.visualization.visualization_request_id
    assert report["status"] == "completed"
    assert [outcome["name"] for outcome in report["outcomes"]] == [
        "density_vs_temperature",
        "density_map",
        "enthalpy_entropy",
        "pressure_specific_volume",
        "temperature_entropy",
    ]
    for outcome in report["outcomes"]:
        sidecar = json.loads(Path(outcome["sidecar_path"]).read_text(encoding="utf-8"))
        assert sidecar["visualization_request_id"] == run.visualization.visualization_request_id
        assert sidecar["normalized_request"]["name"] == outcome["name"]
    metadata = json.loads(
        run.output_directory.joinpath("metadata.json").read_text(encoding="utf-8")
    )
    assert all("figure" not in name for name in metadata["artifact_hashes"])


def test_configured_plot_failure_preserves_run_and_successes(tmp_path: Path) -> None:
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
    - name: no_matching_pressure
      kind: property_curves
      property: mass_density
      x: temperature
      filters:
        pressure: 999999
""",
    )
    result = runner.invoke(
        app,
        [
            "generate",
            str(configured),
            "--out",
            str(tmp_path / "runs"),
            "--figures-out",
            str(tmp_path / "figures"),
        ],
        env={"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(tmp_path / "mpl")},
    )

    assert result.exit_code == 1, result.output
    assert "Visualization status: completed_with_failures" in result.output
    output_line = next(
        line for line in result.output.splitlines() if line.startswith("Output directory:")
    )
    assert Path(output_line.partition(":")[2].strip()).is_dir()
    report_line = next(
        line for line in result.output.splitlines() if line.startswith("Visualization report:")
    )
    report = json.loads(Path(report_line.partition(":")[2].strip()).read_text(encoding="utf-8"))
    assert [outcome["status"] for outcome in report["outcomes"]] == [
        "completed",
        "failed",
    ]
    assert Path(report["outcomes"][0]["image_path"]).is_file()


def test_zero_valid_rows_skip_configured_visualization(tmp_path: Path) -> None:
    config = _write_property_config(
        tmp_path / "zero-valid.yaml",
        properties="surface_tension",
        visualization="""
visualization:
  plots:
    - name: surface_tension
      kind: property_curves
      property: surface_tension
      x: temperature
""",
    )
    run = generate_dataset(
        config,
        output_root=tmp_path / "runs",
        figures_root=tmp_path / "figures",
    )
    assert run.run_status == "completed_zero_valid_rows"
    assert run.visualization is not None
    assert run.visualization.status == "skipped_zero_valid_rows"
    assert run.visualization.skipped_plot_count == 1
    assert run.visualization.report_path is not None


def test_visualization_dependency_failure_prevents_run_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
""",
    )

    def missing_dependency() -> None:
        raise VisualizationDependencyError("controlled missing Matplotlib")

    monkeypatch.setattr(
        "carnopy.pipeline.ensure_visualization_dependencies",
        missing_dependency,
    )
    output_root = tmp_path / "runs"
    with pytest.raises(VisualizationDependencyError, match="controlled"):
        generate_dataset(configured, output_root=output_root)
    assert not output_root.exists()
    validation = runner.invoke(app, ["validate", str(configured)])
    assert validation.exit_code == 1
    assert "Validation environment failed: controlled missing Matplotlib" in validation.output


def test_dataset_and_configured_figure_directories_cannot_collide(
    tmp_path: Path,
) -> None:
    configured = _write_property_config(
        tmp_path / "configured.yaml",
        visualization="""
visualization:
  plots:
    - name: density_vs_temperature
      kind: property_curves
      property: mass_density
      x: temperature
""",
    )
    shared_root = tmp_path / "shared"
    with pytest.raises(OutputError, match="visualization output directory"):
        generate_dataset(
            configured,
            output_root=shared_root,
            figures_root=shared_root,
        )
    assert list(shared_root.iterdir()) == []
