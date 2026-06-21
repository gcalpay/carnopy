from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from carnopy.api import generate_dataset
from carnopy.outputs.layout import create_run_layout
from carnopy.outputs.writers import hash_artifacts
from carnopy.provenance import sha256_bytes


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
    assert str(property_config_path.resolve()) not in json.dumps(metadata)
    assert metadata["artifact_hashes"]["dataset.csv"]
    schema_metadata = pq.read_schema(result.output_directory / "dataset.parquet").metadata
    assert schema_metadata is not None
    assert b"carnopy.units" in schema_metadata


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
