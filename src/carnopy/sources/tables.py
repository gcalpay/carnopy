from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from carnopy.config.normalize import canonical_json_bytes
from carnopy.domain.failures import OutputError
from carnopy.sources.bundle import MAX_ARTIFACT_BYTES, MAX_TABLE_ROWS

BUNDLE_SCHEMA_VERSION = 1
TABLE_BATCH_SIZE = 256


def table_schemas() -> dict[str, pa.Schema]:
    text, integer, real, boolean = pa.string(), pa.int64(), pa.float64(), pa.bool_()
    component = pa.struct(
        [
            pa.field("component_id", text, nullable=False),
            pa.field("reported_number", text, nullable=False),
            pa.field("sample_number", text),
        ]
    )
    fraction = pa.struct(
        [
            pa.field("component_id", text, nullable=False),
            pa.field("fraction", real, nullable=False),
            pa.field("fraction_decimal", text, nullable=False),
            pa.field("derived", boolean, nullable=False),
        ]
    )
    definitions: dict[str, list[tuple[str, pa.DataType, bool]]] = {
        "observations": [
            *[
                (name, text, False)
                for name in (
                    "source_document_id",
                    "publication_id",
                    "dataset_id",
                    "point_id",
                    "observation_id",
                    "property_id",
                )
            ],
            *[(name, integer, False) for name in ("source_order", "dataset_index", "point_index")],
            *[(name, text, False) for name in ("property_number", "quantity", "unit", "basis")],
            ("value", real, False),
            ("value_decimal", text, False),
            ("temperature_K", real, True),
            ("pressure_Pa", real, True),
            ("phase", text, False),
            ("reported_phase", text, True),
            ("data_origin", text, False),
            ("components", pa.list_(pa.field("element", component)), False),
            ("composition_basis", text, True),
            ("composition_scope", text, True),
            ("composition", pa.list_(pa.field("element", fraction)), False),
        ],
        "provenance": [
            *[(name, text, False) for name in ("observation_id", "source_document_id", "locator")],
            ("reported_dataset_number", text, True),
            *[
                (name, text, False)
                for name in ("reported_property_number", "reported_quantity", "reported_value")
            ],
            ("reported_digits", text, True),
            *[
                (name, text, False)
                for name in (
                    "reported_unit",
                    "reported_basis",
                    "origin_rule",
                    "conversions_json",
                    "reported_property_json",
                )
            ],
        ],
        "uncertainties": [
            ("dataset_id", text, False),
            ("point_id", text, True),
            ("observation_id", text, True),
            *[
                (name, text, False)
                for name in (
                    "target_id",
                    "target_kind",
                    "quantity",
                    "locator",
                    "uncertainty_id",
                    "assessment_id",
                    "assessment_number",
                    "family",
                    "classification",
                )
            ],
            ("combined", boolean, False),
            ("asymmetric", boolean, False),
            *[(name, text, False) for name in ("basis", "unit", "reported_unit")],
            *[
                (name, text, True)
                for name in (
                    "reported_value",
                    "reported_lower",
                    "reported_upper",
                    "canonical_decimal",
                    "lower_decimal",
                    "upper_decimal",
                )
            ],
            *[
                (name, real, True)
                for name in (
                    "value",
                    "lower",
                    "upper",
                    "standard_uncertainty",
                    "standard_lower",
                    "standard_upper",
                )
            ],
            *[(name, text, True) for name in ("coverage_factor", "confidence_level", "evaluator")],
            *[
                (name, text, False)
                for name in (
                    "method_json",
                    "definition_json",
                    "reported_json",
                    "conversion_json",
                    "status",
                )
            ],
            ("issue", text, True),
        ],
        "diagnostics": [
            ("diagnostic_id", text, False),
            *[
                (name, text, True)
                for name in ("dataset_id", "point_id", "source_record_id", "observation_id")
            ],
            *[
                (name, text, False)
                for name in ("target_id", "locator", "severity", "code", "message")
            ],
        ],
    }
    result = {}
    for name, columns in definitions.items():
        units: dict[str, object] = (
            {
                "temperature_K": "K",
                "pressure_Pa": "Pa",
                "value": "row.unit",
                "composition.fraction": "1",
            }
            if name == "observations"
            else {}
        )
        result[name] = pa.schema(
            [pa.field(field, dtype, nullable=nullable) for field, dtype, nullable in columns],
            metadata={
                b"carnopy.bundle_kind": b"imported_source",
                b"carnopy.bundle_schema_version": b"1",
                b"carnopy.table": name.encode(),
                b"carnopy.units": canonical_json_bytes(units),
            },
        )
    return result


def schema_description(schema: pa.Schema) -> list[dict[str, Any]]:
    return [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in schema
    ]


class SourceTableWriter:
    """Write bounded batches and retain declared schemas even for empty tables."""

    def __init__(self, path: Path, schema: pa.Schema, checkpoint: Callable[[], None]) -> None:
        self.schema = schema
        self.checkpoint = checkpoint
        self.rows: list[dict[str, Any]] = []
        self.count = 0
        self.stream = path.open("xb")
        try:
            self.writer = pq.ParquetWriter(  # type: ignore[no-untyped-call]
                self.stream, schema, compression="zstd"
            )
        except BaseException:
            self.stream.close()
            raise

    def append(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        if len(self.rows) >= TABLE_BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        self.checkpoint()
        if self.rows:
            table = pa.Table.from_pylist(self.rows, schema=self.schema)
            self.writer.write_table(table)  # type: ignore[no-untyped-call]
            self.count += len(self.rows)
            self.rows.clear()
            if self.count > MAX_TABLE_ROWS or self.stream.tell() > MAX_ARTIFACT_BYTES:
                raise OutputError("source-import table resource limit exceeded")

    def close(self) -> None:
        try:
            self.flush()
        finally:
            try:
                self.writer.close()  # type: ignore[no-untyped-call]
            finally:
                self.stream.close()

    def abort(self) -> None:
        try:
            self.writer.close()  # type: ignore[no-untyped-call]
        finally:
            self.stream.close()
