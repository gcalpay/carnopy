from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset, generate_model_sweep
from carnopy.config.io import load_sweep_config_file
from carnopy.domain.failures import ConfigError, OutputError
from carnopy.provenance import DATASET_SCHEMA_VERSION
from carnopy.templates import template_text


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _property_sweep_config(
    *,
    properties: str = "properties: [mass_density]",
    pressure_values: str = "[100000]",
    comparison_plots: str = "",
) -> str:
    return f"""schema_version: 2
document_type: model_sweep
backend:
  name: coolprop
  models: [heos, pr]
  reference_model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature:
    kind: explicit
    values: [300, 310]
    unit: K
  pressure:
    kind: explicit
    values: {pressure_values}
    unit: Pa
{properties}
outputs:
  dataset_formats: [parquet]
{comparison_plots}
"""


def test_dataset_schema_v2_records_backend_model(
    tmp_path: Path,
    property_config_path: Path,
) -> None:
    result = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    metadata = json.loads((result.output_directory / "metadata.json").read_text())
    frame = pd.read_parquet(result.output_directory / "dataset.parquet")

    assert DATASET_SCHEMA_VERSION == 2
    assert metadata["dataset_schema_version"] == 2
    assert "backend_model" in frame.columns
    assert frame["backend_model"].unique().tolist() == ["heos"]


def test_model_sweep_normalizes_models_and_rejects_duplicates(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "sweep.yaml",
        """schema_version: 2
document_type: model_sweep
backend:
  name: coolprop
  models: [HEOS, heos]
  reference_model: HEOS
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300], unit: K}
  pressure: {kind: explicit, values: [100000], unit: Pa}
properties: [mass_density]
""",
    )
    with pytest.raises(ConfigError, match="duplicate backend models"):
        load_sweep_config_file(config)


def test_model_sweep_rejects_known_unsupported_property(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "sweep.yaml",
        _property_sweep_config(properties="properties: [dynamic_viscosity]"),
    )
    with pytest.raises(ConfigError, match="do not support requested properties"):
        generate_model_sweep(config, output_root=tmp_path / "outputs")


def test_model_sweep_writes_child_runs_and_comparison_tables(tmp_path: Path) -> None:
    config = _write(tmp_path / "sweep.yaml", _property_sweep_config())

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.sweep_status == "completed"
    assert result.output_directory.parent == tmp_path / "outputs"
    assert result.values_path is not None and result.values_path.is_file()
    assert result.deltas_path is not None and result.deltas_path.is_file()
    assert {run.backend_model for run in result.child_runs} == {"heos", "pr"}

    for child in result.child_runs:
        assert ".staging" not in str(child.output_directory)
        metadata = json.loads((child.output_directory / "metadata.json").read_text())
        assert metadata["output_directory"] == str(child.output_directory)
        frame = pd.read_parquet(child.output_directory / "dataset.parquet")
        assert {"state_key", "state_key_version", "state_key_temperature_index"}.issubset(
            frame.columns
        )
        assert frame["backend_model"].unique().tolist() == [child.backend_model]

    values = pd.read_parquet(result.values_path)
    deltas = pd.read_parquet(result.deltas_path)
    assert set(values["backend_model"]) == {"heos", "pr"}
    assert set(values["property"]) == {"mass_density"}
    assert set(deltas["backend_model"]) == {"pr"}
    assert "signed_absolute_difference" in deltas.columns
    assert "signed_relative_difference" in deltas.columns
    assert values["state_key"].notna().all()


def test_model_sweep_concise_template_runs_without_comparison_plots(tmp_path: Path) -> None:
    config = _write(tmp_path / "sweep.yaml", template_text("model_sweep"))

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.sweep_status == "completed"
    assert result.values_path is not None and result.values_path.is_file()
    assert result.deltas_path is not None and result.deltas_path.is_file()
    assert result.comparison_plot_directory is None
    assert not (result.output_directory / "comparison_plots").exists()


def test_model_sweep_excludes_reference_dependent_deltas(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "sweep.yaml",
        _property_sweep_config(properties="properties: [specific_enthalpy]"),
    )

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.deltas_path is not None
    deltas = pd.read_parquet(result.deltas_path)
    assert set(deltas["unavailable_reason"]) == {"reference_dependent_property_excluded"}
    assert deltas["comparison_valid"].eq(False).all()


def test_model_sweep_comparison_plot_sidecar_records_provenance(tmp_path: Path) -> None:
    comparison = """comparison_plots:
  format: png
  plots:
    - name: propane_density_temperature
      kind: property_comparison
      fluid: Propane
      property: mass_density
      x: temperature
      models: [heos, pr]
"""
    config = _write(tmp_path / "sweep.yaml", _property_sweep_config(comparison_plots=comparison))

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.comparison_plot_directory is not None
    image = result.comparison_plot_directory / "propane_density_temperature.png"
    sidecar = result.comparison_plot_directory / "propane_density_temperature.plot.json"
    payload = json.loads(sidecar.read_text())
    assert image.is_file()
    assert payload["resolved_models"] == ["heos", "pr"]
    assert payload["requested_fluid"] == "Propane"
    assert payload["selected_fluid"] == "n-Propane"
    assert payload["x_axis"] == "temperature"
    assert payload["comparison_artifact_hashes"]["comparison/values.parquet"]


def test_model_sweep_rejects_ambiguous_comparison_plot(tmp_path: Path) -> None:
    comparison = """comparison_plots:
  format: png
  plots:
    - name: ambiguous_density_temperature
      kind: property_comparison
      fluid: Propane
      property: mass_density
      x: temperature
      models: [heos, pr]
"""
    config = _write(
        tmp_path / "sweep.yaml",
        _property_sweep_config(
            pressure_values="[100000, 200000]",
            comparison_plots=comparison,
        ),
    )

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.sweep_status == "incomplete"
    assert result.comparison_report_path is not None
    report = json.loads(result.comparison_report_path.read_text())
    assert report["failed_plot_count"] == 1
    assert "uncontrolled dimensions" in report["outcomes"][0]["error_message"]


def test_model_sweep_fatal_child_failure_finalizes_incomplete_without_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import carnopy.sweeps.pipeline as sweep_pipeline

    original = sweep_pipeline.run_generation

    def fail_second(*args: object, **kwargs: object) -> object:
        loaded = args[0]
        if loaded.model.backend.model == "pr":
            raise OutputError("forced child failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(sweep_pipeline, "run_generation", fail_second)
    config = _write(tmp_path / "sweep.yaml", _property_sweep_config())

    result = generate_model_sweep(config, output_root=tmp_path / "outputs")

    assert result.sweep_status == "incomplete"
    assert result.failure_message == "forced child failure"
    assert len(result.child_runs) == 1
    assert result.values_path is None
    assert result.deltas_path is None
    assert not (result.output_directory / "comparison").exists()
    report = json.loads((result.output_directory / "report.json").read_text())
    assert report["sweep_status"] == "incomplete"
