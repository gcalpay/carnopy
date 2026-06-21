from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from carnopy.domain.failures import OutputError
from carnopy.provenance import DATASET_SCHEMA_VERSION, sha256_bytes


class _ParquetWriter(Protocol):
    """Typed boundary for PyArrow's currently incomplete inline stubs."""

    def write_table(self, table: object, where: str | Path) -> None: ...


_PARQUET_WRITER = cast(_ParquetWriter, pq)


def write_dataset(
    frame: pd.DataFrame,
    directory: Path,
    unit_map: dict[str, str],
) -> None:
    csv_path = directory / "dataset.csv"
    parquet_path = directory / "dataset.parquet"
    try:
        frame.to_csv(csv_path, index=False)
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata[b"carnopy.dataset_schema_version"] = str(DATASET_SCHEMA_VERSION).encode()
        metadata[b"carnopy.units"] = json.dumps(
            unit_map, sort_keys=True, separators=(",", ":")
        ).encode()
        _PARQUET_WRITER.write_table(table.replace_schema_metadata(metadata), parquet_path)
    except Exception as exc:
        raise OutputError(f"could not write dataset files: {exc}") from exc


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
            hashes[name] = sha256_bytes((directory / name).read_bytes())
        except OSError as exc:
            raise OutputError(f"could not hash {name}: {exc}") from exc
    return hashes
