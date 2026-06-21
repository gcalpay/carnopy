from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset
from carnopy.visualization.io import load_plot_source
from carnopy.visualization.models import VisualizationError


def test_run_directory_prefers_verified_parquet(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    source = load_plot_source(run.output_directory)
    assert source.dataset_path.name == "dataset.parquet"
    assert source.source_format == "parquet"
    assert source.source_integrity == "verified"
    assert source.coordinate == "temperature"
    assert source.coordinate_display_unit == "K"


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


def test_hash_mismatch_is_rejected(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    parquet = run.output_directory / "dataset.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"modified")
    with pytest.raises(VisualizationError, match="hash mismatch"):
        load_plot_source(run.output_directory)


def test_standalone_source_requires_coordinate_and_is_unverified(
    vapor_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(vapor_config_path, output_root=tmp_path / "runs")
    standalone = tmp_path / "standalone.csv"
    standalone.write_bytes((run.output_directory / "dataset.csv").read_bytes())
    with pytest.raises(VisualizationError, match=r"require.*coordinate"):
        load_plot_source(standalone)
    source = load_plot_source(standalone, coordinate="temperature")
    assert source.source_integrity == "unverified"


def test_unsupported_dataset_mode_is_rejected(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    with pytest.raises(VisualizationError, match="supports only"):
        load_plot_source(run.output_directory)


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
        load_plot_source(standalone, coordinate="temperature")


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
        load_plot_source(standalone, coordinate="temperature")


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
        load_plot_source(standalone, coordinate="temperature")
