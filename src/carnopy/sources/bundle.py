from __future__ import annotations

import json
import os
import stat
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import PREVIEW_RECORD_LIMIT
from carnopy.sources.files import (
    Checkpoint,
    SourceDescriptor,
    checkpoint,
    read_source_descriptor,
    read_source_snapshot,
)

# Version-1 bundle-reader bounds. These bound verification and never truncate
# tables or original evidence. Writers enforce the same bounds before publishing.
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_TABLE_ROWS = 16_000_000
TABLE_NAMES = ("observations", "provenance", "uncertainties", "diagnostics")


def directory_identity(path: Path, *, allow_missing: bool = False) -> tuple[int, int] | None:
    """Check the original absolute spelling so resolving cannot hide links."""
    for part in (*reversed(path.absolute().parents), path.absolute()):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            raise SourceImportError("bundle_integrity", f"missing directory: {part}") from None
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise SourceImportError("unsafe_bundle_path", f"not a real directory: {part}")
    return info.st_dev, info.st_ino


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceImportError("bundle_integrity", "duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise SourceImportError("bundle_integrity", f"nonfinite JSON value: {value}")


def json_object(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(content, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SourceImportError("bundle_integrity", "invalid bundle JSON") from exc
    if not isinstance(value, dict):
        raise SourceImportError("bundle_integrity", "JSON root must be an object")
    return value


@dataclass(frozen=True)
class SourceBundle:
    root: Path
    manifest: dict[str, Any]
    manifest_descriptor: SourceDescriptor
    artifacts: tuple[SourceDescriptor, ...]
    catalog: dict[str, Any]
    report: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceImportError("bundle_integrity", message)


@contextmanager
def _parquet(
    path: Path, descriptor: SourceDescriptor, *, cancel: Checkpoint | None
) -> Iterator[Any]:
    import pyarrow.parquet as pq

    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        _require(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            == (
                descriptor.device,
                descriptor.inode,
                descriptor.size,
                descriptor.modified_ns,
                descriptor.changed_ns,
            ),
            "Parquet changed before reading",
        )
        checkpoint(cancel)
        parquet = pq.ParquetFile(stream)  # type: ignore[no-untyped-call]
        _require(parquet.metadata.num_rows <= MAX_TABLE_ROWS, "Parquet row limit exceeded")
        uncompressed = sum(
            parquet.metadata.row_group(index).total_byte_size
            for index in range(parquet.metadata.num_row_groups)
        )
        _require(uncompressed <= MAX_ARTIFACT_BYTES, "Parquet uncompressed size limit exceeded")
        yield parquet


def _table_rows(
    path: Path, descriptor: SourceDescriptor, *, cancel: Checkpoint | None
) -> Iterator[dict[str, Any]]:
    with _parquet(path, descriptor, cancel=cancel) as parquet:
        for batch in parquet.iter_batches(batch_size=256):
            checkpoint(cancel)
            yield from batch.to_pylist()


def read_source_bundle(source: str | Path, *, cancel: Checkpoint | None = None) -> SourceBundle:
    """Verify kind/version, exact bytes, declared schemas, accounting and joins."""
    from carnopy.sources.tables import schema_description, table_schemas

    root = Path(source).absolute()
    try:
        root_identity = directory_identity(root)
        snapshot = read_source_snapshot(
            root / "manifest.json", maximum_bytes=MAX_MANIFEST_BYTES, cancel=cancel
        )
        manifest = json_object(snapshot.raw_bytes)
        if manifest.get("bundle_kind") != "imported_source":
            raise SourceImportError(
                "unsupported_bundle_kind", "expected an imported_source manifest"
            )
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
            raise SourceImportError(
                "unsupported_bundle_version", "expected source bundle schema version 1"
            )
        for field in ("source_document_id", "publication_id", "request_id", "context_id", "run_id"):
            _require(
                isinstance(manifest.get(field), str) and bool(manifest[field]),
                f"missing bundle identity: {field}",
            )
        source_format = manifest.get("format")
        _require(source_format in {"thermoml_xml", "thermoml_json"}, "unsupported source format")
        source_path = (
            "source/original.xml" if source_format == "thermoml_xml" else "source/original.json"
        )
        expected = {
            "request.original.yaml",
            "request.normalized.json",
            "catalog.json",
            "report.json",
            source_path,
            *(f"data/{name}.parquet" for name in TABLE_NAMES),
        }
        hashes = manifest.get("artifact_hashes")
        _require(
            isinstance(hashes, dict) and set(hashes) == expected,
            "unexpected or missing artifact paths",
        )
        assert isinstance(hashes, dict)
        descriptors = {}
        for relative in sorted(expected):
            descriptor = read_source_descriptor(
                root / relative, maximum_bytes=MAX_ARTIFACT_BYTES, cancel=cancel
            )
            _require(descriptor.sha256 == hashes[relative], f"artifact hash mismatch: {relative}")
            descriptors[relative] = descriptor
        _require(
            descriptors[source_path].sha256 == manifest.get("source_document_id"),
            "original evidence identity mismatch",
        )
        catalog = json_object(
            read_source_snapshot(
                root / "catalog.json", maximum_bytes=MAX_ARTIFACT_BYTES, cancel=cancel
            ).raw_bytes
        )
        report = json_object(
            read_source_snapshot(
                root / "report.json", maximum_bytes=MAX_ARTIFACT_BYTES, cancel=cancel
            ).raw_bytes
        )
        for field in ("reason_counts", "warning_counts", "data_origin_counts"):
            values = report.get(field)
            _require(
                isinstance(values, dict)
                and all(type(value) is int and value >= 0 for value in values.values()),
                f"invalid report field: {field}",
            )
        preview = report.get("diagnostics_preview")
        _require(
            isinstance(preview, list) and len(preview) <= PREVIEW_RECORD_LIMIT,
            "invalid diagnostics preview",
        )
        assert isinstance(preview, list)
        for item in preview:
            _require(
                isinstance(item, dict)
                and all(
                    isinstance(item.get(field), str) for field in ("code", "locator", "message")
                ),
                "invalid diagnostic projection",
            )
        for field in ("diagnostic_count", "omitted_diagnostics"):
            _require(
                type(report.get(field)) is int and report[field] >= 0,
                f"invalid report field: {field}",
            )
        _require(
            report["diagnostic_count"] == len(preview) + report["omitted_diagnostics"],
            "diagnostic accounting differs",
        )
        counts = manifest.get("counts")
        _require(
            isinstance(counts, dict)
            and set(counts) == {"total", "normalized", "unsupported", "invalid", "unselected"},
            "invalid import accounting",
        )
        assert isinstance(counts, dict)
        _require(
            all(type(value) is int and value >= 0 for value in counts.values()),
            "invalid import counts",
        )
        _require(
            counts["total"] == sum(value for key, value in counts.items() if key != "total"),
            "import accounting does not sum",
        )
        _require(
            counts == report.get("counts") == catalog.get("counts"), "report/catalog counts differ"
        )
        for name in (
            "source_document_id",
            "publication_id",
            "request_id",
            "context_id",
            "run_id",
            "status",
        ):
            _require(manifest.get(name) == report.get(name), f"report identity differs: {name}")
        _require(
            catalog.get("source_document_id") == manifest.get("source_document_id"),
            "catalog source differs",
        )
        _require(
            catalog.get("publication_id") == manifest.get("publication_id"),
            "catalog publication differs",
        )
        _require(
            manifest.get("status")
            in {"completed", "completed_with_limitations", "no_eligible_observations"},
            "invalid completion status",
        )
        _require(
            (manifest["status"] == "no_eligible_observations") == (counts["normalized"] == 0),
            "status/count mismatch",
        )
        descriptions = manifest.get("tables")
        _require(
            isinstance(descriptions, dict) and set(descriptions) == set(TABLE_NAMES),
            "missing table contracts",
        )
        assert isinstance(descriptions, dict)
        for name, schema in table_schemas().items():
            path = root / "data" / f"{name}.parquet"
            with _parquet(path, descriptors[f"data/{name}.parquet"], cancel=cancel) as parquet:
                _require(
                    parquet.schema_arrow.equals(schema, check_metadata=True),
                    f"table schema mismatch: {name}",
                )
                row_count = parquet.metadata.num_rows
            description = descriptions[name]
            _require(
                isinstance(description, dict)
                and type(description.get("row_count")) is int
                and description.get("path") == f"data/{name}.parquet"
                and description.get("columns") == schema_description(schema),
                f"manifest table contract mismatch: {name}",
            )
            _require(
                row_count == description.get("row_count"),
                f"table row count mismatch: {name}",
            )
        _verify_joins(root, manifest, catalog, descriptors, cancel)
        _require(
            descriptions["diagnostics"]["row_count"] == report["diagnostic_count"],
            "diagnostic table/report counts differ",
        )
        for descriptor in (*descriptors.values(), snapshot.descriptor):
            _require(
                read_source_descriptor(
                    descriptor.path, maximum_bytes=MAX_ARTIFACT_BYTES, cancel=cancel
                )
                == descriptor,
                "artifact changed during bundle verification",
            )
        _require(directory_identity(root) == root_identity, "bundle directory changed")
        return SourceBundle(
            root, manifest, snapshot.descriptor, tuple(descriptors.values()), catalog, report
        )
    except SourceImportError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise SourceImportError(
            "bundle_integrity", f"could not verify source bundle: {exc}"
        ) from exc


def _verify_joins(
    root: Path,
    manifest: dict[str, Any],
    catalog: dict[str, Any],
    descriptors: dict[str, SourceDescriptor],
    cancel: Checkpoint | None,
) -> None:
    def rows(name: str) -> Iterator[dict[str, Any]]:
        relative = f"data/{name}.parquet"
        return _table_rows(root / relative, descriptors[relative], cancel=cancel)

    inventory = catalog.get("records")
    _require(isinstance(inventory, list), "catalog inventory missing")
    assert isinstance(inventory, list)
    records = {}
    accounted: Counter[str] = Counter()
    for order, record in enumerate(inventory):
        checkpoint(cancel)
        _require(
            isinstance(record, dict) and record.get("source_order") == order,
            "invalid source record order",
        )
        identity = record.get("source_record_id")
        _require(
            isinstance(identity, str) and identity not in records,
            "duplicate source record identity",
        )
        records[identity] = record
        accounted[record.get("status")] += 1
    counts = manifest["counts"]
    _require(
        len(records) == counts["total"]
        and all(
            accounted[key] == counts[key]
            for key in ("normalized", "unsupported", "invalid", "unselected")
        ),
        "catalog inventory accounting differs",
    )
    ids: list[str] = []
    points: set[str] = set()
    datasets = {dataset["dataset_id"] for dataset in catalog["datasets"]}
    for row in rows("observations"):
        record = records.get(row["observation_id"])
        _require(
            record is not None
            and record["status"] == "normalized"
            and record["observation_id"] == row["observation_id"],
            "observation absent from normalized inventory",
        )
        assert record is not None
        _require(
            all(
                row[field] == record[field]
                for field in (
                    "dataset_id",
                    "point_id",
                    "dataset_index",
                    "point_index",
                    "property_number",
                    "source_order",
                    "quantity",
                    "data_origin",
                )
            ),
            "observation locator/context differs",
        )
        _require(
            row["source_document_id"] == manifest["source_document_id"]
            and row["publication_id"] == manifest["publication_id"],
            "observation source identity differs",
        )
        ids.append(row["observation_id"])
        points.add(row["point_id"])
    expected_ids = [
        record["observation_id"] for record in inventory if record["status"] == "normalized"
    ]
    _require(
        ids == expected_ids and len(set(ids)) == len(ids) == counts["normalized"],
        "observation ordering or count differs",
    )
    provenance_ids = []
    for row in rows("provenance"):
        _require(
            row["source_document_id"] == manifest["source_document_id"], "provenance source differs"
        )
        provenance_ids.append(row["observation_id"])
    _require(provenance_ids == ids, "provenance must join one-to-one in observation order")
    id_set = set(ids)
    for name, key in (("uncertainties", "uncertainty_id"), ("diagnostics", "diagnostic_id")):
        seen: set[str] = set()
        for row in rows(name):
            _require(row[key] not in seen, f"duplicate {name} identity")
            seen.add(row[key])
            _require(
                row["observation_id"] is None or row["observation_id"] in id_set,
                f"broken {name} observation join",
            )
            _require(
                row["dataset_id"] is None or row["dataset_id"] in datasets,
                f"broken {name} dataset join",
            )
            if name == "uncertainties":
                _require(
                    row["point_id"] is None or row["point_id"] in points,
                    "broken uncertainty point join",
                )
            else:
                _require(
                    row["source_record_id"] is None or row["source_record_id"] in records,
                    "broken diagnostic source record join",
                )
