from __future__ import annotations

from pathlib import Path

import pytest

from carnopy.api import validate_config
from carnopy.config.io import load_config_file
from carnopy.domain.failures import ConfigError


def test_valid_example_config(property_config_path: Path) -> None:
    result = validate_config(property_config_path)
    assert result.projected_rows == 2
    assert result.canonical_fluids == ("n-Propane",)
    assert result.dataset_formats == ("csv", "parquet")
    assert result.output_request_id.startswith("out-")


def test_invalid_vapor_mass_fraction_fails(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        """
schema_version: 1
backend: coolprop
mode: vapor_mass_fraction_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [250], unit: K}
  vapor_mass_fraction: {kind: explicit, values: [1.1], unit: "1"}
properties: [mass_density]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="between 0 and 1"):
        validate_config(path)


def test_unsupported_property_fails_before_backend_calls(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300], unit: K}
  pressure: {kind: explicit, values: [1], unit: bar}
properties: [HMASS]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unsupported properties"):
        load_config_file(path)


def test_expanded_row_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.yaml"
    path.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: linspace, start: 200, stop: 400, num: 1001, unit: K}
  pressure: {kind: linspace, start: 1, stop: 100, num: 1000, unit: bar}
properties: [mass_density]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="exceeds limit"):
        validate_config(path)


def test_dataset_formats_are_canonical_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "parquet.yaml"
    path.write_text(
        """
schema_version: 1
backend: coolprop
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300], unit: K}
  pressure: {kind: explicit, values: [1], unit: bar}
properties: [mass_density]
outputs:
  dataset_formats: [parquet, csv]
""",
        encoding="utf-8",
    )
    explicit = validate_config(path)
    assert explicit.dataset_formats == ("csv", "parquet")

    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        path.read_text(encoding="utf-8").replace(
            "outputs:\n  dataset_formats: [parquet, csv]\n",
            "",
        ),
        encoding="utf-8",
    )
    default = validate_config(default_path)
    assert explicit.output_request_id == default.output_request_id

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        path.read_text(encoding="utf-8").replace(
            "dataset_formats: [parquet, csv]",
            "dataset_formats: [csv, csv]",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate dataset formats"):
        validate_config(duplicate)
