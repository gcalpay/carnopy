from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from carnopy.api import generate_dataset
from carnopy.outputs.writers import hash_artifacts
from carnopy.provenance import sha256_bytes


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
