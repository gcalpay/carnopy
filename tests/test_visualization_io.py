from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset
from carnopy.visualization.io import load_plot_source
from carnopy.visualization.models import VisualizationError


def test_run_directory_prefers_verified_parquet_and_infers_saturation_coordinate(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    source = load_plot_source(run.output_directory)
    assert source.dataset_path.name == "dataset.parquet"
    assert source.source_format == "parquet"
    assert source.source_integrity == "verified"
    assert source.mode == "vapor_mass_fraction_table"
    assert source.saturation_coordinate == "temperature"
    assert source.saturation_coordinate_display_unit == "K"


def test_all_milestone_modes_are_valid_plot_sources(
    property_config_path: Path,
    saturation_config_path: Path,
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    expected = {
        property_config_path: ("property_table", None),
        saturation_config_path: ("saturation_table", "temperature"),
        vapor_config_path: ("vapor_mass_fraction_table", "temperature"),
    }
    for config, (mode, coordinate) in expected.items():
        run = generate_dataset(config, output_root=tmp_path / mode)
        source = load_plot_source(run.output_directory)
        assert source.mode == mode
        assert source.saturation_coordinate == coordinate


def test_existing_long_named_run_directory_remains_readable(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    legacy_directory = run.output_directory.with_name(
        "20260621T172006.270984Z_vapor_mass_fraction_table_712208da178a_c8e28e9f"
    )
    run.output_directory.rename(legacy_directory)
    source = load_plot_source(legacy_directory)
    assert source.dataset_path == legacy_directory / "dataset.parquet"
    assert source.source_integrity == "verified"


def test_direct_csv_uses_sibling_metadata(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    source = load_plot_source(run.output_directory / "dataset.csv")
    assert source.source_format == "csv"
    assert source.source_integrity == "verified"


def test_csv_only_run_is_a_verified_plot_source(tmp_path: Path) -> None:
    config = tmp_path / "csv-only.yaml"
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
  temperature: {kind: explicit, values: [300, 310], unit: K}
  pressure: {kind: explicit, values: [1, 2], unit: bar}
properties: [mass_density]
outputs:
  dataset_formats: [csv]
""",
        encoding="utf-8",
    )
    run = generate_dataset(config, output_root=tmp_path / "runs")
    source = load_plot_source(run.output_directory)
    assert source.dataset_path.name == "dataset.csv"
    assert source.source_format == "csv"
    assert source.source_integrity == "verified"


def test_hash_mismatch_is_rejected(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    parquet = run.output_directory / "dataset.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"modified")
    with pytest.raises(VisualizationError, match="hash mismatch"):
        load_plot_source(run.output_directory)


def test_standalone_source_is_unverified_without_inventing_coordinate(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    standalone = tmp_path / "standalone.csv"
    standalone.write_bytes((run.output_directory / "dataset.csv").read_bytes())
    source = load_plot_source(standalone)
    assert source.source_integrity == "unverified"
    assert source.saturation_coordinate is None


def test_multiple_run_identities_are_rejected(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[0, "run_id"] = "another-run"
    standalone = tmp_path / "mixed.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match="exactly one run_id"):
        load_plot_source(standalone)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("mode", None, "null dataset mode"),
        ("mode", "   ", "blank dataset mode"),
        ("run_id", None, "null run_id"),
        ("run_id", "   ", "blank run_id"),
    ],
)
def test_null_and_blank_dataset_identity_is_rejected_before_filtering(
    vapor_config_path: Path,
    tmp_path: Path,
    column: str,
    value: object,
    message: str,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[0, column] = value
    standalone = tmp_path / f"invalid-{column}.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match=message):
        load_plot_source(standalone)


def test_multiple_modes_are_rejected_before_property_selection(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv")
    frame.loc[0, "mode"] = "property_table"
    standalone = tmp_path / "mixed-mode.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match="exactly one dataset mode"):
        load_plot_source(standalone)


@pytest.mark.parametrize("column", ["case_id", "phase"])
def test_plot_source_requires_ordering_and_phase_columns(
    vapor_config_path: Path,
    tmp_path: Path,
    column: str,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    frame = pd.read_csv(run.output_directory / "dataset.csv").drop(columns=[column])
    standalone = tmp_path / f"missing-{column}.csv"
    frame.to_csv(standalone, index=False)
    with pytest.raises(VisualizationError, match=column):
        load_plot_source(standalone)
