from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from carnopy.domain.failures import OutputError
from carnopy.provenance import DATASET_SCHEMA_VERSION, sha256_file


class _ParquetWriter(Protocol):
    """Typed boundary for PyArrow's currently incomplete inline stubs."""

    def write_table(self, table: object, where: str | Path) -> None: ...


_PARQUET_WRITER = cast(_ParquetWriter, pq)


def write_dataset(
    frame: pd.DataFrame,
    directory: Path,
    unit_map: dict[str, str],
) -> list[str]:
    return write_dataset_formats(
        frame,
        directory,
        unit_map,
        dataset_formats=("csv", "parquet"),
    )


def write_dataset_formats(
    frame: pd.DataFrame,
    directory: Path,
    unit_map: dict[str, str],
    *,
    dataset_formats: tuple[str, ...],
) -> list[str]:
    written: list[str] = []
    try:
        if "csv" in dataset_formats:
            frame.to_csv(directory / "dataset.csv", index=False)
            written.append("dataset.csv")
        if "parquet" in dataset_formats:
            table = pa.Table.from_pandas(frame, preserve_index=False)
            metadata = dict(table.schema.metadata or {})
            metadata[b"carnopy.dataset_schema_version"] = str(DATASET_SCHEMA_VERSION).encode()
            metadata[b"carnopy.units"] = json.dumps(
                unit_map, sort_keys=True, separators=(",", ":")
            ).encode()
            _PARQUET_WRITER.write_table(
                table.replace_schema_metadata(metadata),
                directory / "dataset.parquet",
            )
            written.append("dataset.parquet")
    except Exception as exc:
        raise OutputError(f"could not write dataset files: {exc}") from exc
    return written


def write_json(path: Path, value: dict[str, Any]) -> None:
    try:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc


def write_bytes(path: Path, value: bytes) -> None:
    try:
        path.write_bytes(value)
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc


def hash_artifacts(directory: Path, names: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in names:
        try:
            hashes[name] = sha256_file(directory / name)
        except OSError as exc:
            raise OutputError(f"could not hash {name}: {exc}") from exc
    return hashes
