from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from carnopy.api import generate_dataset
from carnopy.domain.failures import OutputError
from carnopy.outputs.layout import cleanup_run_layout, create_run_layout
from carnopy.outputs.writers import hash_artifacts
from carnopy.provenance import sha256_bytes, sha256_file
from carnopy.templates import template_text


@pytest.mark.parametrize(
    ("mode", "mode_slug"),
    [
        ("property_table", "property"),
        ("saturation_table", "saturation"),
        ("vapor_mass_fraction_table", "vapor_fraction"),
    ],
)
def test_run_layout_uses_short_human_facing_name(
    tmp_path: Path,
    mode: str,
    mode_slug: str,
) -> None:
    layout = create_run_layout(
        output_root=tmp_path,
        mode=mode,
        run_id="c8e28e9f-26f5-4d31-a8ae-47f8d8232aae",
        created_at=datetime(2026, 6, 21, 17, 20, 6, 270984, tzinfo=timezone.utc),
    )
    assert layout.final_directory.name == f"20260621T172006Z_{mode_slug}_c8e28e9f"
    assert layout.staging_directory.name == (f".20260621T172006Z_{mode_slug}_c8e28e9f.staging")


def test_run_layout_distinguishes_attempts_with_same_timestamp(tmp_path: Path) -> None:
    created_at = datetime(2026, 6, 21, 17, 20, 6, tzinfo=timezone.utc)
    first = create_run_layout(
        output_root=tmp_path,
        mode="property_table",
        run_id="11111111-1111-4111-8111-111111111111",
        created_at=created_at,
    )
    second = create_run_layout(
        output_root=tmp_path,
        mode="property_table",
        run_id="22222222-2222-4222-8222-222222222222",
        created_at=created_at,
    )
    assert first.final_directory != second.final_directory


def test_run_layout_cleanup_preserves_replaced_staging_directory(tmp_path: Path) -> None:
    layout = create_run_layout(
        output_root=tmp_path,
        mode="property_table",
        run_id="11111111-1111-4111-8111-111111111111",
        created_at=datetime(2026, 6, 21, 17, 20, 6, tzinfo=timezone.utc),
    )
    original = tmp_path / "original-staging"
    layout.staging_directory.rename(original)
    layout.staging_directory.mkdir()
    marker = layout.staging_directory / "external.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(OutputError, match="replaced staging directory"):
        cleanup_run_layout(layout)

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_generation_writes_complete_immutable_artifacts(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    result = generate_dataset(property_config_path, output_root=tmp_path)
    expected = {
        "dataset.csv",
        "dataset.parquet",
        "config.original.yaml",
        "config.normalized.json",
        "config.reference.yaml",
        "metadata.json",
        "report.json",
    }
    assert {path.name for path in result.output_directory.iterdir()} == expected
    csv_frame = pd.read_csv(result.output_directory / "dataset.csv")
    parquet_frame = pd.read_parquet(result.output_directory / "dataset.parquet")
    assert list(csv_frame.columns) == list(parquet_frame.columns)
    metadata = json.loads((result.output_directory / "metadata.json").read_text())
    report = json.loads((result.output_directory / "report.json").read_text())
    assert metadata["run_id"] == report["run_id"] == result.run_id
    assert metadata["spec_id"] == result.spec_id
    assert metadata["generation_context_id"] == result.generation_context_id
    assert metadata["output_request_id"] == result.output_request_id
    assert metadata["dataset_formats"] == ["csv", "parquet"]
    assert str(property_config_path.resolve()) not in json.dumps(metadata)
    assert metadata["artifact_hashes"]["dataset.csv"]
    reference = result.output_directory / "config.reference.yaml"
    assert metadata["artifact_hashes"]["config.reference.yaml"]
    assert reference.read_text(encoding="utf-8").startswith(
        "# Pure-fluid states on a temperature-pressure Cartesian grid."
    )
    assert reference.read_text(encoding="utf-8") == template_text(
        "property_table",
        full=True,
    )
    assert metadata["artifact_hashes"]["config.reference.yaml"] == sha256_file(reference)
    schema_metadata = pq.read_schema(result.output_directory / "dataset.parquet").metadata
    assert schema_metadata is not None
    assert b"carnopy.units" in schema_metadata


@pytest.mark.parametrize(
    ("dataset_formats", "expected_dataset_files"),
    [
        (["csv"], {"dataset.csv"}),
        (["parquet"], {"dataset.parquet"}),
    ],
)
def test_generation_writes_selected_dataset_formats(
    tmp_path: Path,
    dataset_formats: list[str],
    expected_dataset_files: set[str],
) -> None:
    config = tmp_path / "formats.yaml"
    config.write_text(
        f"""
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {{kind: explicit, values: [300], unit: K}}
  pressure: {{kind: explicit, values: [1], unit: bar}}
properties: [mass_density]
outputs:
  dataset_formats: [{", ".join(dataset_formats)}]
""",
        encoding="utf-8",
    )
    result = generate_dataset(config, output_root=tmp_path / "runs")
    dataset_files = {
        path.name for path in result.output_directory.glob("dataset.*") if path.is_file()
    }
    assert dataset_files == expected_dataset_files
    metadata = json.loads(
        result.output_directory.joinpath("metadata.json").read_text(encoding="utf-8")
    )
    assert set(metadata["artifact_hashes"]) & {"dataset.csv", "dataset.parquet"} == (
        expected_dataset_files
    )
    assert metadata["dataset_formats"] == dataset_formats
    assert "config.reference.yaml" in metadata["output_files"]
    assert "config.reference.yaml" in metadata["artifact_hashes"]


def test_new_runs_do_not_modify_existing_run_reference(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    first = generate_dataset(property_config_path, output_root=output_root)
    reference = first.output_directory / "config.reference.yaml"
    reference.write_text("preserve existing immutable run\n", encoding="utf-8")

    second = generate_dataset(property_config_path, output_root=output_root)

    assert second.output_directory != first.output_directory
    assert reference.read_text(encoding="utf-8") == "preserve existing immutable run\n"
    assert (second.output_directory / "config.reference.yaml").read_text(
        encoding="utf-8"
    ) != "preserve existing immutable run\n"


def test_output_formats_change_context_but_not_scientific_spec(tmp_path: Path) -> None:
    base = """
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
properties: [mass_density]
"""
    csv_config = tmp_path / "csv.yaml"
    csv_config.write_text(
        base + "outputs:\n  dataset_formats: [csv]\n",
        encoding="utf-8",
    )
    parquet_config = tmp_path / "parquet.yaml"
    parquet_config.write_text(
        base + "outputs:\n  dataset_formats: [parquet]\n",
        encoding="utf-8",
    )
    csv_run = generate_dataset(csv_config, output_root=tmp_path / "csv-runs")
    parquet_run = generate_dataset(parquet_config, output_root=tmp_path / "parquet-runs")

    assert csv_run.spec_id == parquet_run.spec_id
    assert csv_run.output_request_id != parquet_run.output_request_id
    assert csv_run.generation_context_id != parquet_run.generation_context_id
    assert (
        csv_run.output_directory.joinpath("config.normalized.json").read_bytes()
        == parquet_run.output_directory.joinpath("config.normalized.json").read_bytes()
    )


def test_artifact_hashing_does_not_require_read_bytes(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    path = tmp_path / "artifact.bin"
    content = b"large-artifact" * 100_000
    path.write_bytes(content)

    def reject_read_bytes(_path: Path) -> bytes:
        raise AssertionError("artifact hashing must be chunked")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    assert hash_artifacts(tmp_path, [path.name]) == {path.name: sha256_bytes(content)}
