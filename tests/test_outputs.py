from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from carnopy.api import generate_dataset


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
